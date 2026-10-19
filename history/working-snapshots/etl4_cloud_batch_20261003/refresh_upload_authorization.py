"""Accept refreshed authorisation for the current batch while retaining the previous actual partial receipt."""
import gzip
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BATCH = "8039f5a6c2c5711141bb201eaa1fb96636924d23c48faddd66edb782253519cd"
round_number = int(sys.argv[1])
downloads = Path("C:/Users/USER/Downloads")
payload = gzip.decompress((downloads / f"private_upload_urls_round{round_number}.json.gz").read_bytes())
document = json.loads(payload)
assert document["batch_id"] == BATCH
assert document["manifest_sha256"] == "e8f404230838ba81fdea39b8fd57fcbddc2c285c7413b584d5a54d883ba348f5"
assert document["bucket"] == "hyloggerdemo-000000000000-ap-southeast-2-an"
export = HERE.parents[1] / "etl4/single_final_check_20260930/database/exports" / BATCH
receipt = (export / "upload_receipt.json").read_bytes()
(HERE / f"upload_partial_round{round_number - 1}.json").write_bytes(receipt)
(downloads / "private_upload_urls.json").write_bytes(payload)
summary = json.loads(receipt)
print(json.dumps({"authorization_refreshed": True, "created_at": document["created_at"],
                  "previous_completed": summary["completed_objects"]}))
