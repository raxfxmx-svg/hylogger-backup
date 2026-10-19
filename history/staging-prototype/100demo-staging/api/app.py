from __future__ import annotations

import json
import mimetypes
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import Settings
from .schemas import (
    DatasetSummary,
    HealthResponse,
    HoleDetail,
    HoleFeature,
    HoleFeatureCollection,
    HoleFeatureProperties,
    PageMeta,
    PointGeometry,
    Section,
    SectionImage,
    SectionMineral,
    SectionListResponse,
)


ROLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_pool(settings: Settings) -> ConnectionPool:
    settings.validate()

    def configure(connection: Any) -> None:
        if settings.db_set_role:
            if not ROLE_RE.fullmatch(settings.db_set_role):
                raise RuntimeError("Invalid HYLOGGER_DB_SET_ROLE")
            connection.execute(
                sql.SQL("SET ROLE {}").format(sql.Identifier(settings.db_set_role))
            )
            connection.commit()

    return ConnectionPool(
        conninfo="",
        kwargs={
            "host": settings.db_host,
            "port": settings.db_port,
            "dbname": settings.db_name,
            "user": settings.db_user,
            "password": settings.db_password,
            "row_factory": dict_row,
        },
        min_size=1,
        max_size=5,
        timeout=5,
        configure=configure,
        open=False,
    )


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        parts = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="bbox must contain four numbers") from exc
    if len(parts) != 4:
        raise HTTPException(status_code=422, detail="bbox must be min_lon,min_lat,max_lon,max_lat")
    min_lon, min_lat, max_lon, max_lat = parts
    if not (-180 <= min_lon <= max_lon <= 180 and -90 <= min_lat <= max_lat <= 90):
        raise HTTPException(status_code=422, detail="bbox is outside EPSG:4326 or has reversed bounds")
    return min_lon, min_lat, max_lon, max_lat


def point(value: str | None) -> PointGeometry | None:
    if value is None:
        return None
    geometry = json.loads(value)
    return PointGeometry(type="Point", coordinates=tuple(geometry["coordinates"]))


def image_url(asset_id: str) -> str:
    return f"/api/v1/assets/{quote(asset_id, safe='')}/content"


def section_from_row(row: dict[str, Any]) -> Section:
    image = None
    if row.get("strip_asset_id") and row.get("image_status") == "complete":
        image = SectionImage(
            asset_id=row["strip_asset_id"],
            url=image_url(row["strip_asset_id"]),
            status=row["image_status"],
            quality=row.get("image_quality"),
            pixel_width=row.get("pixel_width"),
            pixel_height=row.get("pixel_height"),
            nbytes=row.get("nbytes"),
            sha256=row.get("sha256"),
        )
    mineral = None
    if row.get("mineral_quality") is not None:
        mineral = SectionMineral(
            primary_raw=row.get("mineral_primary_raw"),
            primary_fraction=row.get("mineral_primary_fraction"),
            secondary_raw=row.get("mineral_secondary_raw"),
            secondary_fraction=row.get("mineral_secondary_fraction"),
            display_group=row.get("mineral_display_group"),
            display_color=row["mineral_display_color"],
            confidence=row["mineral_confidence"],
            quality=row["mineral_quality"],
            classified_sample_count=row["mineral_classified_sample_count"],
            total_sample_count=row["mineral_total_sample_count"],
            source_log_name=row.get("mineral_source_log_name"),
            source_log_id=row.get("mineral_source_log_id"),
            source_algorithm_id=row.get("mineral_source_algorithm_id"),
            aggregation=row["mineral_aggregation"],
        )
    return Section(
        dataset_id=row["dataset_id"],
        section_index=row["section_index"],
        tray_index=row["tray_index"],
        row=row["row_number"],
        sample_index_from=row["sample_index_from"],
        sample_index_to=row["sample_index_to"],
        depth_from_m=row["depth_from_m"],
        depth_to_m=row["depth_to_m"],
        depth_direction=row.get("depth_direction"),
        image=image,
        mineral=mineral,
    )


SECTION_SELECT = """
SELECT s.dataset_id, s.section_index, s.tray_index,
       COALESCE(si.row_number, s.section_index_within_tray + 1) AS row_number,
       s.sample_index_from, s.sample_index_to,
       s.depth_from_m, s.depth_to_m,
       si.strip_asset_id, si.image_status, si.image_quality,
       si.pixel_width, si.pixel_height, si.nbytes, si.sha256,
       si.depth_direction,
       sm.primary_raw AS mineral_primary_raw,
       sm.primary_fraction AS mineral_primary_fraction,
       sm.secondary_raw AS mineral_secondary_raw,
       sm.secondary_fraction AS mineral_secondary_fraction,
       sm.display_group AS mineral_display_group,
       sm.display_color AS mineral_display_color,
       sm.confidence AS mineral_confidence,
       sm.quality AS mineral_quality,
       sm.classified_sample_count AS mineral_classified_sample_count,
       sm.total_sample_count AS mineral_total_sample_count,
       sm.source_log_name AS mineral_source_log_name,
       sm.source_log_id AS mineral_source_log_id,
       sm.source_algorithm_id AS mineral_source_algorithm_id,
       sm.aggregation AS mineral_aggregation
FROM api.current_sections s
LEFT JOIN api.current_section_images si
  ON si.release_id = s.release_id
 AND si.dataset_id = s.dataset_id
 AND si.section_index = s.section_index
LEFT JOIN api.current_section_minerals sm
  ON sm.release_id = s.release_id
 AND sm.dataset_id = s.dataset_id
 AND sm.section_index = s.section_index
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool = build_pool(active_settings)
        pool.open(wait=True, timeout=10)
        app.state.pool = pool
        app.state.settings = active_settings
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(
        title="HyLogger demo2 read-only API",
        version="1.1.0",
        description="PostgreSQL/PostGIS read-only API for boreholes and core section images.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        with request.app.state.pool.connection() as connection:
            row = connection.execute(
                """
                SELECT current_database() AS database,
                       postgis_version() AS postgis_version,
                       (SELECT count(*) FROM api.current_holes) AS hole_count,
                       (SELECT count(*) FROM api.current_sections) AS section_count,
                       (SELECT count(*) FROM api.current_section_images) AS section_image_count
                """
            ).fetchone()
        return HealthResponse(status="ok", **row)

    @app.get("/api/v1/holes", response_model=HoleFeatureCollection)
    def holes(
        request: Request,
        bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> HoleFeatureCollection:
        bounds = parse_bbox(bbox)
        where = "WHERE collar IS NOT NULL"
        params: list[Any] = []
        if bounds:
            where += " AND ST_Intersects(collar, ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
            params.extend(bounds)
        with request.app.state.pool.connection() as connection:
            total = connection.execute(
                f"SELECT count(*) AS count FROM api.current_holes {where}",
                params,
            ).fetchone()["count"]
            rows = connection.execute(
                f"""
                SELECT hole_id, release_id, source_name, borehole_length_m,
                       source_operator, drill_start_date, ST_AsGeoJSON(collar) AS geometry
                FROM api.current_holes
                {where}
                ORDER BY hole_id
                LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            ).fetchall()
        features = [
            HoleFeature(
                id=row["hole_id"],
                geometry=point(row["geometry"]),
                properties=HoleFeatureProperties(
                    hole_id=row["hole_id"],
                    release_id=row["release_id"],
                    name=row["source_name"],
                    borehole_length_m=row["borehole_length_m"],
                    operator=row["source_operator"],
                    drill_start_date=row["drill_start_date"],
                ),
            )
            for row in rows
        ]
        return HoleFeatureCollection(features=features, meta=PageMeta(total=total, limit=limit, offset=offset))

    @app.get("/api/v1/holes/{hole_id}", response_model=HoleDetail)
    def hole_detail(request: Request, hole_id: str = ApiPath(pattern=r"^[A-Za-z0-9_-]+$")) -> HoleDetail:
        with request.app.state.pool.connection() as connection:
            hole = connection.execute(
                """
                SELECT hole_id, release_id, source_name, borehole_length_m,
                       source_drilling_method, source_operator, drill_start_date,
                       ST_AsGeoJSON(collar) AS location
                FROM api.current_holes
                WHERE hole_id = %s
                """,
                (hole_id,),
            ).fetchone()
            if hole is None:
                raise HTTPException(status_code=404, detail=f"unknown hole: {hole_id}")
            datasets = connection.execute(
                """
                SELECT d.dataset_id, d.source_dataset_name,
                       d.azimuth_deg, d.inclination_deg, d.orientation_status,
                       min(s.depth_from_m) AS depth_from_m,
                       max(s.depth_to_m) AS depth_to_m,
                       count(DISTINCT t.tray_index) AS tray_count,
                       count(DISTINCT s.section_index) AS section_count,
                       count(DISTINCT si.section_index) FILTER (WHERE si.image_status = 'complete') AS section_image_count
                FROM api.current_datasets d
                LEFT JOIN api.current_trays t
                  ON t.release_id = d.release_id AND t.dataset_id = d.dataset_id
                LEFT JOIN api.current_sections s
                  ON s.release_id = d.release_id AND s.dataset_id = d.dataset_id
                LEFT JOIN api.current_section_images si
                  ON si.release_id = d.release_id AND si.dataset_id = d.dataset_id
                 AND si.section_index = s.section_index
                WHERE d.hole_id = %s
                GROUP BY d.dataset_id, d.source_dataset_name,
                         d.azimuth_deg, d.inclination_deg, d.orientation_status
                ORDER BY d.dataset_id
                """,
                (hole_id,),
            ).fetchall()
        summaries = [
            DatasetSummary(
                dataset_id=row["dataset_id"],
                name=row["source_dataset_name"],
                depth_from_m=row["depth_from_m"],
                depth_to_m=row["depth_to_m"],
                tray_count=row["tray_count"],
                section_count=row["section_count"],
                section_image_count=row["section_image_count"],
            )
            for row in datasets
        ]
        valid_orientations = {
            (float(row["azimuth_deg"]), float(row["inclination_deg"]))
            for row in datasets
            if row["orientation_status"] == "reported"
            and row["azimuth_deg"] is not None
            and row["inclination_deg"] is not None
        }
        if len(valid_orientations) > 1:
            azimuth_deg = None
            inclination_deg = None
            orientation_status = "conflicting"
        elif len(valid_orientations) == 1:
            azimuth_deg, inclination_deg = next(iter(valid_orientations))
            orientation_status = "reported"
        else:
            azimuth_deg = None
            inclination_deg = None
            absence_statuses = {row["orientation_status"] for row in datasets}
            orientation_status = next(
                (
                    status
                    for status in ("invalid", "source_zero_placeholder", "missing")
                    if status in absence_statuses
                ),
                "missing",
            )
        return HoleDetail(
            hole_id=hole["hole_id"],
            release_id=hole["release_id"],
            name=hole["source_name"],
            borehole_length_m=hole["borehole_length_m"],
            drilling_method=hole["source_drilling_method"],
            operator=hole["source_operator"],
            drill_start_date=hole["drill_start_date"],
            location=point(hole["location"]),
            azimuth_deg=azimuth_deg,
            inclination_deg=inclination_deg,
            orientation_status=orientation_status,
            datasets=summaries,
        )

    @app.get("/api/v1/datasets/{dataset_id}/sections", response_model=SectionListResponse)
    def sections(request: Request, dataset_id: str) -> SectionListResponse:
        with request.app.state.pool.connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM api.current_datasets WHERE dataset_id = %s",
                (dataset_id,),
            ).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail=f"unknown active dataset: {dataset_id}")
            rows = connection.execute(
                SECTION_SELECT + " WHERE s.dataset_id = %s ORDER BY s.section_index",
                (dataset_id,),
            ).fetchall()
        result = [section_from_row(row) for row in rows]
        return SectionListResponse(dataset_id=dataset_id, count=len(result), sections=result)

    @app.get("/api/v1/datasets/{dataset_id}/sections/{section_index}", response_model=Section)
    def section_detail(request: Request, dataset_id: str, section_index: int = ApiPath(ge=0)) -> Section:
        with request.app.state.pool.connection() as connection:
            row = connection.execute(
                SECTION_SELECT + " WHERE s.dataset_id = %s AND s.section_index = %s",
                (dataset_id, section_index),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="unknown active section")
        return section_from_row(row)

    @app.get("/api/v1/assets/{asset_id}/content", response_class=FileResponse)
    def asset_content(request: Request, asset_id: str) -> FileResponse:
        with request.app.state.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT release_id, storage_key, nbytes, sha256, image_format, source_status
                FROM api.current_assets
                WHERE asset_id = %s
                ORDER BY release_id
                LIMIT 2
                """,
                (asset_id,),
            ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"unknown active asset: {asset_id}")
        if len(rows) > 1:
            raise HTTPException(status_code=409, detail=f"ambiguous active asset: {asset_id}")
        asset = rows[0]
        if asset["source_status"] != "complete" or not asset["storage_key"]:
            raise HTTPException(status_code=404, detail=f"asset content unavailable: {asset_id}")

        settings: Settings = request.app.state.settings
        release_root = (settings.data_root / "releases" / asset["release_id"]).resolve()
        file_path = (release_root / asset["storage_key"]).resolve()
        try:
            file_path.relative_to(release_root)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="registered asset path escapes release root") from exc
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="registered asset file is missing")
        if asset["nbytes"] is not None and file_path.stat().st_size != asset["nbytes"]:
            raise HTTPException(status_code=500, detail="registered asset size differs from file")

        media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if str(asset["image_format"] or "").upper() in {"JPEG", "JPG"}:
            media_type = "image/jpeg"
        headers = {
            "Cache-Control": "public, max-age=86400, immutable",
            "X-Content-Type-Options": "nosniff",
        }
        if asset["sha256"]:
            headers["ETag"] = f'"{asset["sha256"]}"'
        return FileResponse(file_path, media_type=media_type, headers=headers)

    return app


app = create_app()
