"""Package actual upload receipts with the current merge code; exclude local mappings and temporary authorisations."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BATCH = "8039f5a6c2c5711141bb201eaa1fb96636924d23c48faddd66edb782253519cd"
EXPORT = ROOT / "etl4/single_final_check_20260930/database/exports" / BATCH
receipt = json.loads((EXPORT / "upload_receipt.json").read_text(encoding="utf-8"))
assert receipt["status"] == "complete" and receipt["completed_objects"] == 10163
assert receipt["batch_id"] == BATCH
assert receipt["manifest_sha256"] == "e8f404230838ba81fdea39b8fd57fcbddc2c285c7413b584d5a54d883ba348f5"
files = {EXPORT / "upload_receipt.json": f"export/{BATCH}/upload_receipt.json",
         HERE / "cloud_batch_runner.py": "cloud_batch_runner.py",
         ROOT / "etl4/_file_checks.py": "etl4/_file_checks.py"}
for name in ("39_upload_batch.py", "40_merge_cloud_batch.py", "41_cleanup_batch.py", "_batch_files.py"):
    files[ROOT / "etl4/database" / name] = "etl4/database/" + name
archive = HERE / "etl4_merge_delivery.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
    for path, name in files.items():
        target.write(path, name)
summary = {"archive": str(archive), "byte_size": archive.stat().st_size,
           "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "files": list(files.values()),
           "uploaded_objects": receipt["completed_objects"],
           "confirmed_bytes": sum(row["byte_size"] for row in receipt["objects"])}
(HERE / "merge_delivery_inventory.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary), flush=True)
