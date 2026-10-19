"""Use small files to test both local acceptance stages and external directories without a real database connection."""

import copy
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]

import _db_common as db
import _final_import as final
import _media_import as media
from _db_files import digest, encoded, read, sha
from _file_checks import FileChecks
from _ingest import add_asset
from _media_reader import local_assets
from _media_common import prepare_contract_evidence
from _settings import (
    SOURCE_ROOT, StepParser, configure, settings, raw_path, path_reference,
    local_location, local_asset_path, resolve_reference,
)
from processing._etl_common import METADATA, pipeline_id, source_path

final_entry = importlib.import_module("37_import_final_version")


class LocalBatchTests(unittest.TestCase):
    def setUp(self):
        self.previous = copy.copy(settings.__dict__)
        self.temporary = tempfile.TemporaryDirectory(prefix="etl4_local_batch_")
        self.root = Path(self.temporary.name).resolve()
        args = StepParser().parse_args([
            "--raw-dir", str(self.root / "raw"), "--work-dir", str(self.root / "work"),
            "--dbname", "etl4_local_fixture",
        ])
        configure(args)

    def tearDown(self):
        settings.__dict__.update(self.previous)
        self.temporary.cleanup()

    def make_prepared_package(self, *, multi=False, report_status="passed"):
        hole = "EXAMPLE"
        raw = raw_path(hole, "input.csv")
        raw.parent.mkdir(parents=True)
        raw.write_bytes(b"value\n1\n")
        for name, value in (("borehole.json", {}), ("datasets.json", [])):
            (raw.parent / name).write_bytes(encoded(value))
        folder = settings.prepared_dir / ("multidataset/EXAMPLE/data" if multi else hole)
        folder.mkdir(parents=True)
        revision = {"id": "revision", "pipeline_id": "rules", "source_snapshot_id": "snapshot"}
        status = {"status": report_status, "pipeline_id": "rules", "source_snapshot_id": "snapshot"}
        documents = {
            "1_inventory.json": status, "2_integrity.json": status,
            "3_metadata_report.json": status,
            "3_normalized_metadata.json": {"dataset": {"id": "dataset"}, "dataset_revision": revision},
            "4_alignment_report.json": {**status, "axis_id": "axis", "sample_count": 1},
            "4_axis_bindings.json": [], "4_core_intervals.json": [], "4_image_frames.json": [],
            "5_storage_report.json": {
                **status, "assets": [], "raw_assets": [{"source_relative_path": "input.csv",
                    "byte_size": raw.stat().st_size, "sha256": sha(raw)}],
            },
        }
        for name, value in documents.items():
            (folder / name).write_bytes(encoded(value))
        # Use NPZ consistently with step 4; step 5 storage manifests manage canonical Parquet.
        axis_bytes = io.BytesIO()
        np.savez(axis_bytes, sample_no=np.array([0]), md_m=np.array([1.0]))
        (folder / "4_sample_axis.npz").write_bytes(axis_bytes.getvalue())
        unit = {
            "dataset_id": "dataset", "source_dataset_id": "source-dataset", "hole_id": hole,
            "source_revision_id": "revision", "source_snapshot_id": "snapshot",
            "source_axis_id": "axis", "sample_count": 1,
            "prepared_directory": folder.relative_to(settings.prepared_dir).as_posix(),
            "prepared_object_key": path_reference(folder),
            "prepared_hashes": {p.name: sha(p) for p in folder.iterdir()},
            "prepared_summary": {"hole_id": hole},
        }
        steps = {n: {"status": "passed"} for n in range(20, 28)}
        steps[20].update(datasets=[unit], source_release_id=None)
        steps[21]["spectra"] = []
        steps[22]["arrays"] = []
        steps[25]["status"] = "reviewed"
        steps[27]["rows"] = []
        payloads = {f"steps/{n}.json": encoded(value) for n, value in steps.items()}
        import hashlib

        manifest = {"contract": media.MEDIA_RULE_VERSION,
                    "datasets": {"dataset": media.media_identity(unit, [], [])},
                    "files": {name: {"byte_size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                              for name, data in payloads.items()}}
        directory = settings.database_dir / "media_releases" / digest(manifest)
        (directory / "steps").mkdir(parents=True)
        for name, data in payloads.items():
            (directory / name).write_bytes(data)
        (directory / "manifest.json").write_bytes(encoded(manifest))
        package = media.check_package(directory, manifest)
        batch = {"packages": [{"directory": str(directory), "prepared_work_dir": str(settings.work_dir)}]}
        return package, batch, raw, folder

    def test_external_raw_is_read_directly_and_locations_round_trip(self):
        package, _, raw, _ = self.make_prepared_package()
        self.assertEqual(source_path("EXAMPLE", "input.csv"), raw)
        self.assertFalse(raw.is_relative_to(SOURCE_ROOT))
        for path in (raw, package["directory"] / "manifest.json", DATABASE / "37_import_final_version.py"):
            self.assertEqual(resolve_reference(path_reference(path)), path.resolve())
        with patch("_ingest.insert") as insert:
            aid = add_asset(None, "revision", "raw", "input.csv", "scalar", raw.stat().st_size,
                            sha(raw), path_reference(raw), "raw", {})
        location = next(c.args[2] for c in insert.call_args_list if c.args[1] == "asset_location")
        self.assertEqual(local_asset_path(location), raw)
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [{**location, "id": aid, "byte_size": raw.stat().st_size}]
        self.assertEqual(local_assets(conn, [aid])[aid][1], raw)

    def test_external_root_is_stable_across_processes_and_not_retargeted(self):
        file = settings.work_dir / "processing/output.txt"
        reference = path_reference(file)
        script = "import sys; sys.path.insert(0, sys.argv[1]); from _settings import resolve_reference; print(resolve_reference(sys.argv[2]))"
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", script, str(SOURCE_ROOT), reference],
                                env={**os.environ, "ETL4_RAW_DIR": str(settings.raw_dir),
                                     "ETL4_WORK_DIR": str(settings.work_dir)}, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(file))
        before = pipeline_id(dataset_id="source-dataset")
        settings.work_dir = self.root / "another-batch"
        self.assertEqual(before, pipeline_id(dataset_id="source-dataset"))
        with self.assertRaisesRegex(ValueError, "Unknown file root"):
            resolve_reference(reference)

    def test_inventory_identity_stays_the_same_after_changing_raw_and_work_location(self):
        raw = raw_path("EXAMPLE", "input.csv")
        raw.parent.mkdir(parents=True)
        raw.write_bytes(b"StartDepth,EndDepth,value\n1,1,2\n")
        metadata = {name: [] for name in METADATA}
        metadata.update({
            "borehole.json": {"name": "EXAMPLE"}, "datasets.json": [{"dataset_id": "source"}],
            "package_manifest.json": {"content_fingerprint": "source-package"},
            "images_manifest.json": {"files": []},
            "scalar_manifest.json": [{"file": raw.name, "sha256": sha(raw), "nbytes": raw.stat().st_size}],
        })
        for name, value in metadata.items():
            (raw.parent / name).write_bytes(encoded(value))
        inventory = importlib.import_module("processing.1_inventory")
        inventory.inventory_hole("EXAMPLE")
        before = read(next(settings.prepared_dir.rglob("1_inventory.json")))
        alternate_raw = self.root / "another-raw"
        shutil.copytree(settings.raw_dir, alternate_raw)
        settings.raw_dir = alternate_raw
        settings.work_dir = self.root / "another-work"
        inventory.inventory_hole("EXAMPLE")
        after = read(next(settings.prepared_dir.rglob("1_inventory.json")))
        self.assertEqual(before, after)

    def test_traversal_and_overlapping_output_are_rejected(self):
        root = next(key for key in settings.local_roots if key.startswith("raw_"))
        for ref in ("../outside", f"@{root}/../outside", str(self.root / "outside")):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                local_location(ref)
        args = StepParser().parse_args(["--work-dir", str(settings.raw_dir / "outputs")])
        with self.assertRaisesRegex(ValueError, "cannot overlap"):
            configure(args)

    def test_dsn_can_connect_without_a_runtime_config(self):
        with patch.dict(os.environ, {"ETL4_INGEST_DSN": "host=localhost user=fixture"}), patch.object(
            db, "config", side_effect=AssertionError("config file read")
        ), patch.object(db.psycopg, "connect") as connect:
            db.connection("ingest")
        self.assertEqual(connect.call_args.kwargs["dbname"], "etl4_local_fixture")

    def test_new_work_dir_receives_contract_evidence_without_overwriting_changes(self):
        prepare_contract_evidence(settings.media_evidence_dir)
        target = settings.media_evidence_dir / "official/NVCLDataSvcDao.java"
        self.assertEqual(sha(target), sha(DATABASE / "media_evidence/official" / target.name))
        self.assertEqual({p.name for p in target.parent.iterdir()},
                         {p.name for p in (DATABASE / "media_evidence/official").iterdir() if p.is_file()})
        prepare_contract_evidence(settings.media_evidence_dir)
        target.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            prepare_contract_evidence(settings.media_evidence_dir)

    def test_existing_instance_config_cannot_start_a_new_cluster(self):
        settings.db_config = self.root / "existing-instance.json"
        preflight = importlib.import_module("7_preflight_database")
        with patch.object(preflight, "command", side_effect=AssertionError("cluster command")), self.assertRaisesRegex(
            ValueError, "existing instance configuration"
        ):
            preflight.local_runtime("start")

    def test_explicit_config_reuses_instance_but_selects_batch_database(self):
        settings.db_config = self.root / "existing-instance.json"
        settings.db_config.write_bytes(encoded({"database": "old-db", "host": "127.0.0.1", "port": 5432,
            "roles": {"reader": {"user": "fixture-reader", "password": "fixture-only"}}}))
        with patch.dict(os.environ, {}, clear=True), patch.object(db.psycopg, "connect") as connect:
            db.connection("reader")
        self.assertEqual(connect.call_args.kwargs["dbname"], "etl4_local_fixture")
        self.assertEqual(connect.call_args.kwargs["user"], "fixture-reader")

    def test_first_acceptance_works_for_single_and_multi_without_database(self):
        package, batch, _, _ = self.make_prepared_package(multi=True)
        with patch.object(db, "connection", side_effect=AssertionError("database used")), FileChecks() as checks:
            path, result = media.accept_prepared_package(package)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(read(path)["dataset_count"], 1)
        self.assertGreater(checks.cache_hits, 0)
        with patch.object(final, "make_final_context", return_value={"unit": {"source_dataset_id": "source-dataset"}}):
            items = final.load_final_inputs(batch)
        self.assertEqual(len(items), 1)
        link = items[0]["prepared_acceptance"]
        self.assertEqual(resolve_reference(link["report_path"]), path)
        self.assertEqual(link["content_sha256"], result["content_sha256"])
        self.assertEqual(link["package_sha256"], package["key"])
        self.assertFalse(settings.media_work_dir.exists())

    def test_first_acceptance_fails_for_missing_or_same_size_changed_raw(self):
        package, _, raw, _ = self.make_prepared_package()
        path, _ = media.accept_prepared_package(package)
        before = raw.stat()
        raw.write_bytes(b"value\n2\n")
        os.utime(raw, ns=(before.st_atime_ns, before.st_mtime_ns))
        with FileChecks(), self.assertRaisesRegex(ValueError, "Raw files do not match"):
            media.accept_prepared_package(package)
        self.assertEqual(read(path)["status"], "failed")
        raw.unlink()
        with self.assertRaises(FileNotFoundError):
            media.accept_prepared_package(package)
        self.assertEqual(read(path)["status"], "failed")

    def test_first_acceptance_requires_actual_npz_axis_in_inventory(self):
        package, _, _, folder = self.make_prepared_package()
        self.assertTrue((folder / "4_sample_axis.npz").is_file())
        self.assertFalse((folder / "4_sample_axis.parquet").exists())
        _, accepted = media.accept_prepared_package(package)
        self.assertEqual(accepted["status"], "passed")
        package["datasets"]["dataset"]["unit"]["prepared_hashes"].pop("4_sample_axis.npz")
        with self.assertRaisesRegex(ValueError, "missing required outputs"):
            media.accept_prepared_package(package)

    def test_failed_processing_report_cannot_pass_first_acceptance(self):
        package, _, _, _ = self.make_prepared_package(report_status="failed")
        with self.assertRaisesRegex(ValueError, "preparation report failed"):
            media.accept_prepared_package(package)

    def test_mixed_dataset_context_and_changed_prepared_file_are_rejected(self):
        package, _, _, folder = self.make_prepared_package()
        package["datasets"]["dataset"]["unit"]["source_axis_id"] = "foreign-axis"
        with self.assertRaisesRegex(ValueError, "differ in dataset, version, or sample axis"):
            media.accept_prepared_package(package)
        package["datasets"]["dataset"]["unit"]["source_axis_id"] = "axis"
        (folder / "4_image_frames.json").write_bytes(b"[1]\n")
        with self.assertRaisesRegex(ValueError, "Prepared artifact changed"):
            media.accept_prepared_package(package)

    def test_missing_or_stale_first_acceptance_stops_before_database(self):
        package, batch, _, _ = self.make_prepared_package()
        with patch.object(final_entry, "connection", side_effect=AssertionError("database used")), self.assertRaisesRegex(
            ValueError, "First local acceptance is missing"
        ):
            final_entry.run_final_import(batch)
        self.assertEqual(read(settings.reports_dir / "local_acceptance_2.json")["status"], "failed")
        path, accepted = media.accept_prepared_package(package)
        accepted["content_sha256"] = "stale"
        path.write_bytes(encoded(accepted))
        with self.assertRaisesRegex(ValueError, "does not match the current inputs"):
            final.load_final_inputs(batch)

    def test_second_receipt_binds_results_and_failure_replaces_latest_success(self):
        result = {"run_id": "fixture-run", "release_id": "release", "database": settings.dbname,
                  "prepared_acceptances": [{"package_sha256": "a" * 64, "content_sha256": "b" * 64,
                                             "report_path": "evidence/first.json"}],
                  "datasets": [{"dataset_id": "dataset"}], "checks": [{"status": "passed"}],
                  "dataset_contents": {"dataset": {"dataset_revision_id": "revision", "input_digest": "content"}}}
        with patch.object(final_entry, "import_checked_batch", return_value=result):
            final_entry.run_final_import({})
        path = settings.reports_dir / "local_acceptance_2.json"
        receipt = read(path)
        self.assertEqual(receipt["dataset_contents"], result["dataset_contents"])
        self.assertEqual(receipt["content_sha256"], digest(result["dataset_contents"]))
        self.assertEqual(receipt["prepared_acceptances"], result["prepared_acceptances"])
        with patch.object(final_entry, "import_checked_batch", side_effect=ValueError("fixture failure")), self.assertRaises(ValueError):
            final_entry.run_final_import({})
        self.assertEqual(read(path)["status"], "failed")
        self.assertTrue((path.parent / "local_acceptance_2_fixture-run.json").exists())

    def final_batch_items(self):
        return [
            {"dataset_id": name, "dataset_revision_id": "revision-" + name,
             "input_digest": "content-" + name,
             "unit": {"hole_id": "EXAMPLE", "source_dataset_id": name},
             "prepared_acceptance": {"package_sha256": "package", "content_sha256": "accepted",
                                     "report_path": "evidence/first.json"}}
            for name in ("one", "two")
        ]

    def final_batch_connection(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn

        def execute(sql, *args):
            cursor = MagicMock()
            if "pg_try_advisory_lock" in sql:
                cursor.fetchone.return_value = {"ok": True}
            elif "FROM core.active_release" in sql:
                cursor.fetchone.return_value = {"release_id": "previous"}
            return cursor

        conn.execute.side_effect = execute
        return conn

    def test_final_entry_commits_each_dataset_before_publishing(self):
        items = self.final_batch_items()
        conn = self.final_batch_connection()
        imported = [{"dataset_id": item["dataset_id"], "action": "inserted"} for item in items]
        checks = [{"status": "passed", "dataset_revision_id": item["dataset_revision_id"]} for item in items]

        def publish(*args):
            self.assertEqual(conn.transaction.call_count, 2)
            exits = conn.transaction.return_value.__exit__.call_args_list
            self.assertEqual([call.args for call in exits], [(None, None, None), (None, None, None)])
            self.assertEqual(args[3], checks)
            self.assertEqual(args[6], imported)
            return "release"

        with patch.object(final_entry, "load_final_inputs", return_value=items), \
                patch.object(final_entry, "connection", return_value=conn), \
                patch.object(final_entry, "assert_schema"), patch.object(final_entry, "insert"), \
                patch.object(final_entry, "schema_hash", return_value="schema"), \
                patch.object(final_entry, "import_final_dataset", side_effect=imported), \
                patch.object(final_entry, "verify_final_dataset", side_effect=checks), \
                patch.object(final_entry, "publish_final_batch", side_effect=publish) as publisher:
            result = final_entry.run_final_import({})
        publisher.assert_called_once()
        self.assertEqual(result["datasets"], imported)
        self.assertEqual(len(result["prepared_acceptances"]), 1)
        self.assertEqual(read(settings.reports_dir / "local_acceptance_2.json")["status"], "passed")
        self.assertIn("pg_advisory_unlock", conn.execute.call_args.args[0])

    def test_final_entry_failed_dataset_rolls_back_and_does_not_publish(self):
        items = self.final_batch_items()
        conn = self.final_batch_connection()
        imported = [{"dataset_id": item["dataset_id"], "action": "inserted"} for item in items]
        failure = ValueError("second dataset verification failed")
        with patch.object(final_entry, "load_final_inputs", return_value=items), \
                patch.object(final_entry, "connection", return_value=conn), \
                patch.object(final_entry, "assert_schema"), patch.object(final_entry, "insert"), \
                patch.object(final_entry, "schema_hash", return_value="schema"), \
                patch.object(final_entry, "import_final_dataset", side_effect=imported), \
                patch.object(final_entry, "verify_final_dataset", side_effect=[{"status": "passed"}, failure]), \
                patch.object(final_entry, "publish_final_batch") as publisher:
            with self.assertRaisesRegex(ValueError, "second dataset verification failed"):
                final_entry.run_final_import({})
        exits = conn.transaction.return_value.__exit__.call_args_list
        self.assertEqual(exits[0].args, (None, None, None))
        self.assertEqual(exits[1].args[:2], (ValueError, failure))
        publisher.assert_not_called()
        failed = [call for call in conn.execute.call_args_list if "status='failed'" in call.args[0]]
        self.assertEqual(failed[0].args[1][0].obj["completed_datasets"], imported[:1])
        self.assertIn("pg_advisory_unlock", conn.execute.call_args.args[0])
        self.assertEqual(read(settings.reports_dir / "local_acceptance_2.json")["status"], "failed")

    def test_final_publication_failure_does_not_update_latest_manifest(self):
        conn = self.final_batch_connection()
        failure = OSError("asset manifest cannot be saved")
        with patch.object(final_entry, "stage_release", return_value="release"), \
                patch.object(final_entry, "install_composites"), patch.object(final_entry, "verify_composites"), \
                patch.object(final_entry, "publish_release", side_effect=failure), \
                patch.object(final_entry, "read") as reader, patch.object(final_entry, "write") as writer:
            with self.assertRaisesRegex(OSError, "asset manifest cannot be saved"):
                final_entry.publish_final_batch(conn, [], {"succession_decisions": {}}, [], "previous", "run", [])
        self.assertEqual(conn.transaction.return_value.__exit__.call_args.args[:2], (OSError, failure))
        conn.execute.assert_not_called()
        reader.assert_not_called()
        writer.assert_not_called()

    def test_numbered_help_exposes_same_local_configuration(self):
        entries = sorted(p for directory in (DATABASE, SOURCE_ROOT / "processing")
                         for p in directory.glob("*.py") if p.name.split("_")[0].isdigit())
        for path in entries:
            with self.subTest(entry=path.name):
                result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(path), "--help"],
                                        capture_output=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                for option in ("--raw-dir", "--work-dir", "--dbname", "--db-config"):
                    self.assertIn(option, result.stdout)


if __name__ == "__main__":
    unittest.main()
