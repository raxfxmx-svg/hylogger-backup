"""Check entry-point configuration, initial metadata writes, and import transaction boundaries."""

import copy
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

DATABASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATABASE))
sys.path.insert(0, str(DATABASE.parent))

from _settings import SOURCE_ROOT, StepParser, configure, settings
from _file_checks import run_record
from _media_common import stage, save_stage
from _run_reports import run_report_directory
from processing._etl_common import DatasetContext, METADATA, read_json, sha_file, write_json
from processing import metadata_normalization

multi_import = importlib.import_module("34_import_multi_dataset_database")


class CodeStructureTests(unittest.TestCase):
    def setUp(self):
        self.old_work_dir = settings.work_dir
        self.old_dbname = settings.dbname
        self.temporary = tempfile.TemporaryDirectory(prefix="structure_test_", dir=SOURCE_ROOT)
        self.folder = Path(self.temporary.name)

    def tearDown(self):
        settings.work_dir = self.old_work_dir
        settings.dbname = self.old_dbname
        self.temporary.cleanup()

    def select_work_dir(self, folder, dbname="etl4_structure_test"):
        args = StepParser().parse_args(["--work-dir", str(folder), "--dbname", dbname])
        configure(args)

    def test_importing_settings_does_not_parse_command_line(self):
        script = """
import argparse
import sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
with patch.object(argparse.ArgumentParser, 'parse_args', side_effect=AssertionError('parsed on import')):
    with patch.object(argparse.ArgumentParser, 'parse_known_args', side_effect=AssertionError('parsed on import')):
        import _settings
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(SOURCE_ROOT)], capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_entry_parses_arguments_once(self):
        args = [
            "34_import_multi_dataset_database.py",
            "--work-dir",
            str(self.folder),
            "--dbname",
            "etl4_structure_test",
        ]
        with patch.object(sys, "argv", args), patch.object(
            StepParser,
            "parse_known_args",
            autospec=True,
            wraps=None,
            side_effect=lambda parser, args=None, namespace=None: super(
                StepParser, parser
            ).parse_known_args(args, namespace),
        ) as parse:
            selected = multi_import.parse_arguments()
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(selected.work_dir, settings.work_dir)
        self.assertEqual(settings.dbname, "etl4_structure_test")

    def test_media_helpers_use_selected_work_dir_after_import(self):
        self.select_work_dir(self.folder / "one")
        save_stage(20, {"status": "passed", "datasets": [{"dataset_id": "one"}]})
        first = settings.media_work_dir / "20.json"
        self.select_work_dir(self.folder / "two")
        save_stage(20, {"status": "passed", "datasets": [{"dataset_id": "two"}]})
        self.assertEqual(stage(20)["datasets"], [{"dataset_id": "two"}])
        self.assertEqual(json.loads(first.read_text(encoding="utf-8"))["datasets"], [{"dataset_id": "one"}])

    def test_run_report_uses_configuration_selected_by_entry(self):
        def work():
            self.select_work_dir(self.folder / "selected")
            return "done"

        self.assertEqual(run_record(run_report_directory, work), "done")
        reports = list((settings.reports_dir / "runs").glob("*.json"))
        self.assertEqual(len(reports), 1)
        self.assertEqual(json.loads(reports[0].read_text(encoding="utf-8"))["status"], "passed")

    def test_help_exit_does_not_create_run_report(self):
        self.select_work_dir(self.folder)

        def help_exit():
            raise SystemExit(0)

        with self.assertRaises(SystemExit):
            run_record(run_report_directory, help_exit)
        self.assertFalse((settings.reports_dir / "runs").exists())

    def test_normalization_writes_complete_metadata_once(self):
        self.select_work_dir(self.folder)
        folder = settings.prepared_dir / "example"
        raw = {name: [] for name in METADATA}
        raw.update(
            {
                "borehole.json": {"nvcl_id": "hole", "name": "example", "x": 120, "y": -30},
                "datasets.json": [
                    {"dataset_id": "dataset", "dataset_name": "example", "borehole_uri": "hole"}
                ],
                "package_manifest.json": {"provider": "fixture"},
                "images_manifest.json": {"logs": [], "files": []},
            }
        )
        full_source = copy.deepcopy(raw)
        full_source["datasets.json"].append({"dataset_id": "unselected"})
        selection = {"source_dataset_id": "dataset", "log_ids": {}, "membership_evidence": {}}
        inventory = {"hole_id": "hole", "source_snapshot_id": "input", "pipeline_id": "rules"}
        context = DatasetContext("hole", folder, inventory, raw, {})
        write_json(folder / "2_integrity.json", {"status": "passed", "step": 2, "files": []})
        with patch.object(metadata_normalization, "write_json", wraps=write_json) as writer:
            metadata_normalization.normalize_hole(
                "hole",
                context=context,
                source_metadata=full_source,
                dataset_selection=selection,
                orientation_missing_reason="downhole_survey_not_provided",
                orientation_missing_reason_source="fixture_source",
            )
        metadata_writes = [
            call
            for call in writer.call_args_list
            if call.args[0].name == "3_normalized_metadata.json"
        ]
        self.assertEqual(len(metadata_writes), 1)
        metadata = read_json(folder / "3_normalized_metadata.json")
        self.assertEqual(metadata["raw_metadata"], full_source)
        self.assertEqual(metadata["selected_dataset_context"], selection)
        self.assertEqual(
            metadata["borehole"]["orientation_missing_reason_source"], "fixture_source"
        )
        self.assertEqual(raw["datasets.json"], [full_source["datasets.json"][0]])
        report = read_json(folder / "3_metadata_report.json")
        self.assertEqual(
            report["normalized_metadata_sha256"], sha_file(folder / "3_normalized_metadata.json")
        )

    def test_failed_media_import_rolls_back_and_releases_lock(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"ok": True}
        failure = ValueError("media import interrupted")
        with patch.object(multi_import, "assert_schema"), patch.object(
            multi_import, "start_import_record", return_value="run"
        ), patch.object(multi_import, "import_complete_datasets"), patch.object(
            multi_import, "import_dataset_media", side_effect=failure
        ), patch.object(
            multi_import, "stage_release"
        ) as stage_release, patch.object(
            multi_import, "finish_import_record"
        ) as finish:
            with self.assertRaisesRegex(ValueError, "media import interrupted"):
                multi_import.import_release(
                    conn, {"release_id": "source"}, {"key": "key", "source": {"datasets": []}}, {}
                )
        rollback = conn.transaction.return_value.__exit__
        rollback.assert_called_once()
        self.assertEqual(rollback.call_args.args[:2], (ValueError, failure))
        self.assertIsNotNone(rollback.call_args.args[2])
        stage_release.assert_not_called()
        self.assertEqual(finish.call_args.args[2], "failed")
        self.assertIn("pg_advisory_unlock", conn.execute.call_args.args[0])

    def test_duplicate_release_members_are_rejected(self):
        member = {"dataset_id": "same", "dataset_revision_id": "revision"}
        with self.assertRaisesRegex(ValueError, "Duplicate dataset"):
            multi_import.combine_release_members({"members": [member]}, [member])


if __name__ == "__main__":
    unittest.main()
