"""Package the completed upload receipt, excluding private signatures.
Package completed upload receipts without private signatures.
"""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BATCH = "ac79c3d1825a46ce967237b230bf615e1a2425dc759f4f9a2ec947c5c8bb1fe9"
source = ROOT / "etl4_english_delivery_20261004/database/exports" / BATCH / "upload_receipt.json"
receipt = json.loads(source.read_text(encoding="utf-8"))
if receipt.get("status") != "complete" or receipt["batch_id"] != BATCH:
    raise ValueError("The upload has not completed")
first = json.loads((HERE / "upload_round1_receipt.json").read_text(encoding="utf-8"))
new_keys = {row["object_key"] for group in [first, receipt] for row in group["objects"] if not row["reused"]}
objects = {row["object_key"]: row for row in receipt["objects"]}
archive = HERE / "etl4_english_receipt.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
    target.write(source, "export/" + BATCH + "/upload_receipt.json")
result = {"status": "complete", "batch_id": BATCH, "objects": len(objects),
          "new_objects": len(new_keys), "reused_objects": len(objects) - len(new_keys),
          "uploaded_bytes": sum(objects[key]["byte_size"] for key in new_keys),
          "reused_bytes": sum(row["byte_size"] for key, row in objects.items() if key not in new_keys),
          "receipt_archive_bytes": archive.stat().st_size,
          "receipt_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
(HERE / "upload_statistics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
