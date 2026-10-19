from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from api.app import app


DATASET_ID = "8a294cfc-68df-4f03-995b-c5fd0d47ab0"


def test_health_and_read_only_openapi() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["hole_count"] >= 1
        assert response.json()["section_count"] >= 198
        assert response.json()["section_image_count"] >= 198
        methods = {
            method
            for path in client.get("/openapi.json").json()["paths"].values()
            for method in path
        }
        assert methods == {"get"}


def test_holes_geojson_and_bbox() -> None:
    with TestClient(app) as client:
        data = client.get("/api/v1/holes").json()
        assert data["type"] == "FeatureCollection"
        assert data["meta"]["total"] >= 1
        assert data["features"][0]["id"] == "05GJD001"
        assert data["features"][0]["geometry"]["coordinates"] == [118.96361011, -33.72188606]
        assert client.get("/api/v1/holes", params={"bbox": "118,-34,120,-33"}).json()["meta"]["total"] >= 1
        assert client.get("/api/v1/holes", params={"bbox": "0,0,1,1"}).json()["meta"]["total"] == 0
        assert client.get("/api/v1/holes", params={"bbox": "bad"}).status_code == 422


def test_hole_sections_and_image() -> None:
    with TestClient(app) as client:
        hole = client.get("/api/v1/holes/05GJD001")
        assert hole.status_code == 200
        hole_data = hole.json()
        assert hole_data["azimuth_deg"] == 90.0
        assert hole_data["inclination_deg"] == -60.0
        assert hole_data["orientation_status"] == "reported"
        placeholder = client.get("/api/v1/holes/05KCD001").json()
        assert placeholder["azimuth_deg"] is None
        assert placeholder["inclination_deg"] is None
        assert placeholder["orientation_status"] == "source_zero_placeholder"

        dataset = hole_data["datasets"][0]
        assert dataset["tray_count"] == 33
        assert dataset["section_count"] == 198
        assert dataset["section_image_count"] == 198

        sections = client.get(f"/api/v1/datasets/{DATASET_ID}/sections")
        assert sections.status_code == 200
        assert sections.json()["count"] == 198
        first = sections.json()["sections"][0]
        assert first["depth_from_m"] == 150.0
        assert first["image"]["quality"] == "thumbnail_derived"
        assert first["mineral"]["aggregation"] == "section_mode_v1"
        assert first["mineral"]["total_sample_count"] > 0
        assert first["mineral"]["display_color"].startswith("#")

        detail = client.get(f"/api/v1/datasets/{DATASET_ID}/sections/0")
        assert detail.status_code == 200
        image = client.get(detail.json()["image"]["url"])
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/jpeg"
        assert hashlib.sha256(image.content).hexdigest() == first["image"]["sha256"]
        assert image.headers["etag"].strip('"') == first["image"]["sha256"]


def test_not_found_cases() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/holes/UNKNOWN").status_code == 404
        assert client.get("/api/v1/datasets/UNKNOWN/sections").status_code == 404
        assert client.get(f"/api/v1/datasets/{DATASET_ID}/sections/9999").status_code == 404
        assert client.get("/api/v1/assets/UNKNOWN/content").status_code == 404
