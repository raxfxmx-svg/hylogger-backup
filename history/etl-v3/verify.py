from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import pyarrow.parquet as pq
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing ETL3 dependency. Run: python -m pip install -r requirements.txt"
    ) from exc

from common import ETLError, raw_tree_summary, read_json, sha256_file


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ETLError(message)


def resolve_inside(root: Path, key: str) -> Path:
    require(bool(key), "Empty storage key")
    path = (root / key).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ETLError(f"Storage key escapes release root: {key}") from exc
    return path


def parquet_rows(path: Path) -> int:
    return pq.ParquetFile(path).metadata.num_rows


def verify_release(project_root: Path, release_id: str | None = None) -> dict[str, Any]:
    processed_root = project_root / "data" / "processed"
    current = read_json(processed_root / "current.json")
    selected = release_id or str(current.get("release_id") or "")
    require(bool(selected), "No release_id supplied and current.json has none")
    release_root = processed_root / "releases" / selected
    require(release_root.is_dir(), f"Release directory is missing: {release_root}")
    manifest = read_json(release_root / "release_manifest.json")
    require(manifest.get("release_id") == selected, "Release ID mismatch")

    verified_files = 0
    for item in manifest.get("files") or []:
        key = str(item.get("storage_key") or "")
        path = resolve_inside(release_root, key)
        require(path.is_file(), f"Published file is missing: {key}")
        require(path.stat().st_size == int(item.get("nbytes") or -1), f"Size mismatch: {key}")
        require(sha256_file(path) == item.get("sha256"), f"SHA-256 mismatch: {key}")
        verified_files += 1

    hole_ids = manifest.get("holes") or []
    require(len(hole_ids) == 1, "ETL3 v1 verification expects one hole per release")
    hole_id = str(hole_ids[0])
    hole_root = release_root / "holes" / hole_id
    sample_axis_path = hole_root / "sample_axis.parquet"
    scalar_values_path = hole_root / "scalars" / "values.parquet"
    trays_path = hole_root / "core" / "trays.parquet"
    sections_path = hole_root / "core" / "sections.parquet"
    section_images_path = hole_root / "core" / "section_images.parquet"
    section_images_json_path = hole_root / "core" / "section_images.json"

    axis_table = pq.read_table(sample_axis_path)
    sample_count = axis_table.num_rows
    sample_indices = axis_table.column("sample_index").to_pylist()
    require(sample_indices == list(range(sample_count)), "sample_index is not contiguous and unique")
    axis_pairs = list(
        zip(
            axis_table.column("source_start_depth").to_pylist(),
            axis_table.column("source_end_depth").to_pylist(),
        )
    )
    duplicate_axis_rows = sample_count - len(set(axis_pairs))

    scalar_metadata = pq.ParquetFile(scalar_values_path).metadata
    require(scalar_metadata.num_rows == sample_count, "Scalar row count differs from sample axis")
    scalar_catalog = pq.read_table(release_root / "catalog" / "scalar_series.parquet")
    canonical_columns = sum(
        bool(value)
        for value in scalar_catalog.column("is_canonical_physical_column").to_pylist()
    )
    require(
        scalar_metadata.num_columns == canonical_columns + 2,
        "Scalar physical column count does not match its catalog",
    )

    tray_count = parquet_rows(trays_path)
    section_count = parquet_rows(sections_path)
    trays = pq.read_table(trays_path)
    sections = pq.read_table(sections_path)
    require(trays.column("sample_index_from")[0].as_py() == 0, "Tray coverage does not start at zero")
    require(
        trays.column("sample_index_to")[-1].as_py() == sample_count - 1,
        "Tray coverage does not end at the last sample",
    )
    require(sections.column("sample_index_from")[0].as_py() == 0, "Section coverage does not start at zero")
    require(
        sections.column("sample_index_to")[-1].as_py() == sample_count - 1,
        "Section coverage does not end at the last sample",
    )

    section_images = pq.read_table(section_images_path)
    section_image_json = read_json(section_images_json_path)
    require(
        section_images.num_rows == section_count,
        "Section image mapping count differs from section count",
    )
    require(
        len(section_image_json) == section_count,
        "Section image JSON count differs from section count",
    )
    section_indices = sections.column("section_index").to_pylist()
    require(
        section_images.column("section_index").to_pylist() == section_indices,
        "Section image mappings are not aligned to sections",
    )
    require(
        [int(row["section_index"]) for row in section_image_json] == section_indices,
        "Section image JSON is not aligned to sections",
    )
    section_image_rows = section_images.to_pylist()
    require(
        section_image_json == section_image_rows,
        "Section image JSON differs from the canonical Parquet mapping",
    )

    asset_catalog = pq.read_table(release_root / "catalog" / "assets.parquet")
    asset_rows = asset_catalog.to_pylist()
    assets_by_id = {str(row["asset_id"]): row for row in asset_rows}
    complete_section_images = 0
    section_image_widths: set[int] = set()
    section_rows = sections.to_pylist()
    for index, mapping in enumerate(section_image_rows):
        section = section_rows[index]
        require(
            int(mapping["tray_index"]) == int(section["tray_index"]),
            f"Section image tray mismatch at section {index}",
        )
        require(
            int(mapping["section_index_within_tray"])
            == int(section["section_index_within_tray"]),
            f"Section image row mismatch at section {index}",
        )
        require(
            int(mapping["sample_index_from"]) == int(section["sample_index_from"])
            and int(mapping["sample_index_to"]) == int(section["sample_index_to"]),
            f"Section image sample range mismatch at section {index}",
        )
        require(
            abs(float(mapping["depth_from_m"]) - float(section["sample_axis_start_value"]))
            < 1e-9
            and abs(float(mapping["depth_to_m"]) - float(section["sample_axis_end_value"]))
            < 1e-9,
            f"Section image depth mismatch at section {index}",
        )
        require(
            mapping["mapping_precision"] == "section_interval",
            f"Invalid section image mapping precision at section {index}",
        )
        require(
            mapping["image_quality"] == "thumbnail_derived",
            f"Invalid section image quality at section {index}",
        )
        require(
            mapping["depth_direction"] == "left_to_right",
            f"Invalid section image depth direction at section {index}",
        )
        source_asset_id = str(mapping.get("source_thumbnail_asset_id") or "")
        if mapping["image_status"] != "complete":
            if source_asset_id:
                require(
                    source_asset_id in assets_by_id,
                    f"Unknown optional source thumbnail asset at section {index}",
                )
            continue
        require(
            source_asset_id in assets_by_id,
            f"Unknown source thumbnail asset at section {index}",
        )
        require(
            assets_by_id[source_asset_id]["asset_kind"] == "tray_thumbnail",
            f"Section {index} source is not a tray thumbnail",
        )
        complete_section_images += 1
        strip_asset_id = str(mapping.get("strip_asset_id") or "")
        require(strip_asset_id in assets_by_id, f"Unknown strip asset at section {index}")
        strip_asset = assets_by_id[strip_asset_id]
        require(
            strip_asset["asset_kind"] == "core_section_strip",
            f"Wrong strip asset kind at section {index}",
        )
        key = str(mapping.get("storage_key") or "")
        require(strip_asset["storage_key"] == key, f"Strip storage mismatch at section {index}")
        image_path = resolve_inside(release_root, key)
        require(image_path.is_file(), f"Section image file is missing: {key}")
        require(image_path.stat().st_size == int(mapping["nbytes"]), f"Section image size mismatch: {key}")
        require(sha256_file(image_path) == mapping["sha256"], f"Section image hash mismatch: {key}")
        with Image.open(image_path) as image:
            width, height = image.size
            image.verify()
        require(width == int(mapping["pixel_width"]), f"Section image width mismatch: {key}")
        require(height == int(mapping["pixel_height"]), f"Section image height mismatch: {key}")
        require(
            width == int(mapping["source_pixel_width"]),
            f"Section thumbnail was horizontally resized: {key}",
        )
        section_image_widths.add(width)

    spectral_catalog = pq.read_table(release_root / "catalog" / "spectral_series.parquet")
    statuses = spectral_catalog.column("source_status").to_pylist()
    complete_indices = [index for index, status in enumerate(statuses) if status == "complete"]
    complete_shapes: list[list[int]] = []
    value_keys: set[str] = set()
    for index in complete_indices:
        values_key = spectral_catalog.column("values_storage_key")[index].as_py()
        manifest_key = spectral_catalog.column("manifest_storage_key")[index].as_py()
        require(values_key not in value_keys, "Complete spectra share one physical value file")
        value_keys.add(values_key)
        values_path = resolve_inside(release_root, values_key)
        series_manifest = read_json(resolve_inside(release_root, manifest_key))
        shape = series_manifest.get("shape") or []
        require(len(shape) == 2, f"Invalid spectral shape: {shape}")
        require(values_path.stat().st_size == int(shape[0]) * int(shape[1]) * 4, "Spectral byte size mismatch")
        require(sha256_file(values_path) == series_manifest.get("sha256"), "Spectral hash mismatch")
        complete_shapes.append([int(shape[0]), int(shape[1])])

    combined_signal_files = [
        path for path in release_root.rglob("*") if path.is_file() and path.name.lower() == "signals.csv"
    ]
    require(not combined_signal_files, "A combined signals.csv was created")

    raw_key = str(manifest.get("source_raw_key") or "")
    raw_dir = resolve_inside(project_root, raw_key)
    require(raw_dir.is_dir(), f"Raw package is missing: {raw_key}")
    current_raw_tree = raw_tree_summary(raw_dir)
    require(current_raw_tree == manifest.get("source_raw_tree"), "Raw package changed after publication")

    quality = read_json(release_root / "quality_report.json")
    require(quality.get("status") == "pass", "Quality report is not pass")
    interpretation = quality.get("interpretation_policy") or {}
    require(not interpretation.get("scientific_interpretation_added"), "Scientific interpretation flag is true")

    return {
        "status": "ok",
        "release_id": selected,
        "verified_manifest_files": verified_files,
        "hole_id": hole_id,
        "sample_count": sample_count,
        "duplicate_axis_coordinate_rows": duplicate_axis_rows,
        "scalar_physical_value_columns": canonical_columns,
        "tray_count": tray_count,
        "section_count": section_count,
        "section_image_mapping_rows": section_images.num_rows,
        "section_image_complete_count": complete_section_images,
        "section_image_widths": sorted(section_image_widths),
        "section_image_quality": "thumbnail_derived",
        "spectral_source_series_count": spectral_catalog.num_rows,
        "spectral_complete_series_count": len(complete_indices),
        "spectral_complete_shapes": complete_shapes,
        "combined_signals_csv": False,
        "raw_tree_verified": True,
        "warnings": quality.get("warnings") or [],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify an ETL3 published release")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--release-id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = verify_release(args.project_root.resolve(), args.release_id)
    except ETLError as exc:
        print(f"ETL3 verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
