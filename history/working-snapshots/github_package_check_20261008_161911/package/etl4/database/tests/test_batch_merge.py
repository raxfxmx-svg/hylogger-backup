"""Test cloud merges with fake connections, without reading credentials or connecting to databases/AWS."""

import base64
import contextlib
import copy
import gzip
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent), str(DATABASE / "tests")]
from _batch_files import DATA_TABLES, file_info, load_export, write_json
from _db_files import digest, read
import test_batch_export as export_tests
from test_batch_export import uid

merge = importlib.import_module("40_merge_cloud_batch")


def query_text(query):
    return query.as_string() if hasattr(query, "as_string") else query


class StateConnection:
    """Simulate only transactions and ingest_run to establish that receipts report success after commit."""
    def __init__(self):
        self.info = MagicMock(host="cloud.example", port=5432, dbname="static_database")
        self.run = None
        self.events = []
        self.fail_commit = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @contextlib.contextmanager
    def transaction(self):
        saved = copy.deepcopy(self.run)
        self.events.append("begin")
        try:
            yield
            if self.fail_commit:
                self.fail_commit = False
                raise RuntimeError("commit failed")
            self.events.append("commit")
        except BaseException:
            self.run = saved
            self.events.append("rollback")
            raise

    def execute(self, query, parameters=()):
        query = query_text(query)
        self.events.append((query, parameters))
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        if "pg_try_advisory_lock" in query:
            result.fetchone.return_value = {"ok": True}
        elif "SELECT status,input_digest,detail FROM core.ingest_run" in query:
            result.fetchone.return_value = copy.deepcopy(self.run)
        elif "INSERT INTO core.ingest_run" in query:
            self.run = {"status": "running", "input_digest": parameters[1], "detail": copy.deepcopy(parameters[-1].obj)}
        elif query.startswith("UPDATE core.ingest_run"):
            self.run.update(status=parameters[0], detail=copy.deepcopy(parameters[2].obj))
        return result


class CloudBatchMergeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = export_tests.BatchExportTests(methodName="test_all_39_tables_are_classified_and_every_data_table_has_scope")
        self.fixture.setUp()
        self.directory = Path(self.fixture.run_export()["directory"])
        self.manifest, self.manifest_sha = load_export(self.directory)
        validation_path = self.directory / "evidence/revision_validation.json"
        value = read(validation_path)
        value["rows"][0]["verification_code_sha256"] = "f" * 64
        write_json(validation_path, value)
        self.manifest["files"]["evidence/revision_validation.json"] = file_info(validation_path, "evidence")
        write_json(self.directory / "manifest.json", self.manifest)
        self.manifest, self.manifest_sha = load_export(self.directory)
        self.upload = self.make_upload()
        self.upload_path = self.directory / "upload_receipt.json"
        write_json(self.upload_path, self.upload)
        self.conn = StateConnection()
        self.release = uid("cloud-candidate")

    def tearDown(self):
        self.fixture.tearDown()

    def make_upload(self):
        prefix = "etl4"
        base = f"{prefix}/batches/{self.manifest['batch_id']}/{self.manifest_sha}"
        entries = {item["object_key"]: {"sha256": item["sha256"], "byte_size": item["byte_size"], "kind": "asset", "object_key": prefix + "/" + item["object_key"]}
                   for item in self.manifest["assets"]}
        entries.update({name: {**info, "object_key": base + "/" + name} for name, info in self.manifest["files"].items()})
        entries["manifest.json"] = {**file_info(self.directory / "manifest.json", "manifest"), "object_key": base + "/manifest.json"}
        objects = [{**row, "source_key": key, "checksum_type": "FULL_OBJECT", "checksum_algorithm": "SHA256",
                    "checksum": base64.b64encode(bytes.fromhex(row["sha256"])).decode(), "reused": False}
                   for key, row in sorted(entries.items())]
        return {"format": "etl4-batch-upload-v1", "status": "complete", "batch_id": self.manifest["batch_id"],
                "manifest_sha256": self.manifest_sha, "bucket": "bucket-example", "region": "ap-southeast-2",
                "prefix": prefix, "expected_objects": len(objects), "completed_objects": len(objects), "objects": objects}

    @contextlib.contextmanager
    def pipeline(self, **overrides):
        defaults = {"ensure_schema": None, "load_staging": None, "check_staging_scope": None,
                    "check_source_identity": None, "insert_table": 1, "register_assets": None,
                    "record_validation": None, "accumulated_members": (self.manifest["identity"]["datasets"], [], []),
                    "stage_candidate": self.release, "members_of": self.manifest["identity"]["datasets"]}
        defaults.update(overrides)
        with contextlib.ExitStack() as stack:
            mocks = {}
            for name, value in defaults.items():
                mocks[name] = stack.enter_context(patch.object(merge, name, side_effect=value if callable(value) or isinstance(value, BaseException) else None,
                                                              return_value=None if callable(value) or isinstance(value, BaseException) else value))
            yield mocks

    def merge(self, **kwargs):
        return merge.merge_batch(self.directory, connect=lambda: self.conn, **kwargs)

    def test_cloud_connection_is_independent_and_does_not_load_local_config(self):
        dsn = "host=cloud.example dbname=static_database user=test sslmode=verify-full"
        with patch.dict(os.environ, {"ETL4_CLOUD_DSN": dsn}), patch.object(merge.psycopg, "connect") as connect, \
                patch("_db_common.config", side_effect=AssertionError("local config read")):
            merge.cloud_connection()
        self.assertEqual(connect.call_args.args, (dsn,))
        self.assertEqual(connect.call_args.kwargs["sslmode"], "verify-full")
        with self.assertRaisesRegex(ValueError, "ETL4_CLOUD_"):
            merge.cloud_connection("ETL4_ADMIN_DSN")

    def test_target_receipt_contains_only_stable_nonsecret_identity(self):
        target = merge.cloud_target(self.conn)
        self.assertEqual(target["fingerprint"], digest({"host": "cloud.example", "port": 5432, "dbname": "static_database"}))
        self.assertEqual(set(target), {"host", "port", "dbname", "fingerprint"})

    def test_upload_requires_complete_exact_object_scope(self):
        receipt, sha, objects = merge.upload_evidence(self.directory, self.manifest, self.manifest_sha, self.upload_path)
        self.assertEqual(receipt, self.upload)
        self.assertEqual(len(objects), self.upload["expected_objects"])
        self.assertEqual(sha, file_info(self.upload_path, "receipt")["sha256"])
        for change in ({"status": "partial"}, {"manifest_sha256": "0" * 64}, {"objects": self.upload["objects"][:-1]}):
            with self.subTest(change=list(change)):
                write_json(self.upload_path, {**self.upload, **change})
                with self.assertRaises(ValueError):
                    merge.upload_evidence(self.directory, self.manifest, self.manifest_sha, self.upload_path)

    def test_upload_receipt_rejects_metadata_only_or_changed_object(self):
        for field, value in (("checksum_type", "COMPOSITE"), ("object_key", "elsewhere"), ("checksum", "invalid")):
            receipt = copy.deepcopy(self.upload)
            receipt["objects"][0][field] = value
            write_json(self.upload_path, receipt)
            with self.subTest(field=field), self.assertRaises(ValueError):
                merge.upload_evidence(self.directory, self.manifest, self.manifest_sha, self.upload_path)

    def test_local_two_acceptances_and_display_identity_must_match(self):
        validations, _ = merge.local_acceptance_evidence(self.directory, self.manifest)
        self.assertEqual(set(validations), {self.fixture.revision})
        second_path = self.directory / "evidence/acceptance_2.json"
        second = read(second_path)
        second["status"] = "failed"
        write_json(second_path, second)
        with self.assertRaisesRegex(ValueError, 'second local acceptance does not correspond'):
            merge.local_acceptance_evidence(self.directory, self.manifest)

    def test_merge_commits_dataset_and_candidate_without_activating(self):
        with self.pipeline() as mocks:
            result = self.merge()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["database_commit"], "complete")
        self.assertEqual(result["datasets"], self.manifest["identity"]["datasets"])
        self.assertFalse(result["active_release_changed"])
        self.assertIsNone(result["finalized_release_id"])
        self.assertEqual(self.conn.run["status"], "staged")
        self.assertEqual(self.conn.events.count("commit"), 2)
        self.assertEqual(mocks["insert_table"].call_count, len(DATA_TABLES))
        self.assertFalse(any(isinstance(item, tuple) and "INSERT INTO core.active_release" in item[0] for item in self.conn.events))

    def test_merge_does_not_need_original_asset_files_or_private_mapping(self):
        (self.directory / "local_sources.json").unlink()
        self.fixture.asset_file.unlink()
        with self.pipeline():
            result = self.merge()
        self.assertEqual(result["status"], "complete")

    def test_failed_dataset_rolls_back_and_partial_receipt_cannot_cleanup(self):
        with self.pipeline(insert_table=RuntimeError("simulated insertion failure")), self.assertRaises(RuntimeError):
            self.merge()
        receipt = read(self.directory / "merge_receipt.json")
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["datasets"], [])
        self.assertIn("rollback", self.conn.events)
        self.assertEqual(self.conn.run["status"], "failed")

    def test_failed_commit_does_not_mark_dataset_completed(self):
        self.conn.fail_commit = True
        with self.pipeline(), self.assertRaises(RuntimeError):
            self.merge()
        self.assertEqual(read(self.directory / "merge_receipt.json")["datasets"], [])
        self.assertEqual(self.conn.run["detail"]["completed_datasets"], [])

    def test_candidate_failure_preserves_committed_dataset_for_resume(self):
        with self.pipeline(stage_candidate=RuntimeError("candidate failed")), self.assertRaises(RuntimeError):
            self.merge()
        self.assertEqual(self.conn.run["status"], "failed")
        self.assertEqual(self.conn.run["detail"]["completed_datasets"], self.manifest["identity"]["datasets"])
        with self.pipeline() as mocks:
            result = self.merge()
        self.assertEqual(result["status"], "complete")
        mocks["load_staging"].assert_not_called()
        mocks["insert_table"].assert_not_called()
        mocks["stage_candidate"].assert_called_once()

    def test_repeat_skips_existing_business_rows_and_keeps_candidate(self):
        with self.pipeline():
            first = self.merge()
        with self.pipeline() as mocks:
            second = self.merge()
        self.assertTrue(second["reused"])
        self.assertEqual(first["release_id"], second["release_id"])
        mocks["insert_table"].assert_not_called()
        mocks["load_staging"].assert_not_called()
        mocks["stage_candidate"].assert_not_called()

    def test_repeat_rejects_same_batch_different_business_files(self):
        with self.pipeline():
            self.merge()
        self.conn.run["detail"]["business_signature"] = "0" * 64
        with self.pipeline(), self.assertRaisesRegex(ValueError, 'different business files'):
            self.merge()

    def test_report_write_failure_after_commit_can_resume(self):
        actual_write = merge.write_json
        def fail_complete(path, value):
            if value.get("format") == "etl4-batch-merge-v1" and value.get("status") == "complete":
                raise OSError("disk full")
            return actual_write(path, value)
        with self.pipeline(), patch.object(merge, "write_json", side_effect=fail_complete), self.assertRaises(OSError):
            self.merge()
        self.assertEqual(self.conn.run["status"], "staged")
        self.assertEqual(read(self.directory / "merge_receipt.json")["status"], "partial")
        with self.pipeline() as mocks:
            result = self.merge()
        self.assertEqual(result["status"], "complete")
        mocks["insert_table"].assert_not_called()

    def test_finalize_is_only_called_for_explicit_selection_file(self):
        selection = self.directory / "final_selection.json"
        write_json(selection, {"datasets": [], "expected_active_release_id": None})
        with self.pipeline(), patch.object(merge, "finalize_release", return_value=(uid("final"), True)) as finalize:
            result = self.merge(finalize=selection)
        finalize.assert_called_once()
        self.assertTrue(result["active_release_changed"])
        self.assertEqual(result["finalized_release_id"], uid("final"))

    def test_new_revision_replaces_only_same_dataset_in_accumulated_candidate(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [{"release_id": uid("active")}, {"release_id": uid("recent")}]
        old = {"dataset_id": self.fixture.dataset, "dataset_revision_id": uid("old-media-version")}
        previous_batch = {"dataset_id": uid("previous-batch-dataset"), "dataset_revision_id": uid("previous-batch-revision")}
        with patch.object(merge, "members_of", side_effect=[[old], [old, previous_batch]]):
            members, sources, replacements = merge.accumulated_members(conn, self.manifest["identity"]["datasets"])
        self.assertEqual(len(members), 2)
        self.assertIn(previous_batch, members)
        self.assertEqual(next(item for item in members if item["dataset_id"] == self.fixture.dataset)["dataset_revision_id"], self.fixture.revision)
        self.assertEqual(len(replacements), 1)
        self.assertIn("equivalence not inferred", replacements[0]["basis"])

    def test_same_uuid_different_contents_is_rejected_before_insert(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"exists": 1}
        with self.assertRaisesRegex(ValueError, 'different content for the same primary key'):
            merge.insert_table(conn, "dataset_revision", self.fixture.revision, self.manifest)
        self.assertEqual(conn.execute.call_count, 1)

    def test_shared_identity_conflict_does_not_remap_uuids(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"exists": 1}
        with self.assertRaisesRegex(ValueError, 'different entity UUIDs'):
            merge.check_source_identity(conn, self.fixture.revision)

    def test_geometry_conflict_uses_ewkb_and_interval_insert_is_ordered(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        merge.insert_table(conn, "borehole_revision", self.fixture.revision, self.manifest)
        self.assertIn("ST_AsEWKB(t.collar_geom)", query_text(conn.execute.call_args_list[0].args[0]))
        conn.reset_mock()
        merge.insert_table(conn, "core_interval", self.fixture.revision, self.manifest)
        self.assertIn("CASE WHEN s.interval_kind='tray' THEN 0 ELSE 1 END", query_text(conn.execute.call_args_list[1].args[0]))

    def test_staging_sends_original_numeric_text_and_restores_ewkb(self):
        manifest = copy.deepcopy(self.manifest)
        self.fixture.records["dataset_revision"] = [{"id": self.fixture.revision}]
        table = "borehole_revision"
        path = self.directory / manifest["tables"][table]["path"]
        numeric = '{"id":"' + uid("metadata") + '","collar_geom":"0101000020E6100000","value":0.1234567890123456789012345}\n'
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            stream.write(numeric)
        manifest["tables"][table].update(columns=["id", "collar_geom", "value"], rows=1)
        manifest["schema"]["tables"][table]["columns"] = [{"column_name": name} for name in ("id", "collar_geom", "value")]
        conn = MagicMock()
        writer = conn.cursor.return_value.copy.return_value.__enter__.return_value
        merge.load_staging(conn, self.directory, manifest)
        self.assertTrue(any(call.args == (tuple([numeric.strip()]),) for call in writer.write_row.call_args_list))
        sqls = [query_text(call.args[0]) for call in conn.execute.call_args_list]
        self.assertTrue(any("ST_GeomFromEWKB(decode(j.payload->>'collar_geom','hex'))" in statement for statement in sqls))

    def test_asset_registration_uses_uploaded_s3_keys_only(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        objects = {item["source_key"]: item for item in self.upload["objects"]}
        merge.register_assets(conn, self.fixture.revision, self.manifest, objects, "s3_fixture")
        records = conn.execute.call_args_list[-1].args[1][0].obj
        self.assertEqual(records[0]["backend"], "s3")
        self.assertEqual(records[0]["access_status"], "verified_remote")
        self.assertEqual(records[0]["object_key"], "etl4/" + self.manifest["assets"][0]["object_key"])
        self.assertNotIn("path", records[0])

    def test_storage_root_cannot_be_reused_for_another_bucket(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [{"storage": {"root_key": "one", "bucket": "old"}}]
        with self.assertRaisesRegex(ValueError, 'another upload target'):
            merge.check_storage_root(conn, {"root_key": "one", "bucket": "new"})

    def test_finalize_requires_explicit_omissions_and_expected_pointer(self):
        member = {"dataset_id": self.fixture.dataset, "dataset_revision_id": self.fixture.revision}
        other = {"dataset_id": uid("other"), "dataset_revision_id": uid("other-revision")}
        conn = MagicMock()
        with patch.object(merge, "accumulated_members", return_value=([member, other], [], [])), self.assertRaisesRegex(ValueError, 'Finalize omits accumulated members'):
            merge.finalize_release(conn, self.manifest, {"datasets": [member], "expected_active_release_id": None}, [], self.fixture.composites)
        with self.assertRaisesRegex(ValueError, "expected_active_release_id"):
            merge.finalize_release(conn, self.manifest, {"datasets": [member]}, [], self.fixture.composites)

    def test_finalize_pointer_change_does_not_execute_switch(self):
        member = {"dataset_id": self.fixture.dataset, "dataset_revision_id": self.fixture.revision}
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [member]
        conn.execute.return_value.fetchone.return_value = {"release_id": uid("unexpected")}
        with patch.object(merge, "accumulated_members", return_value=([member], [], [])), \
                patch.object(merge, "stage_candidate", return_value=self.release), self.assertRaisesRegex(ValueError, 'active release has changed'):
            merge.finalize_release(conn, self.manifest, {"datasets": [member], "expected_active_release_id": None}, [], self.fixture.composites)
        self.assertFalse(any("INSERT INTO core.active_release" in query_text(call.args[0]) for call in conn.execute.call_args_list))

    def test_schema_missing_migration_needs_explicit_flag(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"name": "core.schema_migration"}
        conn.execute.return_value.fetchall.return_value = self.manifest["schema"]["migrations"][:-1]
        with self.assertRaisesRegex(ValueError, "apply-migrations"):
            merge.ensure_schema(conn, self.manifest)
        self.assertFalse(any("CREATE EXTENSION" in query_text(call.args[0]) for call in conn.execute.call_args_list))
        with patch.object(merge, "inspect_columns", return_value=self.manifest["schema"]["tables"]), \
                patch.object(merge, "existing_readers", return_value=["existing_reader"]):
            merge.ensure_schema(conn, self.manifest, True)
        statements = [query_text(call.args[0]) for call in conn.execute.call_args_list]
        self.assertTrue(any("CREATE TABLE core.dataset_succession" in statement for statement in statements))
        self.assertFalse(any("CREATE TABLE core.borehole (" in statement for statement in statements))
        self.assertTrue(any('GRANT SELECT ON ALL TABLES IN SCHEMA core TO "existing_reader"' in statement for statement in statements))
        self.assertFalse(any("GRANT INSERT" in statement for statement in statements))


if __name__ == "__main__":
    unittest.main()
