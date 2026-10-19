from __future__ import annotations

import csv
import json
from pathlib import Path

WORKSPACE = Path(r"C:\path\to\project")
SOURCE_CSV = WORKSPACE / "29" / "SM_05KCD001.csv"
OUTPUT_DIR = WORKSPACE / "hylogger-visualisation" / "data" / "fixtures" / "05KCD001"

HOLE = {
    "hole_name": "05KCD001",
    "unique_well_id": "M0002408",
    "dataset_filename": "30",
    "archived_at": "Perth",
    "project": "Lake Magenta",
    "commodity": "Au",
    "catalog_location": "Youanmi Terrane, Murchison Domain",
    "longitude": 118.9696138,
    "latitude": -33.72360603,
    "easting": 682490.0222,
    "northing": 6266747.2327,
    "datum": "GDA94",
    "zone": 50,
    "map_sheet_100k": "Jerramungup 2640",
    "map_sheet_250k": "Newdegate SI50-08",
    "total_depth_m": 201.5,
    "scanned_from_m": 59.5,
    "scanned_to_m": 201.5,
    "scanned_length_m": 142.0,
    "elevation_m": 322.0,
    "initial_dip_deg": -60.0,
    "initial_azimuth_deg": 90.0,
    "process_level": 2,
    "drill_report": "A73613",
    "source": {
        "file": "gswa-hylogger-2026_07_06 (1).xlsx",
        "sheet": "Sheet1",
        "excel_row": 29,
        "range": "A29:AC29",
    },
}

def number_or_none(value: str):
    value = value.strip()
    if not value or value.upper() == "N.A.":
        return None
    return round(float(value), 8)

def mineral_name(column: str) -> str:
    return column.split("_(", 1)[0]

def sensor_columns(header: list[str], sensor: str):
    suffix = f"(System_{sensor})".lower()
    valid = []
    invalid = None
    for index, column in enumerate(header):
        normalized = column.strip().lower()
        if not normalized.endswith(suffix):
            continue
        name = mineral_name(column.strip())
        if name.lower() == "invalid":
            invalid = index
        else:
            valid.append((index, name))
    return valid, invalid

def confidence(dominant_weight, invalid_weight):
    flags = []
    if invalid_weight is not None and invalid_weight >= 0.5:
        flags.append("high_invalid_weight")
        return "low", flags
    if dominant_weight is None:
        flags.append("no_valid_mineral")
        return "missing", flags
    if dominant_weight < 0.25:
        flags.append("weak_dominant_mineral")
        return "low", flags
    if dominant_weight < 0.5:
        return "medium", flags
    return "high", flags

def build_intervals():
    with SOURCE_CSV.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    header_index = next(
        i for i, row in enumerate(rows)
        if row and row[0].strip() == "Depth_from_(m)"
    )
    header = rows[header_index]
    swir_columns, swir_invalid = sensor_columns(header, "SWIR")
    tir_columns, tir_invalid = sensor_columns(header, "TIR")
    if not swir_columns or not tir_columns:
        raise RuntimeError("Could not identify both SWIR and TIR mineral columns")

    intervals = []
    for source_row, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        if not row or not row[0].strip():
            continue
        padded = row + [""] * (len(header) - len(row))
        depth_from = float(padded[0])
        depth_to = float(padded[1])
        for sensor, columns, invalid_index in (
            ("SWIR", swir_columns, swir_invalid),
            ("TIR", tir_columns, tir_invalid),
        ):
            weights = {}
            for index, name in columns:
                value = number_or_none(padded[index])
                if value is not None:
                    weights[name] = value
            if weights:
                dominant_mineral, dominant_weight = max(
                    weights.items(), key=lambda item: item[1]
                )
            else:
                dominant_mineral, dominant_weight = None, None
            invalid_weight = (
                number_or_none(padded[invalid_index])
                if invalid_index is not None else None
            )
            status, flags = confidence(dominant_weight, invalid_weight)
            if depth_from < HOLE["scanned_from_m"] < depth_to:
                flags.append("catalog_scan_start_59_5_but_csv_bin_starts_59_0")
            if depth_from < HOLE["scanned_to_m"] < depth_to:
                flags.append("catalog_scan_end_201_5_but_csv_bin_ends_202_0")
            intervals.append({
                "hole_name": HOLE["hole_name"],
                "depth_from_m": depth_from,
                "depth_to_m": depth_to,
                "sensor": sensor,
                "interpretation": "System",
                "dominant_mineral": dominant_mineral,
                "dominant_weight": dominant_weight,
                "invalid_weight": invalid_weight,
                "confidence": status,
                "quality_flags": flags,
                "mineral_weights": weights,
                "provenance": {
                    "source_file": SOURCE_CSV.name,
                    "source_row": source_row,
                    "algorithm": "dominant_valid_weight_v1",
                },
            })
    return header_index + 1, intervals

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    header_row, intervals = build_intervals()
    swir_count = sum(i["sensor"] == "SWIR" for i in intervals)
    tir_count = sum(i["sensor"] == "TIR" for i in intervals)
    confidence_counts = {}
    for interval in intervals:
        key = f'{interval["sensor"]}:{interval["confidence"]}'
        confidence_counts[key] = confidence_counts.get(key, 0) + 1

    mineral_log = {
        "schema_version": "1.0",
        "hole_name": HOLE["hole_name"],
        "source_file": SOURCE_CSV.name,
        "source_header_row": header_row,
        "interval_count": len(intervals),
        "sensor_interval_counts": {"SWIR": swir_count, "TIR": tir_count},
        "confidence_rule": {
            "low": "invalid_weight >= 0.50, or dominant_weight < 0.25",
            "missing": "no valid mineral weight",
            "medium": "0.25 <= dominant_weight < 0.50 and invalid_weight < 0.50",
            "high": "dominant_weight >= 0.50 and invalid_weight < 0.50",
        },
        "confidence_counts": confidence_counts,
        "notes": [
            "Weights are relative spectral model weights, not mineral mass percentages.",
            "Mineral weights are not gold grades.",
            "The source CSV contains System interpretation columns.",
            "The catalogue scan start is 59.5 m while the first CSV bin is 59.0-60.0 m.",
            "The catalogue scan end is 201.5 m while the final CSV bin is 201.0-202.0 m.",
        ],
        "intervals": intervals,
    }
    manifest = {
        "fixture_name": "05KCD001 golden dataset",
        "schema_version": "1.0",
        "files": {"hole": "hole.json", "mineral_log": "mineral-log.json"},
        "expected": {
            "drillhole_rows": 1,
            "mineral_interval_rows": len(intervals),
            "swir_rows": swir_count,
            "tir_rows": tir_count,
        },
        "raw_sources": [
            "gswa-hylogger-2026_07_06 (1).xlsx / Sheet1 / row 29",
            "29/SM_05KCD001.csv",
        ],
    }
    drillholes_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": HOLE["hole_name"],
                "geometry": {
                    "type": "Point",
                    "coordinates": [HOLE["longitude"], HOLE["latitude"]],
                },
                "properties": {
                    "hole_name": HOLE["hole_name"],
                    "unique_well_id": HOLE["unique_well_id"],
                    "project": HOLE["project"],
                    "commodity": HOLE["commodity"],
                    "total_depth_m": HOLE["total_depth_m"],
                    "scanned_from_m": HOLE["scanned_from_m"],
                    "scanned_to_m": HOLE["scanned_to_m"],
                },
            }
        ],
    }
    for filename, payload in (
        ("hole.json", HOLE),
        ("mineral-log.json", mineral_log),
        ("manifest.json", manifest),
        ("drillholes.geojson", drillholes_geojson),
    ):
        with (OUTPUT_DIR / filename).open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    with (OUTPUT_DIR / "mineral-log-flat.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        fieldnames = [
            "hole_name",
            "depth_from_m",
            "depth_to_m",
            "sensor",
            "interpretation",
            "dominant_mineral",
            "dominant_weight",
            "invalid_weight",
            "confidence",
            "quality_flags",
            "source_file",
            "source_row",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for interval in intervals:
            writer.writerow({
                "hole_name": interval["hole_name"],
                "depth_from_m": interval["depth_from_m"],
                "depth_to_m": interval["depth_to_m"],
                "sensor": interval["sensor"],
                "interpretation": interval["interpretation"],
                "dominant_mineral": interval["dominant_mineral"],
                "dominant_weight": interval["dominant_weight"],
                "invalid_weight": interval["invalid_weight"],
                "confidence": interval["confidence"],
                "quality_flags": "|".join(interval["quality_flags"]),
                "source_file": interval["provenance"]["source_file"],
                "source_row": interval["provenance"]["source_row"],
            })
    print(json.dumps({
        "output_dir": str(OUTPUT_DIR),
        "intervals": len(intervals),
        "swir": swir_count,
        "tir": tir_count,
        "first": intervals[0],
        "last": intervals[-1],
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
