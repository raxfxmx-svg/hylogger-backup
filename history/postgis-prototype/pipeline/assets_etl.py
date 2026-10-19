from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from common import ETLError, read_json, relative_key, sha256_file, validate_declared_file


def process_assets(
    raw_dir: Path,
    release_root: Path,
    hole_id: str,
    availability_rows: list[dict[str, Any]],
    checks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, str]]:
    manifest = read_json(raw_dir / "images_manifest.json")
    log_entries = manifest.get("logs") or []
    files = manifest.get("files") or []
    log_by_id = {str(item.get("log_id") or ""): item for item in log_entries}

    for item in log_entries:
        availability_rows.append(
            {
                "hole_id": hole_id,
                "dataset_id": str(item.get("dataset_id") or ""),
                "data_kind": "image",
                "source_log_id": str(item.get("log_id") or ""),
                "source_log_name": str(item.get("log_name") or ""),
                "source_status": str(item.get("status") or ""),
                "expected_count": int(item.get("sample_count") or 0),
                "available_count": int(item.get("downloaded") or 0),
            }
        )

    rows: list[dict[str, Any]] = []
    thumbnail_by_tray_index: dict[int, str] = {}
    for item in files:
        declared = dict(item)
        declared["status"] = "complete"
        source = validate_declared_file(raw_dir, declared, "image asset")
        assert source is not None
        source_key = str(item.get("file") or "")
        target = release_root / "holes" / hole_id / "assets" / "files" / source_key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256_file(target) != str(item.get("sha256") or ""):
            raise ETLError(f"Copied asset changed: {source_key}")

        width: int | None = None
        height: int | None = None
        image_format = ""
        if target.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}:
            with Image.open(target) as image:
                width, height = image.size
                image_format = str(image.format or "")
                image.verify()

        log_id = str(item.get("log_id") or "")
        sample_no_raw = item.get("sample_no")
        asset_id = f"{log_id}:{sample_no_raw if sample_no_raw is not None else 'file'}"
        row = {
            "asset_id": asset_id,
            "hole_id": hole_id,
            "dataset_id": str(item.get("dataset_id") or ""),
            "source_log_id": log_id,
            "source_log_name": str(item.get("log_name") or ""),
            "asset_kind": str(item.get("kind") or ""),
            "source_status": "complete",
            "source_sample_no": None if sample_no_raw is None else str(sample_no_raw),
            "source_depth_from": item.get("depth_from"),
            "source_depth_to": item.get("depth_to"),
            "mapping_precision": "tray_interval"
            if str(item.get("kind") or "") == "tray_thumbnail"
            else "source_record_only",
            "storage_key": relative_key(target, release_root),
            "nbytes": target.stat().st_size,
            "sha256": sha256_file(target),
            "image_format": image_format,
            "pixel_width": width,
            "pixel_height": height,
            "derived_from_asset_id": None,
            "section_index": None,
            "tray_index": int(sample_no_raw)
            if str(item.get("kind") or "") == "tray_thumbnail"
            and sample_no_raw is not None
            else None,
            "section_index_within_tray": None,
            "image_quality": "source_thumbnail"
            if str(item.get("kind") or "") == "tray_thumbnail"
            else "source_asset",
            "depth_direction": None,
        }
        rows.append(row)
        if row["asset_kind"] == "tray_thumbnail" and sample_no_raw is not None:
            thumbnail_by_tray_index[int(sample_no_raw)] = asset_id

    file_log_ids = {str(item.get("log_id") or "") for item in files}
    for log_id, item in log_by_id.items():
        if log_id in file_log_ids or str(item.get("status") or "") == "complete":
            continue
        rows.append(
            {
                "asset_id": f"{log_id}:status",
                "hole_id": hole_id,
                "dataset_id": str(item.get("dataset_id") or ""),
                "source_log_id": log_id,
                "source_log_name": str(item.get("log_name") or ""),
                "asset_kind": "source_log_status",
                "source_status": str(item.get("status") or ""),
                "source_sample_no": None,
                "source_depth_from": None,
                "source_depth_to": None,
                "mapping_precision": "none",
                "storage_key": None,
                "nbytes": 0,
                "sha256": None,
                "image_format": "",
                "pixel_width": None,
                "pixel_height": None,
                "derived_from_asset_id": None,
                "section_index": None,
                "tray_index": None,
                "section_index_within_tray": None,
                "image_quality": None,
                "depth_direction": None,
            }
        )

    checks.append(
        {
            "name": "asset_files_verified_and_copied",
            "status": "pass",
            "details": {"copied_files": len(files), "catalog_rows": len(rows)},
        }
    )
    return rows, thumbnail_by_tray_index
