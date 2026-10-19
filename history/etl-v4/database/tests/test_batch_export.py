"""Small offline tests for step 38, using fake database connections and real JSON/gzip files."""

import copy
import gzip
import importlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import uuid

DATABASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]

export = importlib.import_module("38_export_batch")
from _batch_files import file_info, load_export, load_sources, object_key, write_json
from _db_files import digest, read
from _settings import settings, path_reference, local_location


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


class FakeCursor:
    def __init__(self, rows, queries):
        self.rows, self.queries = rows, queries

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, parameters):
        text = query.as_string()
        self.queries.append((text, parameters))
        self.table = re.search(r'FROM core\."([a-z_]+)" t', text).group(1)

    def __iter__(self):
        for row in self.rows.get(self.table, []):
            yield {"row_json": json.dumps(row, separators=(",", ":"), ensure_ascii=False)}


class BatchExportTests(unittest.TestCase):
    def setUp(self):
        self.previous = copy.copy(settings.__dict__)
        self.temporary = tempfile.TemporaryDirectory(prefix="etl4_batch_export_")
        self.root = Path(self.temporary.name).resolve()
        settings.work_dir = self.root / "work"
        settings.raw_dir = self.root / "raw"
        settings.dbname = "etl4_export_fixture"
        self.dataset, self.revision, self.hole = uid("dataset"), uid("revision"), uid("hole")
        self.release = uid("release")
        self.package = "a" * 64
        self.content = "b" * 64
        self.asset_file = settings.raw_dir / "EXAMPLE" / "small.bin"
        self.asset_file.parent.mkdir(parents=True)
        self.asset_file.write_bytes(b"small scientific fixture")
        self.asset_info = file_info(self.asset_file, "asset")
        self.asset = {"id": uid("asset"), "dataset_revision_id": self.revision,
                      "media_type": "application/octet-stream",
                      "sha256": self.asset_info["sha256"], "byte_size": self.asset_info["byte_size"]}
        self.first = {"stage": 1, "status": "passed", "content": {
            "package_sha256": self.package,
            "datasets": {self.dataset: {"source_revision_id": uid("prepared"),
                "prepared_hashes": {"5_storage_report.json": "c" * 64},
                "raw_assets": [{"source_relative_path": "small.bin", "sha256": self.asset["sha256"],
                                "byte_size": self.asset["byte_size"]}]}}}}
        self.first["content_sha256"] = digest(self.first["content"])
        self.first_path = settings.reports_dir / f"local_acceptance_1_{self.package}.json"
        write_json(self.first_path, self.first)
        self.second = {"stage": 2, "status": "passed", "database": settings.dbname,
                       "release_id": self.release, "run_id": uid("run"),
                       "dataset_contents": {self.dataset: {"dataset_revision_id": self.revision,
                                                           "input_digest": self.content}},
                       "prepared_acceptances": [{"package_sha256": self.package,
                            "content_sha256": self.first["content_sha256"], "report_path": path_reference(self.first_path)}]}
        self.second["content_sha256"] = digest(self.second["dataset_contents"])
        self.second_path = settings.reports_dir / "local_acceptance_2.json"
        write_json(self.second_path, self.second)
        self.revision_row = {"id": self.revision, "dataset_id": self.dataset, "input_digest": self.content,
            "borehole_id": self.hole, "borehole_revision_id": uid("hole-revision"),
            "source_hole_id": "EXAMPLE", "source_dataset_id": "NVCL-example",
            "normalized_metadata": {"prepared_revision_id": uid("prepared"), "content_sha256": self.content,
                "final_identity": {"raw_files": [["small.bin", self.asset["byte_size"], self.asset["sha256"]]]}}}
        self.validation = {"dataset_revision_id": self.revision, "input_digest": self.content,
                           "validated_at": "2026-10-03", "result": {"status": "passed"}}
        self.scope = {"revisions": [self.revision], "holes": [self.hole], "dataset_ids": [self.dataset],
            "borehole_revisions": [uid("hole-revision")], "relations": [], "validations": [self.validation],
            "datasets": [{"dataset_id": self.dataset, "dataset_revision_id": self.revision,
                "input_digest": self.content, "borehole_id": self.hole,
                "source_hole_id": "EXAMPLE", "source_dataset_id": "NVCL-example"}]}
        self.composites = {"source_release_id": self.release, "composites": [], "parts": [], "succession": [],
                           "decisions": {"orders": {}}, "definition": {"parts": [{"dataset_revision_id": self.revision}]}}
        self.schema = {"migrations": [{"name": path.name, "sha256": file_info(path, "schema")["sha256"]}
                                       for path in sorted((DATABASE / "migrations").glob("*.sql"))],
            "tables": {table: {"columns": [{"column_name": "id", "data_type": "uuid", "nullable": False}],
                                "primary_key": ["id"]} for table in sorted(export.KNOWN_TABLES)}, "geometry": {}}
        self.records = {"dataset_revision": [{"id": self.revision}], "borehole": [{"id": self.hole}]}
        self.queries = []
        self.conn = MagicMock()
        self.conn.__enter__.return_value = self.conn
        self.conn.execute.return_value.fetchone.return_value = {"database": settings.dbname}
        self.conn.cursor.side_effect = lambda **kwargs: FakeCursor(self.records, self.queries)
        self.public_asset = {"asset_id": self.asset["id"], **{key: self.asset[key] for key in
                             ("dataset_revision_id", "sha256", "byte_size", "media_type")},
                             "object_key": object_key(self.asset["sha256"])}
        self.sources = {self.public_asset["object_key"]: {"path": str(self.asset_file),
                        "sha256": self.asset["sha256"], "byte_size": self.asset["byte_size"]}}

    def tearDown(self):
        settings.__dict__.update(self.previous)
        self.temporary.cleanup()

    def run_export(self):
        with patch.object(export, "connection", return_value=self.conn), \
                patch.object(export, "inspect_schema", return_value=self.schema), \
                patch.object(export, "select_scope", return_value=self.scope), \
                patch.object(export, "read_composites", return_value=self.composites), \
                patch.object(export, "select_assets", return_value=([self.public_asset], self.sources)):
            return export.export_batch()

    def test_all_39_tables_are_classified_and_every_data_table_has_scope(self):
        self.assertEqual(len(export.KNOWN_TABLES), 39)
        self.assertEqual(len(export.DATA_TABLES), 29)
        self.assertEqual(len(export.DATA_TABLES + export.EVIDENCE_TABLES + export.RELEASE_TABLES + export.ADMIN_TABLES), 39)
        for table in export.DATA_TABLES + export.EVIDENCE_TABLES:
            condition, values = export.where_clause(table, self.scope)
            self.assertIn("%s", condition)
            self.assertTrue(values)
            self.assertNotIn("active_release", condition)
        self.assertIn("dataset_revision_id", export.where_clause("spectral_block", self.scope)[0])
        self.assertEqual(export.where_clause("survey_station", self.scope)[1], ([self.hole],))
        self.assertEqual(export.where_clause("borehole_branch", self.scope)[1], ([self.hole],))
        with self.assertRaisesRegex(ValueError, 'No batch scope is defined'):
            export.where_clause("new_table", self.scope)

    def test_unknown_catalog_table_is_rejected(self):
        self.conn.execute.return_value.fetchall.return_value = [{"table_name": name} for name in export.KNOWN_TABLES | {"new_extension"}]
        with self.assertRaisesRegex(ValueError, 'update the export format'):
            export.inspect_schema(self.conn)

    def test_failed_or_unbound_acceptance_is_rejected_before_connection(self):
        changes = ({"status": "failed"}, {"database": "another"}, {"content_sha256": "0" * 64}, {"prepared_acceptances": []})
        for change in changes:
            with self.subTest(change=change):
                write_json(self.second_path, {**self.second, **change})
                with patch.object(export, "connection", side_effect=AssertionError("database opened")), self.assertRaises(ValueError):
                    export.export_batch()

    def test_first_acceptance_must_match_digest_and_dataset_scope(self):
        altered = copy.deepcopy(self.first)
        altered["content"]["datasets"][uid("outside")] = altered["content"]["datasets"][self.dataset]
        write_json(self.first_path, altered)
        with self.assertRaisesRegex(ValueError, 'first-stage acceptance status or digest'):
            export.read_acceptances(self.second_path)
        altered["content_sha256"] = digest(altered["content"])
        write_json(self.first_path, altered)
        self.second["prepared_acceptances"][0]["content_sha256"] = altered["content_sha256"]
        write_json(self.second_path, self.second)
        with self.assertRaisesRegex(ValueError, 'two acceptances cover different datasets'):
            export.read_acceptances(self.second_path)

    def scope_connection(self, published=None, revision=None):
        conn = MagicMock()
        def execute(query, parameters):
            cursor = MagicMock()
            if "SELECT r.*" in query:
                cursor.fetchall.return_value = [revision or self.revision_row]
                self.assertEqual(parameters, ([self.revision],))
            elif "FROM core.release_dataset" in query:
                self.assertEqual(parameters, (self.release, [self.hole]))
                cursor.fetchall.return_value = published if published is not None else [{"dataset_id": self.dataset, "dataset_revision_id": self.revision}]
            elif "revision_validation" in query:
                cursor.fetchall.return_value = [self.validation]
            else:
                raise AssertionError(query)
            return cursor
        conn.execute.side_effect = execute
        return conn

    def test_scope_selects_acceptance_revisions_and_rejects_partial_hole(self):
        prepared = self.first["content"]["datasets"]
        scope = export.select_scope(self.scope_connection(), self.second, prepared)
        self.assertEqual(scope["revisions"], [self.revision])
        self.assertEqual(scope["holes"], [self.hole])
        published = [{"dataset_id": self.dataset, "dataset_revision_id": self.revision},
                     {"dataset_id": uid("same-hole-second-dataset"), "dataset_revision_id": uid("outside-revision")}]
        with self.assertRaisesRegex(ValueError, 'Export complete boreholes'):
            export.select_scope(self.scope_connection(published=published), self.second, prepared)

    def test_prepared_input_must_match_final_database_version(self):
        row = copy.deepcopy(self.revision_row)
        row["normalized_metadata"]["prepared_revision_id"] = uid("different")
        with self.assertRaisesRegex(ValueError, 'first-stage input does not match the final revision'):
            export.select_scope(self.scope_connection(revision=row), self.second, self.first["content"]["datasets"])

    def test_real_gzip_stream_has_stable_bytes_geometry_and_sort_order(self):
        table = "borehole_revision"
        self.schema["tables"][table]["columns"].append({"column_name": "collar_geom", "data_type": "geometry(Point,4326)", "nullable": True})
        self.records[table] = [{"id": uid("collar"), "collar_geom": "0101000020E6100000"}]
        first = self.root / "one.jsonl.gz"
        second = self.root / "two.jsonl.gz"
        export.export_table(self.conn, table, self.schema, self.scope, first)
        export.export_table(self.conn, table, self.schema, self.scope, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first.read_bytes()[4:8], b"\0" * 4)
        self.assertEqual(json.loads(gzip.decompress(first.read_bytes())), self.records[table][0])
        query, parameters = self.queries[-1]
        self.assertIn("encode(ST_AsEWKB(t.collar_geom),'hex')", query)
        self.assertIn('ORDER BY t."id"', query)
        self.assertEqual(parameters, (self.scope["borehole_revisions"],))
        export.export_table(self.conn, "core_interval", self.schema, self.scope, self.root / "intervals.gz")
        self.assertIn("CASE WHEN t.interval_kind='tray' THEN 0 ELSE 1 END", self.queries[-1][0])

    def test_export_keeps_private_paths_out_of_payload_and_does_not_copy_assets(self):
        example = {"asset_id": self.asset["id"], "local_path": str(self.asset_file)}
        self.second["checks"] = [{"status": "passed", "sample_count": 3, "example_selections": [example]}]
        self.validation["result"]["example_selections"] = [example]
        write_json(self.second_path, self.second)
        source_before = self.second_path.read_bytes()
        result = self.run_export()
        folder = Path(result["directory"])
        manifest, sha = load_export(folder)
        sources = load_sources(folder, manifest, sha)
        self.assertEqual(sources, self.sources)
        self.assertNotIn("local_sources.json", manifest["files"])
        self.assertEqual(set(manifest["tables"]), set(export.DATA_TABLES))
        self.assertNotIn("asset_location", manifest["tables"])
        self.assertNotIn("revision_validation", manifest["tables"])
        self.assertNotIn("dataset_succession", manifest["tables"])
        for relative in manifest["files"]:
            self.assertNotIn(str(self.asset_file).encode(), (folder / relative).read_bytes())
        self.assertFalse((folder / "objects").exists())
        second = read(folder / "evidence/acceptance_2.json")
        self.assertEqual(second["checks"], [{"status": "passed", "sample_count": 3}])
        self.assertEqual(second["export_evidence"]["source_report_sha256"], file_info(self.second_path, "evidence")["sha256"])
        self.assertEqual(source_before, self.second_path.read_bytes())
        self.assertEqual(len(list(folder.rglob("small.bin"))), 0)
        self.assertEqual(self.conn.execute.call_args_list[0].args[0], "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        self.assertEqual([call.args[0] for call in self.conn.execute.call_args_list[1:4]], [
            "SET LOCAL TIME ZONE 'UTC'", "SET LOCAL DateStyle TO 'ISO, YMD'", "SET LOCAL extra_float_digits TO 3"])
        self.assertEqual(len(self.queries), len(export.DATA_TABLES))
        for query, parameters in self.queries:
            self.assertIn("WHERE", query)
            self.assertNotIn(uid("outside-revision"), repr(parameters))

    def test_reexport_keeps_identity_and_original_audit_reports(self):
        first = self.run_export()
        folder = Path(first["directory"])
        before = (folder / "manifest.json").read_bytes()
        self.second["run_id"] = uid("another-run")
        write_json(self.second_path, self.second)
        self.scope["validations"][0]["validated_at"] = "2026-10-04"
        second = self.run_export()
        self.assertEqual(first["batch_id"], second["batch_id"])
        self.assertTrue(second["reused"])
        self.assertEqual(before, (folder / "manifest.json").read_bytes())
        self.assertEqual(read(folder / "evidence/acceptance_2.json")["run_id"], uid("run"))

    def test_reexport_business_conflict_preserves_original_package(self):
        first = self.run_export()
        folder = Path(first["directory"])
        before = (folder / "manifest.json").read_bytes()
        self.records["dataset_revision"][0]["changed_scientific_value"] = 7
        with self.assertRaisesRegex(ValueError, 'different business content'):
            self.run_export()
        self.assertEqual(before, (folder / "manifest.json").read_bytes())
        self.assertEqual(list(folder.parent.glob(".export-*")), [])

    def test_interrupted_write_never_leaves_completed_manifest(self):
        with patch.object(export, "export_table", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.run_export()
        parent = settings.database_dir / "exports"
        self.assertEqual(list(parent.iterdir()), [])

    def test_assets_only_read_selected_local_files_and_do_not_hash_large_data(self):
        manifest = settings.reports_dir / f"asset_manifest_{self.release}.json"
        old = {**self.asset, "id": uid("old-asset"), "dataset_revision_id": uid("old-revision")}
        write_json(manifest, {"release_id": self.release, "assets": [self.asset, old]})
        location = {"asset_id": self.asset["id"], "backend": "local", "verified_sha256": self.asset["sha256"],
                    **local_location(path_reference(self.asset_file))}
        conn = MagicMock()
        conn.execute.return_value.fetchall.side_effect = [[self.asset], [location]]
        with patch.object(export, "file_info", side_effect=AssertionError("asset full hash")):
            assets, sources = export.select_assets(conn, self.scope, self.release, manifest)
        self.assertEqual(assets, [self.public_asset])
        self.assertEqual(sources, self.sources)
        self.assertEqual(len(conn.execute.call_args_list), 2)
        self.assertTrue(all(call.args[1] == ([self.revision],) for call in conn.execute.call_args_list))
        self.asset_file.unlink()
        conn.execute.return_value.fetchall.side_effect = [[self.asset], [location]]
        with self.assertRaisesRegex(ValueError, 'no readable local file'):
            export.select_assets(conn, self.scope, self.release, manifest)

    def test_identity_excludes_release_run_paths_and_unselected_decisions(self):
        first = export.export_identity(self.schema, self.scope, self.composites)
        second = copy.deepcopy(self.composites)
        second["source_release_id"] = uid("new-release")
        second["run_id"] = uid("unrelated-run")
        second["path"] = str(self.root)
        self.assertEqual(first, export.export_identity(self.schema, self.scope, second))
        filtered = export.selected_decisions({"orders": {"EXAMPLE": ["a", "b"], "OLD": ["c"]}}, {"EXAMPLE"})
        self.assertEqual(filtered, {"orders": {"EXAMPLE": ["a", "b"]}})
        self.assertIsInstance(first["schema_migrations"], dict)

    def test_display_identity_ignores_unrelated_holes_and_keeps_source_records(self):
        second_revision = uid("second-revision")
        scope = copy.deepcopy(self.scope)
        scope["revisions"].append(second_revision)
        relation = {"id": uid("relation"), "borehole_id": self.hole,
                    "predecessor_revision_id": self.revision, "successor_revision_id": second_revision,
                    "relation_kind": "confirmed_display_successor", "switch_md_m": 10,
                    "switch_basis": "successor_first_actual_sample_md_m",
                    "confirmation_basis": {"orders": {"EXAMPLE": ["one", "two"], "OLD": ["old"]},
                                           "confirmation_date": "2026-09-24"}}
        composite = {"id": uid("composite"), "release_id": self.release, "borehole_id": self.hole,
                     "definition_sha256": "d" * 64, "composition_kind": "confirmed_successor_chain",
                     "evidence": {"decisions": copy.deepcopy(relation["confirmation_basis"])}}
        parts = [{"composite_id": composite["id"], "release_id": self.release, "borehole_id": self.hole,
                  "sequence_no": number, "dataset_revision_id": revision,
                  "predecessor_relation_id": relation["id"] if number else None}
                 for number, revision in enumerate(scope["revisions"])]

        def read_display():
            conn = MagicMock()
            values = ([composite], parts, [relation])
            conn.execute.return_value.fetchall.side_effect = copy.deepcopy(values)
            conn.execute.return_value.fetchone.return_value = {"manifest": {"succession_decisions": relation["confirmation_basis"]}}
            return export.read_composites(conn, self.release, scope)

        first = read_display()
        self.assertEqual(first["composites"][0], composite)
        self.assertEqual(first["succession"][0], relation)
        self.assertNotIn("OLD", first["definition"]["decisions"]["orders"])
        self.assertNotIn("confirmation_date", first["definition"]["decisions"])
        relation["id"] = uid("new-relation")
        relation["confirmation_basis"]["orders"]["OLD"].append("another")
        relation["confirmation_basis"]["confirmation_date"] = "2026-10-03"
        composite["id"] = uid("new-composite")
        composite["release_id"] = uid("new-release")
        composite["definition_sha256"] = "e" * 64
        for part in parts:
            part["release_id"] = composite["release_id"]
            part["composite_id"] = composite["id"]
            if part["predecessor_relation_id"]:
                part["predecessor_relation_id"] = relation["id"]
        second = read_display()
        self.assertEqual(first["definition"], second["definition"])
        self.assertEqual(export.export_identity(self.schema, self.scope, first), export.export_identity(self.schema, self.scope, second))
        self.composites = first
        before = self.run_export()
        self.composites = second
        after = self.run_export()
        self.assertEqual(before["batch_id"], after["batch_id"])
        self.assertTrue(after["reused"])


if __name__ == "__main__":
    unittest.main()
