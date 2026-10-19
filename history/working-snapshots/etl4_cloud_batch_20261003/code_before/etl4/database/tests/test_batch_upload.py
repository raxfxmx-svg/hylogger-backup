"""Check S3 receipt, reuse, failure receipts, and batch object scope offline without AWS credentials."""

import argparse
import base64
import contextlib
import copy
import gzip
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
import zlib

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]

from _batch_files import DATA_TABLES, KNOWN_TABLES, file_info, object_key, write_json
from _db_files import digest, sha

upload = importlib.import_module("39_upload_batch")
ops = upload.upload_tools()


class S3Error(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": str(code)}}
        super().__init__("simulated S3 failure")


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.parts = {}
        self.calls = []
        self.fail_key = None
        self.part_failure = None
        self.complete_failure = None
        self.race = False

    def store(self, key, data, metadata=None):
        self.objects[key] = {"ContentLength": len(data), "ChecksumType": "FULL_OBJECT",
                             "ChecksumCRC32": ops.crc32_text(zlib.crc32(data)),
                             "Metadata": metadata or {}, "ETag": "etag", "VersionId": "version"}

    def head_object(self, **kwargs):
        self.calls.append(("head", kwargs))
        assert kwargs["ChecksumMode"] == "ENABLED"
        if kwargs["Key"] not in self.objects:
            raise S3Error(404)
        return copy.deepcopy(self.objects[kwargs["Key"]])

    def put_object(self, **kwargs):
        self.calls.append(("put", kwargs["Key"]))
        assert kwargs["IfNoneMatch"] == "*"
        if kwargs["Key"] == self.fail_key:
            raise S3Error(403)
        data = b"".join(iter(lambda: kwargs["Body"].read(1024**2), b""))
        assert len(data) == kwargs["ContentLength"]
        assert kwargs["ChecksumCRC32"] == ops.crc32_text(zlib.crc32(data))
        if kwargs["Key"] in self.objects:
            raise S3Error(412)
        self.store(kwargs["Key"], data, kwargs["Metadata"])
        if self.race:
            raise S3Error(412)
        return {}

    def create_multipart_upload(self, **kwargs):
        self.calls.append(("create", kwargs))
        assert kwargs["ChecksumAlgorithm"] == "CRC32"
        assert kwargs["ChecksumType"] == "FULL_OBJECT"
        self.multipart = kwargs
        return {"UploadId": "upload"}

    def upload_part(self, **kwargs):
        self.calls.append(("part", kwargs["PartNumber"]))
        if self.part_failure == kwargs["PartNumber"]:
            raise S3Error("BadDigest")
        assert kwargs["ChecksumCRC32"] == ops.crc32_text(zlib.crc32(kwargs["Body"]))
        self.parts[kwargs["PartNumber"]] = kwargs["Body"]
        return {"ETag": "part-etag", "ChecksumCRC32": kwargs["ChecksumCRC32"]}

    def complete_multipart_upload(self, **kwargs):
        self.calls.append(("complete", kwargs))
        assert kwargs["IfNoneMatch"] == "*"
        assert kwargs["ChecksumType"] == "FULL_OBJECT"
        if self.complete_failure:
            raise S3Error(self.complete_failure)
        numbers = [part["PartNumber"] for part in kwargs["MultipartUpload"]["Parts"]]
        assert numbers == list(range(1, len(self.parts) + 1))
        data = b"".join(self.parts[number] for number in numbers)
        assert kwargs["MpuObjectSize"] == len(data)
        assert kwargs["ChecksumCRC32"] == ops.crc32_text(zlib.crc32(data))
        self.store(kwargs["Key"], data, self.multipart["Metadata"])
        return {}

    def abort_multipart_upload(self, **kwargs):
        self.calls.append(("abort", kwargs))
        self.parts.clear()
        return {}

    def get_object(self, **kwargs):
        raise AssertionError('Default uploads must not download objects')


class ObjectUploadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "data.bin"
        self.source.write_bytes(b"source bytes")
        self.client = FakeS3()

    def tearDown(self):
        self.temporary.cleanup()

    def send(self, **kwargs):
        return ops.upload_object(self.client, self.source, "bucket", "key", sha(self.source),
                                 self.source.stat().st_size, **kwargs)

    def test_new_object_server_checksum_then_head_without_get(self):
        progress = []
        result = self.send(progress=lambda sent, size: progress.append((sent, size)))
        self.assertFalse(result["reused"])
        self.assertEqual(result["checksum_type"], "FULL_OBJECT")
        self.assertEqual([call[0] for call in self.client.calls], ["head", "put", "head"])
        self.assertEqual(progress[-1], (12, 12))

    def test_matching_crc32_object_is_reused(self):
        self.client.store("key", self.source.read_bytes(), {"source-sha256": sha(self.source)})
        self.assertTrue(self.send()["reused"])
        self.assertEqual(len(self.client.calls), 1)

    def test_full_sha256_object_is_reused(self):
        self.client.store("key", self.source.read_bytes())
        head = self.client.objects["key"]
        del head["ChecksumCRC32"]
        head["ChecksumSHA256"] = base64.b64encode(bytes.fromhex(sha(self.source))).decode()
        self.assertEqual(self.send()["checksum_algorithm"], "SHA256")

    def test_metadata_etag_and_composite_cannot_replace_full_checksum(self):
        for checksum_type in (None, "COMPOSITE", "FULL_OBJECT"):
            with self.subTest(checksum_type=checksum_type):
                self.client.store("key", self.source.read_bytes(), {"source-sha256": sha(self.source)})
                self.client.objects["key"]["ChecksumType"] = checksum_type
                if checksum_type == "FULL_OBJECT":
                    del self.client.objects["key"]["ChecksumCRC32"]
                with self.assertRaises(ValueError):
                    self.send()
                self.assertFalse(any(name == "put" for name, _ in self.client.calls))

    def test_existing_size_checksum_and_identity_conflict_rejected(self):
        for field, value in (("ContentLength", 5), ("ChecksumCRC32", "wrong"),
                             ("Metadata", {"source-sha256": "0" * 64})):
            with self.subTest(field=field):
                self.client.store("key", self.source.read_bytes())
                self.client.objects["key"][field] = value
                with self.assertRaises(ValueError):
                    self.send()

    def test_source_tampering_same_size_and_mtime_detected_before_s3(self):
        expected = sha(self.source)
        before = self.source.stat()
        self.source.write_bytes(b"source byteX")
        os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'content'):
            ops.upload_object(self.client, self.source, "bucket", "key", expected, before.st_size)
        self.assertEqual(self.client.calls, [])

    def test_403_is_not_missing(self):
        with patch.object(self.client, "head_object", side_effect=S3Error(403)):
            with self.assertRaises(S3Error):
                self.send()
        self.assertFalse(any(name == "put" for name, _ in self.client.calls))

    def test_412_race_reuses_only_after_checksum_head(self):
        self.client.race = True
        self.assertTrue(self.send()["reused"])
        self.assertEqual([name for name, _ in self.client.calls], ["head", "put", "head"])

    def test_412_conflicting_object_is_not_reused(self):
        def conflict(**kwargs):
            self.client.store("key", b"wrong object")
            raise S3Error(412)
        with patch.object(self.client, "put_object", side_effect=conflict):
            with self.assertRaises(ValueError):
                self.send()

    def test_empty_object_uploads_as_put(self):
        self.source.write_bytes(b"")
        self.assertEqual(self.send()["byte_size"], 0)
        self.assertFalse(any(name == "create" for name, _ in self.client.calls))

    def test_multipart_uses_whole_checksum_and_consecutive_parts(self):
        self.source.write_bytes(b"a" * (5 * 1024**2) + b"last part")
        result = self.send(part_size=5 * 1024**2, multipart_threshold=1)
        self.assertFalse(result["reused"])
        self.assertEqual([value for name, value in self.client.calls if name == "part"], [1, 2])
        self.assertFalse(any(name == "abort" for name, _ in self.client.calls))

    def test_multipart_failure_aborts_and_does_not_publish(self):
        self.source.write_bytes(b"a" * (5 * 1024**2) + b"last part")
        self.client.part_failure = 2
        with self.assertRaises(S3Error):
            self.send(part_size=5 * 1024**2, multipart_threshold=1)
        self.assertTrue(any(name == "abort" for name, _ in self.client.calls))
        self.assertFalse(any(name == "complete" for name, _ in self.client.calls))
        self.assertNotIn("key", self.client.objects)

    def test_409_aborts_and_requires_retry_not_success(self):
        self.client.complete_failure = 409
        with self.assertRaises(S3Error):
            self.send(multipart_threshold=1)
        self.assertTrue(any(name == "abort" for name, _ in self.client.calls))
        self.assertNotIn("key", self.client.objects)

    def test_larger_than_single_put_limit_forces_multipart_without_large_fixture(self):
        size = 5 * 1024**3 + 1
        remote = {"sha256": "0" * 64, "byte_size": size}
        with patch.object(ops, "file_checks", return_value="checksum"), \
                patch.object(ops, "remote_object", side_effect=[None, remote]), \
                patch.object(ops, "upload_multipart") as multipart:
            ops.upload_object(self.client, self.source, "bucket", "key", "0" * 64, size,
                              multipart_threshold=10 * 1024**3)
        multipart.assert_called_once()

    def test_old_sdk_fails_before_upload(self):
        client = MagicMock()
        client.meta.service_model.operation_model.return_value.input_shape.members = {}
        with self.assertRaisesRegex(ValueError, 'upgrade'):
            ops.check_upload_sdk(client)
        client.put_object.assert_not_called()


class BatchUploadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.export = self.root / "export"
        self.export.mkdir()
        self.asset = self.root / "raw.bin"
        self.asset.write_bytes(b"asset bytes")
        (self.export / "tables").mkdir()
        files, tables = {}, {}
        for name in DATA_TABLES:
            relative = f"tables/{name}.jsonl.gz"
            table = self.export / relative
            rows = [{"id": "dataset"}] if name == "dataset" else []
            content = "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")
            table.write_bytes(gzip.compress(content, mtime=0))
            info = file_info(table, "table")
            files[relative] = info
            tables[name] = {"path": relative, "rows": len(rows), "columns": ["id"],
                            "primary_key": ["id"], "encoding": "postgres-jsonl-gzip", **info}
        schema_tables = {name: {"columns": [{"column_name": "id", "data_type": "text", "nullable": False}],
                               "primary_key": ["id"]} for name in KNOWN_TABLES}
        datasets = [{"dataset_id": "dataset", "dataset_revision_id": "revision", "input_digest": "d" * 64}]
        identity = {"format": "etl4-batch-v1", "datasets": datasets, "rule": "one", "schema_migrations": {}}
        self.manifest = {"format": "etl4-batch-v1", "batch_id": digest(identity), "identity": identity,
                         "files": files, "tables": tables,
                         "datasets": datasets, "schema": {"tables": schema_tables, "migrations": []},
                         "assets": [{"asset_id": "asset", "dataset_revision_id": "revision",
                                     "sha256": sha(self.asset), "byte_size": self.asset.stat().st_size,
                                     "media_type": "application/octet-stream", "object_key": object_key(sha(self.asset))}]}
        self.save_fixture()
        self.client = FakeS3()

    def tearDown(self):
        self.temporary.cleanup()

    def save_fixture(self):
        write_json(self.export / "manifest.json", self.manifest)
        self.sources = {"batch_id": self.manifest["batch_id"], "manifest_sha256": sha(self.export / "manifest.json"),
                        "objects": {item["object_key"]: {"path": str(self.asset), "sha256": item["sha256"],
                                                        "byte_size": item["byte_size"]}
                                    for item in self.manifest["assets"]}}
        write_json(self.export / "local_sources.json", self.sources)

    def send(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(upload, "upload_tools", return_value=ops):
            return upload.upload_batch(self.export, "bucket", "region", client=self.client, **kwargs)

    def expected_count(self):
        return len(self.manifest["files"]) + len(self.sources["objects"]) + 1

    def test_upload_scope_manifest_last_and_private_mapping_excluded(self):
        result = self.send()
        keys = [row["object_key"] for row in result["objects"]]
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(keys), self.expected_count())
        self.assertTrue(keys[0].startswith("etl4/objects/sha256/"))
        self.assertTrue(keys[-1].endswith("/manifest.json"))
        self.assertFalse(any("local_sources" in key or "raw.bin" in key for key in keys))
        self.assertEqual(result["completed_objects"], self.expected_count())

    def test_partial_progress_and_retry_reuses_completed_objects(self):
        expected_key = "etl4/batches/" + self.manifest["batch_id"] + "/" + self.sources["manifest_sha256"]
        self.client.fail_key = expected_key + "/" + sorted(self.manifest["files"])[0]
        with self.assertRaises(S3Error):
            self.send()
        partial = json.loads((self.export / "upload_receipt.json").read_text())
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(len(partial["objects"]), 1)
        self.assertEqual(partial["error_type"], "S3Error")
        self.assertNotIn("error", partial)
        self.client.fail_key = None
        result = self.send()
        self.assertTrue(result["objects"][0]["reused"])
        self.assertEqual(result["status"], "complete")

    def test_sealed_and_private_files_cannot_be_receipt(self):
        for path in (self.export / "manifest.json", self.export / "local_sources.json",
                     self.export / "tables/asset.jsonl.gz", self.asset):
            before = path.read_bytes()
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'overwrite'):
                self.send(receipt_path=path)
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.client.calls, [])

    def test_other_target_receipt_is_preserved(self):
        self.send()
        path = self.export / "upload_receipt.json"
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'another batch or upload target'):
            self.send(prefix="different")
        self.assertEqual(path.read_bytes(), before)

    def test_tampered_manifest_identity_rejected_before_upload(self):
        self.manifest["batch_id"] = "0" * 64
        self.save_fixture()
        with self.assertRaisesRegex(ValueError, 'ID'):
            self.send()
        self.assertEqual(self.client.calls, [])
        self.assertFalse((self.export / "upload_receipt.json").exists())

    def test_removing_table_from_manifest_cannot_upload_incomplete_batch(self):
        table = self.manifest["tables"].pop("scan_sample")
        self.manifest["files"].pop(table["path"])
        self.save_fixture()
        with self.assertRaises(ValueError):
            self.send()
        self.assertEqual(self.client.calls, [])
        self.assertFalse((self.export / "upload_receipt.json").exists())

    def test_incomplete_schema_cannot_upload(self):
        self.manifest["schema"]["tables"].pop("active_release")
        self.save_fixture()
        with self.assertRaises(ValueError):
            self.send()
        self.assertEqual(self.client.calls, [])

    def test_wrong_object_key_rejected_before_upload(self):
        self.manifest["assets"][0]["object_key"] = "objects/other"
        self.save_fixture()
        with self.assertRaisesRegex(ValueError, 'object key'):
            self.send()
        self.assertEqual(self.client.calls, [])

    def test_file_path_traversal_rejected_before_upload(self):
        self.manifest['files']['tables/../../raw.bin'] = file_info(self.asset, 'table')
        self.save_fixture()
        with self.assertRaisesRegex(ValueError, 'path'):
            self.send()
        self.assertEqual(self.client.calls, [])

    def test_receipt_cannot_be_switched_to_another_batch(self):
        self.send()
        receipt_path = self.export / 'upload_receipt.json'
        before = receipt_path.read_bytes()
        self.manifest['identity']['rule'] = 'changed'
        self.manifest['batch_id'] = digest(self.manifest['identity'])
        self.save_fixture()
        with self.assertRaisesRegex(ValueError, 'another batch'):
            self.send()
        self.assertEqual(receipt_path.read_bytes(), before)

    def test_failed_final_receipt_write_does_not_leave_complete(self):
        from _batch_files import write_json as actual_write
        def fail_complete(path, value):
            if value.get('status') == 'complete':
                raise OSError('disk full')
            actual_write(path, value)
        with patch('_batch_files.write_json', side_effect=fail_complete):
            with self.assertRaises(OSError):
                self.send()
        value = json.loads((self.export / 'upload_receipt.json').read_text())
        self.assertEqual(value['status'], 'partial')
        self.assertEqual(len(value['objects']), self.expected_count())

    def test_missing_mapping_rejected_without_upload(self):
        self.sources["objects"] = {}
        write_json(self.export / "local_sources.json", self.sources)
        with self.assertRaisesRegex(ValueError, 'scope'):
            self.send()
        self.assertEqual(self.client.calls, [])

    def test_tampered_asset_changes_complete_receipt_to_partial_on_new_attempt(self):
        self.send()
        self.asset.write_bytes(b"asset byteX")
        with self.assertRaisesRegex(ValueError, 'content'):
            self.send()
        receipt = json.loads((self.export / "upload_receipt.json").read_text())
        self.assertEqual(receipt["status"], "partial")

    def test_same_asset_content_uploads_once(self):
        self.manifest["assets"].append({**self.manifest["assets"][0], "asset_id": "second"})
        self.save_fixture()
        self.assertEqual(self.send()["expected_objects"], self.expected_count())

    def test_help_does_not_need_aws_sdk(self):
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(DATABASE / "39_upload_batch.py"), "--help"],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--export-dir", result.stdout)
        self.assertIn("--raw-dir", result.stdout)

    def test_legacy_upload_uses_common_function_and_compatible_receipt(self):
        rows = {"raw.bin": {"source_key": "raw.bin", "sha256": sha(self.asset), "byte_size": self.asset.stat().st_size}}
        result = {"object_key": "old/raw.bin", "version_id": "version", "reused": False}
        saved = []
        sdk = types.SimpleNamespace(client=lambda *args, **kwargs: self.client)
        with patch.dict(sys.modules, {"boto3": sdk}), patch.object(ops, "assets", return_value=({}, rows)), \
                patch.object(ops, "DATA", self.root), patch.object(ops, "sha", return_value="manifest-hash"), \
                patch.object(ops, "check_upload_sdk"), patch.object(ops, "upload_object", return_value=result) as shared, \
                patch.object(ops, "save", side_effect=lambda name, row: saved.append(copy.deepcopy(row))), \
                contextlib.redirect_stdout(io.StringIO()):
            ops.upload(argparse.Namespace(prefix="old", bucket="bucket", region="region", workers=1))
        shared.assert_called_once()
        self.assertEqual(saved[0]["status"], "partial")
        self.assertEqual(saved[-1]["status"], "verified_remote")
        self.assertEqual(saved[-1]["transfer_status"], "complete")
        self.assertEqual(saved[-1]["objects"][0]["remote_sha256"], rows["raw.bin"]["sha256"])


if __name__ == "__main__":
    unittest.main()
