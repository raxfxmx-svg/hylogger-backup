"""Save run reports and provide shared command execution and entry-point error handling.

Save run reports and provide shared command execution and entry-point error handling.
"""

import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from _db_files import write
from _settings import settings


def now():
    return datetime.now(timezone.utc).isoformat()


def command(args, env=None, timeout=60):
    # Capture output in a temporary file so background processes do not keep a pipe open.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run(
            [str(a) for a in args],
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            env=env,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(
            f"{Path(str(args[0])).name} failed ({result.returncode}): {err[-3000:]} {out[-1000:]}"
        )
    return out


def report(name, value, directory=None):
    directory = settings.reports_dir if directory is None else directory
    value = {"recorded_at": now(), **value}
    # The latest reference may be replaced; keep each complete check result separately.
    write(directory / "history" / f"{Path(name).stem}_{uuid.uuid4().hex}.json", value)
    write(directory / name, value)
    return value


def main_guard(fn):
    from _file_checks import run_record
    from _db_common import config

    try:
        run_record(run_report_directory, fn)
    except Exception as exc:
        # Connection settings may contain passwords; omit their contents from error messages.
        msg = str(exc)
        if settings.config_file.exists():
            try:
                for r in config()["roles"].values():
                    msg = msg.replace(r["password"], "[redacted]")
            except OSError:
                msg = "Local credential configuration is inaccessible; check file permissions"
        report(
            "last_failure.json",
            {
                "script": Path(sys.argv[0]).name,
                "error_type": type(exc).__name__,
                "detail": msg,
                "status": "failed",
            },
        )
        print(f"STOP: {type(exc).__name__}: {msg}", file=sys.stderr, flush=True)
        raise SystemExit(1)


def run_report_directory():
    return settings.reports_dir / "runs"
