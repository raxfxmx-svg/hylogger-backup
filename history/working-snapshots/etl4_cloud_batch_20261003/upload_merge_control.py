"""Upload the reviewed merge control package to the same S3 bucket using one temporary authorisation for that object."""
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

HERE = Path(__file__).resolve().parent
data = (HERE / "etl4_merge_delivery.zip").read_bytes()
sha = hashlib.sha256(data).hexdigest()
assert sha == "b3a051b951c52111773552df5e3c6d2c792e3a118ccd94c3e76292fe4ebe34b8"
document = json.loads(Path("C:/Users/USER/Downloads/private_control_put.json").read_text(encoding="utf-8"))
assert document["sha256"] == sha and document["byte_size"] == len(data)
address = urlsplit(document["url"])
assert address.scheme == "https" and address.netloc == "hyloggerdemo-000000000000-ap-southeast-2-an.s3.ap-southeast-2.amazonaws.com"
assert address.path == f"/etl4/control/{sha}/etl4_merge_delivery.zip"
request = Request(document["url"], data=data, method="PUT", headers={
    "Content-Type": "application/zip", "If-None-Match": "*",
    "x-amz-checksum-sha256": base64.b64encode(bytes.fromhex(sha)).decode("ascii")})
try:
    with urlopen(request, timeout=60) as response:
        assert response.status == 200
    result = {"status": "uploaded", "sha256": sha, "byte_size": len(data), "key": address.path[1:]}
    (HERE / "control_upload_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
except HTTPError as error:
    print(json.dumps({"status": "failed", "http_status": error.code}))
    raise SystemExit(1)
except Exception as error:
    print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
    raise SystemExit(1)
