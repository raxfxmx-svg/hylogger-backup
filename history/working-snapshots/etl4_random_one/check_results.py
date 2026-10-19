"""Record before/after digests and confirm existing business records remain intact."""

import gzip
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from prepare_check import AUDIT, ETL, connection, save, settings, sha, snapshot

selection = json.loads((AUDIT / "selection.json").read_text(encoding="utf-8"))
settings.work_dir = Path(selection["work_dir"])
settings.dbname = selection["database"]
phase = sys.argv[1]
with connection("reader") as conn:
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        tables = snapshot(conn)
        active = str(conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()["release_id"])
        versions = conn.execute("SELECT count(*) n FROM core.dataset_revision").fetchone()["n"]
        datasets = conn.execute("SELECT count(*) n FROM core.dataset").fetchone()["n"]
        db_bytes = conn.execute("SELECT pg_database_size(current_database()) n").fetchone()["n"]
result = {
    "active_release": active,
    "database_bytes": db_bytes,
    "dataset_count": datasets,
    "revision_count": versions,
    "table_counts": {name: len(rows) for name, rows in tables.items()},
    "business_fingerprints": {name: hashlib.sha256("\n".join(rows).encode()).hexdigest() for name, rows in tables.items()},
    "prepared_files": {path.relative_to(settings.prepared_dir).as_posix(): sha(path) for path in sorted(settings.prepared_dir.rglob("*")) if path.is_file()},
}
with gzip.open(AUDIT / "original_business_rows.json.gz", "rt", encoding="utf-8") as stream:
    original = json.load(stream)
missing = {name: sum((Counter(rows) - Counter(tables[name])).values()) for name, rows in original.items()}
assert not any(missing.values()), f"Existing records changed: {missing}"
original_state = json.loads((AUDIT / "database_before.json").read_text(encoding="utf-8"))
assert active == original_state["active_release"], 'Existing active release changed'
result["original_business_tables_preserved"] = len(original)
result["original_business_rows_preserved"] = sum(map(len, original.values()))
result["original_active_release_preserved"] = True
if phase == "after_replay":
    before = json.loads((AUDIT / "before_replay.json").read_text(encoding="utf-8"))
    assert result["table_counts"] == before["table_counts"], 'Rerun added business records'
    assert result["business_fingerprints"] == before["business_fingerprints"], 'Rerun changed business content'
    assert result["prepared_files"] == before["prepared_files"], 'Rerun changed prepared files'
    result["replay_new_business_rows"] = 0
    result["replay_new_revisions"] = 0
    result["replay_prepared_files_unchanged"] = len(result["prepared_files"])
result["free_after"] = shutil.disk_usage(ETL).free
result["status"] = "passed"
save(AUDIT / f"{phase}.json", result)
print(json.dumps({key: value for key, value in result.items() if key not in ("business_fingerprints", "prepared_files", "table_counts")}, ensure_ascii=False), flush=True)
