from pathlib import Path
import importlib, io, json, os, socket, sys, tempfile, unittest
check = Path(__file__).resolve().parent
code = check / "package/etl4"
sys.path[:0] = [str(code / "database/tests"), str(code / "database"), str(code)]
temp_root = (check / "temp").resolve()
assert temp_root.is_relative_to(check) and temp_root.is_dir()
tempfile.tempdir = str(temp_root)
os.environ["TEMP"] = str(temp_root)
os.environ["TMP"] = str(temp_root)
os.environ["PYTHONUTF8"] = "1"
for key in list(os.environ):
    if key.startswith("ETL4_"):
        del os.environ[key]
import psycopg
def blocked(*args, **kwargs):
    raise AssertionError("External connections forbidden")
psycopg.connect = blocked
socket.create_connection = blocked
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
names = [
    "test_batch_cleanup.BatchCleanupTests.test_file_replacement_after_preview_is_rejected",
    "test_batch_cleanup.BatchCleanupTests.test_hardlinked_file_is_retained",
    "test_batch_cleanup.BatchCleanupTests.test_raw_retained_without_both_explicit_options",
]
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
with (check / "environment-retry.log").open("w", encoding="utf-8") as log:
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
summary = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors)}
(check / "environment-retry-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary))
if not result.wasSuccessful():
    print((check / "environment-retry.log").read_text(encoding="utf-8"))
sys.exit(0 if result.wasSuccessful() else 1)
