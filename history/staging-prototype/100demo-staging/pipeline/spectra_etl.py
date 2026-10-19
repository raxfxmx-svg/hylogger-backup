from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np

from common import (
    ETLError,
    SCHEMA_VERSION,
    read_json,
    resolved_storage_path,
    sha256_file,
    sha256_json,
    source_log_map,
    validate_declared_file,
    write_json,
)


def spectral_statistics(
    path: Path, dtype: np.dtype[Any], value_count: int
) -> dict[str, Any]:
    values = np.memmap(path, mode="r", dtype=dtype, shape=(value_count,))
    finite_count = 0
    nonfinite_count = 0
    minimum: float | None = None
    maximum: float | None = None
    chunk_size = 1024 * 1024
    for start in range(0, value_count, chunk_size):
        chunk = np.asarray(values[start : start + chunk_size])
        finite_mask = np.isfinite(chunk)
        count = int(finite_mask.sum())
        finite_count += count
        nonfinite_count += int(chunk.size - count)
        if count:
            finite = chunk[finite_mask]
            chunk_min = float(finite.min())
            chunk_max = float(finite.max())
            minimum = chunk_min if minimum is None else min(minimum, chunk_min)
            maximum = chunk_max if maximum is None else max(maximum, chunk_max)
    del values
    return {
        "finite_value_count": finite_count,
        "nonfinite_value_count": nonfinite_count,
        "finite_min": minimum,
        "finite_max": maximum,
    }


def process_spectra(
    raw_dir: Path,
    release_root: Path,
    hole_id: str,
    dataset_id: str,
    sample_count: int,
    availability_rows: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    logs = source_log_map(raw_dir, "logs_spectral.json")
    manifest = read_json(raw_dir / "spectral_manifest.json")
    axes: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    complete_count = 0

    for item in manifest:
        log_id = str(item.get("log_id") or "")
        log = logs.get(log_id, {})
        status = str(item.get("status") or "")
        wavelengths = log.get("wavelengths") or []
        units = str(log.get("wavelength_units") or "")
        axis_payload = {"units": units, "values": wavelengths}
        axis_hash = sha256_json(axis_payload)
        axis_id = "axis_" + axis_hash[:16]
        axis_key = f"holes/{hole_id}/spectra/axes/{axis_id}.json"
        if axis_id not in axes:
            axes[axis_id] = {
                "axis_id": axis_id,
                "wavelength_units": units,
                "band_count": len(wavelengths),
                "values_sha256": axis_hash,
                "storage_key": axis_key,
            }
            write_json(resolved_storage_path(release_root, axis_key), axis_payload)

        availability_rows.append(
            {
                "hole_id": hole_id,
                "dataset_id": dataset_id,
                "data_kind": "spectrum",
                "source_log_id": log_id,
                "source_log_name": str(item.get("log_name") or log.get("log_name") or ""),
                "source_status": status,
                "expected_count": int(log.get("sample_count") or item.get("sample_count") or 0),
                "available_count": int(item.get("sample_count") or 0),
            }
        )

        output_key: str | None = None
        manifest_key: str | None = None
        statistics = {
            "finite_value_count": None,
            "nonfinite_value_count": None,
            "finite_min": None,
            "finite_max": None,
        }
        alignment_status = "no_values"
        if status == "complete":
            source = validate_declared_file(raw_dir, item, "spectrum")
            assert source is not None
            manifest_sample_count = int(item.get("sample_count") or 0)
            band_count = int(item.get("band_count") or 0)
            if len(wavelengths) != band_count:
                raise ETLError(
                    f"Spectrum {log_id}: wavelength count {len(wavelengths)} != band count {band_count}"
                )
            expected_size = manifest_sample_count * band_count * 4
            if source.stat().st_size != expected_size:
                raise ETLError(
                    f"Spectrum {log_id}: size {source.stat().st_size} != shape bytes {expected_size}"
                )
            output_key = f"holes/{hole_id}/spectra/series/{log_id}/values.f32"
            manifest_key = f"holes/{hole_id}/spectra/series/{log_id}/manifest.json"
            output_path = resolved_storage_path(release_root, output_key)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output_path)
            copied_hash = sha256_file(output_path)
            if copied_hash != str(item.get("sha256") or ""):
                raise ETLError(f"Copied spectrum changed: {log_id}")

            byte_order = str(item.get("byte_order") or "little")
            dtype = np.dtype("<f4" if byte_order == "little" else ">f4")
            statistics = spectral_statistics(
                output_path, dtype, manifest_sample_count * band_count
            )
            alignment_status = (
                "aligned_to_sample_index"
                if manifest_sample_count == sample_count
                else "sample_count_mismatch"
            )
            if alignment_status != "aligned_to_sample_index":
                warnings.append(
                    f"Spectrum {log_id} has {manifest_sample_count} samples; common axis has {sample_count}"
                )
            series_manifest = {
                "schema_version": SCHEMA_VERSION,
                "hole_id": hole_id,
                "dataset_id": dataset_id,
                "source_log_id": log_id,
                "source_log_name": str(item.get("log_name") or log.get("log_name") or ""),
                "source_status": status,
                "shape": [manifest_sample_count, band_count],
                "dtype": str(item.get("dtype") or "float32"),
                "byte_order": byte_order,
                "row_order": "sample_index",
                "row_byte_width": band_count * 4,
                "row_offset_formula": "sample_index * band_count * 4",
                "axis_id": axis_id,
                "axis_storage_key": axis_key,
                "values_storage_key": output_key,
                "nbytes": output_path.stat().st_size,
                "sha256": copied_hash,
                "statistics_for_validation_only": statistics,
            }
            write_json(resolved_storage_path(release_root, manifest_key), series_manifest)
            complete_count += 1

        rows.append(
            {
                "series_id": f"{dataset_id}:{log_id}",
                "hole_id": hole_id,
                "dataset_id": dataset_id,
                "source_log_id": log_id,
                "source_log_name": str(item.get("log_name") or log.get("log_name") or ""),
                "source_status": status,
                "sample_count": int(item.get("sample_count") or 0),
                "band_count": int(item.get("band_count") or len(wavelengths)),
                "dtype": str(item.get("dtype") or "float32"),
                "byte_order": str(item.get("byte_order") or "little"),
                "axis_id": axis_id,
                "axis_storage_key": axis_key,
                "sample_alignment_status": alignment_status,
                "values_storage_key": output_key,
                "manifest_storage_key": manifest_key,
                "nbytes": int(item.get("nbytes") or 0),
                "sha256": item.get("sha256"),
                **statistics,
            }
        )

    profiler_manifest_path = raw_dir / "profilometer_manifest.json"
    if profiler_manifest_path.is_file():
        profiler_logs = source_log_map(raw_dir, "logs_profilometer.json")
        for item in read_json(profiler_manifest_path):
            log_id = str(item.get("log_id") or "")
            log = profiler_logs.get(log_id, {})
            status = str(item.get("status") or "")
            availability_rows.append(
                {
                    "hole_id": hole_id,
                    "dataset_id": dataset_id,
                    "data_kind": "profilometer",
                    "source_log_id": log_id,
                    "source_log_name": str(item.get("log_name") or log.get("log_name") or ""),
                    "source_status": status,
                    "expected_count": int(item.get("sample_count") or 0),
                    "available_count": int(item.get("records") or 0),
                }
            )
            if status == "complete":
                validate_declared_file(raw_dir, item, "profilometer")

    axes_rows = list(axes.values())
    write_json(
        release_root / "holes" / hole_id / "spectra" / "series_catalog.json", rows
    )
    checks.append(
        {
            "name": "spectral_series_separated",
            "status": "pass",
            "details": {
                "source_series": len(rows),
                "complete_series": complete_count,
                "axis_count": len(axes_rows),
                "combined_signals_csv_created": False,
            },
        }
    )
    return rows, axes_rows, complete_count
