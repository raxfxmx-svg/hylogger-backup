"""Record test-database business tables read-only and compare reruns for added or changed content."""

import hashlib
import json
from pathlib import Path
import sys

AUDIT = Path(__file__).resolve().parent
ETL = AUDIT.parents[1] / "etl4"
sys.path[:0] = [str(ETL / "database"), str(ETL)]
from _settings import settings
from _db_common import connection
from psycopg import sql

selection = json.loads((AUDIT / "selection.json").read_text(encoding="utf-8"))
settings.work_dir = Path(selection["work_dir"])
settings.dbname = selection["database"]
label = sys.argv[1]
if label not in ("before_replay", "after_replay"):
    raise ValueError("Unknown snapshot label")
path = AUDIT / f"{label}.json"
if path.exists():
    raise ValueError('Do not overwrite the existing comparison')
result = {"database": settings.dbname, "tables": {}}
with connection("reader") as conn, conn.transaction():
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    result["active_release"] = str(conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()["release_id"])
    for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='core' ORDER BY tablename").fetchall():
        name = row["tablename"]
        if name in ("ingest_run", "revision_validation", "active_release", "schema_migration"):
            continue
        query = sql.SQL("SELECT row_to_json(t)::text AS value FROM core.{} t ORDER BY 1").format(sql.Identifier(name))
        checksum = hashlib.sha256()
        count = 0
        with conn.cursor(name="table_check") as cursor:
            cursor.execute(query)
            for value in cursor:
                checksum.update(value["value"].encode("utf-8") + b"\n")
                count += 1
        result["tables"][name] = {"count": count, "sha256": checksum.hexdigest()}
    result["database_bytes"] = conn.execute("SELECT pg_database_size(current_database()) AS n").fetchone()["n"]
path.write_text(json.dumps(result, indent=2), encoding="utf-8")
if label == "after_replay":
    before = json.loads((AUDIT / "before_replay.json").read_text(encoding="utf-8"))
    assert before["tables"] == result["tables"], 'Rerun changed business tables'
    assert before["active_release"] == result["active_release"], 'Rerun changed active release identity'
    print(f"Replay unchanged: {len(result['tables'])} business tables; no new business rows or versions.")
else:
    print(f"Recorded {len(result['tables'])} business tables before replay.")
