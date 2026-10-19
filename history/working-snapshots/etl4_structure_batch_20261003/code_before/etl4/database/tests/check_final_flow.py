"""Validate final revisions, recovery, and failure boundaries in a temporary database using explicitly selected prepared packages."""

import copy
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _db_common import connection
from _db_files import encoded, read, sha, write
from _file_checks import FileChecks
from _final_import import import_final_dataset, load_final_inputs, run_final_import
from _settings import StepParser, configure, settings
from _trial_support import create_trial, drop_trial, fingerprints, trial_schema


def active():
    with connection() as conn:
        return str(conn.execute("SELECT release_id FROM core.active_release").fetchone()["release_id"])


def count_revisions():
    with connection() as conn:
        return conn.execute("SELECT count(*) n FROM core.dataset_revision").fetchone()["n"]


def expect_failure(name, operation, results):
    try:
        operation()
    except (ValueError, OSError, psycopg.Error) as error:
        results[name] = {"status": "passed", "rejected_by": type(error).__name__, "message": str(error).splitlines()[0]}
        return
    raise AssertionError(name + ": invalid operation was accepted")


def run_checks(batch):
    original_database = settings.dbname
    original_work = settings.work_dir
    trial = create_trial("test")
    results = {"database": trial}
    try:
        trial_schema(trial)
        trial_work = original_work / "validation_trials" / trial
        (trial_work / "database/runtime").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original_work / "database/runtime/local_config.json",
                        trial_work / "database/runtime/local_config.json")
        settings.work_dir = trial_work
        settings.dbname = trial
        with patch("_media_import.clone_revision", side_effect=AssertionError("Final flow called clone_revision")):
            first = run_final_import(batch)
        expected = len(first["datasets"])
        assert expected >= 2 and count_revisions() == expected
        results["first_import"] = {"revisions": expected, "elapsed_seconds": first["elapsed_seconds"]}
        before = fingerprints()
        actual_sha = sha

        def changed_code_hash(path):
            if Path(path).name == "_final_import.py":
                return "e" * 64
            return actual_sha(path)

        # Simulate source/validator hash changes while keeping data inputs and explicit processing rules unchanged.
        with patch("_final_import.sha", side_effect=changed_code_hash):
            replay = run_final_import(batch)
        assert fingerprints() == before and replay["release_id"] == first["release_id"]
        assert all(r["action"] == "already_present" for r in replay["datasets"])
        results["code_only_replay"] = {"new_business_records": 0, "elapsed_seconds": replay["elapsed_seconds"]}

        items = load_final_inputs(batch)
        changed = copy.deepcopy(batch)
        source_id = items[0]["unit"]["source_dataset_id"]
        changed["rule_versions"] = {source_id: "single-final-history-test-v2"}
        changed["source_release_id"] = first["release_id"]
        history = run_final_import(changed)
        assert count_revisions() == expected + 1
        assert sum(r["action"] == "inserted" for r in history["datasets"]) == 1
        with connection() as conn:
            assert conn.execute("SELECT 1 FROM core.data_release WHERE id=%s", (first["release_id"],)).fetchone()
        results["one_dataset_rule_change"] = {"new_revisions": 1, "previous_release_preserved": True}
        increment_replay = run_final_import(changed)
        assert increment_replay["release_id"] == history["release_id"] and count_revisions() == expected + 1
        results["incremental_replay_uses_recorded_source"] = True

        changed["source_release_id"] = history["release_id"]
        changed["rule_versions"][source_id] = "single-final-failure-test-v3"
        stable = fingerprints()
        previous = active()
        expect_failure("sample_copy_interruption", lambda: run_final_import(changed, fail_after_samples=True), results)
        assert fingerprints() == stable and active() == previous
        with patch("_final_import.verify_dataset", side_effect=ValueError("Injected verification failure")):
            expect_failure("verification_failure", lambda: run_final_import(changed), results)
        assert fingerprints() == stable and active() == previous
        with patch("_publication.write_asset_manifest", side_effect=OSError("Injected manifest write failure")):
            expect_failure("manifest_write_failure", lambda: run_final_import(changed), results)
        assert active() == previous and count_revisions() == expected + 2
        results["manifest_write_failure"]["completed_version_retained_for_resume"] = True
        resumed = run_final_import(changed)
        assert count_revisions() == expected + 2
        assert all(r["action"] == "already_present" for r in resumed["datasets"])
        results["resume_completed_versions"] = {"new_business_versions": 0, "status": "passed"}

        # Run each error case in its own transaction and check that every business table remains unchanged.
        stable = fingerprints()
        with connection() as conn:
            def attempt(item):
                with conn.transaction():
                    import_final_dataset(conn, item)
                    raise AssertionError("Invalid dataset was inserted")

            conflict = load_final_inputs(changed)[0]
            conflict["input_digest"] = "f" * 64
            expect_failure("same_identity_different_output", lambda: attempt(conflict), results)
            for name in ("wrong_crop_source", "spectral_dimensions", "cross_dataset_log", "sample_out_of_range"):
                candidate_batch = copy.deepcopy(changed)
                candidate_batch["rule_versions"][source_id] = "single-final-" + name
                candidate = load_final_inputs(candidate_batch)[0]
                selected = candidate["package"]["datasets"][candidate["dataset_id"]]
                if name == "wrong_crop_source":
                    selected["rows"][0]["source_path"] = "images/another-source.jpg"
                elif name == "spectral_dimensions":
                    selected["arrays"][0]["band_count"] += 1
                elif name == "cross_dataset_log":
                    selected["arrays"][0]["log_id"] = "not-this-dataset-log"
                else:
                    selected["rows"][0]["sample_no_to"] = candidate["unit"]["sample_count"]
                expect_failure(name, lambda: attempt(candidate), results)
        assert fingerprints() == stable
        results["all_fault_transactions_rolled_back"] = True
        return results
    finally:
        settings.dbname = original_database
        settings.work_dir = original_work
        drop_trial(trial)


def main():
    parser = StepParser()
    parser.add_argument("--batch", type=Path, required=True)
    args = parser.parse_args()
    configure(args)
    with FileChecks() as scans:
        result = run_checks(read(args.batch))
        result["file_checks"] = scans.stats()
    result["status"] = "passed"
    write(settings.reports_dir / "final_flow_failure_checks.json", result)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
