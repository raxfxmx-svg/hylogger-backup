#!/usr/bin/env python3
"""load_db.py — load samples + intervals into SQLite for one hole (thin CLI).

Usage:
    python scripts/load_db.py <raw_dir> <hole_id> [--out-root data]

Reads the fixture products under ``<out-root>/holes/<hole_id>/fixture/``
(scalar CSVs + intervals.json) and:
  * rebuilds ``holes/<hole_id>/hole.sqlite`` (tables samples, intervals,
    trays, photos, annotations) from scratch - WARNING: this discards the
    annotations table (manual review state); back up hole.sqlite first,
  * upserts the hole row in ``<out-root>/index.sqlite`` (raw_dir stored as
    an absolute path),
  * exports ``fixture/hole.json``,
  * appends a database section to ``fixture/intervals-report.txt``.

Table notes:
  samples/intervals  one row per sensor sample / per Min1 run; min1/grp1
                     decoded to names via the class maps in intervals.json
  trays              0-based tray id, label '0001'..; photo_file follows the
                     rule tray+1 -> four-digit file name, NULL (with a
                     warning) when the photo does not exist in raw_dir
  photos             catalogues the tray photos that actually exist; mosaic
                     images are not catalogued
  annotations        interval-review audit trail; recreated empty
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tsg_core import StepError, discover_inputs, load_hole_db  # noqa: E402

DEFAULT_OUT_ROOT = Path(__file__).resolve().parents[1] / "data"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Load one hole's samples + intervals into SQLite.")
    ap.add_argument("raw_dir", type=Path,
                    help="raw dataset directory (photo check + index raw_dir, "
                         "read-only)")
    ap.add_argument("hole_id")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT,
                    help=f"output data root (default: {DEFAULT_OUT_ROOT})")
    args = ap.parse_args(argv)

    out_root = args.out_root.resolve()
    hole_dir = out_root / "holes" / args.hole_id
    try:
        inputs = discover_inputs(args.raw_dir.resolve(), args.hole_id)
        summary = load_hole_db(args.hole_id, args.raw_dir.resolve(),
                               inputs["photos"], hole_dir / "fixture",
                               hole_dir / "hole.sqlite",
                               out_root / "index.sqlite")
    except StepError as err:
        print(f"FAILED: {err}", file=sys.stderr)
        return 1
    print(f"db: {summary['n_samples']} samples/sensor, {summary['n_trays']} "
          f"trays, depth {summary['depth_from']:.3f}.."
          f"{summary['depth_to']:.3f} m, sensors {summary['sensors']}, "
          f"photos {summary['n_photos']}"
          + (f", MISSING PHOTOS: {summary['missing_photos']}"
             if summary["missing_photos"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
