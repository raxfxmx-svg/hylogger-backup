"""Remove the exact obsolete CloudShell files approved by the project owner.
Remove old CloudShell files listed in the project owner's confirmed inventory.
"""
import json
from pathlib import Path

ROOT = Path.home().resolve()
HERE = ROOT / "etl4-english-20261004"
receipt = json.loads((HERE / "replacement_receipt.json").read_text())
if receipt.get("database_commit") != "complete":
    raise ValueError("The database replacement has not committed")
cleanup = json.loads((HERE / "cleanup_receipt.json").read_text())
if cleanup.get("status") != "complete":
    raise ValueError("S3 cleanup has not completed")
plan = json.loads((HERE / "cloudshell_cleanup_plan.json").read_text())
if plan["count"] != 156 or plan["bytes"] != 108008876:
    raise ValueError("The approved CloudShell cleanup scope changed")
directories = [ROOT / name for name in ("etl4-batch-20261003", "etl4-pilot/manifests", "etl4-pilot/validation")]
singles = {ROOT / name for name in ("etl4_cloud_control.zip", "etl4-upload-urls.json")}
expected = {Path(row["path"]): row["byte_size"] for row in plan["files"]}
actual = {path for folder in directories for path in folder.rglob("*") if path.is_file()} | singles
if actual != set(expected):
    raise ValueError("The obsolete directories contain changed or unlisted files")
for path, size in expected.items():
    resolved = path.resolve()
    if path.is_symlink() or resolved != path or not resolved.is_relative_to(ROOT):
        raise ValueError("Unsafe cleanup path: " + str(path))
    if path not in singles and not any(resolved.is_relative_to(folder) for folder in directories):
        raise ValueError("The file is outside the approved directories")
    if path.stat().st_size != size:
        raise ValueError("An approved file changed: " + str(path))
for path in sorted(expected):
    path.unlink()
for folder in directories:
    for child in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        child.rmdir()
    folder.rmdir()
result = {"status": "complete", "removed_files": len(expected), "removed_bytes": sum(expected.values()),
          "scope": [str(path) for path in directories] + sorted(str(path) for path in singles)}
(HERE / "cloudshell_cleanup_receipt.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result), flush=True)
