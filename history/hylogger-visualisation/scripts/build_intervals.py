#!/usr/bin/env python3
"""build_intervals.py — rebuild mineral intervals from fixture CSVs (thin CLI).

Usage:
    python scripts/build_intervals.py <raw_dir> <hole_id> [--out-root data]

Reads ``<out-root>/holes/<hole_id>/fixture/{vnir,tir}-scalars.csv`` (whichever
exist) and decodes the Min1/Grp1 class indices via the raw .tsg files in
raw_dir (read-only): the class number stored in each parameter's band header
selects the [class N] section, which is then read by its own ``name =`` line
and entries - class names are never hard-coded.

Interval model: run-length encoding of consecutive identical Min1 class
indices in sample order. Runs whose Min1 is empty (CSV empty cell) are kept
with mineral=NULL, status='doubtful', flags='unassigned'.

Writes fixture/intervals.json and fixture/intervals-report.txt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tsg_core import StepError, build_intervals, discover_inputs  # noqa: E402

# --- doubtful thresholds (tuned in a previous session - do not retune) ---
# A run is 'doubtful' when its average fails any of:
#   wt1_avg < WT1_MIN[sensor]   (TSA weight too low)
#   error_avg > ERROR_MAX[sensor] (fit error too high)
#   nil_avg > NIL_MAX[sensor]   (NIL fraction too high)
# An average that is entirely NaN does not trip a threshold (stored NULL).
# WARNING: changing these changes interval statuses; re-running the pipeline
# rebuilds hole.sqlite and discards manual review state (annotations).
WT1_MIN = {"vnir": 0.50, "tir": 0.40}
ERROR_MAX = {"vnir": 300.0, "tir": 200.0}
NIL_MAX = {"vnir": 0.50, "tir": 0.10}

DEFAULT_OUT_ROOT = Path(__file__).resolve().parents[1] / "data"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Rebuild mineral intervals from the fixture scalar CSVs.")
    ap.add_argument("raw_dir", type=Path,
                    help="raw dataset directory (class decoding only, read-only)")
    ap.add_argument("hole_id")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT,
                    help=f"output data root (default: {DEFAULT_OUT_ROOT})")
    args = ap.parse_args(argv)

    try:
        inputs = discover_inputs(args.raw_dir.resolve(), args.hole_id)
        fixture = args.out_root.resolve() / "holes" / args.hole_id / "fixture"
        tsg_paths = {"vnir": inputs["vnir"]["tsg"]}
        if inputs["tir"] is not None \
                and (fixture / "tir-scalars.csv").is_file():
            tsg_paths["tir"] = inputs["tir"]["tsg"]
        result = build_intervals(fixture, tsg_paths, args.hole_id,
                                 WT1_MIN, ERROR_MAX, NIL_MAX)
    except StepError as err:
        print(f"FAILED: {err}", file=sys.stderr)
        return 1
    for sensor, s in result["summary"].items():
        print(f"{sensor}: {s['total']} intervals ({s['unassigned']} "
              f"unassigned), confirmed/doubtful "
              f"{s['confirmed']}/{s['doubtful']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
