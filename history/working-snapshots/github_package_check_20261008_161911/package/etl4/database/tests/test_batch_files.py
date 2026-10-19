"""Content binding, path boundaries, and atomic writes for batch delivery manifests."""

import copy
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]

import _batch_files as batch
from _db_files import digest, encoded, sha
from _file_checks import FileChecks


class BatchFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="etl4_export_files_")
        self.folder = Path(self.temporary.name).resolve()
        self.directory = self.folder / "export"
        (self.directory / "tables").mkdir(parents=True)
        self.file = self.directory / "tables/dataset.jsonl.gz"
        self.file.write_bytes(gzip.compress(b'{"id":"dataset"}\n', mtime=0))
        self.raw = self.folder / "raw.f32"
        self.raw.write_bytes(b"fake-spectrum")
        dataset = {"dataset_id": "dataset", "dataset_revision_id": "revision", "input_digest": "d" * 64}
        identity = {"format": batch.FORMAT, "schema_migrations": {}, "datasets": [dataset]}
        files, tables = {}, {}
        for name in batch.DATA_TABLES:
            relative = f"tables/{name}.jsonl.gz"
            path = self.directory / relative
            if name != "dataset":
                path.write_bytes(gzip.compress(b"", mtime=0))
            info = batch.file_info(path, "table")
            files[relative] = info
            tables[name] = {**info, "path": relative, "rows": int(name == "dataset")}
        self.manifest = {"format": batch.FORMAT, "identity": identity, "batch_id": digest(identity),
                         "datasets": [dict(dataset)],
                         "schema": {"tables": {name: {} for name in batch.KNOWN_TABLES}, "migrations": []},
                         "tables": tables, "files": files,
                         "assets": [{"asset_id": "asset", "dataset_revision_id": "revision",
                                     "sha256": sha(self.raw), "byte_size": self.raw.stat().st_size,
                                     "media_type": "application/octet-stream", "object_key": batch.object_key(sha(self.raw))}]}
        self.save()

    def tearDown(self):
        self.temporary.cleanup()

    def save(self):
        batch.write_json(self.directory / "manifest.json", self.manifest)
        source = {"batch_id": self.manifest["batch_id"], "manifest_sha256": sha(self.directory / "manifest.json"),
                  "objects": {asset["object_key"]: {"path": str(self.raw), "sha256": asset["sha256"],
                              "byte_size": asset["byte_size"]} for asset in self.manifest["assets"]}}
        batch.write_json(self.directory / "local_sources.json", source)

    def test_export_can_be_checked_without_original_assets(self):
        self.raw.unlink()
        manifest, checksum = batch.load_export(self.directory)
        sources = batch.load_sources(self.directory, manifest, checksum)
        self.assertEqual(sources[self.manifest["assets"][0]["object_key"]]["path"], str(self.raw))
        self.assertNotIn(str(self.folder), (self.directory / "manifest.json").read_text(encoding="utf-8"))

    def test_same_content_assets_share_object_without_losing_asset_ids(self):
        second = {**self.manifest["assets"][0], "asset_id": "another-asset"}
        self.manifest["assets"].append(second)
        self.save()
        manifest, checksum = batch.load_export(self.directory)
        self.assertEqual(len(manifest["assets"]), 2)
        self.assertEqual(len(batch.load_sources(self.directory, manifest, checksum)), 1)

    def test_same_size_same_mtime_table_tampering_is_detected(self):
        with FileChecks():
            batch.load_export(self.directory)
        before = self.file.stat()
        data = bytearray(self.file.read_bytes())
        data[-1] ^= 1
        self.file.write_bytes(data)
        os.utime(self.file, ns=(before.st_atime_ns, before.st_mtime_ns))
        with FileChecks(), self.assertRaisesRegex(ValueError, 'content changed'):
            batch.load_export(self.directory)

    def test_manifest_identity_cannot_be_changed_without_new_batch_id(self):
        self.manifest["identity"]["rule"] = "changed"
        self.save()
        with self.assertRaisesRegex(ValueError, 'batch ID does not match its identity'):
            batch.load_export(self.directory)

    def test_private_paths_and_parent_traversal_cannot_be_uploaded(self):
        for path in ("local_sources.json", "upload_receipt.json", "tables/../../raw.f32", "tables/C:/secret", "tables/..\\secret"):
            with self.subTest(path=path):
                changed = copy.deepcopy(self.manifest)
                changed["files"][path] = changed["files"]["tables/dataset.jsonl.gz"]
                batch.write_json(self.directory / "manifest.json", changed)
                with self.assertRaises(ValueError):
                    batch.load_export(self.directory)

    def test_wrong_asset_membership_key_and_duplicates_are_rejected(self):
        for change in ({"dataset_revision_id": "other-batch"}, {"object_key": "objects/wrong"}, {"byte_size": -1}):
            with self.subTest(change=change):
                changed = copy.deepcopy(self.manifest)
                changed["assets"][0].update(change)
                batch.write_json(self.directory / "manifest.json", changed)
                with self.assertRaises(ValueError):
                    batch.load_export(self.directory)
        self.manifest["assets"].append(dict(self.manifest["assets"][0]))
        self.save()
        with self.assertRaisesRegex(ValueError, 'asset ID is missing or duplicated'):
            batch.load_export(self.directory)

    def test_table_entry_cannot_silently_point_to_other_file(self):
        self.manifest["tables"]["dataset"]["sha256"] = "e" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, 'data table digest does not match the file manifest'):
            batch.load_export(self.directory)

    def test_local_mapping_is_bound_to_this_exact_manifest(self):
        self.manifest["description"] = "new export metadata"
        batch.write_json(self.directory / "manifest.json", self.manifest)
        manifest, checksum = batch.load_export(self.directory)
        with self.assertRaisesRegex(ValueError, 'local path mapping belongs to another export'):
            batch.load_sources(self.directory, manifest, checksum)

    def test_dataset_scope_must_match_identity(self):
        self.manifest["datasets"][0]["input_digest"] = "e" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, 'dataset manifest does not match the batch identity'):
            batch.load_export(self.directory)

    def test_missing_table_is_rejected_even_if_file_inventory_also_omits_it(self):
        del self.manifest["tables"]["scan_sample"]
        del self.manifest["files"]["tables/scan_sample.jsonl.gz"]
        self.save()
        with self.assertRaisesRegex(ValueError, 'incomplete data table scope'):
            batch.load_export(self.directory)

    def test_missing_schema_table_is_rejected(self):
        del self.manifest["schema"]["tables"]["active_release"]
        self.save()
        with self.assertRaisesRegex(ValueError, 'database schema has an incomplete table scope'):
            batch.load_export(self.directory)

    def test_unlisted_table_file_is_rejected(self):
        relative = "tables/extra.jsonl.gz"
        (self.directory / relative).write_bytes(b"extra")
        self.manifest["files"][relative] = batch.file_info(self.directory / relative, "table")
        self.save()
        with self.assertRaisesRegex(ValueError, 'unlisted data tables'):
            batch.load_export(self.directory)

    def test_migration_file_must_match_schema_identity(self):
        (self.directory / "schema").mkdir()
        path = self.directory / "schema/001.sql"
        path.write_bytes(b"SELECT 1;")
        self.manifest["files"]["schema/001.sql"] = batch.file_info(path, "schema")
        self.manifest["schema"]["migrations"] = [{"name": "001.sql", "sha256": sha(path)}]
        self.save()
        with self.assertRaisesRegex(ValueError, 'migration manifest does not match the batch identity'):
            batch.load_export(self.directory)

    def test_mapping_cannot_add_an_unlisted_local_file(self):
        path = self.directory / "local_sources.json"
        source = json.loads(path.read_text(encoding="utf-8"))
        source["objects"]["unlisted"] = {"path": str(self.raw)}
        batch.write_json(path, source)
        manifest, checksum = batch.load_export(self.directory)
        with self.assertRaisesRegex(ValueError, 'local path mapping does not match the asset scope'):
            batch.load_sources(self.directory, manifest, checksum)

    def test_atomic_receipt_write_preserves_previous_on_failure(self):
        path = self.directory / "receipt.json"
        batch.write_json(path, {"status": "partial"})
        with patch.object(batch.os, "replace", side_effect=OSError("fixture failure")) as replace, \
                patch.object(batch.time, "sleep") as sleep, self.assertRaises(OSError):
            batch.write_json(path, {"status": "complete"})
        replace.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(batch.read_json(path), {"status": "partial"})
        self.assertEqual(list(self.directory.glob("receipt.json.*.tmp")), [])

    def test_atomic_receipt_write_retries_temporary_file_lock_then_replaces(self):
        path = self.directory / "receipt.json"
        batch.write_json(path, {"status": "partial"})
        original_replace, attempts = batch.os.replace, []

        def temporarily_locked(source, target):
            self.assertEqual(batch.read_json(path), {"status": "partial"})
            self.assertEqual(batch.read_json(source), {"status": "complete"})
            attempts.append(source)
            if len(attempts) < 3:
                raise PermissionError(13, "temporary fixture lock")
            return original_replace(source, target)

        with patch.object(batch.os, "replace", side_effect=temporarily_locked), patch.object(batch.time, "sleep") as sleep:
            batch.write_json(path, {"status": "complete"})
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(set(attempts)), 1)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.05, 0.15])
        self.assertEqual(batch.read_json(path), {"status": "complete"})
        self.assertEqual(list(self.directory.glob("receipt.json.*.tmp")), [])

    def test_persistent_permission_failure_is_bounded_and_preserves_old_file(self):
        path = self.directory / "receipt.json"
        batch.write_json(path, {"status": "partial"})
        previous = path.read_bytes()
        failure = PermissionError(13, "persistent fixture permission")
        with patch.object(batch.os, "replace", side_effect=failure) as replace, \
                patch.object(batch.time, "sleep") as sleep, self.assertRaises(PermissionError) as error:
            batch.write_json(path, {"status": "complete"})
        self.assertIs(error.exception, failure)
        self.assertEqual(replace.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.05, 0.15, 0.3])
        self.assertLessEqual(sum(call.args[0] for call in sleep.call_args_list), 1)
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(list(self.directory.glob("receipt.json.*.tmp")), [])

    def test_duplicate_json_keys_are_rejected(self):
        (self.directory / "manifest.json").write_bytes(b'{"format":"one","format":"two"}')
        with self.assertRaisesRegex(ValueError, 'duplicate key'):
            batch.load_export(self.directory)


if __name__ == "__main__":
    unittest.main()
