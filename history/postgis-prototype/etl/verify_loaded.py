from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql


ROLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify an active hole loaded into PostgreSQL")
    parser.add_argument("hole_id")
    parser.add_argument("--data-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--db-host", default=os.getenv("HYLOGGER_DB_HOST", "localhost"))
    parser.add_argument("--db-port", type=int, default=int(os.getenv("HYLOGGER_DB_PORT", "5432")))
    parser.add_argument("--db-name", default=os.getenv("HYLOGGER_DB_NAME", "hylogger"))
    parser.add_argument("--db-user", default=os.getenv("HYLOGGER_DB_USER"))
    parser.add_argument("--set-role", default=os.getenv("HYLOGGER_DB_SET_ROLE"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    password = os.getenv("HYLOGGER_DB_PASSWORD") or os.getenv("PGPASSWORD")
    try:
        require(bool(args.db_user), "Set HYLOGGER_DB_USER or pass --db-user")
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

            with connection.cursor() as cursor:
                hole = cursor.execute(
                    """
                    SELECT release_id, hole_id, source_x, source_y,
                           ST_X(collar), ST_Y(collar), ST_SRID(collar),
                           ST_AsGeoJSON(collar)
                    FROM catalog.holes
                    WHERE (release_id, hole_id) = (
                        SELECT release_id, hole_id
                        FROM catalog.current_releases
                        WHERE hole_id = %s
                    )
                    """,
                    (args.hole_id,),
                ).fetchone()
                require(hole is not None, f"No active release for hole {args.hole_id}")
                release_id = str(hole[0])
                require(hole[6] == 4326, f"Unexpected collar SRID: {hole[6]}")
                require(abs(float(hole[2]) - float(hole[4])) < 1e-12, "Collar longitude differs")
                require(abs(float(hole[3]) - float(hole[5])) < 1e-12, "Collar latitude differs")

                release_root = (args.data_root.resolve() / "releases" / release_id).resolve()
                manifest = json.loads((release_root / "release_manifest.json").read_text(encoding="utf-8"))
                expected = manifest["counts"]
                count_map = {
                    "holes": "hole_count",
                    "datasets": "dataset_count",
                    "samples": "sample_count",
                    "assets": "asset_catalog_rows",
                    "trays": "tray_count",
                    "sections": "section_count",
                    "section_images": "section_image_mapping_rows",
                    "availability": "availability_rows",
                    "scalar_series": "scalar_source_series_count",
                    "spectral_axes": "spectral_axis_count",
                    "spectral_series": "spectral_source_series_count",
                }
                actual: dict[str, int] = {}
                for table, manifest_key in count_map.items():
                    value = cursor.execute(
                        sql.SQL("SELECT count(*) FROM catalog.{} WHERE release_id = %s").format(
                            sql.Identifier(table)
                        ),
                        (release_id,),
                    ).fetchone()[0]
                    actual[table] = int(value)
                    require(actual[table] == int(expected[manifest_key]), f"Count mismatch: {table}")

                mismatch_count = cursor.execute(
                    """
                    SELECT count(*)
                    FROM catalog.section_images si
                    LEFT JOIN catalog.assets a
                      ON a.release_id = si.release_id
                     AND a.asset_id = si.strip_asset_id
                    WHERE si.release_id = %s
                      AND (
                          a.asset_id IS NULL OR
                          a.storage_key IS DISTINCT FROM si.storage_key OR
                          a.sha256 IS DISTINCT FROM si.sha256 OR
                          a.nbytes IS DISTINCT FROM si.nbytes
                      )
                    """,
                    (release_id,),
                ).fetchone()[0]
                require(mismatch_count == 0, f"Section-image asset mismatches: {mismatch_count}")

                images = cursor.execute(
                    """
                    SELECT storage_key, nbytes, sha256
                    FROM catalog.section_images
                    WHERE release_id = %s AND image_status = 'complete'
                    ORDER BY dataset_id, section_index
                    """,
                    (release_id,),
                ).fetchall()

        checked_images = 0
        for storage_key, nbytes, expected_sha in images:
            require(bool(storage_key), "Complete image has no storage_key")
            path = (release_root / storage_key).resolve()
            try:
                path.relative_to(release_root)
            except ValueError as exc:
                raise RuntimeError(f"Image path escapes release root: {storage_key}") from exc
            require(path.is_file(), f"Image file is missing: {storage_key}")
            require(path.stat().st_size == int(nbytes), f"Image size mismatch: {storage_key}")
            require(sha256_file(path) == expected_sha, f"Image SHA-256 mismatch: {storage_key}")
            checked_images += 1

        result: dict[str, Any] = {
            "status": "pass",
            "hole_id": args.hole_id,
            "release_id": release_id,
            "collar": json.loads(hole[7]),
            "counts": actual,
            "verified_section_images": checked_images,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"verify_loaded failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
