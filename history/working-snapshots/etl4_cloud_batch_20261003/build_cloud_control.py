"""Package current code and public delivery files without large raw files or local path mappings."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ETL = ROOT / "etl4"
BATCH = "8039f5a6c2c5711141bb201eaa1fb96636924d23c48faddd66edb782253519cd"
EXPORT = ETL / "single_final_check_20260930/database/exports" / BATCH
manifest = json.loads((EXPORT / "manifest.json").read_text(encoding="utf-8"))
selection = {"expected_active_release_id": "fd02659c-dc3d-52ea-a8eb-c032b91e7624",
             "datasets": [{key: item[key] for key in ("dataset_id", "dataset_revision_id")} for item in manifest["identity"]["datasets"]]}
(HERE / "final_selection.json").write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
files = {path: "etl4/" + path.relative_to(ETL).as_posix() for path in [
    *(ETL.glob("*.py")), *(ETL / "database").glob("*.py"),
    *(ETL / "processing").glob("*.py"), *(ETL / "database/migrations").glob("*.sql"),
    ETL / 'handoff/tools/handoff.py']}
for name in [*manifest["files"], "manifest.json"]:
    files[EXPORT / name] = "export/" + BATCH + "/" + name
for name in ("cloud_batch_runner.py", "final_selection.json"):
    files[HERE / name] = name
archive = HERE / "etl4_cloud_control.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
    for path, name in sorted(files.items(), key=lambda item: item[1]):
        target.write(path, name)
record = {"file": str(archive), "byte_size": archive.stat().st_size,
          "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "files": sorted(files.values()),
          "contains_local_sources": False, "contains_raw_assets": False}
(HERE / "cloud_control_inventory.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in record.items() if key != "files"}, ensure_ascii=False))
