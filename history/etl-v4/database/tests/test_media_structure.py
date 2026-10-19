"""Check reruns, compact manifests, and shared image processing without a database connection."""

import copy
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]
from _db_common import uid
from _db_files import encoded, sha
from _media_manifest import pack_document, unpack_document, HEADER
from _media_rows import row_boundaries, bind_row
from _media_common import DIRECTION, decode
import _media_import as media
import _legacy_media_import as legacy_media
import _media_reader as reader

cropper = importlib.import_module("27_build_image_row_assets")


class MediaStructureTests(unittest.TestCase):
    def test_existing_revision_returns_without_loading_clone_tables(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [{"id": "old"}, {"input_digest": "hash"}, {"ok": 1}]
        with patch.object(legacy_media, "select_revision", side_effect=AssertionError("clone table read")):
            ids, created = legacy_media.clone_revision(conn, {"source_revision_id": "old", "source_axis_id": "axis"}, "new", "p", "hash", {})
        self.assertFalse(created)
        self.assertEqual(ids["axis"], uid("media-clone", "new", "sample_axis", "axis"))
        self.assertEqual(conn.execute.call_count, 3)

    def test_existing_revision_conflict_or_missing_axis_is_rejected(self):
        for checksum, axis in (("different", {"ok": 1}), ("hash", None)):
            conn = MagicMock()
            conn.execute.return_value.fetchone.side_effect = [{"id": "old"}, {"input_digest": checksum}, axis]
            with self.subTest(checksum=checksum), self.assertRaises(ValueError), patch.object(legacy_media, "select_revision", side_effect=AssertionError("clone table read")):
                legacy_media.clone_revision(conn, {"source_revision_id": "old", "source_axis_id": "axis"}, "new", "p", "hash", {})

    def document(self):
        return {"status": "passed", "rows": [
            {"dataset_id": "d", "source_frame_id": "frame", "source_axis_id": "axis",
             "prepared_summary": {"files": ["large summary"] * 300}, "source_path": "image.png",
             "height_px": height, "row_key": str(index), "custom": {"kept": index}}
            for index, height in enumerate((20, 22, 21))
        ]}

    def test_manifest_roundtrip_keeps_differences_unknown_fields_and_order(self):
        document = self.document()
        saved = copy.deepcopy(document)
        packed = pack_document(document)
        self.assertLess(len(encoded(packed)), len(encoded(document)) / 2)
        self.assertEqual(unpack_document(packed), document)
        self.assertEqual(document, saved)
        self.assertEqual(pack_document(unpack_document(packed)), packed)
        self.assertEqual(unpack_document(document), document)

    def test_manifest_rejects_missing_cross_dataset_and_conflicting_contexts(self):
        for failure in ("dataset", "frame", "cross", "conflict", "version"):
            packed = pack_document(self.document())
            if failure == "dataset": packed[HEADER]["datasets"].clear()
            elif failure == "frame": packed[HEADER]["frames"].clear()
            elif failure == "cross": packed[HEADER]["frames"]["frame"]["dataset_id"] = "other"
            elif failure == "conflict": packed["rows"][0]["source_axis_id"] = "other"
            else: packed[HEADER]["version"] = 999
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                unpack_document(packed)

    def test_crops_decode_each_source_once_and_keep_order_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            pixels = np.arange(32 * 40 * 3, dtype=np.uint8).reshape(40, 32, 3)
            Image.fromarray(pixels).save(work / "source.png")
            rows = [{"dataset_id": "d", "source_path": "source.png", "source_log_id": "l",
                     "source_sha256": sha(work / "source.png"), "row_key": str(index),
                     "x_px": 0, "y_px": y, "width_px": 32, "height_px": 10}
                    for index, y in enumerate((20, 0, 10))]
            with patch.object(cropper, "source_path", return_value=work / "source.png"), patch.object(cropper, "decode", wraps=decode) as decodes:
                result = cropper.build_crops(rows, work)
            self.assertEqual(sum(call.args[0] == work / "source.png" for call in decodes.call_args_list), 1)
            self.assertEqual([r["row_key"] for r in result], ["0", "1", "2"])
            for row in result:
                expected = Image.fromarray(pixels[row["y_px"]:row["y_px"]+10])
                expected.save(work / "expected.png", format="PNG", optimize=False, compress_level=6)
                self.assertEqual(row["crop_sha256"], sha(work / "expected.png"))
            rows[-1]["source_sha256"] = "changed"
            with patch.object(cropper, "source_path", return_value=work / "source.png"), self.assertRaisesRegex(ValueError, "Changed source"):
                cropper.build_crops(rows, work)
            rows[-1]["source_sha256"] = rows[0]["source_sha256"]
            rows[-1]["y_px"] = 39
            with patch.object(cropper, "source_path", return_value=work / "source.png"), self.assertRaisesRegex(ValueError, "outside source"):
                cropper.build_crops(rows, work)

    def test_common_boundaries_preserve_full_height_and_equal_pitch_fallback(self):
        image = Image.new("RGB", (40, 90), (60, 60, 60))
        boundaries, details = row_boundaries(image, 3)
        self.assertEqual(boundaries, [0, 30, 60, 90])
        self.assertEqual([d["method"] for d in details], ["reviewed_equal_pitch"] * 2)
        pixels = np.asarray(image).copy()
        pixels[32] = 255
        pixels[61] = 255
        boundaries, _ = row_boundaries(Image.fromarray(pixels), 3)
        self.assertEqual(boundaries, [0, 32, 61, 90])

    def test_binding_rejects_wrong_axis_tray_and_range(self):
        row = {"source_axis_id": "axis", "core_interval_id": "tray", "sample_count": 10,
               "section": {"axis_id": "axis", "parent_interval_id": "tray", "sample_no_from": 0, "sample_no_to": 9}}
        self.assertEqual(bind_row(row, DIRECTION)["sample_no_to"], 9)
        for key, value in (("axis_id", "other"), ("parent_interval_id", "other"), ("sample_no_to", 10)):
            altered = copy.deepcopy(row)
            altered["section"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): bind_row(altered, DIRECTION)

    def test_reader_does_not_query_payload_for_metadata_only_logs(self):
        conn = MagicMock()
        source = reader.result_sources(conn, [{"availability_status": "metadata_only"}], "axis", 0)
        conn.execute.assert_not_called()
        self.assertFalse(source["assets"])

    def test_reader_batches_duplicate_asset_requests(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        result = reader.local_assets(conn, ["one", "one", "two", None])
        conn.execute.assert_called_once()
        self.assertEqual(result, {"one": (None, None), "two": (None, None)})


if __name__ == "__main__":
    unittest.main()
