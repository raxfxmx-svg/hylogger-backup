"""Refactoring behavior tests: stable revisions, input checks, and publication order."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

DATABASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATABASE))
sys.path.insert(0, str(DATABASE.parent / "processing"))
from _db_common import ETL
from _db_files import digest, read, sha, write
from _run_reports import report
from processing import _etl_common as processing
from _file_checks import FileChecks, hash_file
import _media_import as media
import _legacy_media_import as legacy_media
import _publication as publication
import _legacy_verification as verification
from _settings import settings


class RefactorContracts(unittest.TestCase):
    def test_reverification_keeps_independent_result_reports(self):
        settings.database_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=settings.database_dir) as temporary:
            first = report(
                "verification.json",
                {"status": "passed", "verifier": "before"},
                directory=Path(temporary),
            )
            second = report(
                "verification.json",
                {"status": "passed", "verifier": "after"},
                directory=Path(temporary),
            )
            saved = [read(p) for p in (Path(temporary) / "history").glob("*.json")]
            self.assertEqual(len(saved), 2)
            self.assertIn(first, saved)
            self.assertIn(second, saved)
            self.assertEqual(read(Path(temporary) / "verification.json"), second)

    def test_rule_version_can_change_for_only_one_dataset(self):
        before = [processing.pipeline_id(dataset_id=name) for name in ("one", "two")]
        with patch.dict(processing.PROCESSING_RULE_VERSIONS, {"one": "revised-parser"}):
            self.assertNotEqual(before[0], processing.pipeline_id(dataset_id="one"))
            self.assertEqual(before[1], processing.pipeline_id(dataset_id="two"))
        units = [
            {
                "dataset_id": name,
                "source_dataset_id": name,
                "source_revision_id": name,
                "source_snapshot_id": name,
            }
            for name in ("one", "two")
        ]
        before = [media.media_identity(u, [], []) for u in units]
        with patch.dict(media.MEDIA_RULE_VERSIONS, {"one": "revised-crop"}):
            self.assertNotEqual(before[0], media.media_identity(units[0], [], []))
            self.assertEqual(before[1], media.media_identity(units[1], [], []))

    def test_wrong_crop_source_and_spectral_dimensions_are_rejected(self):
        conn = MagicMock()
        unit = {"source_revision_id": "revision", "sample_count": 10}
        array = {
            "source_log_pk": "log-pk",
            "log_id": "log",
            "file": "data.f32",
            "sha256": "hash",
            "sample_count": 10,
            "band_count": 3,
        }
        conn.execute.return_value.fetchone.return_value = {
            "sha256": "hash",
            "byte_size": 120,
            "wavelength_count": 4,
        }
        with self.assertRaisesRegex(ValueError, "Spectral source"):
            media.verify_media_sources(conn, unit, [array], [])
        row = {
            "source_frame_id": "frame",
            "source_path": "a.jpg",
            "source_log_id": "image-log",
            "image_ordinal": 0,
            "source_sha256": "source-hash",
            "recipe": {"source_sha256": "source-hash"},
        }
        conn.execute.return_value.fetchone.return_value = {
            "logical_path": "b.jpg",
            "source_log_id": "image-log",
            "image_ordinal": 0,
            "sha256": "source-hash",
        }
        with self.assertRaisesRegex(ValueError, "different source frame"):
            media.verify_media_sources(conn, unit, [], [row])

    def test_shared_manifest_change_only_versions_the_affected_dataset(self):
        import importlib

        prepare = importlib.import_module("32_prepare_multi_dataset_payloads")
        raw = {
            "datasets.json": [{"dataset_id": "one"}, {"dataset_id": "two"}],
            "package_manifest.json": {"content_fingerprint": "whole-package-before"},
            "images_manifest.json": {"files": []},
            "tray_depths.json": {},
        }
        for name in (
            "logs_scalar.json",
            "scalar_manifest.json",
            "logs_spectral.json",
            "spectral_manifest.json",
            "logs_profilometer.json",
            "profilometer_manifest.json",
            "logs_image.json",
            "image_logs_by_dataset.json",
        ):
            raw[name] = [
                {"log_id": "log-one", "sha256": "one"},
                {"log_id": "log-two", "sha256": "two"},
            ]
        units = [
            {
                "source_dataset_id": value,
                "membership_evidence": {},
                "log_ids": {
                    kind: ["log-" + value] for kind in ("scalar", "spectral", "profile", "image")
                },
            }
            for value in ("one", "two")
        ]
        before = [
            prepare.dataset_input_identity(prepare.selected_metadata(raw, u), u, []) for u in units
        ]
        raw["scalar_manifest.json"][0]["sha256"] = "changed-one"
        raw["package_manifest.json"]["content_fingerprint"] = "whole-package-after"
        after = [
            prepare.dataset_input_identity(prepare.selected_metadata(raw, u), u, []) for u in units
        ]
        self.assertNotEqual(before[0], after[0])
        self.assertEqual(before[1], after[1])

    def test_audit_only_changes_do_not_replace_sealed_data(self):
        settings.processing_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=settings.processing_dir) as temporary:
            folder = Path(temporary)
            processing.write_json(folder / "result.json", {"value": 1, "environment": "before"})
            processing.write_json(folder / "5_storage_report.json", {})
            before = (folder / "result.json").read_bytes()
            processing.write_json(folder / "result.json", {"value": 1, "environment": "after"})
            self.assertEqual((folder / "result.json").read_bytes(), before)
            with self.assertRaisesRegex(ValueError, 'Same processing version'):
                processing.write_json(folder / "result.json", {"value": 2})
            self.assertEqual((folder / "result.json").read_bytes(), before)

    def test_import_rechecks_referenced_source_content(self):
        settings.database_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=settings.database_dir) as temporary:
            path = Path(temporary) / "source.bin"
            path.write_bytes(b"1234")
            before = path.stat()
            asset = {
                "byte_size": 4,
                "sha256": sha(path),
                "object_key": path.relative_to(ETL).as_posix(),
            }
            conn = MagicMock()
            conn.execute.return_value.fetchone.return_value = {"id": "axis"}
            conn.execute.return_value.fetchall.return_value = [asset]
            unit = {
                "source_revision_id": "revision",
                "dataset_id": "dataset",
                "source_snapshot_id": "input",
                "source_axis_id": "axis",
            }
            with FileChecks():
                legacy_media.verify_source_assets(conn, unit)
            path.write_bytes(b"5678")
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            with FileChecks(), self.assertRaisesRegex(
                ValueError, "Referenced source asset changed"
            ):
                legacy_media.verify_source_assets(conn, unit)
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                legacy_media.verify_source_assets(conn, unit)

    def test_code_and_environment_do_not_define_processing_version(self):
        original = processing.pipeline_id()
        with patch.object(processing, "sha_file", return_value="different-source"), patch.object(
            processing, "environment", return_value={"python": "another-version"}
        ):
            self.assertEqual(processing.pipeline_id(), original)
        with patch.object(processing, "PROCESSING_RULE_VERSION", "changed-rules"):
            self.assertNotEqual(processing.pipeline_id(), original)

    def test_dataset_identity_is_independent_and_output_conflicts_are_visible(self):
        first = {
            "dataset_id": "one",
            "source_revision_id": "base-one",
            "source_snapshot_id": "input-one",
        }
        second = {
            "dataset_id": "two",
            "source_revision_id": "base-two",
            "source_snapshot_id": "input-two",
        }
        before = media.media_identity(first, [], [])
        other = media.media_identity(second, [], [])
        changed = media.media_identity({**first, "source_snapshot_id": "changed"}, [], [])
        self.assertNotEqual(before["input_key"], changed["input_key"])
        self.assertEqual(other, media.media_identity(second, [], []))
        output_change = media.media_identity(first, [{"log_id": "log", "sha256": "changed"}], [])
        self.assertEqual(before["input_key"], output_change["input_key"])
        self.assertNotEqual(before["content_sha256"], output_change["content_sha256"])

    def test_new_check_detects_same_size_and_mtime_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.bin"
            path.write_bytes(b"1234")
            stat = path.stat()
            with FileChecks() as checks:
                before = hash_file(path)
                self.assertEqual(before, hash_file(path))
                self.assertEqual(checks.scans, 1)
                self.assertEqual(checks.cache_hits, 1)
            path.write_bytes(b"5678")
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            with FileChecks() as checks:
                self.assertNotEqual(before, hash_file(path))
                self.assertEqual(checks.scans, 1)

    def test_timestamp_only_change_keeps_content_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.bin"
            path.write_bytes(b"1234")
            original = hash_file(path)
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            self.assertEqual(original, hash_file(path))

    def test_explicit_context_is_isolated(self):
        context = processing.DatasetContext(
            "15EIS001", Path("prepared"), {}, {"file": {"x": 1}}, {}
        )
        before = processing.ALLOWED
        selected = processing.source_json("15EIS001", "file", context)
        selected["x"] = 2
        self.assertEqual(processing.source_json("15EIS001", "file", context), {"x": 1})
        with self.assertRaises(ValueError):
            processing.snapshot("12CADD001", context)
        self.assertEqual(processing.ALLOWED, before)

    def test_changed_output_does_not_replace_existing_parquet(self):
        import pyarrow as pa

        columnar = __import__("processing.columnar_storage", fromlist=["write_verified_parquet"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "values.parquet"
            schema = pa.schema([("value", pa.float64())])
            columnar.write_verified_parquet(path, schema, [{"value": 1.0}])
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "Same output identity"):
                columnar.write_verified_parquet(path, schema, [{"value": 2.0}])
            self.assertEqual(path.read_bytes(), original)

    def test_package_import_does_not_read_working_stages(self):
        settings.database_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=settings.database_dir) as directory:
            folder = Path(directory)
            work, evidence = folder / "work", folder / "evidence"
            unit = {
                "dataset_id": "dataset",
                "source_revision_id": "base",
                "source_snapshot_id": "input",
                "source_axis_id": "axis",
            }
            for number in range(20, 28):
                value = {"status": "passed"}
                if number == 20:
                    value.update(datasets=[unit], source_release_id=None)
                if number == 21:
                    value["spectra"] = []
                if number == 22:
                    value["arrays"] = []
                if number == 27:
                    value["rows"] = []
                write(work / f"{number}.json", value)
            with patch.object(
                type(settings), "database_dir", new_callable=PropertyMock, return_value=folder
            ):
                package = media.prepare_package(work, evidence)
                destination, manifest = package["directory"], package["manifest"]
                with patch.object(media, "MEDIA_RULE_VERSION", "future-rules"):
                    media.check_package(destination, manifest)
                with patch.object(
                    media, "stage", side_effect=AssertionError("temporary work accessed")
                ), patch.object(
                    legacy_media, "clone_revision", return_value=({"axis": "derived-axis"}, False)
                ), patch.object(
                    legacy_media, "verify_source_assets"
                ):
                    result = legacy_media.import_media(None, package, unit["dataset_id"])
                    self.assertEqual(result["action"], "already_present")
                (destination / "steps" / "22.json").write_text('{"arrays": [1]}', encoding="utf-8")
                with self.assertRaises(ValueError):
                    media.check_package(destination, manifest)

    def test_asset_manifest_failure_precedes_activation_transaction(self):
        conn = MagicMock()
        members = [{"dataset_revision_id": "revision", "input_digest": "content"}]
        checks = [
            {"dataset_revision_id": "revision", "input_digest": "content", "status": "passed"}
        ]
        with patch.object(publication, "release_members", return_value=members), patch.object(
            publication, "write_asset_manifest", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                publication.publish_release(conn, "release", checks, __file__)
        conn.transaction.assert_not_called()

    def test_failed_validation_never_writes_asset_manifest(self):
        conn = MagicMock()
        members = [{"dataset_revision_id": "revision", "input_digest": "content"}]
        checks = [
            {"dataset_revision_id": "revision", "input_digest": "content", "status": "failed"}
        ]
        with patch.object(publication, "release_members", return_value=members), patch.object(
            publication, "write_asset_manifest"
        ) as writer:
            with self.assertRaises(ValueError):
                publication.publish_release(conn, "release", checks, __file__)
            writer.assert_not_called()
        conn.transaction.assert_not_called()

    def test_empty_release_is_rejected(self):
        conn = MagicMock()
        manifest = {"dataset_revisions": []}
        conn.execute.return_value.fetchone.return_value = {
            "manifest": manifest,
            "manifest_sha256": digest(manifest),
        }
        conn.execute.return_value.fetchall.return_value = []
        with self.assertRaises(ValueError):
            publication.release_members(conn, "empty")

    def test_api_is_optional_and_explicit_failure_prevents_publish(self):
        selected = [
            {
                "summary": {"hole_id": "hole"},
                "metadata": {"dataset": {"id": "dataset"}, "dataset_revision": {"id": "revision"}},
            }
        ]
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"ok": True}
        manager = MagicMock()
        manager.__enter__.return_value = conn
        with patch.object(verification, "prepared_holes", return_value=selected), patch.object(
            verification, "connection", return_value=manager
        ), patch.object(verification, "assert_schema"), patch.object(
            verification, "verify_hole", return_value={"status": "passed"}
        ), patch.object(
            verification, "report", side_effect=lambda name, value: value
        ), patch.object(
            verification, "api_checks", side_effect=RuntimeError("API unavailable")
        ) as api, patch.object(
            publication, "stage_release", return_value="release"
        ), patch.object(
            publication, "publish_release"
        ) as publish:
            result = verification.verify_and_publish()
            self.assertEqual(result["http_checks"]["status"], "not_requested")
            api.assert_not_called()
            publish.assert_called_once()
            publish.reset_mock()
            with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                verification.verify_and_publish(check_api=True)
            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
