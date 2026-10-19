"""Check the standalone backup entry point offline, with database connections and external commands prohibited."""

import builtins
from contextlib import ExitStack
import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

DATABASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATABASE))
sys.path.insert(0, str(DATABASE.parent))

backup = importlib.import_module("14_verify_database_backup")


class BackupStandaloneTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("psycopg.connect", side_effect=AssertionError("Real DB forbidden")))
        self.stack.enter_context(patch("subprocess.run", side_effect=AssertionError("Subprocess forbidden")))
        self.temporary = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="backup14_"))
        self.folder = Path(self.temporary) / "database"
        self.folder.mkdir()
        self.stack.enter_context(patch.object(backup, "settings", SimpleNamespace(
            database_dir=self.folder, reports_dir=self.folder / "reports"
        )))
        self.database_config = {
            "host": "localhost", "port": 55433, "database": "business_source",
            "roles": {"owner": {"user": "fixture", "password": "fixture"}},
        }
        self.stack.enter_context(patch.object(backup, "config", return_value=self.database_config))
        self.trial = "etl4_restore_" + "a" * 32

    def test_import_does_not_load_old_audit_or_trial_helpers(self):
        real_import = builtins.__import__

        def reject_old(name, *args, **kwargs):
            if name in ("13_audit_database", "_trial_support"):
                raise AssertionError("Legacy dependency imported")
            return real_import(name, *args, **kwargs)

        spec = importlib.util.spec_from_file_location("standalone_backup14", Path(backup.__file__))
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"13_audit_database": None, "_trial_support": None}), patch(
            "builtins.__import__", side_effect=reject_old
        ):
            spec.loader.exec_module(module)
        self.assertTrue(callable(module.main))
        self.assertTrue(callable(module.foreign_key_checks))
        self.assertTrue(callable(module.fingerprints))

    def install_flow(self, *, failure=None):
        self.events = []
        source = MagicMock(name="source")
        restored = MagicMock(name="restored")
        source.__enter__.return_value = source
        restored.__enter__.return_value = restored
        source_checks = 0
        source_structures = 0
        release_reads = 0

        def source_execute(query, params=None):
            nonlocal release_reads
            if "pg_try_advisory_lock" in query:
                self.events.append("lock")
                return SimpleNamespace(fetchone=lambda: {"ok": failure != "locked"})
            release_reads += 1
            self.events.append("source_release")
            release = "other" if failure == "source_release" and release_reads > 1 else "release"
            return SimpleNamespace(fetchone=lambda: {"release_id": release})

        def restored_execute(query, params=None):
            if "active_release" in query:
                self.events.append("restored_release")
                release = "other" if failure == "restored_release" else "release"
                return SimpleNamespace(fetchone=lambda: {"release_id": release})
            if "pg_database_size" in query:
                return SimpleNamespace(fetchone=lambda: {"n": 42})
            return SimpleNamespace(fetchone=lambda: {"n": 1 if failure == "relations" else 0})

        source.execute.side_effect = source_execute
        restored.execute.side_effect = restored_execute
        self.stack.enter_context(patch.object(
            backup, "connection", side_effect=lambda dbname=None: source if dbname is None else restored
        ))

        def check_structure(conn):
            nonlocal source_structures
            kind = "source" if conn is source else "restored"
            self.events.append(kind + "_structure")
            if conn is source:
                source_structures += 1
            differs = failure == "restored_structure" and conn is restored
            differs |= failure == "source_structure" and conn is source and source_structures > 1
            return {"columns": ["changed" if differs else "same"]}

        def check_fingerprints(dbname=None):
            nonlocal source_checks
            kind = "source" if dbname is None else "restored"
            self.events.append(kind + "_fingerprint")
            if dbname is None:
                source_checks += 1
            differs = failure == "restored_records" and dbname is not None
            differs |= failure == "source_records" and dbname is None and source_checks > 1
            return {"dataset": "changed" if differs else "same"}

        def run_command(args, **kwargs):
            kind = "dump" if Path(args[0]).name == "pg_dump.exe" else "restore"
            self.events.append(kind)
            if failure == kind:
                raise RuntimeError(kind + " failed")
            if kind == "dump":
                Path(args[args.index("--file") + 1]).write_bytes(b"offline fixture")

        def create():
            self.events.append("create")
            if failure == "create":
                raise RuntimeError("create failed")
            return self.trial

        def drop(name):
            self.assertEqual(name, self.trial)
            self.events.append("drop")
            if failure == "drop":
                raise RuntimeError("drop failed")

        self.stack.enter_context(patch.object(backup, "schema_signature", side_effect=check_structure))
        self.stack.enter_context(patch.object(backup, "fingerprints", side_effect=check_fingerprints))
        self.stack.enter_context(patch.object(backup, "assert_schema", side_effect=lambda conn: self.events.append("schema")))
        self.stack.enter_context(patch.object(backup, "foreign_key_checks", side_effect=lambda conn: self.events.append("foreign_keys") or 12))
        self.stack.enter_context(patch.object(backup, "command", side_effect=run_command))
        self.stack.enter_context(patch.object(backup, "create_restore_database", side_effect=create))
        self.stack.enter_context(patch.object(backup, "drop_restore_database", side_effect=drop))
        self.stack.enter_context(patch.object(backup, "read", return_value={
            "release_id": "other" if failure == "manifest" else "release"
        }))
        self.stack.enter_context(patch.object(backup, "sha", return_value="file_hash"))
        self.stack.enter_context(patch.object(backup, "schema_hash", return_value="schema_hash"))
        self.writer = self.stack.enter_context(patch.object(backup, "write", side_effect=lambda *args: self.events.append("manifest")))
        self.reporter = self.stack.enter_context(patch.object(backup, "report", side_effect=lambda *args: self.events.append("report")))
        self.stack.enter_context(patch("builtins.print"))

    def test_success_compares_both_databases_then_cleans_before_reporting(self):
        self.install_flow()
        backup.main()
        self.assertEqual(self.events, [
            "lock", "schema", "source_release", "source_structure", "source_fingerprint",
            "dump", "create", "restore", "restored_fingerprint", "restored_structure",
            "schema", "restored_release", "foreign_keys", "source_fingerprint",
            "source_structure", "source_release", "drop", "manifest", "report", "report",
        ])
        result = self.reporter.call_args_list[0].args[1]
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["restored_hashes"], result["business_table_hashes"])
        self.assertEqual(result["audit_code_sha256"], result["code_sha256"])
        self.assertTrue(result["restored_trial_removed"])
        self.assertEqual(self.reporter.call_args_list[-1].args[0], "latest_database_backup.json")

    def assert_failure_without_success_report(self, failure, message):
        self.install_flow(failure=failure)
        with self.assertRaisesRegex((RuntimeError, ValueError), message):
            backup.main()
        self.writer.assert_not_called()
        self.reporter.assert_not_called()

    def test_restore_failure_cleans_the_created_database(self):
        self.assert_failure_without_success_report("restore", "restore failed")
        self.assertEqual(self.events[-2:], ["restore", "drop"])

    def test_changed_restored_records_are_rejected_and_cleaned(self):
        self.assert_failure_without_success_report("restored_records", "Restored records differ")
        self.assertEqual(self.events[-1], "drop")

    def test_changed_restored_structure_is_rejected_and_cleaned(self):
        self.assert_failure_without_success_report("restored_structure", "Restored structure differs")
        self.assertEqual(self.events[-1], "drop")

    def test_wrong_restored_release_is_rejected_and_cleaned(self):
        self.assert_failure_without_success_report("restored_release", "Restored release differs")
        self.assertEqual(self.events[-1], "drop")

    def test_broken_restored_relationships_are_rejected_and_cleaned(self):
        self.assert_failure_without_success_report("relations", "relationship checks failed")
        self.assertEqual(self.events[-1], "drop")

    def test_source_change_is_rejected_and_cleaned(self):
        self.assert_failure_without_success_report("source_records", "Source data changed")
        self.assertEqual(self.events[-1], "drop")

    def test_source_structure_change_is_rejected_and_cleaned(self):
        self.assert_failure_without_success_report("source_structure", "Source structure changed")
        self.assertEqual(self.events[-1], "drop")

    def test_source_release_change_is_rejected_and_cleaned(self):
        self.assert_failure_without_success_report("source_release", "Source release changed")
        self.assertEqual(self.events[-1], "drop")

    def test_asset_manifest_mismatch_prevents_success_report(self):
        self.assert_failure_without_success_report("manifest", "Asset manifest has a different release")
        self.assertEqual(self.events[-1], "drop")

    def test_cleanup_failure_prevents_success_report(self):
        self.assert_failure_without_success_report("drop", "drop failed")

    def test_dump_failure_does_not_create_or_drop_a_database(self):
        self.assert_failure_without_success_report("dump", "dump failed")
        self.assertNotIn("create", self.events)
        self.assertNotIn("drop", self.events)

    def test_creation_failure_does_not_drop_an_existing_database(self):
        self.assert_failure_without_success_report("create", "create failed")
        self.assertNotIn("drop", self.events)

    def test_active_import_lock_prevents_dump(self):
        self.assert_failure_without_success_report("locked", "Importer/validator is active")
        self.assertEqual(self.events, ["lock"])

    def test_restore_creation_uses_a_random_exact_name(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(backup.uuid, "uuid4", return_value=SimpleNamespace(hex="b" * 32)), patch.object(
            backup, "connection", return_value=conn
        ) as connect:
            name = backup.create_restore_database()
        self.assertEqual(name, "etl4_restore_" + "b" * 32)
        connect.assert_called_once_with(dbname="postgres")
        self.assertEqual(conn.execute.call_args.args[0].as_string(),
                         'CREATE DATABASE "' + name + '" TEMPLATE template0 ENCODING \'UTF8\'')

    def test_restore_drop_refuses_business_and_unrelated_database_names(self):
        names = ["postgres", "business_source", "etl4_test_" + "a" * 32,
                 "etl4_restore_short", self.trial + "_suffix", self.trial + ";DROP DATABASE postgres"]
        with patch.object(backup, "connection") as connect:
            for name in names:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Not an isolated restore"):
                    backup.drop_restore_database(name)
            self.database_config["database"] = self.trial
            with self.assertRaisesRegex(ValueError, "Not an isolated restore"):
                backup.drop_restore_database(self.trial)
        connect.assert_not_called()

    def test_restore_drop_has_no_force_or_session_termination(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(backup, "connection", return_value=conn) as connect:
            backup.drop_restore_database(self.trial)
        connect.assert_called_once_with(dbname="postgres")
        conn.execute.assert_called_once()
        self.assertEqual(conn.execute.call_args.args[0].as_string(), 'DROP DATABASE "' + self.trial + '"')


if __name__ == "__main__":
    unittest.main()
