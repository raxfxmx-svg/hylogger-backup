"""Check S3 receipt, reuse, failure receipts, and batch object scope offline without AWS credentials."""

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
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import quote, unquote, urlsplit
import zlib

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]

from _batch_files import DATA_TABLES, KNOWN_TABLES, file_info, object_key, write_json
from _db_files import digest, sha

upload = importlib.import_module("39_upload_batch")
import _s3_upload as ops


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
        with contextlib.redirect_stdout(io.StringIO()):
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

    def test_current_batch_upload_runs_without_handoff_directory(self):
        # Copy current runtime files separately to verify that batch upload no longer depends on the old handoff directory.
        copied = self.root / "standalone" / "etl4"
        required = (
            "_settings.py", "_file_checks.py", "database/39_upload_batch.py",
            "database/_s3_upload.py", "database/_batch_files.py", "database/_db_files.py",
            "database/tests/test_batch_upload.py",
        )
        for relative in required:
            target = copied / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(DATABASE.parent / relative, target)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(copied / "database/tests/test_batch_upload.py"),
             "BatchUploadTests.test_upload_scope_manifest_last_and_private_mapping_excluded"],
            cwd=copied, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stderr)

    def test_parallel_workers_keep_manifest_last_and_receipt_writes_on_main_thread(self):
        original = ops.upload_object
        from _batch_files import write_json as actual_write
        gate = threading.Barrier(2)
        lock = threading.Lock()
        calls, worker_threads = [], set()
        main_thread = threading.get_ident()
        def parallel(*args, **kwargs):
            with lock:
                calls.append(args[3])
                first = len(calls) <= 2
                worker_threads.add(threading.get_ident())
            if first:
                gate.wait(timeout=5)
            return original(*args, **kwargs)
        def write_main(path, value):
            self.assertEqual(threading.get_ident(), main_thread)
            actual_write(path, value)
        with patch.object(ops, "upload_object", side_effect=parallel), patch("_batch_files.write_json", side_effect=write_main):
            result = self.send(workers=2)
        self.assertEqual(result["status"], "complete")
        self.assertTrue(calls[-1].endswith("/manifest.json"))
        self.assertGreaterEqual(len(worker_threads - {main_thread}), 2)
        self.assertEqual(result["objects"][-1]["kind"], "manifest")

    def test_parallel_failure_keeps_partial_and_does_not_upload_manifest(self):
        prefix = "etl4/batches/" + self.manifest["batch_id"] + "/" + self.sources["manifest_sha256"]
        self.client.fail_key = prefix + "/" + sorted(self.manifest["files"])[0]
        with self.assertRaises(S3Error):
            self.send(workers=4)
        receipt = json.loads((self.export / "upload_receipt.json").read_text())
        self.assertEqual(receipt["status"], "partial")
        self.assertFalse(any(key.endswith("/manifest.json") for key in self.client.objects))


class FakeSigner:
    def __init__(self):
        self.region = "ap-southeast-2"
        self.public_blocked = True
        self.calls = []

    def get_bucket_location(self, **kwargs):
        self.calls.append(("location", kwargs))
        return {"LocationConstraint": self.region}

    def get_public_access_block(self, **kwargs):
        self.calls.append(("public", kwargs))
        return {"PublicAccessBlockConfiguration": {key: self.public_blocked for key in
                ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")}}

    def generate_presigned_url(self, operation, **kwargs):
        self.calls.append((operation, kwargs))
        value = kwargs["Params"]
        return f"https://{value['Bucket']}.s3.{self.region}.amazonaws.com/{quote(value['Key'], safe='/')}?X-Amz-Signature=PRIVATE-TEST-SIGNATURE"


class FakeSignedHTTP:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.failure_key = None
        self.failure_method = None
        self.failure_status = 403
        self.failure_code = None
        self.force_race = False
        self.connections = []
        self.close_responses = False
        self.network_failures = 0
        self.response_hook = None

    def connection(self, *args, **kwargs):
        owner = self
        class Connection:
            def __init__(self):
                self.headers = {}
                self.body = bytearray()
                self.closed = False
                self.thread_ids = set()
                self.responses = []
                owner.connections.append(self)

            def putrequest(self, method, target):
                assert not self.closed
                self.headers, self.body = {}, bytearray()
                self.thread_ids.add(threading.get_ident())
                self.method, self.key = method, unquote(urlsplit(target).path)[1:]
                owner.calls.append((method, self.key))

            def putheader(self, key, value):
                self.headers[key.lower()] = value

            def endheaders(self):
                pass

            def send(self, value):
                self.body.extend(value)

            def getresponse(self):
                if owner.network_failures:
                    owner.network_failures -= 1
                    raise OSError("PRIVATE-TEST-SIGNATURE")
                if owner.response_hook:
                    owner.response_hook()
                headers, status, payload = {}, 200, b""
                if self.key == owner.failure_key and (owner.failure_method is None or self.method == owner.failure_method):
                    status = owner.failure_status
                    if owner.failure_code:
                        payload = (f"<Error><Code>{owner.failure_code}</Code>"
                                   "<Message>PRIVATE-TEST-SIGNATURE</Message><StringToSign>PRIVATE-TEST-SIGNATURE</StringToSign></Error>").encode()
                elif self.method == "HEAD":
                    assert self.headers["x-amz-checksum-mode"] == "ENABLED"
                    if self.key in owner.objects:
                        headers = owner.objects[self.key]
                    else:
                        status = 404
                else:
                    assert self.headers["if-none-match"] == "*"
                    assert int(self.headers["content-length"]) == len(self.body)
                    expected = base64.b64encode(hashlib.sha256(self.body).digest()).decode()
                    assert self.headers["x-amz-checksum-sha256"] == expected
                    if self.key in owner.objects:
                        status = 412
                    else:
                        owner.objects[self.key] = {"content-length": str(len(self.body)), "x-amz-checksum-type": "FULL_OBJECT",
                                                  "x-amz-checksum-sha256": expected, "etag": "etag"}
                        if owner.force_race:
                            status = 412
                stream = io.BytesIO(payload)
                self.responses.append(stream)
                return types.SimpleNamespace(status=status, read=stream.read, will_close=owner.close_responses,
                                             getheaders=lambda: list(headers.items()))

            def close(self):
                self.closed = True
        return Connection()


class SignedUploadTests(unittest.TestCase):
    save_fixture = BatchUploadTests.save_fixture
    tearDown = BatchUploadTests.tearDown

    def setUp(self):
        BatchUploadTests.setUp(self)
        self.signer = FakeSigner()
        self.http = FakeSignedHTTP()
        self.private = self.root / "upload_urls.private.json"

    def sign(self, **kwargs):
        return upload.sign_upload_urls(self.export, "test-bucket", "ap-southeast-2", "etl4", self.private,
                                       s3_client=self.signer, **kwargs)

    def send_signed(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), \
                patch.object(upload.http.client, "HTTPSConnection", side_effect=self.http.connection):
            return upload.upload_batch(self.export, "test-bucket", "ap-southeast-2", signed_urls=self.private, **kwargs)

    def test_signing_only_uses_public_export_and_restricted_checksum_headers(self):
        (self.export / "local_sources.json").unlink()
        result = self.sign()
        self.assertEqual(result["object_count"], len(self.manifest["files"]) + 2)
        calls = [value for name, value in self.signer.calls if name == "put_object"]
        self.assertTrue(all(row["Params"]["IfNoneMatch"] == "*" for row in calls))
        self.assertTrue(all(row["Params"]["ChecksumSHA256"] and row["Params"]["ContentType"] for row in calls))
        self.assertTrue(all(row["ExpiresIn"] == 21600 for row in calls))
        self.assertNotIn("objects", result)

    def test_region_public_access_and_account_checked_before_signing(self):
        self.signer.region = "wrong-region"
        with self.assertRaisesRegex(ValueError, 'region'):
            self.sign()
        self.signer.region = "ap-southeast-2"
        self.signer.public_blocked = False
        with self.assertRaisesRegex(ValueError, "Block Public Access"):
            self.sign()
        self.signer.public_blocked = True
        sts = types.SimpleNamespace(get_caller_identity=lambda: {"Account": "wrong"})
        with self.assertRaisesRegex(ValueError, 'account'):
            self.sign(expected_account="000000000000", sts_client=sts)
        self.assertFalse(any(name == "put_object" for name, _ in self.signer.calls))

    def test_signing_freezes_credentials_once_in_memory_for_all_urls(self):
        frozen = types.SimpleNamespace(access_key="PRIVATE-ACCESS-KEY", secret_key="PRIVATE-SECRET-KEY", token="PRIVATE-SESSION-TOKEN")
        credentials = MagicMock()
        credentials.get_frozen_credentials.return_value = frozen
        session = MagicMock()
        session.get_credentials.return_value = credentials
        sts = types.SimpleNamespace(get_caller_identity=lambda: {"Account": "000000000000"})
        session.client.side_effect = lambda name, **kwargs: self.signer if name == "s3" else sts
        sdk = types.SimpleNamespace(Session=lambda **kwargs: session)
        config = types.SimpleNamespace(Config=lambda **kwargs: kwargs)
        with patch.dict(sys.modules, {"boto3": sdk, "botocore": types.ModuleType("botocore"), "botocore.config": config}):
            result = upload.sign_upload_urls(self.export, "test-bucket", "ap-southeast-2", "etl4", self.private,
                                             expected_account="000000000000")
        session.get_credentials.assert_called_once()
        credentials.get_frozen_credentials.assert_called_once()
        self.assertEqual(session.client.call_count, 2)
        for call in session.client.call_args_list:
            self.assertEqual(call.kwargs["aws_access_key_id"], frozen.access_key)
            self.assertEqual(call.kwargs["aws_secret_access_key"], frozen.secret_key)
            self.assertEqual(call.kwargs["aws_session_token"], frozen.token)
        self.assertNotIn(frozen.access_key, self.private.read_text())
        self.assertNotIn(frozen.secret_key, self.private.read_text())
        self.assertNotIn(frozen.token, self.private.read_text())
        self.assertNotIn(frozen.secret_key, json.dumps(result))

    def test_signing_output_cannot_replace_manifest_private_map_or_receipt(self):
        for path in (self.export / "manifest.json", self.export / "local_sources.json", self.export / "upload_receipt.json"):
            before = path.read_bytes() if path.exists() else None
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                upload.sign_upload_urls(self.export, "test-bucket", "ap-southeast-2", "etl4", path, s3_client=self.signer)
            self.assertEqual(path.read_bytes() if path.exists() else None, before)

    def test_signed_mode_streams_native_sha256_and_finishes_same_receipt(self):
        self.sign()
        result = self.send_signed()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["objects"][-1]["kind"], "manifest")
        self.assertTrue(all(row["checksum_algorithm"] == "SHA256" for row in result["objects"]))
        self.assertNotIn("PRIVATE-TEST-SIGNATURE", json.dumps(result))
        self.assertTrue(all(method in ("HEAD", "PUT") for method, _ in self.http.calls))
        self.assertEqual(len(self.http.connections), 1)
        self.assertTrue(self.http.connections[0].closed)

    def test_signed_mode_parallel_upload_also_keeps_manifest_last(self):
        self.sign()
        result = self.send_signed(workers=16)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["workers"], 16)
        self.assertEqual(result["objects"][-1]["kind"], "manifest")
        puts = [key for method, key in self.http.calls if method == "PUT"]
        self.assertTrue(puts[-1].endswith("/manifest.json"))

    def test_expired_signature_leaves_partial_and_refreshed_signature_resumes(self):
        self.sign()
        document = json.loads(self.private.read_text())
        self.http.failure_key = document["objects"][1]["object_key"]
        with self.assertRaises(upload.SignedRequestError) as error:
            self.send_signed()
        self.assertNotIn("PRIVATE-TEST-SIGNATURE", str(error.exception))
        partial = json.loads((self.export / "upload_receipt.json").read_text())
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(len(partial["objects"]), 1)
        self.http.failure_key = None
        self.sign()
        result = self.send_signed()
        self.assertTrue(result["objects"][0]["reused"])
        self.assertEqual(result["status"], "complete")

    def test_signed_conditional_write_race_is_checked_by_head(self):
        self.sign()
        self.http.force_race = True
        result = self.send_signed()
        self.assertTrue(all(row["reused"] for row in result["objects"]))

    def test_signature_target_scope_and_manifest_binding_rejected(self):
        self.sign()
        original = self.private.read_bytes()
        for mutation in ("manifest", "domain", "key", "size", "missing"):
            value = json.loads(original)
            if mutation == "manifest":
                value["manifest_sha256"] = "0" * 64
            elif mutation == "domain":
                value["objects"][0]["put_url"] = value["objects"][0]["put_url"].replace("amazonaws.com", "example.com")
            elif mutation == "key":
                value["objects"][0]["head_url"] = value["objects"][0]["head_url"].replace("/objects/", "/different/")
            elif mutation == "size":
                value["objects"][0]["byte_size"] += 1
            else:
                value["objects"].pop()
            write_json(self.private, value)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError) as error:
                self.send_signed()
            self.assertNotIn("PRIVATE-TEST-SIGNATURE", str(error.exception))
        self.assertEqual(self.http.calls, [])

    def test_receipt_cannot_overwrite_signature_file(self):
        self.sign()
        before = self.private.read_bytes()
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            self.send_signed(receipt_path=self.private)
        self.assertEqual(self.private.read_bytes(), before)

    def test_large_file_rejected_before_signing_without_reading_large_data(self):
        self.manifest["assets"][0]["byte_size"] = upload.SINGLE_PUT_LIMIT + 1
        self.save_fixture()
        with self.assertRaisesRegex(ValueError, "5 GiB"):
            self.sign()
        self.assertEqual(self.signer.calls, [])

    def test_network_error_does_not_expose_private_url(self):
        self.sign()
        with contextlib.redirect_stdout(io.StringIO()), \
                patch.object(upload.http.client, "HTTPSConnection", side_effect=OSError("PRIVATE-TEST-SIGNATURE")), \
                patch.object(upload.time, "sleep"):
            with self.assertRaises(RuntimeError) as error:
                upload.upload_batch(self.export, "test-bucket", "ap-southeast-2", signed_urls=self.private)
        self.assertNotIn("PRIVATE-TEST-SIGNATURE", str(error.exception))
        self.assertEqual(json.loads((self.export / "upload_receipt.json").read_text())["status"], "partial")

    def signed_client(self):
        self.sign()
        document = json.loads(self.private.read_text())
        expected = upload.public_items(self.export, self.manifest, self.sources["manifest_sha256"], "etl4")
        identity = {name: document[name] for name in ("batch_id", "manifest_sha256", "bucket", "region", "prefix")}
        return upload.SignedS3Client(document, expected, identity), document["objects"][0]

    def test_safe_error_code_excludes_unknown_codes_message_and_xml_entities(self):
        self.assertEqual(upload.safe_s3_error_code(b'<Error><Code>ExpiredToken</Code><Message>secret</Message></Error>'), "ExpiredToken")
        self.assertEqual(upload.safe_s3_error_code(b'<Error xmlns="urn:test"><Code>BadDigest</Code></Error>'), "BadDigest")
        for payload in (b'<Error><Code>PRIVATE-TEST-SIGNATURE</Code></Error>', b'not xml',
                        b'<!DOCTYPE Error [<!ENTITY x "secret">]><Error><Code>&x;</Code></Error>'):
            self.assertIsNone(upload.safe_s3_error_code(payload))
        self.assertNotIn("PRIVATE-TEST-SIGNATURE", str(upload.SignedRequestError(403, "PRIVATE-TEST-SIGNATURE")))

    def test_put_error_receipt_reports_only_http_and_whitelisted_aws_code(self):
        self.sign()
        item = json.loads(self.private.read_text())["objects"][0]
        self.http.failure_key = item["object_key"]
        self.http.failure_method = "PUT"
        self.http.failure_code = "ExpiredToken"
        with self.assertRaises(upload.SignedRequestError) as error:
            self.send_signed()
        self.assertEqual(error.exception.status, 403)
        self.assertEqual(error.exception.aws_code, "ExpiredToken")
        self.assertEqual(len([call for call in self.http.calls if call[0] == "PUT"]), 1)
        receipt = json.loads((self.export / "upload_receipt.json").read_text())
        self.assertEqual(receipt["http_status"], 403)
        self.assertEqual(receipt["aws_error_code"], "ExpiredToken")
        self.assertEqual(receipt["failed_object"], item["object_key"])
        self.assertNotIn("PRIVATE-TEST-SIGNATURE", json.dumps(receipt))

    def test_put_retry_rewinds_stream_after_transient_service_failure(self):
        client, item = self.signed_client()
        body, received = io.BytesIO(b"complete payload"), []
        def response(method, row, headers, stream):
            received.append(stream.read())
            if len(received) == 1:
                raise upload.SignedRequestError(503, "SlowDown")
            return {"complete": True}
        with patch.object(client, "request_once", side_effect=response), patch.object(upload.time, "sleep") as sleep:
            result = client.request("PUT", item, {}, body)
        self.assertEqual(result, {"complete": True})
        self.assertEqual(received, [b"complete payload", b"complete payload"])
        sleep.assert_called_once_with(1)

    def test_http_400_expired_token_is_reported_without_retry_or_private_text(self):
        self.sign()
        self.http.failure_key = json.loads(self.private.read_text())["objects"][0]["object_key"]
        self.http.failure_method, self.http.failure_status, self.http.failure_code = "PUT", 400, "ExpiredToken"
        with patch.object(upload.time, "sleep") as sleep, self.assertRaises(upload.SignedRequestError) as error:
            self.send_signed()
        self.assertEqual((error.exception.status, error.exception.aws_code), (400, "ExpiredToken"))
        sleep.assert_not_called()
        receipt = json.loads((self.export / "upload_receipt.json").read_text())
        self.assertEqual((receipt["status"], receipt["http_status"], receipt["aws_error_code"]), ("partial", 400, "ExpiredToken"))
        self.assertNotIn("PRIVATE-TEST-SIGNATURE", json.dumps(receipt))
        self.assertTrue(all(connection.closed for connection in self.http.connections))

    def test_keep_alive_connections_are_isolated_between_threads_and_closed_together(self):
        client, item = self.signed_client()
        barrier = threading.Barrier(2)
        self.http.response_hook = lambda: barrier.wait(timeout=5)
        def check_missing():
            for _ in range(2):
                with self.assertRaises(upload.SignedRequestError):
                    client.request("HEAD", item, {"x-amz-checksum-mode": "ENABLED"})
        with patch.object(upload.http.client, "HTTPSConnection", side_effect=self.http.connection):
            with upload.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(check_missing) for _ in range(2)]
                for future in futures:
                    future.result()
        self.assertEqual(len(self.http.connections), 2)
        self.assertTrue(all(len(connection.thread_ids) == 1 for connection in self.http.connections))
        self.assertEqual(len(set.union(*(connection.thread_ids for connection in self.http.connections))), 2)
        self.assertFalse(any(connection.closed for connection in self.http.connections))
        client.close()
        self.assertTrue(all(connection.closed for connection in self.http.connections))

    def test_connection_close_response_prevents_reuse(self):
        client, item = self.signed_client()
        self.http.close_responses = True
        with patch.object(upload.http.client, "HTTPSConnection", side_effect=self.http.connection):
            for _ in range(2):
                with self.assertRaises(upload.SignedRequestError):
                    client.request("HEAD", item, {"x-amz-checksum-mode": "ENABLED"})
        self.assertEqual(len(self.http.connections), 2)
        self.assertTrue(all(connection.closed for connection in self.http.connections))
        client.close()

    def test_network_failure_discards_connection_before_retry(self):
        client, item = self.signed_client()
        self.http.network_failures = 1
        with patch.object(upload.http.client, "HTTPSConnection", side_effect=self.http.connection), \
                patch.object(upload.time, "sleep") as sleep:
            with self.assertRaises(upload.SignedRequestError) as error:
                client.request("HEAD", item, {"x-amz-checksum-mode": "ENABLED"})
        self.assertEqual(error.exception.status, 404)
        self.assertEqual(len(self.http.connections), 2)
        self.assertTrue(self.http.connections[0].closed)
        self.assertFalse(self.http.connections[1].closed)
        sleep.assert_called_once_with(1)
        client.close()

    def test_long_error_response_is_drained_before_connection_reuse(self):
        client, item = self.signed_client()
        self.http.failure_key, self.http.failure_status = item["object_key"], 404
        self.http.failure_code = "X" * 70000
        with patch.object(upload.http.client, "HTTPSConnection", side_effect=self.http.connection):
            for _ in range(2):
                with self.assertRaises(upload.SignedRequestError) as error:
                    client.request("HEAD", item, {})
                self.assertIsNone(error.exception.aws_code)
        self.assertEqual(len(self.http.connections), 1)
        self.assertTrue(all(stream.read() == b"" for stream in self.http.connections[0].responses))
        client.close()

    def test_network_retry_succeeds_and_service_retries_are_bounded(self):
        client, item = self.signed_client()
        with patch.object(client, "request_once", side_effect=[OSError("PRIVATE-TEST-SIGNATURE"), {"ok": True}]) as request, \
                patch.object(upload.time, "sleep"):
            self.assertEqual(client.request("HEAD", item, {}), {"ok": True})
            self.assertEqual(request.call_count, 2)
        with patch.object(client, "request_once", side_effect=upload.SignedRequestError(503, "ServiceUnavailable")) as request, \
                patch.object(upload.time, "sleep"):
            with self.assertRaises(upload.SignedRequestError):
                client.request("HEAD", item, {})
            self.assertEqual(request.call_count, 3)

    def test_403_and_412_are_not_retried(self):
        client, item = self.signed_client()
        for status, code in ((400, "ExpiredToken"), (403, "AccessDenied"), (412, "PreconditionFailed")):
            with self.subTest(status=status), patch.object(client, "request_once", side_effect=upload.SignedRequestError(status, code)) as request, \
                    patch.object(upload.time, "sleep") as sleep:
                with self.assertRaises(upload.SignedRequestError):
                    client.request("HEAD", item, {})
                request.assert_called_once()
                sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
