#!/usr/bin/env python
"""Convert raw NVCL downloads into a small set of readable wide tables.

The final SQLite database contains:
    hole_summary             One-row borehole and data-availability overview
    measurements             One row per sample, with scalar metrics in separate columns
    measurement_dictionary  Metric meanings, types, sources, and deduplication notes
    core_layout              Combined tray, section, depth, and thumbnail table
    spectrum_<name>          One wide table per physical spectrum, with wavelength columns

Write matching CSV files to data/readable/<hole_id>/ for Excel. UUID-named files
remain in data/raw/<hole_id>/ for source traceability rather than routine reading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


LOG_TYPE_NAMES = {
    "1": "classification/text",
    "2": "numeric/text measurement",
    "5": "numeric/text measurement",
    "6": "mask",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("%", " percent ").replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "value"


def _sql_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_log_file(raw_dir: Path, log_id: str) -> Path:
    matches = list((raw_dir / "scalars").glob(f"{log_id}_*.csv"))
    if len(matches) != 1:
        raise ValueError(f"log_id {log_id}: expected one scalar CSV, found {len(matches)}")
    return matches[0]


def _read_scalar_file(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if frame.shape[1] < 3:
        raise ValueError(f"scalar CSV has fewer than three columns: {path}")
    return frame.iloc[:, :3]


def _normalise_number(value: object):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def build_measurements(raw_dir: Path, datasets: list[dict]):
    """Merge 125 UUID CSV files, collapse byte-identical sources, and omit all-null columns."""
    logs = json.loads((raw_dir / "logs_scalar.json").read_text(encoding="utf-8"))
    special_ids = set()
    for dataset in datasets:
        special_ids.update(
            str(value) for value in (dataset.get("tray_id"), dataset.get("section_id"))
            if value
        )

    catalog = []
    groups: dict[str, list[dict]] = defaultdict(list)
    base_path = None
    for order, log in enumerate(logs):
        log_id = str(log["log_id"])
        path = _find_log_file(raw_dir, log_id)
        frame = _read_scalar_file(path)
        values = frame.iloc[:, 2]
        non_null = int((values != "null").sum())
        record = {
            "order": order,
            "log": log,
            "path": path,
            "rows": len(frame),
            "non_null": non_null,
            "sha256": _sha256(path),
            "special": log_id in special_ids,
        }
        groups[record["sha256"]].append(record)
        if not record["special"] and base_path is None:
            base_path = path

    if base_path is None:
        raise ValueError("no metre-based scalar CSV found")
    base = _read_scalar_file(base_path)
    depth_from = pd.to_numeric(base.iloc[:, 0], errors="raise")
    depth_to = pd.to_numeric(base.iloc[:, 1], errors="raise")
    measurements = pd.DataFrame(
        {
            "sample_no": np.arange(len(base), dtype=np.int64),
            "depth_from_m": depth_from.astype(float),
            "depth_to_m": depth_to.astype(float),
        }
    )

    group_list = sorted(groups.values(), key=lambda items: min(x["order"] for x in items))
    included_groups = [g for g in group_list if not g[0]["special"] and g[0]["non_null"] > 0]
    slug_counts = Counter(_slug(g[0]["log"].get("log_name")) for g in included_groups)
    slug_seen = Counter()

    for members in group_list:
        representative = members[0]
        log = representative["log"]
        display_name = str(log.get("log_name") or representative["path"].stem)
        base_slug = _slug(display_name)
        status = "included"
        column_name = ""
        notes = []
        value_kind = "not_loaded"

        if representative["special"]:
            status = "moved_to_core_layout"
            notes.append("StartDepth/EndDepth are sample indices, not metres")
        elif representative["non_null"] == 0:
            status = "all_null"
            notes.append("source contains no values; omitted from measurements")
        else:
            slug_seen[base_slug] += 1
            column_name = (
                f"{base_slug}_{slug_seen[base_slug]}"
                if slug_counts[base_slug] > 1
                else base_slug
            )
            frame = _read_scalar_file(representative["path"])
            if len(frame) != len(measurements):
                raise ValueError(
                    f"{representative['path'].name}: {len(frame)} rows != {len(measurements)}"
                )
            source_depth_from = pd.to_numeric(frame.iloc[:, 0], errors="raise").to_numpy()
            source_depth_to = pd.to_numeric(frame.iloc[:, 1], errors="raise").to_numpy()
            if not np.array_equal(source_depth_from, measurements["depth_from_m"].to_numpy()):
                raise ValueError(f"depth axis mismatch: {representative['path'].name}")
            if not np.array_equal(source_depth_to, measurements["depth_to_m"].to_numpy()):
                raise ValueError(f"end-depth axis mismatch: {representative['path'].name}")

            raw_values = frame.iloc[:, 2].replace("null", pd.NA)
            numeric_values = pd.to_numeric(raw_values, errors="coerce")
            if int(numeric_values.notna().sum()) == representative["non_null"]:
                value_kind = "numeric"
                measurements[column_name] = numeric_values.astype(float)
            else:
                value_kind = "text/category"
                measurements[column_name] = raw_values.astype("string")

        if len(members) > 1:
            notes.append(f"{len(members)} byte-identical source logs collapsed into one field")
        source_ids = [str(x["log"]["log_id"]) for x in members]
        source_files = [x["path"].name for x in members]
        log_types = sorted({str(x["log"].get("log_type") or "") for x in members})
        algorithms = sorted({str(x["log"].get("algorithm_id") or "") for x in members})
        catalog.append(
            {
                "column_name": column_name,
                "display_name": display_name,
                "value_kind": value_kind,
                "non_null_count": representative["non_null"],
                "source_log_count": len(members),
                "source_log_ids": "; ".join(source_ids),
                "source_files": "; ".join(source_files),
                "log_type_codes": "; ".join(log_types),
                "log_type_meanings": "; ".join(LOG_TYPE_NAMES.get(x, "unknown") for x in log_types),
                "algorithm_ids": "; ".join(algorithms),
                "status": status,
                "notes": "; ".join(notes),
            }
        )

    dictionary = pd.DataFrame(catalog)
    return measurements, dictionary


def build_core_layout(
    raw_dir: Path,
    hole_id: str,
    datasets: list[dict],
    measurements: pd.DataFrame,
) -> pd.DataFrame:
    """Combine Tray, Section, actual depth, tray depth, and thumbnails into one table."""
    if not datasets:
        return pd.DataFrame()
    dataset = datasets[0]
    tray_id = str(dataset.get("tray_id") or "")
    section_id = str(dataset.get("section_id") or "")
    if not tray_id or not section_id:
        return pd.DataFrame()

    tray = _read_scalar_file(_find_log_file(raw_dir, tray_id))
    section = _read_scalar_file(_find_log_file(raw_dir, section_id))
    tray.columns = ["sample_start", "sample_end", "tray_no"]
    section.columns = ["sample_start", "sample_end", "section_no"]
    tray["sample_start"] = pd.to_numeric(tray["sample_start"], errors="raise").astype(int)
    tray["sample_end"] = pd.to_numeric(tray["sample_end"], errors="raise").astype(int)
    section["sample_start"] = pd.to_numeric(section["sample_start"], errors="raise").astype(int)
    section["sample_end"] = pd.to_numeric(section["sample_end"], errors="raise").astype(int)

    tray_depth_raw = json.loads((raw_dir / "tray_depths.json").read_text(encoding="utf-8"))
    tray_depths = {}
    for entries in tray_depth_raw.values():
        for item in entries:
            tray_depths[str(item.get("sample_no"))] = (
                _normalise_number(item.get("start_value")),
                _normalise_number(item.get("end_value")),
            )

    image_manifest = json.loads(
        (raw_dir / "images_manifest.json").read_text(encoding="utf-8")
    )
    thumbnail_by_sample = {
        str(item.get("sample_no")): f"raw/{hole_id}/{item['file']}"
        for item in image_manifest.get("files", [])
        if item.get("kind") == "tray_thumbnail"
    }

    rows = []
    for _, sec in section.iterrows():
        sample_start = int(sec["sample_start"])
        sample_end = int(sec["sample_end"])
        matched = tray[
            (tray["sample_start"] <= sample_start) & (tray["sample_end"] >= sample_end)
        ]
        if matched.empty:
            matched = tray[
                (tray["sample_start"] <= sample_start) & (tray["sample_end"] >= sample_start)
            ]
        if matched.empty:
            raise ValueError(f"section starting at sample {sample_start} has no tray")
        tray_row = matched.iloc[0]
        tray_index = int(matched.index[0])
        tray_depth_from, tray_depth_to = tray_depths.get(str(tray_index), (None, None))
        section_no = _normalise_number(sec["section_no"])
        rows.append(
            {
                "tray_no": str(tray_row["tray_no"]),
                "tray_index": tray_index,
                "section_no": section_no,
                "sample_start": sample_start,
                "sample_end": sample_end,
                "depth_from_m": float(measurements.iloc[sample_start]["depth_from_m"]),
                "depth_to_m": float(measurements.iloc[sample_end]["depth_to_m"]),
                "tray_depth_from_m": tray_depth_from,
                "tray_depth_to_m": tray_depth_to,
                "thumbnail_file": thumbnail_by_sample.get(str(tray_index), ""),
            }
        )
    return pd.DataFrame(rows)


def _wavelength_column(value: float, units: str) -> str:
    number = f"{float(value):g}".replace("-", "neg_").replace(".", "p")
    return f"wl_{number}_{_slug(units or 'unit')}"


def build_spectra(raw_dir: Path, measurements: pd.DataFrame):
    logs = {
        str(item["log_id"]): item
        for item in json.loads((raw_dir / "logs_spectral.json").read_text(encoding="utf-8"))
    }
    manifest = json.loads(
        (raw_dir / "spectral_manifest.json").read_text(encoding="utf-8")
    )
    complete = [item for item in manifest if item.get("status") == "complete"]
    name_counts = Counter(_slug(item.get("log_name")) for item in complete)
    name_seen = Counter()
    result = []

    for item in complete:
        log_id = str(item["log_id"])
        log = logs[log_id]
        base_name = _slug(item.get("log_name") or "spectrum")
        name_seen[base_name] += 1
        suffix = f"_{name_seen[base_name]}" if name_counts[base_name] > 1 else ""
        table_name = f"spectrum_{base_name}{suffix}"
        sample_count = int(item["sample_count"])
        band_count = int(item["band_count"])
        values = np.fromfile(raw_dir / str(item["file"]), dtype="<f4")
        if values.size != sample_count * band_count:
            raise ValueError(
                f"{item['file']}: {values.size} float32 values != "
                f"{sample_count} * {band_count}"
            )
        values = values.reshape(sample_count, band_count)
        wavelengths = log.get("wavelengths") or []
        if len(wavelengths) != band_count:
            raise ValueError(f"spectral wavelength count mismatch for {log_id}")
        columns = [_wavelength_column(w, str(log.get("wavelength_units") or "")) for w in wavelengths]
        if len(columns) != len(set(columns)):
            raise ValueError(f"duplicate wavelength columns for {log_id}")

        if sample_count == len(measurements):
            sample_axis = measurements[["sample_no", "depth_from_m", "depth_to_m"]].reset_index(drop=True)
        else:
            sample_axis = pd.DataFrame(
                {
                    "sample_no": np.arange(sample_count, dtype=np.int64),
                    "depth_from_m": np.nan,
                    "depth_to_m": np.nan,
                }
            )
        frame = pd.concat(
            [sample_axis, pd.DataFrame(values, columns=columns)], axis=1, copy=False
        )
        result.append(
            {
                "table_name": table_name,
                "display_name": str(item.get("log_name") or table_name),
                "log_id": log_id,
                "frame": frame,
                "band_count": band_count,
                "sample_count": sample_count,
            }
        )
    return result


def build_hole_summary(
    raw_dir: Path,
    hole_id: str,
    datasets: list[dict],
    measurements: pd.DataFrame,
    dictionary: pd.DataFrame,
    core_layout: pd.DataFrame,
    spectra: list[dict],
) -> pd.DataFrame:
    borehole = json.loads((raw_dir / "borehole.json").read_text(encoding="utf-8"))
    dataset = datasets[0] if datasets else {}
    prof_manifest = json.loads(
        (raw_dir / "profilometer_manifest.json").read_text(encoding="utf-8")
    )
    image_manifest = json.loads(
        (raw_dir / "images_manifest.json").read_text(encoding="utf-8")
    )
    image_status = {
        _slug(item.get("log_name")): item.get("status")
        for item in image_manifest.get("logs", [])
    }
    mosaic_files = [
        f"raw/{hole_id}/{item['file']}"
        for item in image_manifest.get("files", [])
        if item.get("kind") == "mosaic"
    ]
    prof_status = "; ".join(
        f"{item.get('log_name')}: {item.get('status')}" for item in prof_manifest
    ) or "none"
    return pd.DataFrame(
        [
            {
                "hole_id": hole_id,
                "hole_name": borehole.get("name"),
                "longitude": borehole.get("x"),
                "latitude": borehole.get("y"),
                "elevation_m": borehole.get("elevation_m"),
                "borehole_length_m": borehole.get("boreholeLength_m"),
                "drill_start_date": borehole.get("drillStartDate"),
                "drill_end_date": borehole.get("drillEndDate"),
                "operator": borehole.get("operator"),
                "driller": borehole.get("driller"),
                "project": borehole.get("project"),
                "purpose": borehole.get("purpose"),
                "status": borehole.get("status"),
                "drilling_method": borehole.get("drillingMethod"),
                "dataset_id": dataset.get("dataset_id"),
                "dataset_name": dataset.get("dataset_name"),
                "sample_count": len(measurements),
                "depth_from_m": float(measurements["depth_from_m"].min()),
                "depth_to_m": float(measurements["depth_to_m"].max()),
                "measurement_columns": int((dictionary["status"] == "included").sum()),
                "collapsed_duplicate_sources": int(
                    dictionary.loc[dictionary["status"] == "included", "source_log_count"].sum()
                    - (dictionary["status"] == "included").sum()
                ),
                "all_null_sources": int(
                    dictionary.loc[dictionary["status"] == "all_null", "source_log_count"].sum()
                ),
                "tray_count": int(core_layout["tray_no"].nunique()) if not core_layout.empty else 0,
                "section_count": len(core_layout),
                "spectral_tables": "; ".join(x["table_name"] for x in spectra),
                "spectral_sample_rows": sum(x["sample_count"] for x in spectra),
                "profilometer_status": prof_status,
                "tray_thumbnail_status": image_status.get("tray_thumbnail_images", "unknown"),
                "tray_image_status": image_status.get("tray_images", "unknown"),
                "imagery_status": image_status.get("imagery", "unknown"),
                "mosaic_file": "; ".join(mosaic_files),
                "generated_at_utc": _now(),
            }
        ]
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
        na_rep="",
        float_format="%.9g",
        lineterminator="\n",
    )


def _safe_remove_generated_dir(path: Path, parent: Path) -> None:
    resolved = path.resolve()
    parent_resolved = parent.resolve()
    if resolved.parent != parent_resolved or resolved == parent_resolved:
        raise ValueError(f"refusing to remove unexpected path: {resolved}")
    if path.exists():
        shutil.rmtree(path)


def write_readme(path: Path, hole_id: str, spectra: list[dict]) -> None:
    spectral_lines = "\n".join(
        f"- {index + 5:02d}_{item['table_name']}.csv: {item['display_name']}, "
        f"{item['sample_count']} samples × {item['band_count']} wavelength columns"
        for index, item in enumerate(spectra)
    )
    text = f"""Readable NVCL ETL results:{hole_id}

This is the readable output layer; UUID files under data/raw/{hole_id}/ retain the original source records.

Files
- 01_hole_summary.csv: one-row summary of the borehole, data bounds, volume, and service availability
- 02_measurements.csv: one row per sample, with scalar metrics joined horizontally
- 03_measurement_dictionary.csv: metric meanings, types, source UUIDs, and duplicate/all-null column notes
- 04_core_layout.csv: trays, sections, sample numbers, actual depths, and thumbnail paths
{spectral_lines}

Conversion rules
- Join 123 scalar CSVs sharing one depth axis horizontally by sample_no.
- Byte-identical logs share one field; the dictionary retains every source.
- All-null sources remain in the dictionary without creating empty output columns.
- Tray/Section StartDepth/EndDepth values are sample indexes, not metres; core_layout contains the converted values.
- Raw float32 spectra are expanded into one column per wavelength, named wl_<wavelength>_<unit>.
- unavailable means the NVCL provider exposes no matching data endpoint; it does not mean ETL discarded the data.
"""
    path.write_text(text, encoding="utf-8")


def write_outputs(
    out_root: Path,
    hole_id: str,
    hole_summary: pd.DataFrame,
    measurements: pd.DataFrame,
    dictionary: pd.DataFrame,
    core_layout: pd.DataFrame,
    spectra: list[dict],
) -> tuple[Path, Path, list[str]]:
    readable_root = out_root / "readable"
    readable_root.mkdir(parents=True, exist_ok=True)
    final_dir = readable_root / hole_id
    temp_dir = readable_root / f".{hole_id}.tmp"
    _safe_remove_generated_dir(temp_dir, readable_root)
    temp_dir.mkdir(parents=True)

    db_path = out_root / f"{hole_id}.sqlite"
    temp_db = out_root / f"{hole_id}.sqlite.tmp"
    temp_db.unlink(missing_ok=True)
    csv_files = []
    try:
        outputs = [
            ("01_hole_summary.csv", hole_summary),
            ("02_measurements.csv", measurements),
            ("03_measurement_dictionary.csv", dictionary),
            ("04_core_layout.csv", core_layout),
        ]
        for index, item in enumerate(spectra, start=5):
            outputs.append((f"{index:02d}_{item['table_name']}.csv", item["frame"]))
        for filename, frame in outputs:
            print(f"write CSV: {filename} ({len(frame)} rows × {len(frame.columns)} columns)")
            _write_csv(frame, temp_dir / filename)
            csv_files.append(filename)
        write_readme(temp_dir / "README.txt", hole_id, spectra)

        conn = sqlite3.connect(str(temp_db))
        try:
            conn.execute("PRAGMA synchronous = OFF")
            conn.execute("PRAGMA journal_mode = OFF")
            hole_summary.to_sql("hole_summary", conn, index=False, if_exists="replace")
            measurements.to_sql(
                "measurements", conn, index=False, if_exists="replace", chunksize=500
            )
            dictionary.to_sql(
                "measurement_dictionary", conn, index=False, if_exists="replace"
            )
            core_layout.to_sql("core_layout", conn, index=False, if_exists="replace")
            for item in spectra:
                item["frame"].to_sql(
                    item["table_name"],
                    conn,
                    index=False,
                    if_exists="replace",
                    chunksize=100,
                )
            conn.execute(
                "CREATE UNIQUE INDEX idx_measurements_sample_no"
                " ON measurements(sample_no)"
            )
            conn.execute(
                "CREATE INDEX idx_measurements_depth"
                " ON measurements(depth_from_m, depth_to_m)"
            )
            for item in spectra:
                conn.execute(
                    f"CREATE UNIQUE INDEX {_sql_ident('idx_' + item['table_name'] + '_sample')}"
                    f" ON {_sql_ident(item['table_name'])}(sample_no)"
                )
            conn.commit()
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"SQLite integrity_check failed: {integrity}")
        finally:
            conn.close()

        _safe_remove_generated_dir(final_dir, readable_root)
        os.replace(temp_dir, final_dir)
        os.replace(temp_db, db_path)
        return db_path, final_dir, csv_files
    except Exception:
        _safe_remove_generated_dir(temp_dir, readable_root)
        temp_db.unlink(missing_ok=True)
        raise


def verify_outputs(
    db_path: Path,
    readable_dir: Path,
    measurements: pd.DataFrame,
    dictionary: pd.DataFrame,
    core_layout: pd.DataFrame,
    spectra: list[dict],
) -> list[str]:
    lines = []
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        expected = {
            "hole_summary": 1,
            "measurements": len(measurements),
            "measurement_dictionary": len(dictionary),
            "core_layout": len(core_layout),
            **{item["table_name"]: item["sample_count"] for item in spectra},
        }
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if tables != set(expected):
            raise ValueError(f"unexpected SQLite tables: {sorted(tables)}")
        for table, count in expected.items():
            actual = conn.execute(
                f"SELECT COUNT(*) FROM {_sql_ident(table)}"
            ).fetchone()[0]
            if actual != count:
                raise ValueError(f"{table}: db={actual} expected={count}")
            lines.append(f"  {table}: {actual} rows OK")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity_check failed")
    finally:
        conn.close()

    for csv_path in sorted(readable_dir.glob("*.csv")):
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            header = fh.readline().rstrip("\r\n")
        if not header:
            raise ValueError(f"empty CSV header: {csv_path}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Convert raw NVCL files into readable wide tables'
    )
    parser.add_argument("hole_id", help='Borehole ID, for example 05GJD001')
    parser.add_argument("--out", default="data", help='Data root (default: data)')
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.hole_id):
        print('ERROR: hole_id may contain only letters, digits, dots, underscores, and hyphens.')
        return 2

    out_root = Path(args.out)
    raw_dir = out_root / "raw" / args.hole_id
    if not raw_dir.is_dir():
        print(f"ERROR: raw data directory does not exist: {raw_dir}(Run download.py first.)")
        return 2

    started = time.perf_counter()
    try:
        datasets = json.loads((raw_dir / "datasets.json").read_text(encoding="utf-8"))
        print("build measurements + dictionary")
        measurements, dictionary = build_measurements(raw_dir, datasets)
        print("build core layout")
        core_layout = build_core_layout(raw_dir, args.hole_id, datasets, measurements)
        print("build readable spectra")
        spectra = build_spectra(raw_dir, measurements)
        hole_summary = build_hole_summary(
            raw_dir,
            args.hole_id,
            datasets,
            measurements,
            dictionary,
            core_layout,
            spectra,
        )
        db_path, readable_dir, csv_files = write_outputs(
            out_root,
            args.hole_id,
            hole_summary,
            measurements,
            dictionary,
            core_layout,
            spectra,
        )
        checks = verify_outputs(
            db_path, readable_dir, measurements, dictionary, core_layout, spectra
        )
    except Exception as exc:
        print(f"ERROR: readable ETL failed; the existing database is unchanged: {type(exc).__name__}: {exc}")
        return 1

    report = [
        "human-readable ETL report",
        f"hole_id: {args.hole_id}",
        f"time: {_now()}",
        f"database: {db_path}",
        f"readable directory: {readable_dir}",
        f"CSV files: {len(csv_files)}",
        "",
        *checks,
        "",
        f"measurement columns: {int((dictionary['status'] == 'included').sum())}",
        f"collapsed duplicate source logs: {int(dictionary['source_log_count'].sum() - len(dictionary))}",
        f"all-null source logs: {int(dictionary.loc[dictionary['status'] == 'all_null', 'source_log_count'].sum())}",
        f"elapsed: {time.perf_counter() - started:.1f}s",
    ]
    report_text = "\n".join(report) + "\n"
    (raw_dir / "load-report.txt").write_text(report_text, encoding="utf-8")
    print(report_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
