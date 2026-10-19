"""Compare all existing business records within their original primary-key ranges; exclude new rows from the old-data digest."""

import hashlib
from pathlib import Path
import sys
from psycopg import sql

AUDIT = Path(__file__).resolve().parent
ETL = AUDIT.parents[1] / "etl4"
sys.path[:0] = [str(ETL / "database"), str(ETL)]
from _db_common import connection
from _db_files import read, encoded
from _settings import settings


def setup():
    selection = read(AUDIT / "selection.json")
    settings.work_dir = Path(selection["work_dir"])
    settings.dbname = selection["database"]
    return selection


def capture_scopes(conn):
    rows = conn.execute("""SELECT t.relname name,a.attname column_name
        FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=c.conkey[1]
        WHERE n.nspname='core' AND c.contype='p' ORDER BY t.relname""").fetchall()
    scopes = {}
    for row in rows:
        table, column = row["name"], row["column_name"]
        if table in ("ingest_run", "revision_validation", "active_release", "schema_migration"):
            continue
        values = conn.execute(sql.SQL("SELECT DISTINCT {}::text AS value FROM core.{} ORDER BY 1").format(sql.Identifier(column), sql.Identifier(table))).fetchall()
        scopes[table] = {"column": column, "values": [r["value"] for r in values]}
    assert len(scopes) == 35
    return scopes


def snapshot(conn, scopes):
    result = {}
    for table, scope in scopes.items():
        query = sql.SQL("COPY (SELECT row_to_json(t)::text FROM core.{} t WHERE {}::text=ANY({}::text[]) ORDER BY 1) TO STDOUT").format(sql.Identifier(table), sql.Identifier(scope["column"]), sql.Literal(scope["values"]))
        checksum, count = hashlib.sha256(), 0
        with conn.cursor().copy(query) as stream:
            for block in stream:
                content = bytes(block)
                checksum.update(content)
                count += content.count(b"\n")
        result[table] = {"count": count, "sha256": checksum.hexdigest()}
    return result


if __name__ == "__main__":
    setup()
    path = AUDIT / "original_scope.json"
    assert not path.exists(), 'Do not overwrite the pre-merge comparison'
    with connection("reader") as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        scopes = capture_scopes(conn)
        result = {"scopes": scopes, "tables": snapshot(conn, scopes),
            "active": conn.execute("SELECT * FROM core.active_release WHERE singleton").fetchone()}
    path.write_bytes(encoded(result))
    print("Saved original scopes and content hashes for 35 business tables", flush=True)
