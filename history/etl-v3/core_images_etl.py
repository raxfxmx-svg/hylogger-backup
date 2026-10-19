from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from PIL import Image, ImageOps

from common import (
    ETLError,
    relative_key,
    resolved_storage_path,
    sha256_file,
    table_from_rows,
    write_json,
    write_parquet,
)


IMAGE_QUALITY = "thumbnail_derived"
MAPPING_PRECISION = "section_interval"
DEPTH_DIRECTION = "left_to_right"
JPEG_QUALITY = 90


def detect_thumbnail_row_bands(image: Image.Image, row_count: int) -> list[tuple[int, int]]:
    """Detect the stacked core rows in a small NVCL tray thumbnail.

    Tray thumbnails are already rectified and contain regularly stacked rows.
    Each equal-height slot is inset slightly to exclude its horizontal divider
    rails.  Fixed geometry is intentional at this resolution: a brightness
    detector could mistake genuinely dark rock for a divider and discard data.

    Returned bands use Pillow's half-open ``(top, bottom)`` coordinates.
    """
    if row_count <= 0:
        raise ETLError(f"Invalid thumbnail row count: {row_count}")
    width, height = image.size
    if width <= 0 or height < row_count * 3:
        raise ETLError(
            f"Thumbnail {width}x{height} is too small for {row_count} rows"
        )

    pitch = height / row_count
    bands: list[tuple[int, int]] = []
    for row_index in range(row_count):
        slot_top = int(round(row_index * pitch))
        slot_bottom = int(round((row_index + 1) * pitch))
        inset = max(1, int(round(pitch * 0.09)))
        top = slot_top + inset
        bottom = slot_bottom - inset
        if bottom <= top:
            raise ETLError(
                f"Could not derive a non-empty crop for row {row_index + 1}"
            )
        bands.append((top, bottom))

    return bands


def _mapping_row(
    *,
    hole_id: str,
    section: dict[str, Any],
    source_asset_id: str | None,
    source_storage_key: str | None,
    status: str,
    note: str,
) -> dict[str, Any]:
    section_index = int(section["section_index"])
    tray_index = int(section["tray_index"])
    within_tray = int(section["section_index_within_tray"])
    return {
        "hole_id": hole_id,
        "dataset_id": str(section["dataset_id"]),
        "section_index": section_index,
        "section_number": section_index + 1,
        "tray_index": tray_index,
        "tray_label": f"{tray_index + 1:04d}",
        "section_index_within_tray": within_tray,
        "row": within_tray + 1,
        "sample_index_from": int(section["sample_index_from"]),
        "sample_index_to": int(section["sample_index_to"]),
        "depth_from_m": float(section["sample_axis_start_value"]),
        "depth_to_m": float(section["sample_axis_end_value"]),
        "strip_asset_id": None,
        "storage_key": None,
        "source_thumbnail_asset_id": source_asset_id,
        "source_thumbnail_storage_key": source_storage_key,
        "image_status": status,
        "image_quality": IMAGE_QUALITY,
        "mapping_precision": MAPPING_PRECISION,
        "depth_direction": DEPTH_DIRECTION,
        "crop_method": "equal_height_thumbnail_rows_v1",
        "crop_left_px": None,
        "crop_top_px": None,
        "crop_right_px": None,
        "crop_bottom_px": None,
        "source_pixel_width": None,
        "source_pixel_height": None,
        "pixel_width": None,
        "pixel_height": None,
        "nbytes": 0,
        "sha256": None,
        "note": note,
    }


def process_core_images(
    release_root: Path,
    hole_id: str,
    asset_rows: list[dict[str, Any]],
    thumbnail_by_tray_index: dict[int, str],
    checks: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], int]:
    """Crop one thumbnail strip per core section and publish its mapping."""
    sections_path = release_root / "holes" / hole_id / "core" / "sections.parquet"
    sections = pq.read_table(sections_path).to_pylist()
    sections_by_tray: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for section in sections:
        sections_by_tray[int(section["tray_index"])].append(section)
    for tray_sections in sections_by_tray.values():
        tray_sections.sort(key=lambda row: int(row["section_index_within_tray"]))

    assets_by_id = {str(row["asset_id"]): row for row in asset_rows}
    mappings: list[dict[str, Any]] = []
    complete_count = 0
    output_dir = release_root / "holes" / hole_id / "assets" / "core_strips"

    for tray_index in sorted(sections_by_tray):
        tray_sections = sections_by_tray[tray_index]
        source_asset_id = thumbnail_by_tray_index.get(tray_index)
        source_asset = assets_by_id.get(source_asset_id or "")
        source_key = None if source_asset is None else source_asset.get("storage_key")

        if source_asset is None or not source_key:
            message = f"tray {tray_index + 1:04d}: no local thumbnail; strips unavailable"
            warnings.append(message)
            for section in tray_sections:
                mappings.append(
                    _mapping_row(
                        hole_id=hole_id,
                        section=section,
                        source_asset_id=source_asset_id,
                        source_storage_key=None,
                        status="unavailable",
                        note=message,
                    )
                )
            continue

        source_path = resolved_storage_path(release_root, str(source_key))
        try:
            with Image.open(source_path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
            bands = detect_thumbnail_row_bands(image, len(tray_sections))
        except (OSError, ETLError, ValueError) as exc:
            message = f"tray {tray_index + 1:04d}: thumbnail split failed: {exc}"
            warnings.append(message)
            for section in tray_sections:
                mappings.append(
                    _mapping_row(
                        hole_id=hole_id,
                        section=section,
                        source_asset_id=source_asset_id,
                        source_storage_key=str(source_key),
                        status="failed",
                        note=message,
                    )
                )
            continue

        source_width, source_height = image.size
        for section, (crop_top, crop_bottom) in zip(tray_sections, bands, strict=True):
            mapping = _mapping_row(
                hole_id=hole_id,
                section=section,
                source_asset_id=source_asset_id,
                source_storage_key=str(source_key),
                status="complete",
                note="",
            )
            row_number = int(section["section_index_within_tray"]) + 1
            filename = f"tray_{tray_index + 1:04d}_sec_{row_number}.jpg"
            target = output_dir / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            strip = image.crop((0, crop_top, source_width, crop_bottom))
            strip.save(
                target,
                "JPEG",
                quality=JPEG_QUALITY,
                subsampling=0,
                optimize=True,
            )

            pixel_width, pixel_height = strip.size
            if pixel_width != source_width:
                raise ETLError(
                    f"Thumbnail strip was unexpectedly resized: {pixel_width} != {source_width}"
                )
            storage_key = relative_key(target, release_root)
            digest = sha256_file(target)
            asset_id = f"{hole_id}:core_strip:{int(section['section_index'])}"
            mapping.update(
                {
                    "strip_asset_id": asset_id,
                    "storage_key": storage_key,
                    "crop_left_px": 0,
                    "crop_top_px": crop_top,
                    "crop_right_px": source_width,
                    "crop_bottom_px": crop_bottom,
                    "source_pixel_width": source_width,
                    "source_pixel_height": source_height,
                    "pixel_width": pixel_width,
                    "pixel_height": pixel_height,
                    "nbytes": target.stat().st_size,
                    "sha256": digest,
                }
            )
            mappings.append(mapping)
            asset_rows.append(
                {
                    "asset_id": asset_id,
                    "hole_id": hole_id,
                    "dataset_id": str(section["dataset_id"]),
                    "source_log_id": str(source_asset.get("source_log_id") or ""),
                    "source_log_name": str(source_asset.get("source_log_name") or ""),
                    "asset_kind": "core_section_strip",
                    "source_status": "complete",
                    "source_sample_no": None,
                    "source_depth_from": mapping["depth_from_m"],
                    "source_depth_to": mapping["depth_to_m"],
                    "mapping_precision": MAPPING_PRECISION,
                    "storage_key": storage_key,
                    "nbytes": target.stat().st_size,
                    "sha256": digest,
                    "image_format": "JPEG",
                    "pixel_width": pixel_width,
                    "pixel_height": pixel_height,
                    "derived_from_asset_id": source_asset_id,
                    "section_index": int(section["section_index"]),
                    "tray_index": tray_index,
                    "section_index_within_tray": row_number - 1,
                    "image_quality": IMAGE_QUALITY,
                    "depth_direction": DEPTH_DIRECTION,
                }
            )
            complete_count += 1

    mappings.sort(key=lambda row: int(row["section_index"]))
    core_dir = release_root / "holes" / hole_id / "core"
    write_parquet(core_dir / "section_images.parquet", table_from_rows(mappings))
    write_json(core_dir / "section_images.json", mappings)

    unavailable_count = len(mappings) - complete_count
    checks.append(
        {
            "name": "thumbnail_core_section_strips",
            "status": "pass" if unavailable_count == 0 else "warning",
            "details": {
                "mapping_rows": len(mappings),
                "complete_strips": complete_count,
                "unavailable_or_failed": unavailable_count,
                "image_quality": IMAGE_QUALITY,
                "output_resized": False,
                "jpeg_quality": JPEG_QUALITY,
            },
        }
    )
    return mappings, complete_count
