"""Select and copy a random borehole and record the original database state without changing production processing code."""

import gzip
import hashlib
import json
import random
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ETL = ROOT / "etl4"
AUDIT = Path(__file__).resolve().parent
sys.path[:0] = [str(ETL / "database"), str(ETL)]

from _settings import settings
from _db_common import connection, assert_schema
from psycopg import sql

settings.work_dir = ETL / "new_input_check"
settings.dbname = "etl4_new_input_check"


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def snapshot(conn):
    result = {}
    for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='core' ORDER BY tablename").fetchall():
        name = row["tablename"]
        if name in ("ingest_run", "revision_validation", "active_release", "schema_migration"):
            continue
        query = sql.SQL("SELECT row_to_json(t)::text AS value FROM core.{} t").format(sql.Identifier(name))
        result[name] = sorted(hashlib.sha256(row["value"].encode()).hexdigest() for row in conn.execute(query))
    return result


def main():
    if (AUDIT / "selection.json").exists():
        raise ValueError('A selection already exists for this run; do not redraw or overwrite it')
    raw_report = json.loads((AUDIT / "raw_check/0_raw_check.json").read_text(encoding="utf-8"))
    candidates = sorted(hole for hole in raw_report["groups"]["single"] if not (ETL / hole).exists())
    hole = random.SystemRandom().choice(candidates)
    source = Path(raw_report["raw_dir"]) / hole
    files = sorted(path for path in source.rglob("*") if path.is_file())
    total = sum(path.stat().st_size for path in files)
    if shutil.disk_usage(ETL).free < total * 4 + 2 * 1024**3:
        raise ValueError('Insufficient free space; preserve the selection without starting the copy')
    with connection("reader") as conn:
        assert_schema(conn)
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            active = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()
            tables = snapshot(conn)
            before = {"database": settings.dbname, "active_release": str(active["release_id"]), "table_counts": {name: len(rows) for name, rows in tables.items()}}
    with gzip.open(AUDIT / "original_business_rows.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(tables, stream)
    save(AUDIT / "database_before.json", before)
    work = settings.work_dir / ("random_" + hole)
    selection = {"hole": hole, "method": "SystemRandom.choice: uniform over complete single-dataset holes absent from etl4", "candidate_count": len(candidates), "candidates": candidates, "source": str(source), "work_dir": str(work), "database": settings.dbname, "source_bytes": total, "source_file_count": len(files), "free_before": shutil.disk_usage(ETL).free}
    save(AUDIT / "selection.json", selection)
    print(json.dumps({key: value for key, value in selection.items() if key != "candidates"}, ensure_ascii=False), flush=True)
    started = time.perf_counter()
    copied = []
    for index, path in enumerate(files, 1):
        relative = path.relative_to(source)
        target = ETL / hole / relative
        if target.exists():
            raise ValueError('Target file already exists: ' + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = sha(path)
        shutil.copy2(path, target)
        if sha(target) != expected:
            raise ValueError('Copied content differs: ' + str(relative))
        copied.append({"path": relative.as_posix(), "bytes": path.stat().st_size, "sha256": expected})
        if index % 50 == 0:
            print(f"Copy verified {index}/{len(files)}", flush=True)
    config_target = work / "database/runtime/local_config.json"
    config_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(settings.runtime_dir / "local_config.json", config_target)
    official = settings.media_evidence_dir / "official"
    shutil.copytree(official, work / "database/media_evidence/official")
    (AUDIT / "selected_holes.txt").write_text(hole + "\n", encoding="utf-8")
    save(AUDIT / "copy_result.json", {"status": "passed", "seconds": time.perf_counter() - started, "files": copied})
    print("Selected source copy complete; existing inputs preserved.", flush=True)


if __name__ == "__main__":
    main()
