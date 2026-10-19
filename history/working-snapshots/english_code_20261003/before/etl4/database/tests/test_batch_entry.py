"""Test batch lists, short report names, independent rule versions, and recovery after interruption."""

import argparse
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent), str(DATABASE.parent / "processing")]

from _settings import SOURCE_ROOT, add_hole_arguments, batch_label, selected_holes, settings
from _legacy_verification import profile_window
import pyarrow as pa
import pyarrow.parquet as pq

preflight = importlib.import_module("7_preflight_database")
media_import = importlib.import_module("28_import_media_revision")
raw_check = importlib.import_module("0_check_raw")


class BatchEntryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=SOURCE_ROOT, prefix="batch_test_")
        self.folder = Path(self.temporary.name)
        self.previous_work = settings.work_dir
        settings.work_dir = self.folder

    def tearDown(self):
        settings.work_dir = self.previous_work
        self.temporary.cleanup()

    def test_long_batch_has_short_order_independent_report_name(self):
        holes = [f"HOLE{i:04}" for i in range(1000)]
        self.assertLess(len(batch_label(holes)), 40)
        self.assertEqual(batch_label(holes), batch_label(holes[::-1]))
        self.assertNotEqual(batch_label(holes), batch_label(holes[:-1]))

    def test_incomplete_precheck_cannot_supply_a_list(self):
        path = self.folder / "single_holes.txt"
        path.write_text("ONE\nTWO\n", encoding="utf-8")
        report = {"run_id": "run", "groups": {"single": ["ONE", "TWO"]}}
        (self.folder / "0_raw_check.json").write_text(json.dumps(report), encoding="utf-8")
        status = self.folder / "0_status.json"
        parser = argparse.ArgumentParser()
        add_hole_arguments(parser)
        args = parser.parse_args(["--holes-file", str(path)])
        status.write_text('{"status":"running","run_id":"run"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            selected_holes(args)
        status.write_text('{"status":"complete","run_id":"run"}', encoding="utf-8")
        self.assertEqual(selected_holes(args), ["ONE", "TWO"])
        path.write_text("ONE\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            selected_holes(args)

    def test_unknown_dataset_count_is_not_zero(self):
        hole = self.folder / "EMPTY"
        hole.mkdir()
        result = raw_check.check_hole(hole)
        self.assertIsNone(result["dataset_count"])
        self.assertEqual(result["route"], "attention")

    def test_failed_report_write_does_not_mark_precheck_complete(self):
        status = self.folder / "0_status.json"
        status.write_text('{"status":"running","run_id":"run"}', encoding="utf-8")
        holes = [{"hole_id": "ONE", "dataset_count": 1, "route": "single", "datasets": [], "categories": {}, "errors": [], "warnings": []}]
        original_write = raw_check.write_text

        def interrupted_write(path, text):
            if path.suffix == ".md":
                raise OSError("disk full")
            original_write(path, text)

        with patch.object(raw_check, "write_text", side_effect=interrupted_write):
            with self.assertRaises(OSError):
                raw_check.write_reports(self.folder, self.folder, holes, 0, "run")
        self.assertEqual(json.loads(status.read_text())["status"], "running")
        self.assertEqual((self.folder / "single_holes.txt").read_text(), "ONE\n")
        args = argparse.Namespace(holes=None, holes_file=self.folder / "single_holes.txt")
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            selected_holes(args)

    def test_separate_dataset_rule_version_survives_input_registration(self):
        summary = {
            "pipeline_id": "default-rule", "active_holes": ["ONE"], "totals": {},
            "holes": [{"hole_id": "ONE", "directory": "ONE/input/rules", "pipeline_id": "custom-rule", "report_sha256": {}}],
        }
        documents = {
            "latest_verified.json": {"summary_json": "summary.json", "summary_sha256": "hash"},
            "summary.json": summary,
        }
        names = ["1_inventory.json", "2_integrity.json", "3_metadata_report.json", "4_alignment_report.json", "5_storage_report.json"]
        for index, name in enumerate(names):
            documents[name] = {"status": "passed", "pipeline_id": "custom-rule", "previous_step": index}
        documents[names[2]]["normalized_metadata_sha256"] = "hash"
        documents[names[3]]["artifacts"] = {}
        documents[names[4]].update(assets=[], raw_assets=[])
        with patch.object(preflight, "read", side_effect=lambda path: documents[Path(path).name]), patch.object(preflight, "sha", return_value="hash"):
            result = preflight.freeze_inputs()
        self.assertEqual(result["holes"], ["ONE"])

    def test_failed_media_preparation_does_not_report_acceptance_or_connect_database(self):
        with patch.object(sys, "argv", ["28_import_media_revision.py"]), patch.object(
            media_import, "configure"
        ), patch.object(media_import, "prepare_package", side_effect=ValueError("incomplete media")), patch.object(
            media_import, "accept_prepared_package"
        ) as acceptance, patch.object(media_import, "report") as report, patch(
            "psycopg.connect", side_effect=AssertionError("Database connection")
        ):
            with self.assertRaisesRegex(ValueError, "incomplete media"):
                media_import.main()
        acceptance.assert_not_called()
        report.assert_not_called()

    def test_profile_window_supports_short_files_and_row_group_boundaries(self):
        for count, group_size in [(1, 10), (4, 10), (12, 5)]:
            with self.subTest(count=count):
                path = self.folder / f"{count}.parquet"
                pq.write_table(pa.table({"sample_no": list(range(count))}), path, row_group_size=group_size)
                with pq.ParquetFile(path) as parquet:
                    start, stop, rows = profile_window(parquet)
                self.assertEqual(rows, [{"sample_no": i} for i in range(start, stop + 1)])
                self.assertTrue(0 <= start <= stop < count)
                if count > group_size:
                    self.assertLess(start, group_size)
                    self.assertGreaterEqual(stop, group_size)


if __name__ == "__main__":
    unittest.main()
