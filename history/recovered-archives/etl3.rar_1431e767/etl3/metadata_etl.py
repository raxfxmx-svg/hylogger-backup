from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from common import ETLError, read_json, write_json


def parse_dataset_description(description: str) -> dict[str, str]:
    if not description:
        return {}
    try:
        root = ElementTree.fromstring(description)
    except ElementTree.ParseError:
        return {"_parse_status": "invalid_xml"}
    result: dict[str, str] = {"_parse_status": "parsed"}
    for child in root:
        tag = child.tag.split("}")[-1]
        result[tag] = child.text or ""
    return result


def build_metadata_catalogs(
    raw_dir: Path,
    hole_id: str,
    release_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    borehole = read_json(raw_dir / "borehole.json")
    datasets = read_json(raw_dir / "datasets.json")
    if not isinstance(datasets, list) or not datasets:
        raise ETLError("datasets.json does not contain a non-empty list")

    hole_rows = [
        {
            "hole_id": hole_id,
            "source_nvcl_id": str(borehole.get("nvcl_id") or ""),
            "source_name": str(borehole.get("name") or ""),
            "source_x": borehole.get("x"),
            "source_y": borehole.get("y"),
            "source_z": borehole.get("z"),
            "source_href": str(borehole.get("href") or ""),
            "source_borehole_length": str(borehole.get("boreholeLength_m") or ""),
            "source_drilling_method": str(borehole.get("drillingMethod") or ""),
            "source_operator": str(borehole.get("operator") or ""),
            "source_drill_start_date": str(borehole.get("drillStartDate") or ""),
            "dataset_count": len(datasets),
        }
    ]

    dataset_rows: list[dict[str, Any]] = []
    source_metadata: dict[str, Any] = {"borehole": borehole, "datasets": []}
    for dataset in datasets:
        description = str(dataset.get("description") or "")
        fields = parse_dataset_description(description)
        dataset_id = str(dataset.get("dataset_id") or "")
        dataset_rows.append(
            {
                "dataset_id": dataset_id,
                "hole_id": hole_id,
                "source_dataset_name": str(dataset.get("dataset_name") or ""),
                "source_borehole_uri": str(dataset.get("borehole_uri") or ""),
                "source_tray_log_id": str(dataset.get("tray_id") or ""),
                "source_section_log_id": str(dataset.get("section_id") or ""),
                "source_domain_log_id": str(dataset.get("domain_id") or ""),
                "description_xml": description,
                "description_fields_json": json.dumps(fields, ensure_ascii=False, sort_keys=True),
                "xml_parse_status": fields.get("_parse_status", "not_present"),
                "source_xml_datum": fields.get("Datum", ""),
                "source_xml_latitude": fields.get("Latitude", ""),
                "source_xml_longitude": fields.get("Longitude", ""),
                "source_xml_azimuth": fields.get("Azimuth", ""),
                "source_xml_inclination": fields.get("Inclination", ""),
                "trajectory_availability": "collar_orientation_only_no_downhole_survey",
            }
        )
        source_metadata["datasets"].append(
            {"source": dataset, "description_fields": fields}
        )

    write_json(
        release_root / "holes" / hole_id / "source_metadata.json", source_metadata
    )
    return hole_rows, dataset_rows, datasets
