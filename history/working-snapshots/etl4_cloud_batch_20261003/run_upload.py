"""Save upload logs; report only error types and code locations without signed URLs."""
import importlib.util
import faulthandler
import json
from pathlib import Path
import sys
import time
import traceback
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
sys.stdout = (HERE / "upload_progress.log").open("a", encoding="utf-8", buffering=1)
sys.stderr = (HERE / "upload_diagnostic.log").open("a", encoding="utf-8", buffering=1)
print("upload helper started", flush=True)
print(json.dumps({"attempt_started": datetime.now(timezone.utc).isoformat()}), file=sys.stderr, flush=True)
ROOT = HERE.parents[1]
CODE = ROOT / "etl4/database"
sys.path[:0] = [str(CODE), str(CODE.parent)]
spec = importlib.util.spec_from_file_location("batch_upload", CODE / "39_upload_batch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
started = time.monotonic()
print("upload module ready", flush=True)
try:
    receipt = module.upload_batch(ROOT / "etl4/single_final_check_20260930/database/exports/8039f5a6c2c5711141bb201eaa1fb96636924d23c48faddd66edb782253519cd",
        "hyloggerdemo-000000000000-ap-southeast-2-an", "ap-southeast-2", "etl4",
        signed_urls=Path("C:/Users/USER/Downloads/private_upload_urls.json"), workers=16)
    result = {"status": receipt["status"], "completed_objects": receipt["completed_objects"], "elapsed_seconds": time.monotonic() - started}
    (HERE / "upload_completion.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
except Exception as exc:
    print(json.dumps({"error_type": type(exc).__name__, "errno": getattr(exc, "errno", None),
        "http_status": getattr(exc, "status", None), "aws_error_code": getattr(exc, "aws_code", None),
        "filename": getattr(exc, "filename", None),
        "frames": [{"file": row.filename, "line": row.lineno, "function": row.name} for row in traceback.extract_tb(exc.__traceback__)]}), file=sys.stderr, flush=True)
    raise SystemExit(1)
finally:
    faulthandler.cancel_dump_traceback_later()
