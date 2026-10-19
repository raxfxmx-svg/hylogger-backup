#!/usr/bin/env python3
"""make_strips.py — rebuild core strip images from tray photos (thin CLI).

Usage:
    python scripts/make_strips.py <raw_dir> <hole_id> [--out-root data]

For every tray photo ``<hole_id>_NNNN.jpg`` found in raw_dir (mosaic images
excluded), detects the core area at 1/8 scale from brightness profiles,
crops each core row at full resolution, rescales to 2048 px wide JPEG
(quality 80) and writes ``<out-root>/holes/<hole_id>/strips/``
(tray_XXXX_sec_S.jpg + strips.json + strips-report.txt). Section depth
ranges come from the [sample headers] of ``<hole_id>_tsg.tsg``; the number
of rows per tray and all section geometry are read from the data, and trays
without a photo are skipped with a warning. Rows containing orange foam
filler, core-loss depth gaps and depth clamps are flagged in the JSON
"note" field.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tsg_core import StepError, discover_inputs, make_strips  # noqa: E402

DEFAULT_OUT_ROOT = Path(__file__).resolve().parents[1] / "data"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Rebuild core strip images from HyLogger tray photos.")
    ap.add_argument("raw_dir", type=Path, help="raw dataset directory (read-only)")
    ap.add_argument("hole_id")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT,
                    help=f"output data root (default: {DEFAULT_OUT_ROOT})")
    args = ap.parse_args(argv)

    try:
        inputs = discover_inputs(args.raw_dir.resolve(), args.hole_id)
        if not inputs["photos"]:
            print(f"no tray photos (<hole_id>_NNNN.jpg) found in "
                  f"{args.raw_dir}", file=sys.stderr)
            return 2
        strips = args.out_root.resolve() / "holes" / args.hole_id / "strips"
        records = make_strips(inputs["vnir"]["tsg"], inputs["photos"],
                              args.hole_id, strips)
    except StepError as err:
        print(f"FAILED: {err}", file=sys.stderr)
        return 1
    print(f"strips: {len(records)} strip images written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
