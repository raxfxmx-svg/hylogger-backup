"""Backup, read-only digest and relational-copy utilities for the three-borehole merge."""

import gzip
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ETL = ROOT / "etl4"
AUDIT = Path(__file__).resolve().parent
sys.path[:0] = [str(ETL / "database"), str(ETL)]

from _settings import settings
from _db_common import connection, config, PG_BIN, LOCK_KEY, assert_schema
from _db_files import encoded, read, sha
from psycopg import sql

SOURCE = "etl4_new_input_check"
TARGET = "etl4_refactor_check"
settings.work_dir = ETL / "refactor_work"
settings.dbname = TARGET
NON_BUSINESS = {"ingest_run", "revision_validation", "active_release", "schema_migration"}


def write(path, value):
    """Write review records in this work directory; the official publication function still writes business manifests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


def lock(conn):
    if not conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"]:
        raise ValueError('Another import or validation is running in the current database')


def tables(conn):
    return [row["tablename"] for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='core' ORDER BY tablename")]


def row_hashes(conn, names):
    result = {}
    for name in names:
        query = sql.SQL("SELECT row_to_json(t)::text value FROM core.{} t").format(sql.Identifier(name))
        with conn.cursor(name="snapshot_" + name) as cursor:
            cursor.execute(query)
            result[name] = sorted(hashlib.sha256(row["value"].encode()).hexdigest() for row in cursor)
    return result


def save_hashes(path, values):
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(values, stream)


def load_hashes(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def summarize(values):
    return {name: {"count": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()} for name, rows in values.items()}


def signature(conn):
    return {
        "columns": conn.execute("SELECT table_name,column_name,ordinal_position,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='core' ORDER BY table_name,ordinal_position").fetchall(),
        "constraints": conn.execute("SELECT t.relname,c.conname,pg_get_constraintdef(c.oid) definition FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='core' ORDER BY t.relname,c.conname").fetchall(),
        "triggers": conn.execute("SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='core' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname").fetchall(),
        "views": conn.execute("SELECT viewname,definition FROM pg_views WHERE schemaname='core' ORDER BY viewname").fetchall(),
    }


def backup(dbname, path):
    c = config()
    env = os.environ.copy()
    env.update(PGHOST=c["host"], PGPORT=str(c["port"]), PGUSER=c["roles"]["owner"]["user"], PGPASSWORD=c["roles"]["owner"]["password"], PGCLIENTENCODING="UTF8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError('Do not overwrite an existing backup: ' + str(path))
    subprocess.run([str(PG_BIN / "pg_dump.exe"), "--format=custom", "--no-owner", "--file", str(path), "--dbname", dbname], check=True, env=env, stdin=subprocess.DEVNULL, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return {"database": dbname, "path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def active_release(conn):
    return str(conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()["release_id"])


def copy_business(source, target, names):
    """Copy into temporary tables in foreign-key order; require field-identical conflicts, then check deferred foreign keys."""
    edges = target.execute("""SELECT child.relname child,parent.relname parent FROM pg_constraint c
      JOIN pg_class child ON child.oid=c.conrelid JOIN pg_class parent ON parent.oid=c.confrelid
      JOIN pg_namespace ns ON ns.oid=child.relnamespace
      WHERE ns.nspname='core' AND c.contype='f' AND NOT c.condeferrable""").fetchall()
    dependencies = {name: {row["parent"] for row in edges if row["child"] == name and row["parent"] != name and row["parent"] in names} for name in names}
    order = []
    while len(order) < len(names):
        ready = sorted(name for name in names if name not in order and dependencies[name] <= set(order))
        if not ready:
            raise ValueError('Cyclic foreign keys cannot be deferred')
        order.extend(ready)
    target.execute("SET CONSTRAINTS ALL DEFERRED")
    result = {}
    for name in order:
        temporary = "merge_" + name
        table, stage = sql.Identifier("core", name), sql.Identifier(temporary)
        columns = [row["column_name"] for row in source.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='core' AND table_name=%s ORDER BY ordinal_position", (name,))]
        fields = sql.SQL(",").join(map(sql.Identifier, columns))
        target.execute(sql.SQL("CREATE TEMP TABLE {} (LIKE {}) ON COMMIT DROP").format(stage, table))
        ordering = sql.SQL(" ORDER BY (interval_kind='section'),ordinal") if name == "core_interval" else sql.SQL("")
        with source.cursor().copy(sql.SQL("COPY (SELECT {} FROM {}{}) TO STDOUT (FORMAT BINARY)").format(fields, table, ordering)) as output:
            with target.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN (FORMAT BINARY)").format(stage, fields)) as incoming:
                for block in output:
                    incoming.write(block)
        primary = [row["attname"] for row in target.execute("SELECT a.attname FROM pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum,position) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum WHERE c.conrelid=%s::regclass AND c.contype='p' ORDER BY k.position", ("core." + name,))]
        if not primary:
            raise ValueError('Missing primary key for rerun detection: ' + name)
        conflict = sql.SQL(",").join(map(sql.Identifier, primary))
        selected = sql.SQL(",").join(sql.Identifier("s", field) for field in columns)
        match = sql.SQL(" AND ").join(sql.SQL("{}={}").format(sql.Identifier("d", field), sql.Identifier("s", field)) for field in primary)
        added = target.execute(sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {} s WHERE NOT EXISTS (SELECT 1 FROM {} d WHERE {}){} ON CONFLICT ({}) DO NOTHING").format(table, fields, selected, stage, table, match, ordering, conflict)).rowcount
        missing = target.execute(sql.SQL("SELECT EXISTS(SELECT {} FROM {} EXCEPT SELECT {} FROM {}) missing").format(fields, stage, fields, table)).fetchone()["missing"]
        if missing:
            raise ValueError('Target contains different content under the same key: ' + name)
        result[name] = added
        target.execute(sql.SQL("DROP TABLE {}").format(stage))
        print(f"Copied {name}: {added} new rows", flush=True)
    target.execute("SET CONSTRAINTS ALL IMMEDIATE")
    return result
