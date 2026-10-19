"""Compare entry points using only 14CADD003; default to no database connection and execute only with --run."""

import argparse
import copy
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback
import uuid
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ETL = ROOT / "etl4"
DATABASE = ETL / "database"
sys.path[:0] = [str(DATABASE), str(ETL)]

import psycopg
from psycopg import sql
from _batch_files import write_json
from _db_common import connection
from _db_files import digest, inside, read, sha
from _file_checks import FileChecks
from _settings import settings
from _trial_support import drop_trial, fingerprints, trial_schema

PACKAGE_KEY = "ec89f56974ca834b7769d7cf578a10b685f999c56541e5937f916fe7356eef05"
CONFIG = (ETL / "refactor_work/database/runtime/local_config.json").resolve()
PREPARED_WORK = ETL / "structure_input_20260930"
PACKAGE = PREPARED_WORK / "database/media_releases" / PACKAGE_KEY
FIRST_ACCEPTANCE = (ETL / "single_final_check_20260930/database/reports"
                    / f"local_acceptance_1_{PACKAGE_KEY}.json")
OLD_SOURCE = HERE / "code_before/etl4/database/_final_import.py"
DATASET_ID = "8110cd1e-3b13-5589-b013-fc16d3f51105"
SOURCE_DATASET_ID = "978822fb-de28-4603-b02e-af6882e5951"
REVISION_ID = "984f74b7-3ba5-5d14-bf9d-9f8f783d1506"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    """Write test reports only in this run directory, without production report path boundaries."""
    write_json(inside(HERE, path), value)


def error_details(error):
    """Record stack locations only, without source lines, local variables or connection exception bodies."""
    detail = {"error_type": type(error).__name__, "frames": [
        {"file": frame.filename, "line": frame.lineno, "function": frame.name}
        for frame in traceback.extract_tb(error.__traceback__)
    ]}
    if isinstance(error, (ValueError, AssertionError)) and not isinstance(error, psycopg.Error):
        detail["error"] = str(error)
    return detail


def preflight():
    """Check small manifests and configuration first; validate complete files before database creation."""
    overrides = sorted(name for name, value in os.environ.items() if value and
                       (name.startswith("PG") or (name.startswith("ETL4_") and "DSN" in name)))
    require(not overrides, 'Remove connection-override environment variables first: ' + ", ".join(overrides))
    require(CONFIG.is_absolute() and CONFIG.is_file(), 'Missing explicit configuration for the original local instance')
    config = read(CONFIG)
    require(config.get("host") == "127.0.0.1" and int(config.get("port", 0)) == 55433,
            'Tests permit only the original local instance at 127.0.0.1:55433')
    require(OLD_SOURCE.is_file() and FIRST_ACCEPTANCE.is_file(), 'Missing old source or actual first-validation report')
    manifest = read(PACKAGE / "manifest.json")
    require(set(manifest.get("datasets", {})) == {DATASET_ID}, 'Input package is not the expected single dataset')
    accepted = read(FIRST_ACCEPTANCE)
    require(accepted.get("stage") == 1 and accepted.get("status") == "passed"
            and accepted.get("dataset_count") == 1, 'The original first validation did not pass')
    content = accepted.get("content", {})
    require(content.get("package_sha256") == PACKAGE_KEY
            and set(content.get("datasets", {})) == {DATASET_ID}
            and accepted.get("content_sha256") == digest(content), 'Original first-validation content binding differs')
    return {
        "status": "metadata_ready", "database_accessed": False,
        "config_file": str(CONFIG), "host": "127.0.0.1", "port": 55433,
        "package": str(PACKAGE), "prepared_work": str(PREPARED_WORK),
        "first_acceptance": str(FIRST_ACCEPTANCE), "first_acceptance_sha256": sha(FIRST_ACCEPTANCE),
        "old_source": str(OLD_SOURCE), "old_source_sha256": sha(OLD_SOURCE),
        "new_source_sha256": sha(DATABASE / "37_import_final_version.py"),
        "scope": {"hole": "14CADD003", "datasets": 1, "samples": 1584, "row_images": 12, "spectral_arrays": 2},
        "pending_before_database_creation": 'Compare the complete prepared package and contents against the actual first validation',
    }


def load_previous_import():
    specification = importlib.util.spec_from_file_location("previous_final_import_37_check", OLD_SOURCE)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def guarded_connections(allowed_databases):
    """Recheck the target at the connection layer; prohibit old or remote databases."""
    original_connect = psycopg.connect

    def connect(*args, **kwargs):
        require(not args and not kwargs.get("conninfo"), 'This test does not accept DSN connection strings')
        require(kwargs.get("host") == "127.0.0.1" and int(kwargs.get("port", 0)) == 55433,
                'Connection outside the local test instance blocked')
        require(kwargs.get("dbname") in allowed_databases, 'Connection to an existing business database blocked')
        require(not kwargs.get("hostaddr") and not kwargs.get("service"), 'Fallback connection addresses and service overrides are prohibited')
        return original_connect(**kwargs)

    return patch.object(psycopg, "connect", side_effect=connect)


def database_state(trial):
    with connection("reader", dbname=trial) as conn:
        active = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='core' ORDER BY tablename").fetchall()
        counts = {}
        for row in rows:
            table = row["tablename"]
            counts[table] = conn.execute(sql.SQL("SELECT count(*) n FROM core.{}").format(sql.Identifier(table))).fetchone()["n"]
        members = conn.execute("""SELECT rd.dataset_id,rd.dataset_revision_id,r.input_digest
            FROM core.release_dataset rd JOIN core.dataset_revision r ON r.id=rd.dataset_revision_id
            WHERE rd.release_id=%s ORDER BY rd.dataset_id""", (active["release_id"],)).fetchall()
    return {"release_id": str(active["release_id"]), "counts": counts,
            "members": json.loads(json.dumps(members, default=str)), "business_fingerprints": fingerprints(trial)}


def run_import(function, batch, label, directory):
    started = time.perf_counter()
    with FileChecks() as scans:
        result = function(copy.deepcopy(batch))
        stats = scans.stats()
    report = {"label": label, "result": result, "file_checks": stats,
              "elapsed_seconds": time.perf_counter() - started}
    save(directory / f"{label}.json", report)
    return result


def compare_replay(first_result, before, result, after):
    require(result["dataset_contents"] == first_result["dataset_contents"], 'Rerun changed dataset content identity')
    require(result["release_id"] == first_result["release_id"] == before["release_id"] == after["release_id"],
            'Rerun changed release identity')
    require(before["members"] == after["members"], 'Rerun changed release membership')
    require(before["business_fingerprints"] == after["business_fingerprints"], 'Rerun changed business records')
    actions = [row["action"] for row in result["datasets"]]
    require(actions == ["already_present"], 'Rerun did not reuse the existing revision')
    changed = {name: after["counts"][name] - value for name, value in before["counts"].items()
               if after["counts"][name] != value}
    require(changed == {"ingest_run": 1}, 'Rerun changed row counts beyond expected run records')
    return {"run_id": result["run_id"], "release_id": result["release_id"], "actions": actions,
            "compared_business_tables": len(after["business_fingerprints"]),
            "business_fingerprints_unchanged": True, "dataset_identity_unchanged": True,
            "release_unchanged": True, "count_changes": changed, "new_business_records": 0}


def run_check(prepared):
    """Import through the new entry point, then rerun old and new versions in order; read only this new test database."""
    suffix = uuid.uuid4().hex[:12]
    trial = "etl4_test_structure37_" + suffix
    directory = HERE / ("local_37_" + suffix)
    directory.mkdir()
    work = directory / "work"
    old_settings = copy.copy(settings.__dict__)
    allowed_databases = {"postgres"}
    created = False
    report = {"status": "running", "preflight": prepared, "trial_database": trial,
              "output_directory": str(directory), "only_created_trial_database_modified": True,
              "raw_or_prepared_files_modified": False, "api_or_aws_used": False,
              "trial_database_created": False, "trial_database_dropped": False,
              "earlier_script_failure": 'The test used a production report writer restricted to database_dir; it stopped before database creation and preserved the failed work directory'}
    report_path = HERE / "local_37_old_new_validation.json"
    started = time.perf_counter()
    try:
        settings.work_dir = work
        settings.raw_dir = ETL
        settings.db_config = CONFIG
        settings.dbname = "etl4_structure37_connection_guard"
        settings.reports_dir.mkdir(parents=True)
        # Copy the original bytes of existing passed reports without inventing or rewriting validation results.
        (settings.reports_dir / FIRST_ACCEPTANCE.name).write_bytes(FIRST_ACCEPTANCE.read_bytes())
        batch = {"packages": [{"directory": str(PACKAGE), "prepared_work_dir": str(PREPARED_WORK)}],
                 "decisions": {"orders": {}}}
        save(directory / "batch.json", batch)
        old = load_previous_import()
        new = importlib.import_module("37_import_final_version")
        # Validate all source files under both old and new input rules before creating a database.
        with patch.object(psycopg, "connect", side_effect=AssertionError('Database connections are prohibited during input checks')), FileChecks() as scans:
            old_items = old.load_final_inputs(copy.deepcopy(batch))
            new_items = new.load_final_inputs(copy.deepcopy(batch))
            fields = ("dataset_id", "dataset_revision_id", "axis_id", "input_digest")
            old_identity = [{name: item[name] for name in fields} for item in old_items]
            new_identity = [{name: item[name] for name in fields} for item in new_items]
            require(old_identity == new_identity and len(old_items) == 1, 'Old and new input identities differ')
            item = old_items[0]
            require(item["dataset_id"] == DATASET_ID and item["dataset_revision_id"] == REVISION_ID
                    and item["unit"]["source_dataset_id"] == SOURCE_DATASET_ID
                    and item["unit"]["hole_id"] == "14CADD003" and item["unit"]["sample_count"] == 1584,
                    'Input scope is not the approved minimum single borehole')
            report["input_identity"] = old_identity
            report["input_checks"] = scans.stats()
        save(report_path, report)

        with guarded_connections(allowed_databases):
            with connection(dbname="postgres") as conn:
                conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(trial)))
            created = True
            allowed_databases.add(trial)
            try:
                report["trial_database_created"] = True
                save(report_path, report)
                settings.dbname = trial
                trial_schema(trial)
                first_new = run_import(new.run_final_import, batch, "first_new", directory)
                first_state = database_state(trial)
                require([row["action"] for row in first_new["datasets"]] == ["inserted"], 'The new entry point did not complete its initial import')
                require(first_state["counts"]["dataset_revision"] == 1 and first_state["counts"]["scan_sample"] == 1584
                        and first_state["counts"]["image_region"] == 12 and first_state["counts"]["spectral_array"] == 2,
                        'Initial import counts do not match the minimum single-borehole scope')
                require(first_new["status"] == "passed" and all(check["status"] == "passed" for check in first_new["checks"]),
                        'Initial import through the new entry point failed validation')
                save(directory / "state_first_new.json", first_state)
                report["first_new"] = {"run_id": first_new["run_id"], "release_id": first_new["release_id"],
                                       "actions": ["inserted"], "counts": first_state["counts"], "verified": True}
                save(report_path, report)

                old_replay = run_import(old.run_final_import, batch, "old_replay", directory)
                old_state = database_state(trial)
                save(directory / "state_old_replay.json", old_state)
                report["old_replay"] = compare_replay(first_new, first_state, old_replay, old_state)
                save(report_path, report)

                new_replay = run_import(new.run_final_import, batch, "new_replay", directory)
                new_state = database_state(trial)
                save(directory / "state_new_replay.json", new_state)
                report["new_replay"] = compare_replay(first_new, old_state, new_replay, new_state)
                report.update(status="passed", release_id=new_replay["release_id"], counts=new_state["counts"],
                              compared_business_tables=len(new_state["business_fingerprints"]),
                              business_fingerprints_unchanged=True, dataset_identity_unchanged=True,
                              release_unchanged=True, total_replay_count_changes={"ingest_run": 2},
                              new_business_records_from_replays=0)
            finally:
                # Drop only the random database successfully created by this process, never an existing business database.
                if created:
                    settings.dbname = "etl4_structure37_connection_guard"
                    drop_trial(trial)
                    created = False
                    report["trial_database_dropped"] = True
    except Exception as error:
        report.update(status="failed", **error_details(error))
        raise
    finally:
        settings.__dict__.update(old_settings)
        report["elapsed_seconds"] = time.perf_counter() - started
        save(report_path, report)
        save(directory / "validation.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help='Explicitly start validation in a new local temporary database; otherwise do not connect')
    args = parser.parse_args()
    prepared = preflight()
    result = run_check(prepared) if args.run else prepared
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps(error_details(error), ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
