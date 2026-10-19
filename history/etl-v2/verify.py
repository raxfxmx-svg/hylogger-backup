#!/usr/bin/env python
"""Validate all five ETL2 CSV categories row by row without pandas or a database."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def read_dicts(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def verify_measurements(path: Path, hole_id: str, expected_rows: int) -> tuple[int, int]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        if header[:4] != ["hole_id", "sample_no", "depth_from_m", "depth_to_m"]:
            raise ValueError(f"unexpected measurements header: {path}")
        if len(header) != len(set(header)):
            raise ValueError(f"duplicate measurements columns: {path}")
        rows = 0
        for expected_sample, row in enumerate(reader):
            if len(row) != len(header):
                raise ValueError(f"{path.name}: row {expected_sample + 2} has wrong column count")
            if row[0] != hole_id or int(row[1]) != expected_sample:
                raise ValueError(f"{path.name}: sample sequence error at {expected_sample}")
            float(row[2])
            float(row[3])
            rows += 1
    if rows != expected_rows:
        raise ValueError(f"{path.name}: {rows} rows != {expected_rows}")
    return rows, len(header)


def verify_core(path: Path, hole_id: str, expected_rows: int) -> int:
    rows = 0
    for row in read_dicts(path):
        if row["hole_id"] != hole_id:
            raise ValueError(f"wrong hole id in {path}")
        if int(row["sample_start"]) > int(row["sample_end"]):
            raise ValueError(f"invalid sample interval in {path}")
        if not row["depth_from_m"] or not row["depth_to_m"]:
            raise ValueError(f"missing physical depth in {path}")
        rows += 1
    if rows != expected_rows:
        raise ValueError(f"{path.name}: {rows} rows != {expected_rows}")
    return rows


def verify_signals(path: Path, hole_id: str, expected_rows: int | None) -> tuple[int, int]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        required = [
            "hole_id",
            "signal_name",
            "signal_type",
            "status",
            "sample_no",
            "depth_from_m",
            "depth_to_m",
            "channel_units",
        ]
        if header[:8] != required or header[-1] != "values_json":
            raise ValueError(f"unexpected signals header: {path}")
        rows = 0
        for row in reader:
            if len(row) != len(header):
                raise ValueError(f"{path.name}: signal row {rows + 2} has wrong column count")
            if row[0] != hole_id:
                raise ValueError(f"wrong hole id in {path}")
            if row[3] == "complete" and not row[4]:
                raise ValueError(f"complete signal without sample number in {path}")
            if row[-1]:
                json.loads(row[-1])
            rows += 1
    if expected_rows is not None and rows != expected_rows:
        raise ValueError(f"{path.name}: {rows} rows != {expected_rows}")
    return rows, len(header)


def verify_assets(path: Path, data_root: Path, hole_id: str, expected_rows: int) -> int:
    rows = 0
    for row in read_dicts(path):
        if row["hole_id"] != hole_id:
            raise ValueError(f"wrong hole id in {path}")
        if row["file_path"]:
            stored = Path(row["file_path"])
            resolved = stored if stored.is_absolute() else data_root / stored
            if not resolved.is_file():
                raise ValueError(f"missing asset: {row['file_path']}")
        rows += 1
    if rows != expected_rows:
        raise ValueError(f"{path.name}: {rows} rows != {expected_rows}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate ETL2 CSV outputs')
    parser.add_argument("--out", default=str(HERE / "data"), help='Data root')
    args = parser.parse_args()
    data_root = Path(args.out).resolve()
    csv_root = data_root / "csv"
    holes_path = csv_root / "holes.csv"
    if not holes_path.is_file():
        parser.error(f"missing {holes_path}")

    forbidden = [
        path
        for path in data_root.rglob("*")
        if path.is_file()
        and (
            path.suffix.lower() in {".sqlite", ".db", ".xlsx"}
            or "measurement_dictionary" in path.name.lower()
        )
    ]
    if forbidden:
        raise ValueError(f"forbidden database/workbook/dictionary artifacts: {forbidden}")

    holes = list(read_dicts(holes_path))
    details = []
    for hole in holes:
        hole_id = hole["hole_id"]
        state_path = data_root / "state" / f"{hole_id}.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
        state_summary = state.get("summary", {})
        measurements = verify_measurements(
            csv_root / "measurements" / f"{hole_id}.csv",
            hole_id,
            int(hole["sample_count"]),
        )
        core = verify_core(
            csv_root / "core_intervals" / f"{hole_id}.csv",
            hole_id,
            int(hole["core_interval_count"]),
        )
        signals = verify_signals(
            csv_root / "signals" / f"{hole_id}.csv",
            hole_id,
            int(state_summary["signal_rows"]) if state_summary.get("signal_rows") is not None else None,
        )
        assets = verify_assets(
            csv_root / "assets" / f"{hole_id}.csv",
            data_root,
            hole_id,
            int(hole["asset_record_count"]),
        )
        details.append(
            {
                "hole_id": hole_id,
                "measurement_rows": measurements[0],
                "measurement_columns": measurements[1],
                "core_intervals": core,
                "signal_rows": signals[0],
                "signal_columns": signals[1],
                "asset_rows": assets,
            }
        )
    result = {"status": "ok", "logical_tables": 5, "holes": len(holes), "details": details}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
