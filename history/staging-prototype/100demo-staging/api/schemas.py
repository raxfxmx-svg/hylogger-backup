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
    azimuth_deg: float | None
    inclination_deg: float | None
    orientation_status: Literal[
        "reported", "source_zero_placeholder", "missing", "invalid", "conflicting"
    ]
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


class SectionMineral(BaseModel):
    primary_raw: str | None
    primary_fraction: float | None
    secondary_raw: str | None
    secondary_fraction: float | None
    display_group: str | None
    display_color: str
    confidence: float
    quality: Literal["ok", "low_confidence", "unclassified", "source_unavailable"]
    classified_sample_count: int
    total_sample_count: int
    source_log_name: str | None
    source_log_id: str | None
    source_algorithm_id: str | None
    aggregation: Literal["section_mode_v1"]


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
    mineral: SectionMineral | None


class SectionListResponse(BaseModel):
    dataset_id: str
    count: int
    sections: list[Section]


class ErrorResponse(BaseModel):
    detail: str | list[dict[str, Any]] = Field(description="Human-readable error detail")
