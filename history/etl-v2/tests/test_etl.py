from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import rebuild_holes_csv, transform_hole  # noqa: E402


class CsvEtlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name) / "data"
        self.raw = self.data / "raw"

    def tearDown(self):
        self.temp.cleanup()

    def make_package(self) -> Path:
        folder = self.raw / "GOOD"
        (folder / "scalars").mkdir(parents=True)
        files = {
            "borehole.json": {"name": "GOOD", "x": 120, "y": -30},
            "datasets.json": [],
            "logs_scalar.json": [
                {"log_id": "log-1", "log_name": "Albedo"},
                {"log_id": "log-2", "log_name": "Albedo duplicate"},
                {"log_id": "log-3", "log_name": "Empty"},
            ],
            "logs_spectral.json": [],
            "spectral_manifest.json": [],
            "logs_profilometer.json": [],
            "profilometer_manifest.json": [],
            "images_manifest.json": {"logs": [], "files": []},
        }
        for name, value in files.items():
            (folder / name).write_text(json.dumps(value), encoding="utf-8")
        content = "StartDepth,EndDepth,Value\n0,1,2.5\n1,2,3.5\n"
        (folder / "scalars" / "log-1_Albedo.csv").write_text(content, encoding="utf-8")
        (folder / "scalars" / "log-2_Albedo_duplicate.csv").write_text(content, encoding="utf-8")
        (folder / "scalars" / "log-3_Empty.csv").write_text(
            "StartDepth,EndDepth,Value\n0,1,null\n1,2,null\n", encoding="utf-8"
        )
        return folder

    def test_creates_only_readable_csv_tables(self):
        self.make_package()
        summary = transform_hole(self.data, self.raw, "GOOD")
        rebuild_holes_csv(self.data)
        self.assertEqual(summary["measurement_columns"], 1)
        expected = [
            self.data / "csv" / "holes.csv",
            self.data / "csv" / "measurements" / "GOOD.csv",
            self.data / "csv" / "core_intervals" / "GOOD.csv",
            self.data / "csv" / "signals" / "GOOD.csv",
            self.data / "csv" / "assets" / "GOOD.csv",
        ]
        self.assertTrue(all(path.is_file() for path in expected))
        self.assertFalse(any(self.data.rglob("*.sqlite")))
        with expected[1].open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], ["hole_id", "sample_no", "depth_from_m", "depth_to_m", "Albedo"])
        self.assertEqual(len(rows), 3)

    def test_failed_rebuild_keeps_previous_csv(self):
        folder = self.make_package()
        transform_hole(self.data, self.raw, "GOOD")
        output = self.data / "csv" / "measurements" / "GOOD.csv"
        previous = output.read_bytes()
        (folder / "scalars" / "log-1_Albedo.csv").write_text("bad,header\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            transform_hole(self.data, self.raw, "GOOD")
        self.assertEqual(output.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
