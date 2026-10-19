from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from assets_etl import process_assets
from common import (
    ETLError,
    RELEASE_ID_PREFIX,
    SCHEMA_VERSION,
    raw_tree_summary,
    read_json,
    relative_key,
    sha256_file,
    table_from_rows,
    utc_now,
    write_json,
    write_parquet,
)
from core_images_etl import process_core_images
from metadata_etl import build_metadata_catalogs
from scalars_etl import process_scalars_and_core
from spectra_etl import process_spectra


def build_release_manifest(
    release_root: Path,
    release_id: str,
    hole_id: str,
    raw_tree: dict[str, Any],
    package_manifest: dict[str, Any],
    counts: dict[str, Any],
) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in release_root.rglob("*") if item.is_file()):
        if path.name == "release_manifest.json":
            continue
        files.append(
            {
                "storage_key": relative_key(path, release_root),
                "nbytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_id,
        "created_at": utc_now(),
        "holes": [hole_id],
        "source_raw_key": f"data/raw/{hole_id}",
        "source_package_status": str(package_manifest.get("status") or ""),
        "source_content_fingerprint": str(package_manifest.get("content_fingerprint") or ""),
        "source_raw_tree": raw_tree,
        "counts": counts,
        "files": files,
    }


def transform(
    hole_id: str,
    raw_root: Path,
    processed_root: Path,
    release_id: str | None = None,
) -> dict[str, Any]:
    raw_dir = (raw_root / hole_id).resolve()
    if not raw_dir.is_dir():
        raise ETLError(f"Raw package not found: {raw_dir}")
    package_manifest = read_json(raw_dir / "package_manifest.json")
    if str(package_manifest.get("hole_id") or "") != hole_id:
        raise ETLError("package_manifest hole_id does not match the requested hole")
    if package_manifest.get("errors"):
        raise ETLError(f"Raw package records errors: {package_manifest['errors']}")

    raw_tree = raw_tree_summary(raw_dir)
    source_fingerprint = str(
        package_manifest.get("content_fingerprint") or raw_tree["tree_sha256"]
    )
    release_id = release_id or f"{RELEASE_ID_PREFIX}_{source_fingerprint[:16]}"
    releases_root = processed_root / "releases"
    final_release = releases_root / release_id
    if final_release.exists():
        raise ETLError(
            f"Release already exists and will not be overwritten: {final_release}"
        )

    staging_parent = processed_root / ".staging" / uuid.uuid4().hex
    release_root = staging_parent / release_id
    release_root.mkdir(parents=True, exist_ok=False)
    warnings = [str(item) for item in package_manifest.get("warnings") or []]
    checks: list[dict[str, Any]] = [
        {
            "name": "raw_package_tree_recorded",
            "status": "pass",
            "details": raw_tree,
        }
    ]
    availability_rows: list[dict[str, Any]] = []

    try:
        hole_rows, dataset_rows, datasets = build_metadata_catalogs(
            raw_dir, hole_id, release_root
        )
        asset_rows, thumbnails = process_assets(
            raw_dir, release_root, hole_id, availability_rows, checks
        )
        (
            scalar_rows,
            sample_count,
            tray_count,
            section_count,
            dataset_id,
            sample_axis_key,
            scalar_values_key,
        ) = process_scalars_and_core(
            raw_dir,
            release_root,
            hole_id,
            datasets,
            thumbnails,
            availability_rows,
            checks,
            warnings,
        )
        section_image_rows, complete_core_strips = process_core_images(
            release_root,
            hole_id,
            asset_rows,
            thumbnails,
            checks,
            warnings,
        )
        write_json(
            release_root / "holes" / hole_id / "assets" / "catalog.json",
            asset_rows,
        )
        spectral_rows, axis_rows, complete_spectra = process_spectra(
            raw_dir,
            release_root,
            hole_id,
            dataset_id,
            sample_count,
            availability_rows,
            checks,
            warnings,
        )

        write_parquet(
            release_root / "catalog" / "holes.parquet", table_from_rows(hole_rows)
        )
        write_parquet(
            release_root / "catalog" / "datasets.parquet", table_from_rows(dataset_rows)
        )
        write_parquet(
            release_root / "catalog" / "scalar_series.parquet",
            table_from_rows(scalar_rows),
        )
        write_parquet(
            release_root / "catalog" / "spectral_series.parquet",
            table_from_rows(spectral_rows),
        )
        write_parquet(
            release_root / "catalog" / "spectral_axes.parquet",
            table_from_rows(axis_rows),
        )
        write_parquet(
            release_root / "catalog" / "assets.parquet", table_from_rows(asset_rows)
        )
        write_parquet(
            release_root / "catalog" / "availability.parquet",
            table_from_rows(availability_rows),
        )

        physical_scalar_columns = sum(
            1 for row in scalar_rows if row.get("is_canonical_physical_column")
        )
        counts = {
            "hole_count": len(hole_rows),
            "dataset_count": len(dataset_rows),
            "sample_count": sample_count,
            "scalar_source_series_count": len(scalar_rows),
            "scalar_physical_value_columns": physical_scalar_columns,
            "tray_count": tray_count,
            "section_count": section_count,
            "section_image_mapping_rows": len(section_image_rows),
            "core_strip_complete_count": complete_core_strips,
            "spectral_source_series_count": len(spectral_rows),
            "spectral_complete_series_count": complete_spectra,
            "spectral_axis_count": len(axis_rows),
            "asset_catalog_rows": len(asset_rows),
            "availability_rows": len(availability_rows),
        }
        quality_report = {
            "schema_version": SCHEMA_VERSION,
            "release_id": release_id,
            "hole_id": hole_id,
            "status": "pass",
            "generated_at": utc_now(),
            "warnings": warnings,
            "errors": [],
            "checks": checks,
            "counts": counts,
            "important_storage_keys": {
                "sample_axis": sample_axis_key,
                "scalar_values": scalar_values_key,
                "section_images": relative_key(
                    release_root / "holes" / hole_id / "core" / "section_images.parquet",
                    release_root,
                ),
            },
            "interpretation_policy": {
                "scientific_interpretation_added": False,
                "unknown_source_units_filled": False,
                "mineral_truth_algorithm_selected": False,
                "theoretical_borehole_path_generated": False,
                "heatmap_or_other_visual_derivative_generated": True,
                "visual_derivative_kinds": ["thumbnail_core_section_strips"],
            },
        }
        write_json(release_root / "quality_report.json", quality_report)
        release_manifest = build_release_manifest(
            release_root,
            release_id,
            hole_id,
            raw_tree,
            package_manifest,
            counts,
        )
        write_json(release_root / "release_manifest.json", release_manifest)

        releases_root.mkdir(parents=True, exist_ok=True)
        os.replace(release_root, final_release)
        write_json(
            processed_root / "current.json",
            {
                "schema_version": SCHEMA_VERSION,
                "release_id": release_id,
                "release_key": f"releases/{release_id}",
                "updated_at": utc_now(),
            },
        )
        shutil.rmtree(staging_parent, ignore_errors=True)
        return release_manifest
    except Exception:
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise
