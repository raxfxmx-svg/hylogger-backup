from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

import pyarrow.parquet as pq
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

try:
    from .section_minerals import derive_section_minerals, normalise_orientation
except ImportError:  # Support direct execution: python etl/load_release.py ...
    from section_minerals import derive_section_minerals, normalise_orientation


ROLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleasePackage:
    root: Path
    release_id: str
    hole_id: str
    manifest: dict[str, Any]
    quality: dict[str, Any]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"Cannot read JSON {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseError(message)


def verify_release(release_root: Path) -> ReleasePackage:
    root = release_root.resolve()
    require(root.is_dir(), f"Release directory does not exist: {root}")
    manifest = read_json(root / "release_manifest.json")
    quality = read_json(root / "quality_report.json")

    release_id = str(manifest.get("release_id") or "")
    holes = manifest.get("holes") or []
    require(release_id == root.name, "Release directory name and release_id differ")
    require(len(holes) == 1, "The loader accepts exactly one hole per release")
    hole_id = str(holes[0])
    require(bool(hole_id), "Release hole_id is empty")
    require(quality.get("release_id") == release_id, "Quality report release_id differs")
    require(quality.get("hole_id") == hole_id, "Quality report hole_id differs")
    require(quality.get("status") == "pass", "Quality report status is not pass")
    require(not quality.get("errors"), "Quality report contains errors")

    required = [
        "catalog/holes.parquet",
        "catalog/datasets.parquet",
        "catalog/assets.parquet",
        "catalog/availability.parquet",
        "catalog/scalar_series.parquet",
        "catalog/spectral_axes.parquet",
        "catalog/spectral_series.parquet",
        f"holes/{hole_id}/sample_axis.parquet",
        f"holes/{hole_id}/core/trays.parquet",
        f"holes/{hole_id}/core/sections.parquet",
        f"holes/{hole_id}/core/section_images.parquet",
        f"holes/{hole_id}/source_metadata.json",
    ]
    for key in required:
        require((root / key).is_file(), f"Required release file is missing: {key}")

    manifest_files = manifest.get("files") or []
    require(bool(manifest_files), "Release manifest has no file inventory")
    for item in manifest_files:
        key = str(item.get("storage_key") or "")
        require(bool(key), "Manifest contains an empty storage_key")
        path = (root / key).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ReleaseError(f"Manifest path escapes release root: {key}") from exc
        require(path.is_file(), f"Manifest file is missing: {key}")
        require(path.stat().st_size == int(item["nbytes"]), f"Size mismatch: {key}")
        require(sha256_file(path) == item["sha256"], f"SHA-256 mismatch: {key}")

    return ReleasePackage(root, release_id, hole_id, manifest, quality)


def parquet_rows(package: ReleasePackage, key: str) -> list[dict[str, Any]]:
    try:
        return pq.read_table(package.root / key).to_pylist()
    except Exception as exc:
        raise ReleaseError(f"Cannot read Parquet {key}: {exc}") from exc


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def optional_float(value: Any) -> float | None:
    text = optional_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def optional_date(value: Any) -> date | None:
    text = optional_text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def copy_rows(
    cursor: psycopg.Cursor[Any],
    table: tuple[str, str],
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> int:
    statement = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
        sql.Identifier(table[0]),
        sql.Identifier(table[1]),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
    )
    count = 0
    with cursor.copy(statement) as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count


def package_tables(package: ReleasePackage) -> dict[str, list[dict[str, Any]]]:
    hole = package.hole_id
    tables = {
        "holes": parquet_rows(package, "catalog/holes.parquet"),
        "datasets": parquet_rows(package, "catalog/datasets.parquet"),
        "samples": parquet_rows(package, f"holes/{hole}/sample_axis.parquet"),
        "assets": parquet_rows(package, "catalog/assets.parquet"),
        "trays": parquet_rows(package, f"holes/{hole}/core/trays.parquet"),
        "sections": parquet_rows(package, f"holes/{hole}/core/sections.parquet"),
        "section_images": parquet_rows(
            package, f"holes/{hole}/core/section_images.parquet"
        ),
        "availability": parquet_rows(package, "catalog/availability.parquet"),
        "scalar_series": parquet_rows(package, "catalog/scalar_series.parquet"),
        "spectral_axes": parquet_rows(package, "catalog/spectral_axes.parquet"),
        "spectral_series": parquet_rows(package, "catalog/spectral_series.parquet"),
    }
    try:
        tables["section_minerals"] = derive_section_minerals(
            package.root, tables["sections"], tables["scalar_series"]
        )
    except Exception as exc:
        raise ReleaseError(f"Cannot derive section minerals: {exc}") from exc
    return tables


def expected_counts(package: ReleasePackage) -> dict[str, int]:
    counts = package.manifest.get("counts") or {}
    return {
        "holes": int(counts["hole_count"]),
        "datasets": int(counts["dataset_count"]),
        "samples": int(counts["sample_count"]),
        "assets": int(counts["asset_catalog_rows"]),
        "trays": int(counts["tray_count"]),
        "sections": int(counts["section_count"]),
        "section_images": int(counts["section_image_mapping_rows"]),
        "availability": int(counts["availability_rows"]),
        "scalar_series": int(counts["scalar_source_series_count"]),
        "spectral_axes": int(counts["spectral_axis_count"]),
        "spectral_series": int(counts["spectral_source_series_count"]),
        "section_minerals": int(counts["section_count"]),
    }


def verify_table_counts(
    cursor: psycopg.Cursor[Any], package: ReleasePackage, expected: dict[str, int]
) -> dict[str, int]:
    actual: dict[str, int] = {}
    for table, wanted in expected.items():
        row = cursor.execute(
            sql.SQL("SELECT count(*) FROM catalog.{} WHERE release_id = %s").format(
                sql.Identifier(table)
            ),
            (package.release_id,),
        ).fetchone()
        assert row is not None
        actual[table] = int(row[0])
        require(actual[table] == wanted, f"Database count mismatch for {table}: {actual[table]} != {wanted}")
    return actual


def insert_release_data(
    cursor: psycopg.Cursor[Any],
    package: ReleasePackage,
    tables: dict[str, list[dict[str, Any]]],
) -> None:
    release_id = package.release_id
    hole_id = package.hole_id
    source_metadata = read_json(package.root / f"holes/{hole_id}/source_metadata.json")

    cursor.execute(
        """
        INSERT INTO catalog.releases (
            release_id, schema_version, source_content_fingerprint,
            source_package_status, release_key, quality_status, created_at,
            manifest, quality_report
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            release_id,
            package.manifest["schema_version"],
            package.manifest["source_content_fingerprint"],
            package.manifest["source_package_status"],
            f"releases/{release_id}",
            package.quality["status"],
            package.manifest["created_at"],
            Jsonb(package.manifest),
            Jsonb(package.quality),
        ),
    )

    for row in tables["holes"]:
        source_x = optional_float(row.get("source_x"))
        source_y = optional_float(row.get("source_y"))
        source_length = optional_text(row.get("source_borehole_length"))
        cursor.execute(
            """
            INSERT INTO catalog.holes (
                release_id, hole_id, source_nvcl_id, source_name,
                source_x, source_y, source_z, collar, source_href,
                source_borehole_length, borehole_length_m,
                source_drilling_method, source_operator,
                source_drill_start_date, drill_start_date, dataset_count,
                source_metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s IS NULL OR %s IS NULL THEN NULL
                     ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326) END,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                release_id,
                row["hole_id"],
                optional_text(row.get("source_nvcl_id")),
                optional_text(row.get("source_name")),
                source_x,
                source_y,
                optional_float(row.get("source_z")),
                source_x,
                source_y,
                source_x,
                source_y,
                optional_text(row.get("source_href")),
                source_length,
                optional_float(source_length),
                optional_text(row.get("source_drilling_method")),
                optional_text(row.get("source_operator")),
                optional_text(row.get("source_drill_start_date")),
                optional_date(row.get("source_drill_start_date")),
                int(row.get("dataset_count") or 0),
                Jsonb(source_metadata.get("borehole") or {}),
            ),
        )

    copy_rows(
        cursor,
        ("catalog", "datasets"),
        (
            "release_id", "dataset_id", "hole_id", "source_dataset_name",
            "source_borehole_uri", "source_tray_log_id", "source_section_log_id",
            "source_domain_log_id", "description_xml", "description_fields",
            "xml_parse_status", "source_xml_datum", "source_xml_latitude",
            "source_xml_longitude", "source_xml_azimuth", "source_xml_inclination",
            "source_metadata",
        ),
        (
            (
                release_id, row["dataset_id"], row["hole_id"],
                optional_text(row.get("source_dataset_name")),
                optional_text(row.get("source_borehole_uri")),
                optional_text(row.get("source_tray_log_id")),
                optional_text(row.get("source_section_log_id")),
                optional_text(row.get("source_domain_log_id")),
                optional_text(row.get("description_xml")),
                Jsonb(json_object(row.get("description_fields_json"))),
                optional_text(row.get("xml_parse_status")),
                optional_text(row.get("source_xml_datum")),
                optional_text(row.get("source_xml_latitude")),
                optional_text(row.get("source_xml_longitude")),
                optional_text(row.get("source_xml_azimuth")),
                optional_text(row.get("source_xml_inclination")),
                Jsonb(row),
            )
            for row in tables["datasets"]
        ),
    )

    copy_rows(
        cursor,
        ("catalog", "samples"),
        ("release_id", "dataset_id", "sample_index", "source_start_depth", "source_end_depth", "depth_from_m", "depth_to_m"),
        (
            (
                release_id, row["dataset_id"], row["sample_index"],
                optional_text(row.get("source_start_depth")),
                optional_text(row.get("source_end_depth")),
                optional_float(row.get("source_start_depth")),
                optional_float(row.get("source_end_depth")),
            )
            for row in tables["samples"]
        ),
    )

    asset_columns = (
        "release_id", "asset_id", "hole_id", "dataset_id", "source_log_id",
        "source_log_name", "asset_kind", "source_status", "source_sample_no",
        "source_depth_from", "source_depth_to", "mapping_precision", "storage_key",
        "nbytes", "sha256", "image_format", "pixel_width", "pixel_height",
        "derived_from_asset_id", "section_index", "tray_index",
        "section_index_within_tray", "image_quality", "depth_direction",
    )
    copy_rows(
        cursor,
        ("catalog", "assets"),
        asset_columns,
        ((release_id, *(row.get(column) for column in asset_columns[1:])) for row in tables["assets"]),
    )

    copy_rows(
        cursor,
        ("catalog", "trays"),
        (
            "release_id", "dataset_id", "tray_index", "source_tray_value",
            "source_range_start", "source_range_end", "sample_index_from",
            "sample_index_to", "range_mapping_status", "sample_axis_start_value",
            "sample_axis_end_value", "depth_from_m", "depth_to_m",
            "thumbnail_asset_id", "image_mapping_precision",
        ),
        (
            (
                release_id, row["dataset_id"], row["tray_index"],
                optional_text(row.get("source_tray_value")),
                optional_text(row.get("source_range_start")),
                optional_text(row.get("source_range_end")),
                row["sample_index_from"], row["sample_index_to"],
                row["range_mapping_status"],
                optional_text(row.get("sample_axis_start_value")),
                optional_text(row.get("sample_axis_end_value")),
                optional_float(row.get("sample_axis_start_value")),
                optional_float(row.get("sample_axis_end_value")),
                optional_text(row.get("thumbnail_asset_id")),
                optional_text(row.get("image_mapping_precision")),
            )
            for row in tables["trays"]
        ),
    )

    copy_rows(
        cursor,
        ("catalog", "sections"),
        (
            "release_id", "dataset_id", "section_index", "source_section_value",
            "tray_index", "section_index_within_tray", "source_range_start",
            "source_range_end", "sample_index_from", "sample_index_to",
            "range_mapping_status", "sample_axis_start_value", "sample_axis_end_value",
            "depth_from_m", "depth_to_m",
        ),
        (
            (
                release_id, row["dataset_id"], row["section_index"],
                optional_text(row.get("source_section_value")), row["tray_index"],
                row["section_index_within_tray"],
                optional_text(row.get("source_range_start")),
                optional_text(row.get("source_range_end")),
                row["sample_index_from"], row["sample_index_to"],
                row["range_mapping_status"],
                optional_text(row.get("sample_axis_start_value")),
                optional_text(row.get("sample_axis_end_value")),
                optional_float(row.get("sample_axis_start_value")),
                optional_float(row.get("sample_axis_end_value")),
            )
            for row in tables["sections"]
        ),
    )

    section_image_columns = (
        "release_id", "hole_id", "dataset_id", "section_index", "section_number",
        "tray_index", "tray_label", "section_index_within_tray", "row_number",
        "sample_index_from", "sample_index_to", "depth_from_m", "depth_to_m",
        "strip_asset_id", "storage_key", "source_thumbnail_asset_id",
        "source_thumbnail_storage_key", "image_status", "image_quality",
        "mapping_precision", "depth_direction", "crop_method", "crop_left_px",
        "crop_top_px", "crop_right_px", "crop_bottom_px", "source_pixel_width",
        "source_pixel_height", "pixel_width", "pixel_height", "nbytes", "sha256", "note",
    )
    copy_rows(
        cursor,
        ("catalog", "section_images"),
        section_image_columns,
        (
            (
                release_id, row["hole_id"], row["dataset_id"], row["section_index"],
                row["section_number"], row["tray_index"], optional_text(row.get("tray_label")),
                row["section_index_within_tray"], row["row"], row["sample_index_from"],
                row["sample_index_to"], row["depth_from_m"], row["depth_to_m"],
                optional_text(row.get("strip_asset_id")), optional_text(row.get("storage_key")),
                optional_text(row.get("source_thumbnail_asset_id")),
                optional_text(row.get("source_thumbnail_storage_key")), row["image_status"],
                optional_text(row.get("image_quality")), optional_text(row.get("mapping_precision")),
                optional_text(row.get("depth_direction")), optional_text(row.get("crop_method")),
                row.get("crop_left_px"), row.get("crop_top_px"), row.get("crop_right_px"),
                row.get("crop_bottom_px"), row.get("source_pixel_width"),
                row.get("source_pixel_height"), row.get("pixel_width"), row.get("pixel_height"),
                row.get("nbytes"), optional_text(row.get("sha256")), row.get("note") or "",
            )
            for row in tables["section_images"]
        ),
    )

    copy_rows(
        cursor,
        ("catalog", "availability"),
        (
            "release_id", "hole_id", "dataset_id", "data_kind", "source_log_id",
            "source_log_name", "source_status", "expected_count", "available_count",
        ),
        (
            (
                release_id, row["hole_id"], row["dataset_id"], row["data_kind"],
                optional_text(row.get("source_log_id")), optional_text(row.get("source_log_name")),
                row["source_status"], row.get("expected_count") or 0,
                row.get("available_count") or 0,
            )
            for row in tables["availability"]
        ),
    )

    scalar_columns = (
        "release_id", "hole_id", "dataset_id", "source_log_id", "source_log_name",
        "source_status", "source_log_type", "source_algorithm_id", "source_mask_log_id",
        "source_file", "source_sha256", "alignment_status", "row_count", "non_empty_count",
        "distinct_non_empty_count", "numeric_parseable", "value_sequence_sha256",
        "physical_column", "is_canonical_physical_column", "physical_storage_key",
        "identical_value_series_count",
    )
    copy_rows(
        cursor,
        ("catalog", "scalar_series"),
        scalar_columns,
        ((release_id, *(row.get(column) for column in scalar_columns[1:])) for row in tables["scalar_series"]),
    )

    copy_rows(
        cursor,
        ("catalog", "spectral_axes"),
        ("release_id", "axis_id", "wavelength_units", "band_count", "values_sha256", "storage_key"),
        (
            (
                release_id, row["axis_id"], optional_text(row.get("wavelength_units")),
                row["band_count"], row["values_sha256"], row["storage_key"],
            )
            for row in tables["spectral_axes"]
        ),
    )

    spectral_columns = (
        "release_id", "series_id", "hole_id", "dataset_id", "source_log_id",
        "source_log_name", "source_status", "sample_count", "band_count", "dtype",
        "byte_order", "axis_id", "axis_storage_key", "sample_alignment_status",
        "values_storage_key", "manifest_storage_key", "nbytes", "sha256",
        "finite_value_count", "nonfinite_value_count", "finite_min", "finite_max",
    )
    copy_rows(
        cursor,
        ("catalog", "spectral_series"),
        spectral_columns,
        ((release_id, *(row.get(column) for column in spectral_columns[1:])) for row in tables["spectral_series"]),
    )


def refresh_derived_data(
    cursor: psycopg.Cursor[Any],
    package: ReleasePackage,
    tables: dict[str, list[dict[str, Any]]],
) -> None:
    for row in tables["datasets"]:
        azimuth, inclination, status = normalise_orientation(
            row.get("source_xml_azimuth"), row.get("source_xml_inclination")
        )
        cursor.execute(
            """
            UPDATE catalog.datasets
            SET azimuth_deg = %s,
                inclination_deg = %s,
                orientation_status = %s
            WHERE release_id = %s AND dataset_id = %s
            """,
            (azimuth, inclination, status, package.release_id, row["dataset_id"]),
        )

    cursor.execute(
        "DELETE FROM catalog.section_minerals WHERE release_id = %s",
        (package.release_id,),
    )
    mineral_columns = (
        "release_id", "hole_id", "dataset_id", "section_index",
        "primary_raw", "primary_fraction", "secondary_raw", "secondary_fraction",
        "display_group", "display_color", "confidence", "quality",
        "classified_sample_count", "total_sample_count", "source_log_name",
        "source_log_id", "source_algorithm_id", "aggregation",
    )
    copy_rows(
        cursor,
        ("catalog", "section_minerals"),
        mineral_columns,
        (
            (
                package.release_id,
                package.hole_id,
                *(row.get(column) for column in mineral_columns[2:]),
            )
            for row in tables["section_minerals"]
        ),
    )


def load_package(connection: psycopg.Connection[Any], package: ReleasePackage) -> dict[str, Any]:
    tables = package_tables(package)
    expected = expected_counts(package)
    for name, wanted in expected.items():
        require(len(tables[name]) == wanted, f"Parquet count mismatch for {name}: {len(tables[name])} != {wanted}")

    with connection.cursor() as cursor:
        run_id = cursor.execute(
            """
            INSERT INTO ops.etl_runs (hole_id, release_id, stage, status, detail)
            VALUES (%s, %s, 'postgres_load', 'running', %s)
            RETURNING run_id
            """,
            (package.hole_id, package.release_id, Jsonb({"release_root": str(package.root)})),
        ).fetchone()[0]
    connection.commit()

    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                existing = cursor.execute(
                    "SELECT source_content_fingerprint FROM catalog.releases WHERE release_id = %s",
                    (package.release_id,),
                ).fetchone()
                if existing is None:
                    insert_release_data(cursor, package, tables)
                    mode = "inserted"
                else:
                    require(
                        existing[0] == package.manifest["source_content_fingerprint"],
                        "Existing release_id has a different content fingerprint",
                    )
                    mode = "already_loaded"

                refresh_derived_data(cursor, package, tables)
                actual = verify_table_counts(cursor, package, expected)
                cursor.execute(
                    """
                    INSERT INTO catalog.current_releases (hole_id, release_id)
                    VALUES (%s, %s)
                    ON CONFLICT (hole_id) DO UPDATE
                    SET release_id = EXCLUDED.release_id, activated_at = now()
                    """,
                    (package.hole_id, package.release_id),
                )
                detail = {"mode": mode, "counts": actual}
                cursor.execute(
                    """
                    UPDATE ops.etl_runs
                    SET status = 'passed', finished_at = now(), detail = %s
                    WHERE run_id = %s
                    """,
                    (Jsonb(detail), run_id),
                )
        return {"run_id": run_id, "release_id": package.release_id, "hole_id": package.hole_id, **detail}
    except Exception as exc:
        connection.rollback()
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ops.etl_runs
                    SET status = 'failed', finished_at = now(), detail = %s
                    WHERE run_id = %s
                    """,
                    (Jsonb({"error": str(exc)}), run_id),
                )
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and load one ETL3 release into PostgreSQL")
    parser.add_argument("release", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--db-host", default=os.getenv("HYLOGGER_DB_HOST", "localhost"))
    parser.add_argument("--db-port", type=int, default=int(os.getenv("HYLOGGER_DB_PORT", "5432")))
    parser.add_argument("--db-name", default=os.getenv("HYLOGGER_DB_NAME", "hylogger"))
    parser.add_argument("--db-user", default=os.getenv("HYLOGGER_DB_USER"))
    parser.add_argument("--set-role", default=os.getenv("HYLOGGER_DB_SET_ROLE"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        package = verify_release(args.release)
        tables = package_tables(package)
        expected = expected_counts(package)
        for name, wanted in expected.items():
            require(len(tables[name]) == wanted, f"Parquet count mismatch for {name}: {len(tables[name])} != {wanted}")
        if args.check_only:
            print(json.dumps({"status": "pass", "release_id": package.release_id, "hole_id": package.hole_id, "counts": expected}, ensure_ascii=False, indent=2))
            return 0

        require(bool(args.db_user), "Set HYLOGGER_DB_USER or pass --db-user")
        password = os.getenv("HYLOGGER_DB_PASSWORD") or os.getenv("PGPASSWORD")
        require(bool(password), "Set HYLOGGER_DB_PASSWORD or PGPASSWORD")
        if args.set_role:
            require(bool(ROLE_RE.fullmatch(args.set_role)), "Invalid --set-role value")

        with psycopg.connect(
            host=args.db_host,
            port=args.db_port,
            dbname=args.db_name,
            user=args.db_user,
            password=password,
        ) as connection:
            if args.set_role:
                with connection.cursor() as cursor:
                    cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(args.set_role)))
                connection.commit()
            result = load_package(connection, package)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"load_release failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
