#!/usr/bin/env python

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description='NVCL download and readable CSV ETL')
    parser.add_argument("hole_ids", nargs="*", help='One or more borehole IDs')
    parser.add_argument("--holes-file", help='Borehole ID text file or CSV')
    parser.add_argument("--provider", default="wa", help='NVCL provider (default: wa)')
    parser.add_argument("--out", default=str(HERE / "data"), help='Data root')
    parser.add_argument("--cache", help='Download cache root')
    parser.add_argument("--workers", type=int, default=1, help='Concurrent borehole downloads (default: 1)')
    parser.add_argument("--verify", action="store_true", help='Validate CSV rows after processing')
    args = parser.parse_args()
    if not args.hole_ids and not args.holes_file:
        parser.error("supply hole ids or --holes-file")

    holes = [*args.hole_ids]
    if args.holes_file:
        holes.extend(["--holes-file", args.holes_file])
    download = [
        sys.executable,
        str(HERE / "download.py"),
        *holes,
        "--provider",
        args.provider,
        "--out",
        args.out,
        "--workers",
        str(args.workers),
    ]
    if args.cache:
        download.extend(["--cache", args.cache])
    etl = [sys.executable, str(HERE / "etl.py"), *holes, "--out", args.out]

    print('===== Download =====', flush=True)
    download_rc = subprocess.run(download, check=False).returncode
    print('===== Generate CSV =====', flush=True)
    etl_rc = subprocess.run(etl, check=False).returncode
    verify_rc = 0
    if args.verify and etl_rc == 0:
        print('===== Validate CSV =====', flush=True)
        verify_rc = subprocess.run(
            [sys.executable, str(HERE / "verify.py"), "--out", args.out],
            check=False,
        ).returncode
    return download_rc or etl_rc or verify_rc


if __name__ == "__main__":
    raise SystemExit(main())
