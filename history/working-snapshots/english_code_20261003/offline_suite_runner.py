"""Offline regression: prohibit database and network connections; run only test_*.py."""
import contextlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "etl4/database"), str(ROOT / "etl4/processing"), str(ROOT / "etl4")]
import psycopg

attempts = {"database": 0, "network": 0}

def no_database(*args, **kwargs):
    attempts["database"] += 1
    raise AssertionError("offline suite forbids psycopg.connect")

def no_network(*args, **kwargs):
    attempts["network"] += 1
    raise AssertionError("offline suite forbids socket connections")

class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = []

    def addSuccess(self, test):
        self.passed.append(test.id())
        super().addSuccess(test)

paths = sorted((ROOT / "etl4/processing/tests").glob("test_*.py")) + sorted((ROOT / "etl4/database/tests").glob("test_*.py"))
excluded = [path for path in paths if path.name == "test_database_contracts.py"]
paths = [path for path in paths if path not in excluded]
started = time.monotonic()
with (OUTPUT / "offline_suite.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log), \
        patch.object(psycopg, "connect", side_effect=no_database), patch.object(socket.socket, "connect", side_effect=no_network), \
        patch.object(socket.socket, "connect_ex", side_effect=no_network):
    suite = unittest.TestSuite()
    for path in paths:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = module
        spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=Result).run(suite)
report = {"status": "passed" if result.wasSuccessful() else "failed", "tests_run": result.testsRun,
          "seconds": round(time.monotonic() - started, 3), "guard_attempts": attempts,
          "scope": "processing/tests and database/tests; no AWS, API, or PostgreSQL connections",
          "modules": [str(path.relative_to(ROOT)) for path in paths],
          "excluded": [str(path.relative_to(ROOT)) for path in excluded],
          "passed_tests": result.passed, "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
          "failures": [{"test": test.id(), "traceback": detail} for test, detail in result.failures],
          "errors": [{"test": test.id(), "traceback": detail} for test, detail in result.errors],
          "unexpected_successes": [test.id() for test in result.unexpectedSuccesses]}
(OUTPUT / "offline_suite.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: report[key] for key in ("status", "tests_run", "seconds", "guard_attempts")}, ensure_ascii=False))
raise SystemExit(0 if result.wasSuccessful() else 1)
