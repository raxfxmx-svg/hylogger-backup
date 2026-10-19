"""Verify actual cloud receipts and two database snapshots, then save receipts required for local cleanup."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

HERE = Path(__file__).resolve().parent
BATCH = "8039f5a6c2c5711141bb201eaa1fb96636924d23c48faddd66edb782253519cd"
EXPORT = HERE.parents[1] / "etl4/single_final_check_20260930/database/exports" / BATCH
archive = Path("C:/Users/USER/Downloads/etl4_cloud_results_20261003.zip")
assert hashlib.sha256(archive.read_bytes()).hexdigest() == sys.argv[1]
names = {"audit_before.json", "audit_after.json", "audit_replay.json", "merge_execution.json",
         "replay_execution.json", "merge_first_receipt.json", "merge_receipt.json"}
with zipfile.ZipFile(archive) as source:
    assert set(source.namelist()) == names
    data = {name: source.read(name) for name in names}
records = {name: json.loads(content) for name, content in data.items()}
before = records["audit_before.json"]
after = records["audit_after.json"]
replay = records["audit_replay.json"]
receipt = records["merge_receipt.json"]
assert receipt["batch_id"] == BATCH and receipt["status"] == "complete"
assert receipt["upload_receipt_sha256"] == hashlib.sha256((EXPORT / "upload_receipt.json").read_bytes()).hexdigest()
assert receipt["reused"] and not receipt["active_release_changed"]
assert records["merge_first_receipt.json"]["active_release_changed"]
assert after["table_counts"] == replay["table_counts"]
assert after["release_id"] == replay["release_id"] == receipt["finalized_release_id"]
assert after["members"] == replay["members"]
assert after["history_releases"] == replay["history_releases"]
assert after["core_tables"] == 39 and len(after["migrations"]) == 6
assert (after["holes"], after["datasets"], int(after["samples"]), after["image_region"], after["spectral_array"]) == (12, 17, 732206, 4738, 31)
assert after["active_assets_without_s3"] == 0 and after["reader_can_read_composites"]
for name, content in data.items():
    (HERE / name).write_bytes(content)
(EXPORT / "merge_receipt.json").write_bytes(data["merge_receipt.json"])
summary = {"status": "complete", "cloud_holes_before": before["holes"], "cloud_holes_after": after["holes"],
           "active_datasets": after["datasets"], "total_versions": after["table_counts"]["dataset_revision"],
           "samples": int(after["samples"]), "image_regions": after["image_region"], "spectral_arrays": after["spectral_array"],
           "composite_samples": after["composite_samples"], "release_id": after["release_id"],
           "replay_business_counts_unchanged": True, "replay_release_unchanged": True,
           "active_assets_without_s3": 0, "deleted_local_files": 0}
(HERE / "cloud_completion.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary), flush=True)
