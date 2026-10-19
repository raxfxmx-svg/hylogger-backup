from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: str
    postgis_version: str
    hole_count: int
    section_count: int
    section_image_count: int


class HoleFeatureProperties(BaseModel):
    hole_id: str
    release_id: str
    name: str | None
    borehole_length_m: float | None
    operator: str | None
    drill_start_date: date | None


class HoleFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: PointGeometry
    properties: HoleFeatureProperties


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class HoleFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[HoleFeature]
    meta: PageMeta


class DatasetSummary(BaseModel):
    dataset_id: str
    name: str | None
    depth_from_m: float | None
    depth_to_m: float | None
    tray_count: int
    section_count: int
    section_image_count: int


class HoleDetail(BaseModel):
    hole_id: str
    release_id: str
    name: str | None
    borehole_length_m: float | None
    drilling_method: str | None
    operator: str | None
    drill_start_date: date | None
    location: PointGeometry | None
    datasets: list[DatasetSummary]


class SectionImage(BaseModel):
    asset_id: str
    url: str
    status: str
    quality: str | None
    pixel_width: int | None
    pixel_height: int | None
    nbytes: int | None
    sha256: str | None


class Section(BaseModel):
    dataset_id: str
    section_index: int
    tray_index: int
    row: int
    sample_index_from: int
    sample_index_to: int
    depth_from_m: float
    depth_to_m: float
    depth_direction: str | None
    image: SectionImage | None


class SectionListResponse(BaseModel):
    dataset_id: str
    count: int
    sections: list[Section]


class ErrorResponse(BaseModel):
    detail: str | list[dict[str, Any]] = Field(description="Human-readable error detail")
