from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow as pa

from common import (
    ETLError,
    numeric_parseable,
    read_json,
    read_scalar_csv,
    relative_key,
    source_log_map,
    validate_declared_file,
    values_digest,
    write_json,
    write_parquet,
)


def validated_index_range(start: str, end: str, sample_count: int) -> tuple[int, int]:
    try:
        start_float = float(start)
        end_float = float(end)
    except ValueError as exc:
        raise ETLError(f"Non-numeric interval range: {start}, {end}") from exc
    if not start_float.is_integer() or not end_float.is_integer():
        raise ETLError(f"Interval range is not integral: {start}, {end}")
    start_index = int(start_float)
    end_index = int(end_float)
    if start_index < 0 or end_index < start_index or end_index >= sample_count:
        raise ETLError(
            f"Interval range outside sample axis: {start_index}, {end_index}, n={sample_count}"
        )
    return start_index, end_index


def validate_complete_partition(
    ranges: list[tuple[int, int]], sample_count: int, label: str
) -> None:
    cursor = 0
    for start, end in sorted(ranges):
        if start != cursor:
            raise ETLError(f"{label} ranges do not form a contiguous partition at {cursor}")
        cursor = end + 1
    if cursor != sample_count:
        raise ETLError(f"{label} ranges stop at {cursor - 1}, expected {sample_count - 1}")


def process_scalars_and_core(
    raw_dir: Path,
    release_root: Path,
    hole_id: str,
    datasets: list[dict[str, Any]],
    thumbnail_by_tray_index: dict[int, str],
    availability_rows: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], int, int, int, str, str, str]:
    if len(datasets) != 1:
        raise ETLError(
            "ETL3 v1 requires exactly one dataset per raw hole package; "
            f"found {len(datasets)}"
        )
    dataset = datasets[0]
    dataset_id = str(dataset.get("dataset_id") or "")
    tray_log_id = str(dataset.get("tray_id") or "")
    section_log_id = str(dataset.get("section_id") or "")
    interval_ids = {tray_log_id, section_log_id}

    scalar_manifest = read_json(raw_dir / "scalar_manifest.json")
    scalar_logs = source_log_map(raw_dir, "logs_scalar.json")
    manifest_by_id = {str(item.get("log_id") or ""): item for item in scalar_manifest}
    dense_candidates = [
        item
        for item in scalar_manifest
        if str(item.get("status") or "") == "complete"
        and str(item.get("log_id") or "") not in interval_ids
    ]
    if not dense_candidates:
        raise ETLError("No completed dense scalar log is available to establish the sample axis")

    first = dense_candidates[0]
    first_path = validate_declared_file(raw_dir, first, "scalar axis source")
    assert first_path is not None
    _, first_rows = read_scalar_csv(first_path)
    axis = [(start, end) for start, end, _ in first_rows]
    sample_count = len(axis)
    if not sample_count:
        raise ETLError("The selected sample axis is empty")

    sample_axis_path = release_root / "holes" / hole_id / "sample_axis.parquet"
    sample_axis_table = pa.table(
        {
            "dataset_id": pa.array([dataset_id] * sample_count, type=pa.string()),
            "sample_index": pa.array(range(sample_count), type=pa.int32()),
            "source_start_depth": pa.array([item[0] for item in axis], type=pa.string()),
            "source_end_depth": pa.array([item[1] for item in axis], type=pa.string()),
        }
    )
    write_parquet(sample_axis_path, sample_axis_table)

    aligned_arrays: dict[str, pa.Array] = {
        "dataset_id": pa.array([dataset_id] * sample_count, type=pa.string()),
        "sample_index": pa.array(range(sample_count), type=pa.int32()),
    }
    value_hash_to_column: dict[str, str] = {}
    value_hash_group_size: Counter[str] = Counter()
    catalog_rows: list[dict[str, Any]] = []
    aligned_count = 0
    irregular_count = 0

    for item in scalar_manifest:
        log_id = str(item.get("log_id") or "")
        log = scalar_logs.get(log_id, {})
        status = str(item.get("status") or "")
        availability_rows.append(
            {
                "hole_id": hole_id,
                "dataset_id": dataset_id,
                "data_kind": "scalar",
                "source_log_id": log_id,
                "source_log_name": str(item.get("log_name") or log.get("log_name") or ""),
                "source_status": status,
                "expected_count": None,
                "available_count": None,
            }
        )
        base_catalog = {
            "hole_id": hole_id,
            "dataset_id": dataset_id,
            "source_log_id": log_id,
            "source_log_name": str(item.get("log_name") or log.get("log_name") or ""),
            "source_status": status,
            "source_log_type": str(log.get("log_type") or ""),
            "source_algorithm_id": str(log.get("algorithm_id") or ""),
            "source_mask_log_id": str(log.get("mask_log_id") or ""),
            "source_file": str(item.get("file") or ""),
            "source_sha256": str(item.get("sha256") or ""),
        }
        if status != "complete":
            catalog_rows.append(
                {
                    **base_catalog,
                    "alignment_status": "not_complete",
                    "row_count": 0,
                    "non_empty_count": 0,
                    "distinct_non_empty_count": 0,
                    "numeric_parseable": None,
                    "value_sequence_sha256": "",
                    "physical_column": "",
                    "is_canonical_physical_column": False,
                    "physical_storage_key": "",
                }
            )
            continue

        source = validate_declared_file(raw_dir, item, "scalar")
        assert source is not None
        _, rows = read_scalar_csv(source)
        values = [row[2] for row in rows]
        non_empty = [value for value in values if value != ""]

        if log_id in interval_ids:
            catalog_rows.append(
                {
                    **base_catalog,
                    "alignment_status": "interval_reference",
                    "row_count": len(rows),
                    "non_empty_count": len(non_empty),
                    "distinct_non_empty_count": len(set(non_empty)),
                    "numeric_parseable": numeric_parseable(values),
                    "value_sequence_sha256": values_digest(values),
                    "physical_column": "",
                    "is_canonical_physical_column": False,
                    "physical_storage_key": "",
                }
            )
            continue

        aligned = len(rows) == sample_count and all(
            (row[0], row[1]) == axis[index] for index, row in enumerate(rows)
        )
        sequence_hash = values_digest(values)
        if aligned:
            aligned_count += 1
            value_hash_group_size[sequence_hash] += 1
            physical_column = value_hash_to_column.get(sequence_hash)
            canonical = physical_column is None
            if canonical:
                physical_column = "s_" + log_id.replace("-", "_")
                value_hash_to_column[sequence_hash] = physical_column
                aligned_arrays[physical_column] = pa.array(values, type=pa.string())
            catalog_rows.append(
                {
                    **base_catalog,
                    "alignment_status": "aligned_by_row_index",
                    "row_count": len(rows),
                    "non_empty_count": len(non_empty),
                    "distinct_non_empty_count": len(set(non_empty)),
                    "numeric_parseable": numeric_parseable(values),
                    "value_sequence_sha256": sequence_hash,
                    "physical_column": physical_column,
                    "is_canonical_physical_column": canonical,
                    "physical_storage_key": f"holes/{hole_id}/scalars/values.parquet",
                }
            )
        else:
            irregular_count += 1
            irregular_path = (
                release_root
                / "holes"
                / hole_id
                / "scalars"
                / "irregular"
                / f"{log_id}.parquet"
            )
            irregular_table = pa.table(
                {
                    "dataset_id": pa.array([dataset_id] * len(rows), type=pa.string()),
                    "source_log_id": pa.array([log_id] * len(rows), type=pa.string()),
                    "row_index": pa.array(range(len(rows)), type=pa.int32()),
                    "source_start_depth": pa.array([row[0] for row in rows], type=pa.string()),
                    "source_end_depth": pa.array([row[1] for row in rows], type=pa.string()),
                    "source_value": pa.array(values, type=pa.string()),
                }
            )
            write_parquet(irregular_path, irregular_table)
            warnings.append(
                f"Scalar log {log_id} did not match the common sample axis and was stored separately"
            )
            catalog_rows.append(
                {
                    **base_catalog,
                    "alignment_status": "irregular_separate_file",
                    "row_count": len(rows),
                    "non_empty_count": len(non_empty),
                    "distinct_non_empty_count": len(set(non_empty)),
                    "numeric_parseable": numeric_parseable(values),
                    "value_sequence_sha256": sequence_hash,
                    "physical_column": "source_value",
                    "is_canonical_physical_column": True,
                    "physical_storage_key": relative_key(irregular_path, release_root),
                }
            )

    for row in catalog_rows:
        digest = str(row.get("value_sequence_sha256") or "")
        row["identical_value_series_count"] = value_hash_group_size.get(digest, 0)

    scalar_values_path = release_root / "holes" / hole_id / "scalars" / "values.parquet"
    write_parquet(scalar_values_path, pa.table(aligned_arrays))
    write_json(
        release_root / "holes" / hole_id / "scalars" / "series_catalog.json",
        catalog_rows,
    )

    tray_item = manifest_by_id.get(tray_log_id)
    section_item = manifest_by_id.get(section_log_id)
    if not tray_item or not section_item:
        raise ETLError("Dataset tray_id or section_id is missing from scalar_manifest.json")
    tray_path = validate_declared_file(raw_dir, tray_item, "tray interval log")
    section_path = validate_declared_file(raw_dir, section_item, "section interval log")
    assert tray_path is not None and section_path is not None
    _, tray_source_rows = read_scalar_csv(tray_path)
    _, section_source_rows = read_scalar_csv(section_path)

    tray_rows: list[dict[str, Any]] = []
    tray_ranges: list[tuple[int, int]] = []
    for tray_index, (start_raw, end_raw, value) in enumerate(tray_source_rows):
        start, end = validated_index_range(start_raw, end_raw, sample_count)
        tray_ranges.append((start, end))
        tray_rows.append(
            {
                "dataset_id": dataset_id,
                "tray_index": tray_index,
                "source_tray_value": value,
                "source_range_start": start_raw,
                "source_range_end": end_raw,
                "sample_index_from": start,
                "sample_index_to": end,
                "range_mapping_status": "validated_integer_sample_index_range",
                "sample_axis_start_value": axis[start][0],
                "sample_axis_end_value": axis[end][1],
                "thumbnail_asset_id": thumbnail_by_tray_index.get(tray_index),
                "image_mapping_precision": "tray_interval_only"
                if tray_index in thumbnail_by_tray_index
                else "no_local_image",
            }
        )
    validate_complete_partition(tray_ranges, sample_count, "Tray")

    section_rows: list[dict[str, Any]] = []
    section_ranges: list[tuple[int, int]] = []
    sections_per_tray: Counter[int] = Counter()
    for section_index, (start_raw, end_raw, value) in enumerate(section_source_rows):
        start, end = validated_index_range(start_raw, end_raw, sample_count)
        section_ranges.append((start, end))
        containing = [
            index
            for index, (tray_start, tray_end) in enumerate(tray_ranges)
            if tray_start <= start and end <= tray_end
        ]
        if len(containing) != 1:
            raise ETLError(
                f"Section {section_index} belongs to {len(containing)} trays, expected exactly one"
            )
        tray_index = containing[0]
        sections_per_tray[tray_index] += 1
        section_rows.append(
            {
                "dataset_id": dataset_id,
                "section_index": section_index,
                "source_section_value": value,
                "tray_index": tray_index,
                "section_index_within_tray": sections_per_tray[tray_index] - 1,
                "source_range_start": start_raw,
                "source_range_end": end_raw,
                "sample_index_from": start,
                "sample_index_to": end,
                "range_mapping_status": "validated_integer_sample_index_range",
                "sample_axis_start_value": axis[start][0],
                "sample_axis_end_value": axis[end][1],
            }
        )
    validate_complete_partition(section_ranges, sample_count, "Section")

    trays_path = release_root / "holes" / hole_id / "core" / "trays.parquet"
    sections_path = release_root / "holes" / hole_id / "core" / "sections.parquet"
    write_parquet(trays_path, pa.Table.from_pylist(tray_rows))
    write_parquet(sections_path, pa.Table.from_pylist(section_rows))

    duplicate_axis_coordinates = sample_count - len(set(axis))
    checks.extend(
        [
            {
                "name": "scalar_common_axis",
                "status": "pass",
                "details": {
                    "sample_count": sample_count,
                    "axis_source_log_id": str(first.get("log_id") or ""),
                    "aligned_source_series": aligned_count,
                    "irregular_source_series": irregular_count,
                    "physical_value_columns": len(aligned_arrays) - 2,
                    "duplicate_axis_coordinate_rows": duplicate_axis_coordinates,
                },
            },
            {
                "name": "tray_partition",
                "status": "pass",
                "details": {"tray_count": len(tray_rows)},
            },
            {
                "name": "section_partition",
                "status": "pass",
                "details": {
                    "section_count": len(section_rows),
                    "sections_per_tray": dict(sorted(sections_per_tray.items())),
                },
            },
        ]
    )
    return (
        catalog_rows,
        sample_count,
        len(tray_rows),
        len(section_rows),
        dataset_id,
        relative_key(sample_axis_path, release_root),
        relative_key(scalar_values_path, release_root),
    )
