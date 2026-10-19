"""Create controlled trial databases and compare business-record digests."""

import threading
import hashlib
import uuid
from _db_common import CODE, config, connection, insert, now, sha
from psycopg import sql


def create_trial(purpose):
    name = "etl4_" + purpose + "_" + uuid.uuid4().hex[:10]
    if purpose not in ("test", "restore"):
        raise ValueError("Unrecognized trial purpose")
    with connection(dbname="postgres") as c:
        c.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING {}").format(
                sql.Identifier(name), sql.Literal("UTF8")
            )
        )
    return name


def drop_trial(name):
    if not name.startswith(("etl4_test_", "etl4_restore_")) or name == config()["database"]:
        raise ValueError("Not an isolated trial database")
    with connection(dbname="postgres") as c:
        c.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def trial_schema(name):
    if not name.startswith("etl4_test_"):
        raise ValueError("Schema fixtures require an isolated test database")
    with connection(dbname=name) as c:
        c.execute("CREATE EXTENSION postgis")
        for p in sorted((CODE / "migrations").glob("*.sql")):
            with c.transaction():
                c.execute(p.read_text(encoding="utf-8"))
                insert(c, "schema_migration", {"name": p.name, "sha256": sha(p)})
        for key in ("ingest", "reader"):
            user = config()["roles"][key]["user"]
            c.execute(
                sql.SQL("GRANT USAGE ON SCHEMA core,public TO {}").format(sql.Identifier(user))
            )
            c.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA core TO {}").format(
                    sql.Identifier(user)
                )
            )
        ingest = sql.Identifier(config()["roles"]["ingest"]["user"])
        c.execute(sql.SQL("GRANT INSERT ON ALL TABLES IN SCHEMA core TO {}").format(ingest))
        c.execute(
            sql.SQL(
                "GRANT UPDATE ON core.ingest_run,core.revision_validation,core.active_release,core.asset_location TO {}"
            ).format(ingest)
        )
        c.execute(sql.SQL("REVOKE INSERT ON core.schema_migration FROM {}").format(ingest))


def fingerprints(dbname=None):
    result = {}
    with connection(dbname=dbname) as c:
        tables = c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='core' ORDER BY tablename"
        ).fetchall()
        for row in tables:
            t = row["tablename"]
            if t in ("schema_migration", "ingest_run", "revision_validation", "active_release"):
                continue
            # Sort text consistently so the digest covers every record without relying on internal sequence numbers.
            query = sql.SQL(
                'COPY (SELECT row_to_json(t)::text AS record FROM core.{} t ORDER BY row_to_json(t)::text COLLATE "C") TO STDOUT'
            ).format(sql.Identifier(t))
            h = hashlib.sha256()
            with c.cursor().copy(query) as cp:
                for data in cp:
                    h.update(data)
            result[t] = h.hexdigest()
    return result


class OperationSampler:
    """Sample WAL and temporary-file usage during import trials."""

    def __init__(self, dbname, interval=0.1):
        self.dbname = dbname
        self.interval = interval
        self.samples = []
        self.errors = []
        self.stop = threading.Event()

    def __enter__(self):
        with connection(dbname=self.dbname) as c:
            self.start_lsn = c.execute("SELECT pg_current_wal_lsn()::text AS lsn").fetchone()["lsn"]
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()
        return self

    def sample(self):
        try:
            with connection(dbname=self.dbname) as c:
                while not self.stop.is_set():
                    r = c.execute(
                        """SELECT pg_database_size(current_database()) AS database_bytes,
                         (SELECT sum(size)::bigint FROM pg_ls_waldir()) AS wal_directory_bytes,
                         (SELECT coalesce(sum(size),0)::bigint FROM pg_ls_tmpdir()) AS current_temp_file_bytes"""
                    ).fetchone()
                    self.samples.append({"at": now(), **r})
                    self.stop.wait(self.interval)
        except Exception as exc:
            self.errors.append(type(exc).__name__ + ": " + str(exc))

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=5)
        with connection(dbname=self.dbname) as c:
            self.wal_generated = c.execute(
                "SELECT pg_wal_lsn_diff(pg_current_wal_lsn(),%s)::bigint AS n", (self.start_lsn,)
            ).fetchone()["n"]

    def result(self):
        return {
            "interval_seconds": self.interval,
            "samples": self.samples,
            "errors": self.errors,
            "wal_generated_bytes": self.wal_generated,
            "max_sampled_wal_directory_bytes": max(
                (r["wal_directory_bytes"] for r in self.samples), default=0
            ),
            "max_sampled_temp_file_bytes": max(
                (r["current_temp_file_bytes"] for r in self.samples), default=0
            ),
            "scope": "Dedicated local cluster; WAL includes cluster background activity; 100 ms sampling may miss shorter temporary peaks",
        }
