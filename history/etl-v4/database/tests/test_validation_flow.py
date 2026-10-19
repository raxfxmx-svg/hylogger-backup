"""Check streamlined acceptance using small files and mocked connections, without a database connection."""

import copy
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]

from _db_files import digest, encoded, sha
from _file_checks import FileChecks
from _media_common import marker
import _media_import as media
import _legacy_media_import as legacy_media
import _multi_db as composites

single_import = importlib.import_module("28_import_media_revision")
multi_import = importlib.import_module("34_import_multi_dataset_database")
verifier = importlib.import_module("_media_verification")


class ValidationFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=DATABASE.parent, prefix="validation_test_")
        self.folder = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def make_package(self, arrays=None):
        units = [
            {
                "dataset_id": name,
                "hole_id": name,
                "source_dataset_name": name,
                "source_revision_id": "base-" + name,
                "source_snapshot_id": "input-" + name,
                "source_axis_id": "axis-" + name,
            }
            for name in ("one", "two")
        ]
        documents = {
            "steps/20.json": {"datasets": units, "source_release_id": "base-release"},
            "steps/22.json": {"arrays": arrays or []},
            "steps/27.json": {"rows": []},
        }
        payloads = {name: encoded(value) for name, value in documents.items()}
        import hashlib

        manifest = {
            "contract": media.MEDIA_RULE_VERSION,
            "datasets": {u["dataset_id"]: media.media_identity(u, [], []) for u in units},
            "files": {
                name: {"byte_size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
                for name, value in payloads.items()
            },
        }
        directory = self.folder / digest(manifest)
        directory.mkdir()
        for name, value in payloads.items():
            path = directory / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(value)
        (directory / "manifest.json").write_bytes(encoded(manifest))
        return directory, manifest

    def test_legacy_batch_checks_package_once_but_checks_each_dataset_source(self):
        directory, manifest = self.make_package()
        with patch.object(media, "package_step", wraps=media.package_step) as reads:
            package = media.check_package(directory, manifest)
            with patch.object(media, "check_package", side_effect=AssertionError("whole package rechecked")), patch.object(
                legacy_media, "verify_source_assets"
            ) as sources, patch.object(legacy_media, "verify_media_sources", wraps=media.verify_media_sources) as relations, patch.object(
                legacy_media, "clone_revision", side_effect=lambda conn, unit, *args: ({unit["source_axis_id"]: "new-axis"}, False)
            ):
                results = multi_import.import_dataset_media(MagicMock(), package)
            self.assertEqual([r["dataset_id"] for r in results], ["one", "two"])
            self.assertEqual([c.args[1] for c in reads.call_args_list], [20, 22, 27])
            self.assertEqual([c.args[1]["dataset_id"] for c in sources.call_args_list], ["one", "two"])
            self.assertEqual(relations.call_count, 2)

    def test_new_check_detects_tampering_with_same_size_and_mtime(self):
        directory, manifest = self.make_package()
        with FileChecks():
            media.check_package(directory, manifest)
        path = directory / "steps/22.json"
        before = path.stat()
        path.write_bytes(path.read_bytes().replace(b"arrays", b"arrAys"))
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with FileChecks(), self.assertRaisesRegex(ValueError, "Packaged file differs"):
            media.check_package(directory, manifest)

    def test_missing_package_file_is_rejected(self):
        directory, manifest = self.make_package()
        (directory / "steps/27.json").unlink()
        with self.assertRaisesRegex(ValueError, "Packaged file differs"):
            media.check_package(directory, manifest)

    def test_media_preparation_default_and_compatibility_flag_never_connect_database(self):
        directory, _ = self.make_package()
        results = []
        for option in ([], ["--package-only"]):
            with self.subTest(option=option), patch.object(
                sys, "argv", ["28_import_media_revision.py", "--package", str(directory)] + option
            ), patch.object(single_import, "configure"), patch(
                "psycopg.connect", side_effect=AssertionError("Database connection")
            ), patch.object(single_import, "report") as report, patch.object(
                single_import, "accept_prepared_package", return_value=(
                    self.folder / "acceptance.json", {"status": "passed"})
            ) as acceptance:
                single_import.main()
            acceptance.assert_called_once()
            self.assertEqual(acceptance.call_args.args[0]["directory"], directory)
            self.assertEqual(report.call_args.args[1]["status"], "prepared")
            results.append(report.call_args.args)
        self.assertEqual(results[0], results[1])

    def test_failed_first_acceptance_cannot_report_prepared_success(self):
        directory, _ = self.make_package()
        with patch.object(sys, "argv", ["28_import_media_revision.py", "--package", str(directory)]), patch.object(
            single_import, "configure"
        ), patch.object(single_import, "accept_prepared_package", side_effect=ValueError("source changed")), patch.object(
            single_import, "report"
        ) as report, patch("psycopg.connect", side_effect=AssertionError("Database connection")):
            with self.assertRaisesRegex(ValueError, "source changed"):
                single_import.main()
        report.assert_not_called()

    def test_media_cannot_belong_to_an_unlisted_dataset(self):
        directory, manifest = self.make_package(arrays=[{"dataset_id": "foreign"}])
        with self.assertRaisesRegex(ValueError, "unlisted dataset"):
            media.check_package(directory, manifest)

    def test_parquet_reads_only_required_groups_and_preserves_nulls(self):
        path = self.folder / "samples.parquet"
        table = pa.table({
            "sample_no": list(range(9)),
            "depth_m": [1.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "value_raw": [None, "", "a", "b", "c", "d", "e", "f", "g"],
        })
        pq.write_table(table, path, row_group_size=3)
        read_group = pq.ParquetFile.read_row_group
        with patch.object(pq.ParquetFile, "read", side_effect=AssertionError("whole file read")), patch.object(
            pq.ParquetFile, "read_row_group", autospec=True, side_effect=read_group
        ) as groups:
            result = verifier.read_parquet_samples(path, [8, 0, 1, 2, 6, 8])
        expected = table.to_pylist()
        self.assertEqual(result, {i: expected[i] for i in (0, 1, 2, 6, 8)})
        self.assertEqual([c.args[1] for c in groups.call_args_list], [0, 2])
        self.assertEqual(verifier.read_parquet_samples(path, []), {})
        for invalid in ([-1], [9]):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "outside canonical"):
                verifier.read_parquet_samples(path, invalid)

    def crop_fixture(self):
        original = self.folder / "original.png"
        with Image.new("RGB", (4, 4)) as image:
            image.putdata([(x * 30, y * 40, x + y) for y in range(4) for x in range(4)])
            image.save(original)
            rows, stored = [], {}
            for i, box in enumerate(([0, 0, 4, 2], [0, 2, 4, 4])):
                crop = self.folder / f"crop-{i}.png"
                with image.crop(box) as region:
                    region.save(crop)
                recipe = {"source_sha256": sha(original), "crop_box_half_open": box}
                rows.append({
                    "source_path": "original.png", "source_sha256": sha(original),
                    "image_ordinal": 0, "source_log_id": "images", "region_ordinal": i,
                    "crop_sha256": sha(crop), "recipe": recipe,
                })
                stored[i] = {
                    "sha256": sha(crop), "object_key": crop.relative_to(verifier.ETL).as_posix(),
                    "provenance": {"source_frame_id": "frame", "region_id": str(i), "recipe": recipe},
                    "id": str(i), "frame_id": "frame", "source_sha256": sha(original),
                    "source_path": "original.png",
                }
        conn = MagicMock()
        conn.execute.side_effect = lambda query, params: MagicMock(fetchall=lambda: [stored[params[-1]]])
        return original, rows, stored, conn

    def test_crops_share_decode_but_each_link_and_pixel_is_checked(self):
        original, rows, stored, conn = self.crop_fixture()
        with patch.object(verifier, "source_path", return_value=original), patch.object(
            verifier, "decode", wraps=verifier.decode
        ) as decode:
            verifier.verify_crops(conn, {}, "revision", rows)
        self.assertEqual(sum(c.args[0] == original for c in decode.call_args_list), 1)
        self.assertEqual(conn.execute.call_count, 2)
        stored[1]["source_path"] = "wrong.png"
        with patch.object(verifier, "source_path", return_value=original), self.assertRaisesRegex(ValueError, "wrong source"):
            verifier.verify_crops(conn, {}, "revision", rows)
        stored[1]["source_path"] = "original.png"
        with Image.new("RGB", (4, 2), "red") as altered:
            altered.save(self.folder / "crop-1.png")
        with patch.object(verifier, "source_path", return_value=original), self.assertRaisesRegex(ValueError, "source pixels"):
            verifier.verify_crops(conn, {}, "revision", rows)

    def test_invalid_mapping_is_rejected_without_exercising_marker_formula(self):
        for a, b, width in ((-1, 2, 4), (2, 1, 4), (0, 3, 4), (0, 2, 0)):
            conn = MagicMock()
            conn.execute.side_effect = [
                MagicMock(fetchone=lambda: {"n": 3}),
                MagicMock(fetchone=lambda: {"n": 0}),
                MagicMock(fetchone=lambda: {"n": 0}),
                MagicMock(fetchall=lambda: [{"sample_no_from": a, "sample_no_to": b, "width_px": width}]),
            ]
            with self.subTest(bounds=(a, b, width)), self.assertRaisesRegex(ValueError, "Invalid image mapping"):
                verifier.verify_dataset(
                    conn, {"dataset_id": "one", "source_axis_id": "old", "sample_count": 3},
                    {"axis_id": "new", "dataset_revision_id": "revision"}, "release",
                    {"directory": self.folder, "datasets": {"one": {}}},
                )

    def test_marker_formula_endpoints_singletons_and_invalid_inputs(self):
        self.assertEqual([marker(s, 2, 6, 101)["x_px"] for s in (2, 4, 6)], [0, 50, 100])
        self.assertEqual(marker(2, 2, 2, 101)["x_px"], 50)
        self.assertEqual(marker(2, 2, 2, 1)["x_px"], 0)
        for args in ((1, 2, 6, 101), (7, 2, 6, 101), (2, 2, 6, 0), (True, 0, 2, 10)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                marker(*args)

    def test_composite_verification_rejects_missing_or_changed_rows_without_writing(self):
        group = {
            "composite": {"id": "composite", "definition_sha256": "definition"},
            "parts": [{"composite_id": "composite", "sequence_no": 0}],
            "relations": [{"id": "relation", "switch_md_m": 10}],
        }
        for problem in (None, "composite", "definition", "part", "relation", "relation_value"):
            conn = MagicMock()
            existing = None if problem == "composite" else {"definition_sha256": "changed" if problem == "definition" else "definition"}
            relation = None if problem == "relation" else copy.deepcopy(group["relations"][0])
            if problem == "relation_value":
                relation["switch_md_m"] = 11
            conn.execute.side_effect = [
                MagicMock(fetchone=lambda: existing),
                MagicMock(fetchall=lambda: [] if problem == "part" else group["parts"]),
                MagicMock(fetchone=lambda: relation),
            ]
            with self.subTest(problem=problem), patch.object(composites, "composite_rows", return_value=[group]), patch.object(
                composites, "insert", side_effect=AssertionError("verification wrote a row")
            ):
                if problem is None:
                    self.assertEqual(composites.verify_composites(conn, "release", {}), [group])
                else:
                    with self.assertRaises(ValueError):
                        composites.verify_composites(conn, "release", {})
            self.assertTrue(all(c.args[0].lstrip().startswith("SELECT") for c in conn.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
