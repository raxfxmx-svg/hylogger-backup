#!/usr/bin/env python3
"""parse_vnir.py — parse the VNIR-SWIR TSG file set of any hole (thin CLI).

Usage:
    python scripts/parse_vnir.py <raw_dir> <hole_id> [--out-root data]

Reads (read-only) ``<hole_id>_tsg.{tsg,ini,cal,bip}`` from raw_dir and writes
``<out-root>/holes/<hole_id>/fixture/vnir-scalars.csv``,
``vnir-wavelengths.csv`` and ``vnir-parse-report.txt`` (self-check report).
All logic lives in tsg_core.py; see scripts/README.md for the pipeline.

Key format notes (verified, must not regress):
  * .bip is a float32 little-endian bi-plane cube (2, n_samples, n_bands),
    plane 0 = spectra, plane 1 = scalar parameters; byte size checked exactly.
  * Scalar columns are located by the band numbers of the .tsg
    [band headers] section, NOT by the .ini slot ids; ini<->tsg are
    cross-validated by GUID (name fallback), and the "Index" parameter is
    TSG's virtual 0-based sample index, generated synthetically.
  * Null sentinel: values <= -1e37 are exported as empty cells.
  * Wavelengths are located by scanning the .cal file for a uniform-step
    monotonic float32 ramp (cross-checked against [wavelength specs]).
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
        description="Parse the VNIR-SWIR TSG file set of one hole.")
    ap.add_argument("raw_dir", type=Path, help="raw dataset directory (read-only)")
    ap.add_argument("hole_id")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT,
                    help=f"output data root (default: {DEFAULT_OUT_ROOT})")
    args = ap.parse_args(argv)

    try:
        inputs = discover_inputs(args.raw_dir.resolve(), args.hole_id)
        fixture = args.out_root.resolve() / "holes" / args.hole_id / "fixture"
        stats = parse_sensor("vnir", inputs["vnir"], fixture)
    except StepError as err:
        print(f"FAILED: {err}", file=sys.stderr)
        return 1
    print(f"vnir: {stats['n_samples']} samples, {stats['n_bands']} bands, "
          f"{stats['n_trays']} trays, depth {stats['depth_min']:.3f}.."
          f"{stats['depth_max']:.3f} m, wavelengths {stats['wl_first']:.1f}.."
          f"{stats['wl_last']:.1f} nm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
