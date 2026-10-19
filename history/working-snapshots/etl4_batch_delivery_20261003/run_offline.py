"""List offline tests explicitly and prohibit real database connections."""

import ast
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
ETL = ROOT / "etl4"
DATABASE = ETL / "database"
OUTPUT = Path(__file__).resolve().parent
sys.path[:0] = [str(DATABASE / "tests"), str(ETL / "processing/tests"), str(DATABASE), str(ETL)]

import psycopg
from _settings import settings

modules = [
    "test_batch_entry", "test_code_structure", "test_input_selection", "test_media_structure",
    "test_refactor", "test_validation_flow", "test_local_batch", "test_data_contracts",
    "test_batch_files", "test_batch_export", "test_batch_upload",
]
started = time.perf_counter()
output = io.StringIO()
with tempfile.TemporaryDirectory(prefix="offline_delivery_", dir=ETL) as temporary:
    settings.work_dir = Path(temporary)
    with patch.object(psycopg, "connect", side_effect=AssertionError('Real database connections are prohibited')), \
            contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)

sources = sorted(set([*DATABASE.glob("*.py"), *(ETL / "processing").glob("*.py"),
                      *(DATABASE / "api").rglob("*.py"), ETL / "_settings.py",
                      ETL / 'handoff/tools/handoff.py']))
for path in sources:
    ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))

record = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
          "successful": result.wasSuccessful(), "elapsed_seconds": round(time.perf_counter() - started, 3),
          "syntax_files": len(sources), "modules": modules,
          "real_database_connection_blocked": True, "s3_client": "test fake only"}
(OUTPUT / "offline_test_output.txt").write_text(output.getvalue(), encoding="utf-8")
(OUTPUT / "offline_validation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, ensure_ascii=False))
if not result.wasSuccessful():
    print(output.getvalue()[-12000:])
    raise SystemExit(1)
