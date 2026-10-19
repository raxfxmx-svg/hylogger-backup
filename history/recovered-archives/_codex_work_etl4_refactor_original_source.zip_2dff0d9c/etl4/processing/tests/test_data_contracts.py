"""Small independent fixtures exercise destructive ETL failure modes."""
import importlib.util
import tempfile
from decimal import Decimal
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import _etl_common as common


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validation = load("validation", "2_validate_payloads.py")
normalization = load("normalization", "3_normalize_metadata.py")
alignment = load("alignment", "4_align_samples.py")
columnar = load("columnar", "5_build_columnar.py")


class DataContracts(unittest.TestCase):
    def test_scope_and_path_traversal_are_rejected(self):
        for hole, path in [("15EIS001", "borehole.json"), ("05KCD001", "../07THD002/borehole.json")]:
            with self.assertRaises(ValueError):
                common.source_path(hole, path)

    def test_repeated_depth_and_special_category_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.csv"
            p.write_text("StartDepth,EndDepth,value\n59.5,59.5,null\n59.5,59.5,Aspectral\n59.6,59.6,0001\n", encoding="utf-8")
            r = validation.validate_scalar(p, "1")
            self.assertEqual(r["row_count"], 3)
            self.assertEqual(r["adjacent_equal_start_count"], 1)
            self.assertEqual(r["null_count"], 1)
            self.assertEqual(r["category_counts"], {"Aspectral": 1, "0001": 1})

    def test_scalar_extra_field_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.csv"
            p.write_text("StartDepth,EndDepth,value\n1,1,2,3\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validation.validate_scalar(p, "2")

    def test_valid_spectral_size_does_not_claim_matrix_order(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data.f32"
            np.asarray([-0.2, 0.2, 1.4, 0.8], dtype="<f4").tofile(p)
            r = validation.validate_spectrum(p, {"dtype": "float32", "byte_order": "little", "sample_count": 2, "band_count": 2}, {"wavelengths": [380, 384]})
            self.assertEqual(r["values_below_zero"], 1)
            self.assertEqual(r["values_above_one"], 1)
            self.assertFalse(r["per_sample_spectrum_publication_allowed"])

    def test_closed_intervals_and_labels(self):
        rows = [(0, ["0", "1", "0010"]), (1, ["2", "2", "0011"])]
        with patch.object(alignment, "scalar_rows", return_value=iter(rows)):
            intervals, ids = alignment.expand_intervals("05KCD001", {"log_id": "x"}, 3, "tray", "axis")
        self.assertEqual(ids.tolist(), [0, 0, 1])
        self.assertEqual(intervals[0]["source_label"], "0010")
        with patch.object(alignment, "scalar_rows", return_value=iter([(0, ["0", "0", "a"]), (1, ["2", "2", "b"])])):
            with self.assertRaises(ValueError):
                alignment.expand_intervals("05KCD001", {"log_id": "x"}, 3, "tray", "axis")

    def test_xml_entities_rejected_and_zero_is_not_missing(self):
        self.assertEqual(normalization.number("0"), 0)
        self.assertIsNone(normalization.number("unknown"))
        with self.assertRaises(ValueError):
            normalization.parse_xml('<!DOCTYPE x [<!ENTITY y "bad">]><x>&y;</x>')
        with self.assertRaises(ValueError):
            common.parse_json('{"a": 1, "a": 2}')

    def test_variant_region_and_rank_are_independent(self):
        result = normalization.classify_name("Wt2 ujCLST")
        self.assertEqual(result["source_set_code"], "ujCLST")
        self.assertEqual(result["component_rank"], 2)
        self.assertEqual(result["metric"][0], "mineral_weight")
        self.assertIsNone(normalization.classify_name("Final Mask"))

    def test_decimal_depth_tolerance_boundary(self):
        self.assertEqual(abs(alignment.depth_difference(135.8778, 135.87781)), Decimal("0.00001"))
        self.assertGreater(abs(alignment.depth_difference(135.8778, 135.87782)), Decimal("0.00001"))

    def test_parquet_round_trip_preserves_null_zero_and_text(self):
        schema = pa.schema([("sample_no", pa.int64()), ("depth_m", pa.float64()),
                            ("value", pa.float64()), ("label", pa.string())])
        rows = [{"sample_no": 0, "depth_m": 59.5, "value": None, "label": "0001"},
                {"sample_no": 1, "depth_m": 59.5, "value": 0.0, "label": "INVALID"},
                {"sample_no": 2, "depth_m": 59.6, "value": -1.2, "label": None}]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "values.parquet"
            with patch.object(columnar, "BATCH_ROWS", 2):
                result = columnar.write_verified_parquet(p, schema, iter(rows), "depth_m")
            self.assertEqual(result["row_count"], 3)
            self.assertEqual(len(result["row_groups"]), 2)
            self.assertEqual(pq.read_table(p).to_pylist(), rows)

    def test_profile_lists_preserve_every_value_across_batch_boundaries(self):
        schema = pa.schema([("sample_no", pa.int64()), ("values", pa.list_(pa.float64(), 2))])
        rows = [{"sample_no": i, "values": [i + 0.125, 0.0]} for i in range(5)]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "profiles.parquet"
            with patch.object(columnar, "BATCH_ROWS", 2):
                columnar.write_verified_parquet(p, schema, iter(rows), "sample_no")
            self.assertEqual(pq.read_table(p).to_pylist(), rows)

    def test_large_batches_with_all_null_columns_keep_sample_identity(self):
        schema = pa.schema([("source_row", pa.int64()), ("sample_no", pa.int64()),
                            ("unused_index", pa.int64()), ("value", pa.float64())])
        rows = [{"source_row": i, "sample_no": i, "unused_index": None,
                 "value": None if i % 7 == 0 else i / 13} for i in range(100001)]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nullable.parquet"
            columnar.write_verified_parquet(p, schema, iter(rows), "sample_no")
            self.assertEqual(pq.read_table(p).to_pylist(), rows)

    def test_interrupted_conversion_preserves_previous_asset(self):
        schema = pa.schema([("sample_no", pa.int64()), ("value", pa.float64())])
        previous_rows = [{"sample_no": 0, "value": 0.25}]
        def interrupted_records():
            yield {"sample_no": 0, "value": 0.75}
            raise ValueError("simulated source read failure")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "values.parquet"
            columnar.write_verified_parquet(p, schema, iter(previous_rows), "sample_no")
            previous_hash = common.sha_file(p)
            with patch.object(columnar, "BATCH_ROWS", 1):
                with self.assertRaisesRegex(ValueError, "simulated source read failure"):
                    columnar.write_verified_parquet(p, schema, interrupted_records(), "sample_no")
            self.assertEqual(common.sha_file(p), previous_hash)
            self.assertEqual(pq.read_table(p).to_pylist(), previous_rows)
            self.assertFalse(p.with_suffix(".parquet.tmp").exists())


if __name__ == "__main__":
    unittest.main()
