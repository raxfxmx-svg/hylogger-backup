from __future__ import annotations

from collections import Counter
from math import isfinite
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


SOURCE_LOG_NAME = "Min1 sTSAS"
AGGREGATION = "section_mode_v1"
UNCLASSIFIED_COLOR = "#4a5560"
GROUP_COLORS = {
    "Chlorite": "#2f9e8f",
    "White mica": "#7fb069",
    "Carbonate": "#6a8fd8",
    "Kaolinite": "#c9a227",
    "Other": "#8e7cc3",
}


def _parse_number(value: Any) -> tuple[float | None, bool]:
    if value is None or str(value).strip() == "":
        return None, False
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None, True
    return (number, True) if isfinite(number) else (None, True)


def normalise_orientation(
    source_azimuth: Any, source_inclination: Any
) -> tuple[float | None, float | None, str]:
    azimuth, azimuth_present = _parse_number(source_azimuth)
    inclination, inclination_present = _parse_number(source_inclination)
    if not azimuth_present or not inclination_present:
        return None, None, "missing"
    if azimuth is None or inclination is None:
        return None, None, "invalid"
    if not (0 <= azimuth < 360) or not (-90 <= inclination <= 90):
        return None, None, "invalid"
    if azimuth == 0 and inclination == 0:
        return None, None, "source_zero_placeholder"
    return azimuth, inclination, "reported"


def mineral_display_group(name: str) -> str:
    value = name.casefold()
    if "chlorite" in value:
        return "Chlorite"
    if any(term in value for term in ("muscovite", "phengite", "paragonite", "illite", "white mica", "sericite")):
        return "White mica"
    if any(term in value for term in ("carbonate", "calcite", "dolomite", "ankerite", "siderite", "magnesite")):
        return "Carbonate"
    if "kaolinite" in value:
        return "Kaolinite"
    return "Other"


def _clean_mineral(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"null", "aspectral"}:
        return None
    return text


def _source_for_dataset(
    scalar_series: list[dict[str, Any]], dataset_id: str
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in scalar_series
        if row.get("dataset_id") == dataset_id
        and row.get("source_log_name") == SOURCE_LOG_NAME
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (
            row.get("source_status") != "complete",
            str(row.get("source_algorithm_id") or "") != "108",
            str(row.get("source_log_id") or ""),
        ),
    )[0]


def _unavailable_row(section: dict[str, Any]) -> dict[str, Any]:
    total = int(section["sample_index_to"]) - int(section["sample_index_from"]) + 1
    return {
        "dataset_id": section["dataset_id"],
        "section_index": int(section["section_index"]),
        "primary_raw": None,
        "primary_fraction": None,
        "secondary_raw": None,
        "secondary_fraction": None,
        "display_group": None,
        "display_color": UNCLASSIFIED_COLOR,
        "confidence": 0.0,
        "quality": "source_unavailable",
        "classified_sample_count": 0,
        "total_sample_count": total,
        "source_log_name": None,
        "source_log_id": None,
        "source_algorithm_id": None,
        "aggregation": AGGREGATION,
    }


def derive_section_minerals(
    release_root: Path,
    sections: list[dict[str, Any]],
    scalar_series: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    sections_by_dataset: dict[str, list[dict[str, Any]]] = {}
    for section in sections:
        sections_by_dataset.setdefault(str(section["dataset_id"]), []).append(section)

    for dataset_id, dataset_sections in sections_by_dataset.items():
        source = _source_for_dataset(scalar_series, dataset_id)
        if source is None or source.get("source_status") != "complete":
            results.extend(_unavailable_row(section) for section in dataset_sections)
            continue

        storage_key = str(source.get("physical_storage_key") or "")
        physical_column = str(source.get("physical_column") or "")
        if not storage_key or not physical_column:
            raise ValueError(f"{SOURCE_LOG_NAME} has no physical storage mapping for {dataset_id}")
        table = pq.read_table(
            release_root / storage_key,
            columns=["dataset_id", "sample_index", physical_column],
        )
        value_by_index = {
            int(row["sample_index"]): row[physical_column]
            for row in table.to_pylist()
            if str(row["dataset_id"]) == dataset_id
        }

        for section in dataset_sections:
            start = int(section["sample_index_from"])
            end = int(section["sample_index_to"])
            total = end - start + 1
            counts = Counter(
                mineral
                for index in range(start, end + 1)
                if (mineral := _clean_mineral(value_by_index.get(index))) is not None
            )
            classified = sum(counts.values())
            ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold(), item[0]))
            primary_raw = ranked[0][0] if ranked else None
            primary_count = ranked[0][1] if ranked else 0
            secondary_raw = ranked[1][0] if len(ranked) > 1 else None
            secondary_count = ranked[1][1] if len(ranked) > 1 else 0
            confidence = primary_count / total if total else 0.0
            if not ranked:
                quality = "unclassified"
            elif confidence < 0.5:
                quality = "low_confidence"
            else:
                quality = "ok"
            display_group = mineral_display_group(primary_raw) if primary_raw else None
            display_color = (
                GROUP_COLORS[display_group]
                if display_group is not None and quality == "ok"
                else UNCLASSIFIED_COLOR
            )
            results.append(
                {
                    "dataset_id": dataset_id,
                    "section_index": int(section["section_index"]),
                    "primary_raw": primary_raw,
                    "primary_fraction": primary_count / classified if classified else None,
                    "secondary_raw": secondary_raw,
                    "secondary_fraction": secondary_count / classified if classified and secondary_raw else None,
                    "display_group": display_group,
                    "display_color": display_color,
                    "confidence": confidence,
                    "quality": quality,
                    "classified_sample_count": classified,
                    "total_sample_count": total,
                    "source_log_name": SOURCE_LOG_NAME,
                    "source_log_id": source.get("source_log_id"),
                    "source_algorithm_id": source.get("source_algorithm_id"),
                    "aggregation": AGGREGATION,
                }
            )
    return sorted(results, key=lambda row: (row["dataset_id"], row["section_index"]))
