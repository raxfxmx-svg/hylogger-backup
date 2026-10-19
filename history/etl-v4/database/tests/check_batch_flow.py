"""Small real-PostgreSQL workflow check for steps 38-39-40; synthetic fixtures do not constitute scientific-data acceptance.

Preview scope by default; --execute creates two isolated etl4_test_batch_flow_ databases.
Use in-memory object storage without AWS/API connections or processing/deleting existing raw files.
"""

import argparse
import base64
import contextlib
import copy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
import uuid
import zlib

DATABASE = Path(__file__).resolve().parents[1]
PROJECT = DATABASE.parents[1]
sys.path[:0] = [str(DATABASE), str(DATABASE.parent)]

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from _batch_files import KNOWN_TABLES, read_json, write_json
from _db_files import digest, encoded, sha
from _settings import local_location, path_reference, settings

export = importlib.import_module("38_export_batch")
upload = importlib.import_module("39_upload_batch")
merge = importlib.import_module("40_merge_cloud_batch")
cleanup = importlib.import_module("41_cleanup_batch")

PREFIX = "etl4_test_batch_flow_"
SCOPE = 'Synthetic fixture: 2 boreholes, 3 datasets, 9 samples, and 3 small assets; software-workflow validation, not scientific acceptance'


def require(value, message):
    if not value:
        raise AssertionError(message)


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "etl4-test-batch-flow:" + name))


class ObjectError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": str(code)}, "ResponseMetadata": {"HTTPStatusCode": int(code)}}


class MemoryS3:
    """Simulate object transfer while validating actual local bytes; any GET fails the check."""

    def __init__(self):
        self.objects, self.puts, self.heads = {}, 0, 0

    def head_object(self, *, Bucket, Key, ChecksumMode):
        require(Bucket == "etl4-offline-fixture" and ChecksumMode == "ENABLED", 'Incorrect transfer scope')
        self.heads += 1
        if Key not in self.objects:
            raise ObjectError(404)
        data = self.objects[Key]
        return {"ContentLength": len(data), "ChecksumType": "FULL_OBJECT",
                "ChecksumSHA256": base64.b64encode(hashlib.sha256(data).digest()).decode(), "ETag": "fixture"}

    def put_object(self, **args):
        require(args["Bucket"] == "etl4-offline-fixture" and args["IfNoneMatch"] == "*", 'A conditional write is required')
        if args["Key"] in self.objects:
            raise ObjectError(412)
        data = args["Body"].read()
        require(len(data) == args["ContentLength"], 'Incorrect upload length')
        checksum = base64.b64encode((zlib.crc32(data) & 0xffffffff).to_bytes(4, "big")).decode()
        require(checksum == args["ChecksumCRC32"], 'Transfer CRC32 mismatch')
        self.objects[args["Key"]] = data
        self.puts += 1
        return {"ETag": "fixture"}

    def get_object(self, **args):
        raise AssertionError('Batch upload must not download every object again through GET')


class Check:
    def __init__(self, config_path, output, token):
        require(re.fullmatch(r"[a-z0-9]{6,16}", token), 'Invalid isolated database suffix')
        self.config_path, self.output = Path(config_path).resolve(), Path(output).resolve()
        self.config = read_json(self.config_path)
        require(self.config["host"] in ("127.0.0.1", "localhost", "::1") and int(self.config["port"]) == 55433,
                'Allow only the documented local PostgreSQL instance on port 55433')
        require(not any(os.environ.get(key) for key in ("ETL4_ADMIN_DSN", "ETL4_READ_DSN", "ETL4_INGEST_DSN")),
                'Remove ETL4_*_DSN environment variables that could override local settings before checking')
        self.source, self.target = PREFIX + token + "_source", PREFIX + token + "_target"
        self.created = []
        self.moved_sources = []
        self.s3 = MemoryS3()
        self.report = {"status": "running", "scope": SCOPE, "database_names": [self.source, self.target],
                       "network": "local PostgreSQL only; in-memory S3; no AWS or API", "checks": [], "cleanup": []}

    def connect(self, name, role="owner"):
        require(name in ("postgres", self.source, self.target), 'The connection must stay within the explicitly selected scope')
        credential = self.config["roles"][role]
        conn = psycopg.connect(host=self.config["host"], port=self.config["port"], dbname=name,
            user=credential["user"], password=credential["password"], autocommit=True,
            row_factory=dict_row, connect_timeout=3)
        conn.execute("SET statement_timeout='20s'")
        conn.execute("SET lock_timeout='3s'")
        conn.execute("SET search_path=core,public")
        return conn

    def note(self, name, **evidence):
        self.report["checks"].append({"name": name, "status": "passed", **evidence})
        write_json(self.output / "report.json", self.report)
        print('Passed: ' + name, flush=True)

    def create_databases(self):
        for name in (self.source, self.target):
            require(name.startswith(PREFIX), 'Isolated database boundary error')
            with self.connect("postgres") as conn:
                require(conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone() is None,
                        'A database with this name already exists; never overwrite it')
                conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(name)))
            self.created.append(name)
        with self.connect(self.source) as conn:
            conn.execute("CREATE EXTENSION postgis")
            for path in sorted((DATABASE / "migrations").glob("*.sql")):
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO core.schema_migration(name,sha256) VALUES(%s,%s)", (path.name, sha(path)))
            reader = sql.Identifier(self.config["roles"]["reader"]["user"])
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA core,public TO {}").format(reader))
            conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA core TO {}").format(reader))
        self.note('Create only two isolated databases and apply all six migrations to the source database', migrations=6)

    def drop_databases(self):
        for name in reversed(self.created):
            try:
                require(name in (self.source, self.target) and name.startswith(PREFIX), 'Deletion scope is ambiguous')
                with self.connect("postgres") as conn:
                    conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
                    require(conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone() is None,
                            'Isolated database deletion was not confirmed')
                self.report["cleanup"].append({"database": name, "status": "dropped"})
            except Exception as error:
                self.report["cleanup"].append({"database": name, "status": "failed", "error_type": type(error).__name__})
                self.report["status"] = "failed"

    def restore_sources(self):
        for original, temporary in self.moved_sources:
            try:
                require(original.is_relative_to(self.output) and temporary.is_relative_to(self.output), 'Fixture recovery path escapes its boundary')
                require(not original.exists() and temporary.is_file(), 'Fixture recovery conditions changed')
                temporary.rename(original)
                self.report["cleanup"].append({"fixture_file": str(original), "status": "restored"})
            except Exception as error:
                self.report["cleanup"].append({"fixture_file": str(original), "status": "failed", "error_type": type(error).__name__})
                self.report["status"] = "failed"

    def insert(self, conn, table, record):
        values = [Jsonb(value) if isinstance(value, (dict, list)) else value for value in record.values()]
        conn.execute(sql.SQL("INSERT INTO core.{} ({}) VALUES ({})").format(sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, record)), sql.SQL(",").join(sql.Placeholder() for _ in values)), values)

    def source_batch(self, label, definitions):
        """The fixture defines valid relationships explicitly; all samples and acceptance reports are marked as synthetic tests."""
        hole, hole_revision, release = uid(label + "-hole"), uid(label + "-hole-revision"), uid(label + "-release")
        rows = []
        with self.connect(self.source) as conn, conn.transaction():
            self.insert(conn, "borehole", {"id": hole, "provider_code": "TEST_ONLY", "source_hole_id": "FIXTURE_" + label})
            self.insert(conn, "borehole_revision", {"id": hole_revision, "borehole_id": hole,
                "source_name": "synthetic software fixture", "actual_drill_date_precision": "unknown",
                "trajectory_status": "not_surveyed", "normalized_metadata": {"fixture": True}})
            for number, depths in definitions:
                dataset = str(uuid.UUID(int=number))
                revision, axis = uid(str(number) + "-revision"), uid(str(number) + "-axis")
                prepared = uid(str(number) + "-prepared")
                path = settings.raw_dir / label / (str(number) + ".bin")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(("synthetic software asset " + str(number)).encode())
                raw = {"source_relative_path": path.name, "sha256": sha(path), "byte_size": path.stat().st_size}
                content = digest({"fixture_dataset": number, "depths": depths, "raw": raw})
                self.insert(conn, "dataset", {"id": dataset, "borehole_id": hole, "source_dataset_id": "TEST_" + str(number)})
                self.insert(conn, "dataset_revision", {"id": revision, "dataset_id": dataset, "borehole_id": hole,
                    "borehole_revision_id": hole_revision, "source_dataset_name": "fixture " + str(number),
                    "source_snapshot_id": content, "pipeline_id": "fixture-rules-v1", "input_digest": content, "mapping_version": 1,
                    "normalized_metadata": {"prepared_revision_id": prepared, "content_sha256": content,
                        "final_identity": {"raw_files": [[raw["source_relative_path"], raw["byte_size"], raw["sha256"]]],
                                           "preparation_rules": 1, "final_rules": 1}}})
                self.insert(conn, "sample_axis", {"id": axis, "dataset_revision_id": revision, "sample_count": len(depths),
                    "depth_min_m": min(depths), "depth_max_m": max(depths), "alignment_evidence": {"fixture": True}})
                tray, section = uid(str(number) + "-tray"), uid(str(number) + "-section")
                for kind, interval, parent in (("tray", tray, None), ("section", section, tray)):
                    self.insert(conn, "core_interval", {"id": interval, "axis_id": axis, "interval_kind": kind,
                        "ordinal": 0, "source_label": "fixture", "parent_interval_id": parent,
                        "sample_no_from": 0, "sample_no_to": len(depths) - 1, "source_log_id": "fixture",
                        "source_data_row": 0, "source_interval_convention": "closed"})
                for index, depth in enumerate(depths):
                    self.insert(conn, "scan_sample", {"axis_id": axis, "sample_no": index, "md_m": depth,
                        "tray_interval_id": tray, "section_interval_id": section,
                        "tray_sample_no": index + 1, "section_sample_no": index + 1, "section_distance_mm": None})
                asset = {"id": uid(str(number) + "-asset"), "dataset_revision_id": revision, "asset_kind": "fixture",
                    "representation": "raw", "logical_path": path.name, "sha256": raw["sha256"], "byte_size": raw["byte_size"],
                    "media_type": "application/octet-stream", "semantic_status": "fixture_only", "provenance": {"fixture": True}}
                self.insert(conn, "asset", asset)
                self.insert(conn, "asset_location", {"id": uid(str(number) + "-local"), "asset_id": asset["id"],
                    "backend": "local", **local_location(path_reference(path)), "access_status": "verified_local",
                    "verified_sha256": asset["sha256"]})
                self.insert(conn, "revision_validation", {"dataset_revision_id": revision, "input_digest": content,
                    "verification_code_sha256": digest("synthetic validation"), "result": {"status": "passed", "fixture_only": True}})
                rows.append({"dataset_id": dataset, "dataset_revision_id": revision, "input_digest": content,
                             "axis_id": axis, "depths": depths, "asset": asset, "path": path, "raw": raw,
                             "source_revision_id": prepared})
            members = [{key: row[key] for key in ("dataset_id", "dataset_revision_id")} for row in rows]
            release_manifest = {"dataset_revisions": members, "fixture_only": True}
            self.insert(conn, "data_release", {"id": release, "manifest_sha256": digest(release_manifest), "manifest": release_manifest})
            for member in members:
                self.insert(conn, "release_dataset", {"release_id": release, **member})
            composite = uid(label + "-composite")
            self.insert(conn, "borehole_composite", {"id": composite, "release_id": release, "borehole_id": hole,
                "composition_kind": "single_dataset" if len(rows) == 1 else "confirmed_successor_chain",
                "boundary_rule": "successor_first_actual_sample_md_m", "missing_policy": "preserve_no_fallback",
                "trajectory_kind": "display_composite_not_surveyed_path", "definition_sha256": digest(label), "evidence": {"fixture": True}})
            for index, row in enumerate(rows):
                upper_inclusive = index == len(rows) - 1
                lower = min(row["depths"])
                upper = max(row["depths"]) if upper_inclusive else min(rows[index + 1]["depths"])
                chosen = [number for number, depth in enumerate(row["depths"]) if lower <= depth and
                          (depth < upper or (upper_inclusive and depth == upper))]
                relation = None
                if index:
                    relation = uid(label + "-relation-" + str(index))
                    self.insert(conn, "dataset_succession", {"id": relation, "borehole_id": hole,
                        "predecessor_revision_id": rows[index - 1]["dataset_revision_id"], "successor_revision_id": row["dataset_revision_id"],
                        "relation_kind": "confirmed_display_successor", "switch_md_m": lower,
                        "switch_basis": "successor_first_actual_sample_md_m", "confirmation_basis": {"fixture": True}})
                self.insert(conn, "borehole_composite_part", {"composite_id": composite, "release_id": release, "borehole_id": hole,
                    "sequence_no": index, "dataset_id": row["dataset_id"], "dataset_revision_id": row["dataset_revision_id"],
                    "axis_id": row["axis_id"], "predecessor_relation_id": relation, "selection_from_md_m": lower,
                    "selection_to_md_m": upper, "upper_inclusive": upper_inclusive,
                    "sample_no_from": min(chosen), "sample_no_to": max(chosen), "selection_status": "selected"})
        return {"label": label, "rows": rows, "release_id": release, "acceptance": self.acceptance(label, rows, release)}

    def acceptance(self, label, rows, release):
        package = digest("fixture-package-" + label)
        content = {"package_sha256": package, "datasets": {row["dataset_id"]: {
            "source_revision_id": row["source_revision_id"], "raw_assets": [row["raw"]]} for row in rows}}
        first_path = settings.reports_dir / ("fixture_acceptance_1_" + label + ".json")
        write_json(first_path, {"stage": 1, "status": "passed", "fixture_only": True,
                               "content": content, "content_sha256": digest(content)})
        members = {row["dataset_id"]: {key: row[key] for key in ("dataset_revision_id", "input_digest")} for row in rows}
        path = settings.reports_dir / ("fixture_acceptance_2_" + label + ".json")
        write_json(path, {"stage": 2, "status": "passed", "fixture_only": True, "database": self.source,
            "release_id": release, "dataset_contents": members, "content_sha256": digest(members),
            "prepared_acceptances": [{"package_sha256": package, "content_sha256": digest(content), "report_path": path_reference(first_path)}]})
        write_json(path.parent / ("asset_manifest_" + release + ".json"), {"release_id": release, "assets": [row["asset"] for row in rows]})
        return path

    def export_upload(self, batch):
        started = time.monotonic()
        result = export.export_batch(batch["acceptance"], self.output / "exports")
        folder = Path(result["directory"])
        with contextlib.redirect_stdout(io.StringIO()):
            receipt = upload.upload_batch(folder, "etl4-offline-fixture", "ap-southeast-2", client=self.s3, workers=1)
        require(receipt["status"] == "complete", 'Upload incomplete')
        self.note('batch' + batch["label"] + 'Real export and upload to in-memory S3', datasets=result["datasets"],
                  objects=receipt["completed_objects"], seconds=round(time.monotonic() - started, 3))
        return folder

    def merge(self, folder, **kwargs):
        return merge.merge_batch(folder, connect=lambda: self.connect(self.target), **kwargs)

    def snapshot(self):
        result = {}
        with self.connect(self.target) as conn:
            for table in sorted(KNOWN_TABLES):
                rows = conn.execute(sql.SQL("SELECT to_jsonb(t) value FROM core.{} t ORDER BY to_jsonb(t)::text COLLATE \"C\"").format(sql.Identifier(table))).fetchall()
                result[table] = {"count": len(rows), "sha256": digest(rows)}
        return result

    def active(self):
        with self.connect(self.target) as conn:
            row = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()
        return str(row["release_id"]) if row else None

    def reject_cleanup(self, folder, label, **kwargs):
        before = {str(path): sha(path) for path in settings.raw_dir.rglob("*.bin")}
        try:
            cleanup.cleanup_batch(folder, self.output / "exports", settings.work_dir, raw_root=settings.raw_dir,
                                  include_raw=True, apply=False, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError('Cleanup incorrectly accepted an incomplete receipt')
        require({str(path): sha(path) for path in settings.raw_dir.rglob("*.bin")} == before, 'Files changed after cleanup was rejected')
        self.note(label, unchanged_files=len(before))

    def run(self):
        self.create_databases()
        a = self.source_batch("A", [(1, [0.0, 1.0, 1.0])])
        folder_a = self.export_upload(a)
        selection_a = self.output / "finalize_a.json"
        write_json(selection_a, {"expected_active_release_id": None,
            "datasets": [{key: row[key] for key in ("dataset_id", "dataset_revision_id")} for row in a["rows"]]})
        merged_a = self.merge(folder_a, apply_migrations=True, finalize=selection_a)
        require(self.active() == merged_a["release_id"], 'Release A was not activated')
        baseline = self.snapshot()
        puts_before = self.s3.puts
        again_a = self.export_upload(a)
        repeated_a = self.merge(again_a)
        require(repeated_a["reused"] and self.snapshot() == baseline and self.s3.puts == puts_before,
                'Rerunning A added records or objects')
        self.note('A complete rerun of A preserves all 39 table digests and adds no S3 objects', tables=39)
        original = a["rows"][0]["path"]
        unavailable = original.with_suffix(".unavailable")
        original.rename(unavailable)
        self.moved_sources.append((original, unavailable))
        require(not a["rows"][0]["path"].exists(), 'Source A was not isolated')
        b = self.source_batch("B", [(2, [0.0, 1.0, 2.0]), (3, [1.0, 2.0, 3.0])])
        subset = self.acceptance("B-incomplete", b["rows"][:1], b["release_id"])
        try:
            export.export_batch(subset, self.output / "exports")
        except ValueError as error:
            require('complete boreholes' in str(error), 'Incorrect partial-borehole rejection reason')
        else:
            raise AssertionError('A partial dataset subset of borehole B was incorrectly exported')
        b["acceptance"] = self.acceptance("B", b["rows"], b["release_id"])
        self.note('Complete-borehole selection rejects a partial dataset subset of a multi-dataset borehole')
        folder_b = self.export_upload(b)
        self.note('Batch B still exports and uploads independently after local source A becomes unavailable', a_source_available=False)
        # Raise a real database error during asset writes after inserting the second dataset and its samples.
        blocked_revision = b["rows"][1]["dataset_revision_id"]
        with self.connect(self.target) as conn:
            conn.execute(sql.SQL("""CREATE FUNCTION core.fixture_interrupt() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NEW.dataset_revision_id={}::uuid THEN
                RAISE EXCEPTION 'fixture interruption' USING ERRCODE='P0001'; END IF; RETURN NEW; END $$""").format(sql.Literal(blocked_revision)))
            conn.execute("CREATE TRIGGER fixture_interrupt BEFORE INSERT ON core.asset FOR EACH ROW EXECUTE FUNCTION core.fixture_interrupt()")
        try:
            self.merge(folder_b)
        except psycopg.errors.RaiseException:
            pass
        else:
            raise AssertionError('Injected database failure did not interrupt B')
        partial = read_json(folder_b / "merge_receipt.json")
        require(partial["status"] == "partial" and len(partial["datasets"]) == 1, 'Per-dataset progress was not preserved')
        with self.connect(self.target) as conn:
            count = conn.execute("SELECT count(*) n FROM core.dataset_revision WHERE id=%s", (blocked_revision,)).fetchone()["n"]
            sample_count = conn.execute("SELECT count(*) n FROM core.scan_sample WHERE axis_id=%s", (b["rows"][1]["axis_id"],)).fetchone()["n"]
            require(count == sample_count == 0, 'Failed dataset records or samples were not rolled back')
            require(conn.execute("SELECT count(*) n FROM core.dataset_revision").fetchone()["n"] == 2, 'The previously completed dataset was lost')
            conn.execute("DROP TRIGGER fixture_interrupt ON core.asset")
            conn.execute("DROP FUNCTION core.fixture_interrupt()")
        require(self.active() == merged_a["release_id"], 'Interrupting B switched the active release')
        self.note('A real transaction rolls back the second dataset in B while preserving the first', committed_datasets=1, rolled_back_revision=blocked_revision)
        self.reject_cleanup(folder_b, 'A partial merge receipt must not permit cleanup')
        incomplete_upload = self.output / "incomplete_upload.json"
        write_json(incomplete_upload, {**read_json(folder_b / "upload_receipt.json"), "status": "partial"})
        self.reject_cleanup(folder_b, 'A partial upload receipt must not permit cleanup', upload_receipt=incomplete_upload)
        completed_b = self.merge(folder_b)
        require(completed_b["status"] == "complete" and len(completed_b["datasets"]) == 2, 'B recovery did not complete')
        require(self.active() == merged_a["release_id"], 'Default candidate merge switched the active release')
        baseline = self.snapshot()
        repeated_b = self.merge(folder_b)
        require(repeated_b["reused"] and self.snapshot() == baseline, 'Rerunning B added business records')
        self.note('B resumes to completion while preserving A; reruns leave all 39 table counts and contents unchanged', candidate_release=completed_b["release_id"])
        bad_final = self.output / "finalize_bad.json"
        all_rows = a["rows"] + b["rows"]
        chosen = [{key: row[key] for key in ("dataset_id", "dataset_revision_id")} for row in all_rows]
        write_json(bad_final, {"expected_active_release_id": uid("wrong-release"), "datasets": chosen})
        try:
            self.merge(folder_b, finalize=bad_final)
        except ValueError as error:
            require('active release' in str(error), 'Incorrect finalize failure reason')
        else:
            raise AssertionError('An incorrect active-release precondition was accepted')
        require(self.active() == merged_a["release_id"] and self.snapshot() == baseline, 'Failed finalize changed the database or pointer')
        self.note('A finalize precondition mismatch rolls back the transaction and preserves the pointer')
        final_path = self.output / "finalize_all.json"
        write_json(final_path, {"expected_active_release_id": merged_a["release_id"], "datasets": chosen})
        final = self.merge(folder_b, finalize=final_path)
        require(self.active() == final["finalized_release_id"], 'The explicit final selection was not applied')
        with self.connect(self.target) as conn:
            actual = conn.execute("SELECT axis_id::text,sample_no,md_m,section_distance_mm FROM core.scan_sample ORDER BY axis_id,sample_no").fetchall()
            expected = sorted([{"axis_id": row["axis_id"], "sample_no": index, "md_m": depth, "section_distance_mm": None}
                               for row in all_rows for index, depth in enumerate(row["depths"])], key=lambda row: (row["axis_id"], row["sample_no"]))
            require(actual == expected, 'Complete source samples, repeated depths, or nulls changed')
            counts = conn.execute("""SELECT (SELECT count(*) FROM core.v_borehole_dataset_full WHERE release_id=%s) full_datasets,
                (SELECT count(*) FROM core.v_borehole_composite_samples WHERE release_id=%s) display_samples""",
                (self.active(), self.active())).fetchone()
            require(counts == {"full_datasets": 3, "display_samples": 7}, 'Single/multi-dataset display selections were not preserved')
        self.note('Retain complete sources for both final boreholes and their single/multi-dataset display selections', datasets=3, full_samples=9, display_samples=7,
                  duplicate_depth_and_null_preserved=True)
        self.report["final_snapshot"] = self.snapshot()
        self.report["s3"] = {"objects": len(self.s3.objects), "puts": self.s3.puts, "heads": self.s3.heads, "get_requests": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-config", type=Path, default=DATABASE.parent / "refactor_work/database/runtime/local_config.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "_codex_work/etl4_structure_batch_20261003/batch_flow")
    parser.add_argument("--run-id", default=uuid.uuid4().hex[:10], help='Used only for the two isolated databases and output subdirectory')
    parser.add_argument("--execute", action="store_true", help='Create, check, and delete the isolated databases for this run')
    args = parser.parse_args()
    check = Check(args.db_config, args.output_dir / args.run_id, args.run_id)
    if not args.execute:
        print(json.dumps({"scope": SCOPE, "databases": [check.source, check.target], "output": str(check.output),
                          "action": "preview only; add --execute to run; own databases are dropped in finally"}, ensure_ascii=False))
        return 0
    require(not check.output.exists(), 'The output directory already exists; use a new run-id')
    check.output.mkdir(parents=True)
    previous = copy.copy(settings.__dict__)
    settings.db_config, settings.dbname = check.config_path, check.source
    settings.work_dir, settings.raw_dir = check.output / "work", check.output / "raw"
    started = time.monotonic()
    try:
        check.run()
        check.report["status"] = "passed"
    except Exception as error:
        check.report["status"] = "failed"
        check.report["error_type"] = type(error).__name__
        check.report["error_frames"] = [{"file": frame.filename, "line": frame.lineno, "function": frame.name}
                                        for frame in traceback.extract_tb(error.__traceback__)]
        if isinstance(error, psycopg.Error):
            check.report["sqlstate"] = error.sqlstate
        if isinstance(error, (AssertionError, ValueError)):
            check.report["error"] = str(error)
        # Omit connection exception text to keep credentials out of logs.
        print('Check failed: ' + type(error).__name__, file=sys.stderr)
    finally:
        check.restore_sources()
        check.drop_databases()
        settings.__dict__.update(previous)
        check.report["seconds"] = round(time.monotonic() - started, 3)
        write_json(check.output / "report.json", check.report)
    print('Results:' + check.report["status"] + "；" + str(check.output / "report.json"))
    return 0 if check.report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
