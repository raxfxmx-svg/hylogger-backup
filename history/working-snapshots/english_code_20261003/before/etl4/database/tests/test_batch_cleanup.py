"""Use small temporary files to test previews, receipt boundaries, shared references, and precise cleanup."""

import base64
import copy
import gzip
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]

from _batch_files import DATA_TABLES, KNOWN_TABLES, file_info, object_key, write_json
from _db_files import digest, sha

cleanup = importlib.import_module("41_cleanup_batch")


def make_export(directory, asset, label, complete=True, representation="canonical"):
    directory.mkdir(parents=True)
    (directory / "tables").mkdir()
    files, tables = {}, {}
    for name in DATA_TABLES:
        relative = f"tables/{name}.jsonl.gz"
        path = directory / relative
        rows = [{"id": label + "-asset", "dataset_revision_id": "revision-" + label,
                 "sha256": sha(asset), "byte_size": asset.stat().st_size, "representation": representation}] if name == "asset" else []
        content = "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")
        path.write_bytes(gzip.compress(content, mtime=0))
        info = file_info(path, "table")
        files[relative] = info
        tables[name] = {"path": relative, "rows": len(rows), "columns": ["id"], "primary_key": ["id"],
                        "encoding": "postgres-jsonl-gzip", **info}
    datasets = [{"dataset_id": label, "dataset_revision_id": "revision-" + label, "input_digest": "d" * 64}]
    identity = {"format": "etl4-batch-v1", "datasets": datasets, "schema_migrations": {}}
    schema = {"tables": {name: {"columns": [{"column_name": "id", "data_type": "text", "nullable": False}],
                                "primary_key": ["id"]} for name in KNOWN_TABLES}, "migrations": []}
    manifest = {"format": "etl4-batch-v1", "batch_id": digest(identity), "identity": identity,
                "datasets": datasets, "schema": schema, "tables": tables, "files": files,
                "assets": [{"asset_id": label + "-asset", "dataset_revision_id": "revision-" + label,
                            "sha256": sha(asset), "byte_size": asset.stat().st_size, "media_type": "application/octet-stream",
                            "object_key": object_key(sha(asset))}]}
    write_json(directory / "manifest.json", manifest)
    manifest_sha = sha(directory / "manifest.json")
    sources = {row["object_key"]: {"path": str(asset), "sha256": row["sha256"], "byte_size": row["byte_size"]}
               for row in manifest["assets"]}
    write_json(directory / "local_sources.json", {"batch_id": manifest["batch_id"], "manifest_sha256": manifest_sha,
                                                  "objects": sources})
    if complete:
        expected = cleanup.expected_upload_objects(directory, manifest, manifest_sha, "etl4")
        objects = [{"object_key": key, "sha256": value[0], "byte_size": value[1], "checksum_algorithm": "SHA256",
                    "checksum_type": "FULL_OBJECT", "checksum": base64.b64encode(bytes.fromhex(value[0])).decode()}
                   for key, value in expected.items()]
        uploaded = {"format": "etl4-batch-upload-v1", "status": "complete", "batch_id": manifest["batch_id"],
                    "manifest_sha256": manifest_sha, "bucket": "test-bucket", "region": "test-region", "prefix": "etl4",
                    "expected_objects": len(expected), "completed_objects": len(expected), "objects": objects}
        write_json(directory / "upload_receipt.json", uploaded)
        target = {"host": "test-host", "port": 5432, "dbname": "test-cloud"}
        merged = {"format": "etl4-batch-merge-v1", "status": "complete", "batch_id": manifest["batch_id"],
                  "manifest_sha256": manifest_sha, "upload_receipt_sha256": sha(directory / "upload_receipt.json"),
                  "bucket": uploaded["bucket"], "region": uploaded["region"], "prefix": uploaded["prefix"],
                  "cloud_target": {**target, "fingerprint": digest(target)}, "release_id": "release", "datasets": datasets,
                  "active_release_changed": False}
        write_json(directory / "merge_receipt.json", merged)
    return manifest, manifest_sha


class BatchCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"
        self.exports = self.work / "exports"
        self.export = self.exports / "first"
        self.work.mkdir()
        self.asset = self.work / "asset.bin"
        self.asset.write_bytes(b"small source bytes")
        self.manifest, self.manifest_sha = make_export(self.export, self.asset, "first")

    def tearDown(self):
        self.temporary.cleanup()

    def run_cleanup(self, **kwargs):
        return cleanup.cleanup_batch(self.export, self.exports, self.work, **kwargs)

    def change_merge(self, **changes):
        path = self.export / "merge_receipt.json"
        value = json.loads(path.read_text())
        value.update(changes)
        write_json(path, value)

    def temporary_list(self, path):
        destination = self.export / "cleanup_files.json"
        write_json(destination, {"format": "etl4-batch-cleanup-files-v1", "batch_id": self.manifest["batch_id"],
                                 "manifest_sha256": self.manifest_sha,
                                 "files": [{"path": str(path), **file_info(path, "temporary")}]})
        return destination

    def test_default_preview_does_not_delete_any_file(self):
        before = {path: path.read_bytes() for path in self.export.rglob("*") if path.is_file()}
        result = self.run_cleanup()
        self.assertEqual(result["status"], "preview")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(self.asset.exists())
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_apply_deletes_only_listed_asset_and_keeps_export_evidence(self):
        unrelated = self.work / "unlisted.bin"
        unrelated.write_bytes(b"keep")
        result = self.run_cleanup(apply=True)
        self.assertEqual(result["status"], "complete")
        self.assertFalse(self.asset.exists())
        self.assertTrue(unrelated.exists())
        for path in self.manifest["files"]:
            self.assertTrue((self.export / path).exists())
        self.assertTrue((self.export / "manifest.json").exists())
        self.assertTrue((self.export / "local_sources.json").exists())
        self.assertTrue((self.export / "upload_receipt.json").exists())
        self.assertTrue((self.export / "merge_receipt.json").exists())
        self.assertEqual(result["deleted_bytes"], len(b"small source bytes"))

    def test_repeat_cleanup_accepts_already_removed_files(self):
        self.run_cleanup(apply=True)
        result = self.run_cleanup(apply=True)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["deleted"], [])

    def test_raw_asset_inside_work_still_requires_raw_opt_in(self):
        package = self.exports / "raw-copy"
        make_export(package, self.asset, "raw-copy", representation="raw")
        result = cleanup.cleanup_batch(package, self.exports, self.work, apply=True)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(self.asset.exists())

    def test_evidence_asset_is_retained_even_without_report_filename(self):
        package = self.exports / "evidence"
        make_export(package, self.asset, "evidence", representation="evidence")
        result = cleanup.cleanup_batch(package, self.exports, self.work, apply=True)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(self.asset.exists())

    def test_upload_without_merge_receipt_cannot_delete(self):
        (self.export / "merge_receipt.json").unlink()
        with self.assertRaises(OSError):
            self.run_cleanup(apply=True)
        self.assertTrue(self.asset.exists())

    def test_partial_or_wrong_merge_receipt_cannot_delete(self):
        original = (self.export / "merge_receipt.json").read_bytes()
        for changes in ({"status": "partial"}, {"batch_id": "0" * 64}, {"manifest_sha256": "0" * 64},
                        {"upload_receipt_sha256": "0" * 64}, {"bucket": "another"}, {"datasets": []}):
            with self.subTest(changes=changes):
                (self.export / "merge_receipt.json").write_bytes(original)
                self.change_merge(**changes)
                with self.assertRaises(ValueError):
                    self.run_cleanup(apply=True)
                self.assertTrue(self.asset.exists())

    def test_cloud_target_fingerprint_must_match(self):
        self.change_merge(cloud_target={"host": "test-host", "port": 5432, "dbname": "different", "fingerprint": "0" * 64})
        with self.assertRaisesRegex(ValueError, 'fingerprint'):
            self.run_cleanup(apply=True)

    def test_complete_upload_must_cover_all_objects(self):
        path = self.export / "upload_receipt.json"
        value = json.loads(path.read_text())
        value["objects"].pop()
        write_json(path, value)
        self.change_merge(upload_receipt_sha256=sha(path))
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            self.run_cleanup(apply=True)
        self.assertTrue(self.asset.exists())

    def test_raw_retained_without_both_explicit_options(self):
        raw = self.root / "raw"
        raw.mkdir()
        moved = raw / self.asset.name
        self.asset.rename(moved)
        path = self.export / "local_sources.json"
        mapping = json.loads(path.read_text())
        next(iter(mapping["objects"].values()))["path"] = str(moved)
        write_json(path, mapping)
        result = self.run_cleanup(raw_root=raw, apply=True)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(moved.exists())
        with self.assertRaisesRegex(ValueError, "include-raw"):
            self.run_cleanup(include_raw=True, apply=True)
        result = self.run_cleanup(raw_root=raw, include_raw=True, apply=True)
        self.assertEqual(len(result["deleted"]), 1)
        self.assertFalse(moved.exists())
        self.assertTrue(raw.exists())

    def test_shared_pending_batch_keeps_its_files(self):
        make_export(self.exports / "second", self.asset, "second", complete=False)
        result = self.run_cleanup(apply=True)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["deleted"], [])
        self.assertTrue(self.asset.exists())
        self.assertIn('incomplete', result["kept"][0]["reason"])

    def test_completed_other_batch_allows_same_source_cleanup(self):
        make_export(self.exports / "second", self.asset, "second", complete=True)
        self.assertEqual(len(self.run_cleanup(apply=True)["deleted"]), 1)

    def test_damaged_other_registry_mapping_blocks_all_deletes(self):
        other = self.exports / "second"
        make_export(other, self.asset, "second", complete=False)
        (other / "local_sources.json").write_text("{broken", encoding="utf-8")
        preview = self.run_cleanup()
        self.assertEqual(preview["status"], "blocked")
        with self.assertRaisesRegex(ValueError, 'not deleted'):
            self.run_cleanup(apply=True)
        self.assertTrue(self.asset.exists())

    def test_own_batch_must_be_under_registered_root(self):
        wrong = self.root / "other"
        wrong.mkdir()
        with self.assertRaisesRegex(ValueError, 'registry'):
            cleanup.cleanup_batch(self.export, wrong, self.work, apply=True)

    def test_explicit_temporary_list_only_cleans_proven_file(self):
        temporary = self.work / "temporary.bin"
        temporary.write_bytes(b"temporary")
        list_path = self.temporary_list(temporary)
        preview = self.run_cleanup()
        self.assertNotIn(str(temporary), [row["path"] for row in preview["candidates"]])
        result = self.run_cleanup(temporary_list=list_path, apply=True)
        self.assertEqual(len(result["deleted"]), 2)
        self.assertFalse(temporary.exists())

    def test_pending_other_temporary_reference_is_respected(self):
        other = self.exports / "second"
        manifest, manifest_sha = make_export(other, self.asset, "second", complete=False)
        write_json(other / "cleanup_files.json", {"format": "etl4-batch-cleanup-files-v1",
                    "batch_id": manifest["batch_id"], "manifest_sha256": manifest_sha,
                    "files": [{"path": str(self.asset), **file_info(self.asset, "temporary")}]})
        result = self.run_cleanup(apply=True)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(self.asset.exists())

    def test_source_code_database_and_report_files_are_preserved(self):
        for relative in ("script.py", "pgdata/data.bin", "runtime/cache.bin", "acceptance_2.json"):
            path = self.work / relative
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"keep")
            list_path = self.temporary_list(path)
            result = self.run_cleanup(temporary_list=list_path)
            self.assertNotIn(str(path), [row["path"] for row in result["candidates"]])
        database = self.work / "custom_database"
        database.mkdir()
        (database / "PG_VERSION").write_text("17")
        path = database / "base.bin"
        path.write_bytes(b"database")
        list_path = self.temporary_list(path)
        self.assertNotIn(str(path), [row["path"] for row in self.run_cleanup(temporary_list=list_path)["candidates"]])

    def test_hardlinked_file_is_retained(self):
        linked = self.work / "linked.bin"
        os.link(self.asset, linked)
        result = self.run_cleanup(apply=True)
        self.assertEqual(result["deleted"], [])
        self.assertTrue(self.asset.exists())
        self.assertTrue(linked.exists())

    def test_reparse_path_blocks_apply(self):
        real_lstat = Path.lstat
        def changed(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if path == self.asset:
                values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                values["st_file_attributes"] = 0x400
                return types.SimpleNamespace(**values)
            return info
        with patch.object(Path, "lstat", changed):
            with self.assertRaisesRegex(ValueError, 'not deleted'):
                self.run_cleanup(apply=True)
        self.assertTrue(self.asset.exists())

    def test_file_replacement_after_preview_is_rejected(self):
        original = cleanup.delete_checked_file
        def replaced(row):
            target = Path(row["path"])
            replacement = target.with_suffix(".replacement")
            replacement.write_bytes(target.read_bytes())
            os.replace(replacement, target)
            original(row)
        with patch.object(cleanup, "delete_checked_file", side_effect=replaced):
            with self.assertRaisesRegex(ValueError, 'identity'):
                self.run_cleanup(apply=True)
        self.assertTrue(self.asset.exists())
        report = json.loads((self.export / "cleanup_report.json").read_text())
        self.assertEqual(report["status"], "partial")

    def test_same_size_and_mtime_tampering_is_rejected(self):
        previous = self.asset.stat()
        self.asset.write_bytes(b"small source byteX")
        os.utime(self.asset, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'not deleted'):
            self.run_cleanup(apply=True)
        self.assertTrue(self.asset.exists())

    def test_registry_change_before_deletion_stops_apply(self):
        original = cleanup.scan_registry
        count = [0]
        def changed(*args):
            references, controls, blockers = original(*args)
            count[0] += 1
            if count[0] == 2:
                references[self.asset] = ["new pending batch"]
            return references, controls, blockers
        with patch.object(cleanup, "scan_registry", side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'registry'):
                self.run_cleanup(apply=True)
        self.assertTrue(self.asset.exists())

    def test_help_is_offline_and_apply_is_explicit(self):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(DATABASE / "41_cleanup_batch.py"), "--help"],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--apply", result.stdout)
        self.assertIn("--exports-root", result.stdout)
        self.assertIn("--include-raw", result.stdout)

    def test_cleanup_report_does_not_replace_unrelated_existing_file(self):
        path = self.export / "cleanup_report.json"
        path.write_text('{"user_note":"keep"}', encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'not covered'):
            self.run_cleanup(apply=True)
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(self.asset.exists())


if __name__ == "__main__":
    unittest.main()
