"""Package current code and public export files for the approved AWS replacement.
Package current code and public exports for the authorised AWS replacement.
"""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
exports = ROOT / "etl4_english_delivery_20261004/database/exports"
directories = [p.parent for p in exports.glob("*/manifest.json")]
if len(directories) != 1:
    raise ValueError("Expected one completed English batch export")
directory = directories[0]
manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
files = {}
for uploaded in (ROOT / 'github-upload').rglob("*.py"):
    relative = Path(*uploaded.parts[uploaded.parts.index("etl4"):])
    source = ROOT / relative
    if source.read_bytes() != uploaded.read_bytes():
        raise ValueError("The upload copy differs from the current source: " + str(relative))
    files[relative.as_posix()] = source
for source in (ROOT / "etl4/database/migrations").glob("*.sql"):
    files[source.relative_to(ROOT).as_posix()] = source
for name in [*manifest["files"], "manifest.json"]:
    files["export/" + directory.name + "/" + name] = directory / name
for name in ["cloud_english_delivery.py", "schema_comments.py", "cleanup_delivery.py"]:
    files[name] = HERE / name
archive = HERE / "etl4_english_control.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
    for name, source in sorted(files.items()):
        target.write(source, name)
record = {"archive": str(archive), "export_dir": str(directory), "batch_id": manifest["batch_id"],
          "byte_size": archive.stat().st_size, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
          "files": sorted(files), "contains_local_sources": False, "contains_private_urls": False}
(HERE / "control_inventory.json").write_text(json.dumps(record, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in record.items() if k != "files"}, ensure_ascii=True))
