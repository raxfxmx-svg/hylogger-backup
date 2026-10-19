"""Import only upload source; prohibit connections, external commands and legacy tool modules."""
import builtins
import importlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
STAGING = HERE / "merged_import_check"
sys.path[:0] = [str(STAGING / "etl4/database"), str(STAGING / "etl4")]
import psycopg

original_import = builtins.__import__
attempts = []


def no_effect(*args, **kwargs):
    attempts.append("unexpected effect")
    raise AssertionError("Import check forbids network, databases and external commands")


def current_only(name, *args, **kwargs):
    if name.startswith(("_legacy", "api.", "cloud_api")) or name == "api":
        raise AssertionError("Current upload must not import old workflows or API")
    return original_import(name, *args, **kwargs)


checked = []
with patch.object(psycopg, "connect", side_effect=no_effect), \
        patch.object(socket.socket, "connect", side_effect=no_effect), \
        patch.object(socket.socket, "connect_ex", side_effect=no_effect), \
        patch.object(subprocess, "run", side_effect=no_effect), \
        patch.object(builtins, "__import__", side_effect=current_only):
    for name in json.loads((STAGING / "modules.json").read_text(encoding="utf-8")):
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(STAGING), str(path)
        checked.append({"module": name, "path": path.relative_to(STAGING).as_posix()})
assert not attempts
assert not any(name.startswith("_legacy") for name in sys.modules)
result = {"status": "passed", "modules_imported": len(checked), "effect_attempts": attempts,
          "original_source_fallback": False, "legacy_or_api_loaded": False, "modules": checked}
(HERE / "upload_import_check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in result.items() if key != "modules"}, ensure_ascii=False))
