#!/usr/bin/env python
"""Run downloading and readable-table ETL in sequence.

Usage:
    python run.py <nvcl_id> [--provider wa] [--out data] [--cache data/.cache]

Run download.py and load.py as subprocesses of the current interpreter; stop if either fails.
Print output paths, table row counts, and total elapsed time at completion.
"""

import argparse
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent

def main() -> int:
    ap = argparse.ArgumentParser(description='Download and import NVCL borehole data')
    ap.add_argument("nvcl_id", help='Borehole ID, for example 05GJD001')
    ap.add_argument("--provider", default="wa", help='NVCL provider (default: wa)')
    ap.add_argument("--out", default=str(HERE / "data"), help='Data root')
    ap.add_argument("--cache", default=None, help='HTTP cache directory (default: <out>/.cache)')
    args = ap.parse_args()

    out = Path(args.out)
    cache = args.cache or str(out / ".cache")

    t0 = time.perf_counter()
    steps = [
        ("download", [sys.executable, str(HERE / "download.py"), args.nvcl_id,
                      "--provider", args.provider, "--out", str(out),
                      "--cache", cache]),
        ("load", [sys.executable, str(HERE / "load.py"), args.nvcl_id,
                  "--out", str(out)]),
    ]
    for name, cmd in steps:
        print(f"\n===== {name} =====")
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            print(f"\n{name} Failed (exit code  {rc}); stopping.")
            return rc

    elapsed = time.perf_counter() - t0
    db_path = out / f"{args.nvcl_id}.sqlite"
    print('\n===== Summary =====')
    print(f"Borehole    : {args.nvcl_id}")
    print(f"Database    : {db_path}")
    print(f"Raw files   : {out / 'raw' / args.nvcl_id}")
    print(f"Readable CSV: {out / 'readable' / args.nvcl_id}")
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            tables = [
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                    " AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            for table in tables:
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table:<12} {n} rows")
        finally:
            conn.close()
    print(f"Elapsed     : {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
