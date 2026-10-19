#!/usr/bin/env python3
"""parse_tir.py — parse the TIR TSG file set of any hole (thin CLI).

Usage:
    python scripts/parse_tir.py <raw_dir> <hole_id> [--out-root data]

Reads (read-only) ``<hole_id>_tsg_tir.{tsg,ini,cal,bip}`` from raw_dir and
writes ``<out-root>/holes/<hole_id>/fixture/tir-scalars.csv``,
``tir-wavelengths.csv`` and ``tir-parse-report.txt``. Exits with an error
when the TIR set is absent (the TIR set is optional for the pipeline as a
whole; run ingest_hole.py for the all-or-nothing behaviour).

Format facts (verified, must not regress):
  * .bip is a float32 little-endian bi-plane cube (2, n_samples, n_bands);
    plane 0 = spectra, plane 1 = scalar parameters; byte size exact.
  * Scalar columns are indexed by the band numbers of .tsg [band headers]
    (numbering may be sparse); .ini slot ids must NOT be used as columns.
  * Null sentinel: values < -1e38 are exported as empty cells.
  * TIR wavelengths are NOT in the .cal (per-tray radiometric calibration
    records); they are computed linearly from [wavelength specs].
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tsg_core import StepError, discover_inputs, parse_sensor  # noqa: E402

DEFAULT_OUT_ROOT = Path(__file__).resolve().parents[1] / "data"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Parse the TIR TSG file set of one hole.")
    ap.add_argument("raw_dir", type=Path, help="raw dataset directory (read-only)")
    ap.add_argument("hole_id")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT,
                    help=f"output data root (default: {DEFAULT_OUT_ROOT})")
    args = ap.parse_args(argv)

    try:
        inputs = discover_inputs(args.raw_dir.resolve(), args.hole_id)
        if inputs["tir"] is None:
            print(f"no TIR file set (<hole_id>_tsg_tir.*) found in "
                  f"{args.raw_dir}", file=sys.stderr)
            return 2
        fixture = args.out_root.resolve() / "holes" / args.hole_id / "fixture"
        stats = parse_sensor("tir", inputs["tir"], fixture)
    except StepError as err:
        print(f"FAILED: {err}", file=sys.stderr)
        return 1
    print(f"tir: {stats['n_samples']} samples, {stats['n_bands']} bands, "
          f"{stats['n_trays']} trays, depth {stats['depth_min']:.3f}.."
          f"{stats['depth_max']:.3f} m, wavelengths {stats['wl_first']:.1f}.."
          f"{stats['wl_last']:.1f} nm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
