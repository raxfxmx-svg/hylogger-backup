"""Random selection and source copying for this run; create only an independent test directory."""

import hashlib
import importlib
import json
from pathlib import Path
import random
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
ETL = ROOT / "etl4"
AUDIT = Path(__file__).resolve().parent
WORK = ETL / "structure_input_20260930"
DATABASE = "etl4_refactor_check"
RAW = Path(r"D:\100demo\data\raw")
sys.path[:0] = [str(ETL / "database"), str(ETL / "processing"), str(ETL)]
from _settings import settings
from _db_common import connection


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


if (AUDIT / "selection.json").exists() or WORK.exists():
    raise ValueError('This run directory already exists; do not redraw or overwrite')
settings.work_dir = ETL / "refactor_work"
original = {}
for dbname in ("etl4_refactor_check",):
    with connection("reader", dbname=dbname) as conn:
        original[dbname] = {
            "active_release": conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone(),
            "holes": conn.execute("SELECT source_hole_id FROM core.borehole ORDER BY source_hole_id").fetchall(),
            "revisions": conn.execute("SELECT count(*) n FROM core.dataset_revision").fetchone()["n"],
        }
save(AUDIT / "existing_databases_before.json", original)
precheck = importlib.import_module("0_check_raw")
started = time.perf_counter()
holes = precheck.scan_raw(RAW)
precheck.write_reports(WORK / "raw_check", RAW, holes, time.perf_counter() - started, "structure_20260930")
candidates = sorted(h["hole_id"] for h in holes if h["route"] == "single" and not (ETL / h["hole_id"]).exists() and h["hole_id"] not in {x["source_hole_id"] for x in original[DATABASE]["holes"]})
hole = random.SystemRandom().choice(candidates)
source = RAW / hole
files = sorted(p for p in source.rglob("*") if p.is_file())
size = sum(p.stat().st_size for p in files)
selection = {
    "hole": hole, "source": str(source), "work_dir": str(WORK), "database": DATABASE,
    "method": 'SystemRandom.choice: select once with equal probability among complete single-dataset boreholes not yet copied to etl4',
    "candidates": candidates, "candidate_count": len(candidates),
    "source_file_count": len(files), "source_bytes": size,
}
save(AUDIT / "selection.json", selection)
print(json.dumps({k: v for k, v in selection.items() if k != "candidates"}, ensure_ascii=False), flush=True)
if shutil.disk_usage(ETL).free < size * 4 + 2 * 1024**3:
    raise ValueError('Insufficient space; preserve the selection without starting the copy')
copied = []
for index, path in enumerate(files, 1):
    relative = path.relative_to(source)
    target = ETL / hole / relative
    if target.exists():
        raise ValueError('Target file exists; do not overwrite')
    target.parent.mkdir(parents=True, exist_ok=True)
    checksum = sha(path)
    shutil.copy2(path, target)
    if sha(target) != checksum:
        raise ValueError('Copy verification failed: ' + str(relative))
    copied.append({"path": relative.as_posix(), "sha256": checksum, "bytes": path.stat().st_size})
    if index % 50 == 0:
        print(f"Copied and verified {index}/{len(files)}", flush=True)
save(AUDIT / "copy_result.json", {"status": "passed", "files": copied})
target = WORK / "database/runtime/local_config.json"
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(settings.runtime_dir / "local_config.json", target)
shutil.copytree(settings.media_evidence_dir / "official", WORK / "database/media_evidence/official")
(AUDIT / "selected_holes.txt").write_text(hole + "\n", encoding="utf-8")
print("Random selection and input preparation completed.", flush=True)
