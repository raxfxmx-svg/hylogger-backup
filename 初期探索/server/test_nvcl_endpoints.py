"""Smoke test for the NVCL endpoints in server.app.

Builds a temporary data/ layout (index.sqlite + per-hole hole.sqlite files
containing the nvcl-kit ETL tables), points server.app at it, and exercises
the three /api/holes/{hole_id}/nvcl/* routes with FastAPI's TestClient.

Run from the hylogger-visualisation/ directory:

    .venv/Scripts/python server/test_nvcl_endpoints.py
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

import server.app as server_app

HOLE_ID = "TESTHOLE1"
HOLE_NO_TABLES = "TESTHOLE2"  # hole.sqlite exists but has no NVCL tables
HOLE_NO_DB = "TESTHOLE3"      # listed in index.sqlite but hole.sqlite missing

NVCL_SCHEMA = """
CREATE TABLE borehole_meta (
  nvcl_id TEXT PRIMARY KEY, name TEXT, lon REAL, lat REAL, z REAL,
  boreholeLength_m REAL, elevation_m REAL,
  drillStartDate TEXT, drillEndDate TEXT, operator TEXT, driller TEXT,
  tenement TEXT, project TEXT, purpose TEXT, status TEXT,
  drillingMethod TEXT, inclinationType TEXT, identifier TEXT,
  href TEXT, description TEXT, raw_json TEXT
);
CREATE TABLE nvcl_datasets (
  dataset_id TEXT PRIMARY KEY, dataset_name TEXT, borehole_uri TEXT,
  tray_id TEXT, section_id TEXT, domain_id TEXT,
  created_date TEXT, modified_date TEXT
);
CREATE TABLE nvcl_logs (
  log_id TEXT PRIMARY KEY, dataset_id TEXT, log_name TEXT, log_type TEXT,
  algorithm_id TEXT, kind TEXT, sample_count INTEGER
);
CREATE TABLE nvcl_scalar_data (
  id INTEGER PRIMARY KEY, log_id TEXT, depth REAL,
  scalar_name TEXT, value_text TEXT, value_num REAL
);
CREATE TABLE nvcl_tray_depths (
  id INTEGER PRIMARY KEY, log_id TEXT, sample_no TEXT,
  depth_from REAL, depth_to REAL
);
CREATE TABLE nvcl_images (
  file TEXT PRIMARY KEY, log_id TEXT, kind TEXT, sample_no TEXT,
  depth_from REAL, depth_to REAL, nbytes INTEGER
);
"""


def _make_index_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE holes (hole_id TEXT PRIMARY KEY, depth_from REAL,"
        " depth_to REAL, n_trays INTEGER, n_samples INTEGER, sensors TEXT,"
        " raw_dir TEXT, ingested_at TEXT)"
    )
    for hole_id in (HOLE_ID, HOLE_NO_TABLES, HOLE_NO_DB):
        conn.execute(
            "INSERT INTO holes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (hole_id, 0.0, 100.0, 10, 1000, '["vnir"]', "/tmp/raw", "2026-01-01"),
        )
    conn.commit()
    conn.close()


def _make_hole_db_with_nvcl(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(NVCL_SCHEMA)
    conn.execute(
        "INSERT INTO borehole_meta (nvcl_id, name, lon, lat, z,"
        " boreholeLength_m, elevation_m, drillStartDate, drillEndDate,"
        " operator, driller, tenement, project, purpose, status,"
        " drillingMethod, inclinationType, identifier, href, description,"
        " raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "NVCL-001", "Test Hole 1", 138.6, -32.9, 50.0,
            250.5, 48.2, "2020-01-10", "2020-02-01",
            "GSSA", "Drill Co", "EL1234", "TestProj", "Exploration",
            "completed", "diamond", "vertical", "ID-42",
            "https://example.org/nvcl/NVCL-001", "a test hole", "{}",
        ),
    )
    conn.executemany(
        "INSERT INTO nvcl_datasets VALUES (?,?,?,?,?,?,?,?)",
        [
            ("DS-1", "Dataset One", "uri://borehole/1", "T1", "S1", "D1",
             "2024-01-01", "2024-01-02"),
            ("DS-2", "Dataset Two", "uri://borehole/1", "T2", "S1", "D1",
             "2024-02-01", "2024-02-02"),
        ],
    )
    conn.executemany(
        "INSERT INTO nvcl_logs VALUES (?,?,?,?,?,?,?)",
        [
            ("LOG-1", "DS-1", "MagSus", "scalar", "ALG-1", "downhole", 4),
            ("LOG-2", "DS-2", "Grayscale", "scalar", "ALG-2", "downhole", 2),
        ],
    )
    conn.executemany(
        "INSERT INTO nvcl_scalar_data (log_id, depth, scalar_name, value_text,"
        " value_num) VALUES (?,?,?,?,?)",
        [
            ("LOG-1", 1.0, "MagSus", "0.5", 0.5),
            ("LOG-1", 2.0, "MagSus", "0.6", 0.6),
            ("LOG-1", 3.0, "MagSus", "0.7", 0.7),
            ("LOG-1", 4.0, "MagSus", "0.8", 0.8),
            ("LOG-2", 1.5, "Grayscale", "120", 120.0),
            ("LOG-2", 2.5, "Grayscale", "130", 130.0),
        ],
    )
    conn.commit()
    conn.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data"
        hole_dir = data_dir / "holes" / HOLE_ID
        hole_dir.mkdir(parents=True)
        (data_dir / "holes" / HOLE_NO_TABLES).mkdir(parents=True)
        _make_index_db(data_dir / "index.sqlite")
        _make_hole_db_with_nvcl(hole_dir / "hole.sqlite")
        # hole.sqlite without any NVCL tables
        sqlite3.connect(
            data_dir / "holes" / HOLE_NO_TABLES / "hole.sqlite"
        ).close()

        server_app.DATA_DIR = data_dir
        server_app.INDEX_DB = data_dir / "index.sqlite"
        client = TestClient(server_app.app)

        # --- meta ---
        r = client.get(f"/api/holes/{HOLE_ID}/nvcl/meta")
        assert r.status_code == 200, r.text
        meta = r.json()
        assert meta["nvcl_id"] == "NVCL-001", meta
        assert meta["name"] == "Test Hole 1", meta
        assert meta["lon"] == 138.6 and meta["lat"] == -32.9, meta
        assert meta["boreholeLength_m"] == 250.5, meta

        # --- logs ---
        r = client.get(f"/api/holes/{HOLE_ID}/nvcl/logs")
        assert r.status_code == 200, r.text
        payload = r.json()
        assert [d["dataset_id"] for d in payload["datasets"]] == ["DS-1", "DS-2"]
        assert [l["log_id"] for l in payload["logs"]] == ["LOG-1", "LOG-2"]
        assert payload["logs"][0]["log_name"] == "MagSus"
        assert payload["logs"][0]["sample_count"] == 4

        # --- scalars ---
        r = client.get(f"/api/holes/{HOLE_ID}/nvcl/scalars", params={"log_id": "LOG-1"})
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 4, rows
        assert all(row["log_id"] == "LOG-1" for row in rows)
        assert [row["depth"] for row in rows] == [1.0, 2.0, 3.0, 4.0]
        assert rows[0]["scalar_name"] == "MagSus" and rows[0]["value_num"] == 0.5

        # depth range filter (inclusive)
        r = client.get(
            f"/api/holes/{HOLE_ID}/nvcl/scalars",
            params={"log_id": "LOG-1", "depth_from": 2.0, "depth_to": 3.0},
        )
        assert r.status_code == 200, r.text
        assert [row["depth"] for row in r.json()] == [2.0, 3.0]

        # limit honoured
        r = client.get(
            f"/api/holes/{HOLE_ID}/nvcl/scalars",
            params={"log_id": "LOG-1", "limit": 2},
        )
        assert r.status_code == 200, r.text
        assert len(r.json()) == 2

        # limit above the 50000 cap is rejected
        r = client.get(
            f"/api/holes/{HOLE_ID}/nvcl/scalars",
            params={"log_id": "LOG-1", "limit": 50001},
        )
        assert r.status_code == 422, r.status_code

        # missing required log_id -> 422
        r = client.get(f"/api/holes/{HOLE_ID}/nvcl/scalars")
        assert r.status_code == 422, r.status_code

        # --- 404 cases ---
        for hole in (HOLE_NO_TABLES, HOLE_NO_DB, "NO_SUCH_HOLE"):
            for suffix in ("nvcl/meta", "nvcl/logs"):
                r = client.get(f"/api/holes/{hole}/{suffix}")
                assert r.status_code == 404, (hole, suffix, r.status_code, r.text)
            r = client.get(
                f"/api/holes/{hole}/nvcl/scalars", params={"log_id": "LOG-1"}
            )
            assert r.status_code == 404, (hole, r.status_code, r.text)
        r = client.get(f"/api/holes/{HOLE_NO_TABLES}/nvcl/meta")
        assert "no NVCL data" in r.json()["detail"], r.text

    print("ALL NVCL ENDPOINT TESTS PASSED")


if __name__ == "__main__":
    main()
