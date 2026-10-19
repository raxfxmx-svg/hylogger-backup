from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from verify import verify_release  # noqa: E402


class PublishedReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = verify_release(PROJECT_ROOT)
        current = json.loads(
            (PROJECT_ROOT / "data" / "processed" / "current.json").read_text(encoding="utf-8")
        )
        cls.release_root = (
            PROJECT_ROOT / "data" / "processed" / "releases" / current["release_id"]
        )

    def test_actual_sample_counts(self) -> None:
        self.assertEqual(self.result["sample_count"], 25938)
        self.assertEqual(self.result["tray_count"], 33)
        self.assertEqual(self.result["section_count"], 198)

    def test_thumbnail_sections_are_published_without_upscaling(self) -> None:
        self.assertEqual(self.result["section_image_mapping_rows"], 198)
        self.assertEqual(self.result["section_image_complete_count"], 198)
        self.assertEqual(self.result["section_image_widths"], [400])
        self.assertEqual(self.result["section_image_quality"], "thumbnail_derived")

        mappings = pq.read_table(
            self.release_root
            / "holes"
            / "05GJD001"
            / "core"
            / "section_images.parquet"
        )
        self.assertEqual(
            mappings.column("section_index").to_pylist(), list(range(198))
        )
        self.assertEqual(set(mappings.column("depth_direction").to_pylist()), {"left_to_right"})
        self.assertEqual(set(mappings.column("mapping_precision").to_pylist()), {"section_interval"})
        self.assertEqual(set(mappings.column("image_status").to_pylist()), {"complete"})

    def test_duplicate_depths_do_not_replace_sample_key(self) -> None:
        self.assertGreater(self.result["duplicate_axis_coordinate_rows"], 0)
        axis = pq.read_table(
            self.release_root / "holes" / "05GJD001" / "sample_axis.parquet"
        )
        self.assertEqual(axis.column("sample_index").to_pylist(), list(range(25938)))

    def test_spectra_are_separate_matrices(self) -> None:
        self.assertEqual(self.result["spectral_complete_series_count"], 2)
        self.assertCountEqual(
            self.result["spectral_complete_shapes"],
            [[25938, 531], [25938, 341]],
        )
        self.assertFalse(self.result["combined_signals_csv"])

    def test_scalar_table_uses_one_sample_axis(self) -> None:
        values = pq.ParquetFile(
            self.release_root
            / "holes"
            / "05GJD001"
            / "scalars"
            / "values.parquet"
        ).metadata
        self.assertEqual(values.num_rows, 25938)
        self.assertLess(values.num_rows, 50000)

    def test_raw_package_still_matches_published_provenance(self) -> None:
        self.assertTrue(self.result["raw_tree_verified"])


if __name__ == "__main__":
    unittest.main()
