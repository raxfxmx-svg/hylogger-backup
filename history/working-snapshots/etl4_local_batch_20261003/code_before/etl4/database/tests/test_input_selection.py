"""Accept new boreholes through manifests while rejecting escaping paths and inconsistent manifests."""

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]

from _settings import validate_hole_names
from _prepared_inputs import load_lock, prepared_holes, summary_holes
from _media_common import DIRECTION, confirmed_direction
from processing._etl_common import source_path


class InputSelectionTests(unittest.TestCase):
    def lock(self):
        holes = ["09ATRCD025", "12BRDDH003"]
        return {
            "holes": holes,
            "summary": {"active_holes": holes, "holes": [{"hole_id": h} for h in holes]},
            "prepared_hashes": {h: {} for h in holes},
            "raw_hashes": {h: {} for h in holes},
        }

    def test_new_holes_are_selected_from_manifest(self):
        lock = self.lock()
        with patch("_prepared_inputs.read", return_value=lock):
            self.assertEqual(load_lock(), lock)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            folder = root / "NEW001"
            folder.mkdir()
            (folder / "borehole.json").write_text("{}", encoding="utf-8")
            (folder / "datasets.json").write_text("[]", encoding="utf-8")
            with patch("processing._etl_common.SOURCE", root):
                self.assertEqual(source_path("NEW001", "datasets.json"), folder / "datasets.json")

    def test_empty_duplicate_and_path_names_are_rejected(self):
        for holes in [[], ["same", "same"], ["../outside"], ["C:/outside"], ["a\\b"]]:
            with self.subTest(holes=holes), self.assertRaises(ValueError):
                validate_hole_names(holes)
        with self.assertRaises(ValueError):
            source_path("09ATRCD025", "../12BRDDH003/datasets.json")

    def test_declared_members_must_match_summary_records(self):
        summary = copy.deepcopy(self.lock()["summary"])
        summary["holes"].pop()
        with self.assertRaises(ValueError):
            summary_holes(summary)

    def test_inventory_members_must_match_lock(self):
        for key in ("prepared_hashes", "raw_hashes"):
            lock = self.lock()
            lock[key].pop("09ATRCD025")
            with self.subTest(key=key), patch("_prepared_inputs.read", return_value=lock):
                with self.assertRaises(ValueError):
                    load_lock()

    def test_unselected_hole_cannot_enter_import(self):
        with patch("_prepared_inputs.load_lock", return_value=self.lock()):
            with self.assertRaises(ValueError):
                prepared_holes(["other_hole"])
            with self.assertRaises(ValueError):
                prepared_holes([])

    def test_source_direction_applies_to_new_holes(self):
        self.assertEqual(confirmed_direction("09ATRCD025"), DIRECTION)
        self.assertEqual(confirmed_direction("another_hole"), DIRECTION)

    def test_old_record_is_readable_but_cannot_change_source_direction(self):
        record = {**DIRECTION, "scope": ["new_fixture"]}
        self.assertEqual(confirmed_direction("new_fixture", record), DIRECTION)
        self.assertEqual(confirmed_direction("other_fixture", record), DIRECTION)
        with self.assertRaises(ValueError):
            confirmed_direction(
                "new_fixture", {**record, "source_depth_direction": "right_to_left"}
            )


if __name__ == "__main__":
    unittest.main()
