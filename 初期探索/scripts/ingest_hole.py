#!/usr/bin/env python3
"""ingest_hole.py — one-command, hole-agnostic HyLogger ingestion pipeline.

Usage:
    python scripts/ingest_hole.py <raw_dir> <hole_id> [--out-root data]

Pipeline: discover raw files -> parse VNIR -> parse TIR (if the full
<hole_id>_tsg_tir.* set is present) -> make core strip images -> build
mineral intervals -> (re)build holes/<hole_id>/hole.sqlite -> upsert
<out-root>/index.sqlite.

Raw file naming rules (inside raw_dir, which is only read, never written):
    <hole_id>_tsg.{tsg,ini,cal,bip}      VNIR-SWIR set   (mandatory)
    <hole_id>_tsg_tir.{tsg,ini,cal,bip}  TIR set         (optional, all-or-none)
    <hole_id>_NNNN.jpg                   tray photos     (mosaic images excluded)

All dataset dimensions (trays, rows per tray, samples, bands, depths) are
read from the data itself; nothing is hard-coded to a specific hole.

Idempotent: re-running overwrites the fixture CSVs/reports, the strips and
hole.json, rebuilds hole.sqlite from scratch (annotations/review state is
discarded - back it up first if it contains manual review records) and
upserts the holes row in index.sqlite.

Each step's self-check report is written next to its products:
    holes/<hole_id>/fixture/{vnir,tir}-parse-report.txt
    holes/<hole_id>/fixture/intervals-report.txt   (intervals + db load)
    holes/<hole_id>/fixture/ingest-report.txt      (this orchestrator)
    holes/<hole_id>/strips/strips-report.txt
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tsg_core import (  # noqa: E402
    Reporter,
    StepError,
    build_intervals,
    discover_inputs,
    load_hole_db,
    make_strips,
    parse_sensor,
    sensor_order,
)
from build_intervals import ERROR_MAX, NIL_MAX, WT1_MIN  # noqa: E402

DEFAULT_OUT_ROOT = Path(__file__).resolve().parents[1] / "data"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Ingest one HyLogger hole (VNIR [+ TIR] + photos) into "
                    "the visualisation data tree.")
    ap.add_argument("raw_dir", type=Path,
                    help="directory with the raw TSG files and tray photos "
                         "(read-only)")
    ap.add_argument("hole_id", help="hole id, e.g. 05GJD001; selects the "
                                    "<hole_id>_tsg.* / <hole_id>_*.jpg files")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT,
                    help=f"output data root (default: {DEFAULT_OUT_ROOT}); "
                         "holes/<hole_id>/ and index.sqlite are written under it")
    args = ap.parse_args(argv)

    raw_dir = args.raw_dir.resolve()
    out_root = args.out_root.resolve()
    hole_id = args.hole_id
    hole_dir = out_root / "holes" / hole_id
    fixture = hole_dir / "fixture"
    strips_dir = hole_dir / "strips"
    hole_db = hole_dir / "hole.sqlite"
    index_db = out_root / "index.sqlite"

    t0 = time.time()
    rep = Reporter()
    rep(f"Ingest report - hole {hole_id}")
    rep("=" * 72)
    rep(f"raw dir  : {raw_dir}")
    rep(f"out root : {out_root}")
    rep(f"hole dir : {hole_dir}")
    rep(f"thresholds: WT1_MIN={WT1_MIN} ERROR_MAX={ERROR_MAX} "
        f"NIL_MAX={NIL_MAX} (from build_intervals.py)")
    rep("")

    def bail(step: str, err: StepError) -> int:
        rep("")
        rep(f"PIPELINE FAILED at step '{step}': {err}")
        rep("products from earlier steps were left in place; fix the input "
            "and re-run (idempotent).")
        rep.save(fixture / "ingest-report.txt")
        print(f"report written to {fixture / 'ingest-report.txt'}")
        return 1

    # ---------------------------------------------------------- discovery
    try:
        inputs = discover_inputs(raw_dir, hole_id)
    except StepError as err:
        return bail("discover", err)

    sensors = sensor_order(
        ["vnir"] + (["tir"] if inputs["tir"] is not None else []))
    rep(f"VNIR set  : {inputs['vnir']['tsg'].name} + .ini/.cal/.bip")
    if inputs["tir"] is not None:
        rep(f"TIR set   : {inputs['tir']['tsg'].name} + .ini/.cal/.bip")
    else:
        rep("TIR set   : not present - running VNIR only")
    rep(f"photos    : {len(inputs['photos'])} tray photo(s) found "
        f"(mosaic images excluded)")
    for note in inputs["photo_notes"]:
        rep(f"  note: {note}")
    rep(f"sensors   : {sensors}")
    rep("")

    # ------------------------------------------------------------- steps
    parse_stats: dict[str, dict] = {}
    for sensor in sensors:
        rep(f"--- step: parse {sensor.upper()} " + "-" * 50)
        try:
            parse_stats[sensor] = parse_sensor(
                sensor, inputs[sensor], fixture)
        except StepError as err:
            return bail(f"parse {sensor}", err)
        rep("")

    rep("--- step: make strips " + "-" * 51)
    if inputs["photos"]:
        try:
            records = make_strips(inputs["vnir"]["tsg"], inputs["photos"],
                                  hole_id, strips_dir)
        except StepError as err:
            return bail("make strips", err)
    else:
        records = []
        rep("WARNING: no tray photos found; strip generation skipped and "
            "all trays will get photo_file=NULL")
    rep("")

    rep("--- step: build intervals " + "-" * 47)
    tsg_paths = {s: inputs[s]["tsg"] for s in sensors}
    try:
        intervals = build_intervals(fixture, tsg_paths, hole_id,
                                    WT1_MIN, ERROR_MAX, NIL_MAX)
    except StepError as err:
        return bail("build intervals", err)
    rep("")

    rep("--- step: load database " + "-" * 49)
    try:
        db = load_hole_db(hole_id, raw_dir, inputs["photos"], fixture,
                          hole_db, index_db)
    except StepError as err:
        return bail("load db", err)
    rep("")

    # ----------------------------------------------------------- summary
    rep("=" * 72)
    rep("INGEST SUMMARY")
    rep(f"  hole_id           : {hole_id}")
    rep(f"  sensors           : {db['sensors']}")
    for sensor in sensors:
        st = parse_stats[sensor]
        iv = intervals["summary"][sensor]
        rep(f"  {sensor}: {st['n_samples']} samples, {st['n_bands']} bands, "
            f"wavelengths {st['wl_first']:.1f}..{st['wl_last']:.1f} nm; "
            f"{iv['total']} intervals ({iv['unassigned']} unassigned), "
            f"confirmed/doubtful {iv['confirmed']}/{iv['doubtful']}")
    rep(f"  trays             : {db['n_trays']} "
        f"(depth {db['depth_from']:.3f}..{db['depth_to']:.3f} m)")
    rep(f"  strips written    : {len(records)}")
    rep(f"  photos catalogued : {db['n_photos']}")
    if db["missing_photos"]:
        rep(f"  WARNING: {len(db['missing_photos'])} tray photo(s) missing; "
            f"photo_file NULL for: {db['missing_photos']}")
    rep(f"  hole db           : {hole_db}")
    rep(f"  index db          : {index_db}")
    rep(f"  elapsed           : {time.time() - t0:.1f} s")
    rep("")
    rep("RESULT: pipeline completed, all step self-checks passed")
    rep.save(fixture / "ingest-report.txt")
    print(f"report written to {fixture / 'ingest-report.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
