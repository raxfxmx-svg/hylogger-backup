"""Orchestrate the NVCL pipeline for one hole:

    1. scripts/nvcl_download.py  (download raw data via nvcl-kit)
    2. scripts/nvcl_etl.py       (load raw data into data/holes/<hole_id>/hole.sqlite)

Usage:
    python scripts/ingest_nvcl.py <nvcl_id> [--provider wa] [--out-root data]

Stops with a non-zero exit if any step fails. If the TSG four-file set
(<hole_id>_tsg.{tsg,ini,cal,bip}) is present under data/raw/<hole_id>/, a hint
is printed that the legacy ingest_hole.py can be run as well.
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS_DIR = Path(__file__).resolve().parent

NEW_TABLES = (
    "borehole_meta",
    "nvcl_datasets",
    "nvcl_logs",
    "nvcl_scalar_data",
    "nvcl_tray_depths",
    "nvcl_images",
    "etl_runs",
)


def run_step(label: str, argv: list[str]) -> float:
    print(f"\n=== STEP: {label} ===")
    print("  cmd:", " ".join(argv))
    t0 = time.perf_counter()
    proc = subprocess.run(argv)
    elapsed = time.perf_counter() - t0
    if proc.returncode != 0:
        print(f"STEP FAILED: {label} (exit={proc.returncode}, {elapsed:.1f}s)")
        sys.exit(proc.returncode or 1)
    print(f"step ok: {label} ({elapsed:.1f}s)")
    return elapsed


def main() -> int:
    ap = argparse.ArgumentParser(description="NVCL download + ETL orchestrator")
    ap.add_argument("nvcl_id", help="NVCL hole identifier, e.g. 05GJD001")
    ap.add_argument("--provider", default="wa", help="NVCL provider (default: wa)")
    ap.add_argument("--out-root", default="data", help="output data root (default: data)")
    args = ap.parse_args()

    out_root = Path(args.out_root)
    raw_dir = out_root / "raw" / args.nvcl_id
    hole_dir = out_root / "holes" / args.nvcl_id
    t_start = time.perf_counter()

    t_dl = run_step(
        "download",
        [
            sys.executable, str(SCRIPTS_DIR / "nvcl_download.py"), args.nvcl_id,
            "--provider", args.provider, "--out-root", str(out_root),
        ],
    )
    t_etl = run_step(
        "etl",
        [
            sys.executable, str(SCRIPTS_DIR / "nvcl_etl.py"), args.nvcl_id,
            "--out-root", str(out_root),
        ],
    )

    # TSG four-file set hint
    tsg_exts = [ext for ext in ("tsg", "ini", "cal", "bip")
                if (raw_dir / f"{args.nvcl_id}_tsg.{ext}").exists()]
    if len(tsg_exts) == 4:
        print(
            f"\nTSG four-file set detected in {raw_dir} "
            f"({args.nvcl_id}_tsg.tsg/.ini/.cal/.bip); you may also run the "
            f"legacy pipeline: {sys.executable} scripts/ingest_hole.py {args.nvcl_id}"
        )

    # summary
    print("\n=== SUMMARY ===")
    print(f"raw dir:    {raw_dir}")
    db_path = hole_dir / "hole.sqlite"
    print(f"hole db:    {db_path}")
    print(f"etl report: {hole_dir / 'etl-report.txt'}")
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            existing = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for t in NEW_TABLES:
                if t in existing:
                    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    print(f"  {t}: {n} rows")
        finally:
            conn.close()
    print(f"index db:   {out_root / 'index.sqlite'}")
    total = time.perf_counter() - t_start
    print(f"elapsed: download {t_dl:.1f}s + etl {t_etl:.1f}s = {total:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
