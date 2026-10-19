"""Compare the legacy and final-version workflows in two temporary databases using identical prepared packages."""

import importlib
import sys
import time
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _db_common import ETL, connection
from _db_files import read, write
from _file_checks import FileChecks
from _final_import import load_final_inputs
from _ingest import import_hole
from _legacy_media_import import import_media
from _media_verification import verify_dataset
from _multi_db import install_composites
from _prepared_inputs import prepared_holes
from _publication import publish_release, stage_release
from _settings import StepParser, configure, settings
from _trial_support import create_trial, drop_trial, fingerprints, trial_schema
from _verification import verify_hole

final_entry = importlib.import_module("37_import_final_version")


def old_flow(batch):
    items = load_final_inputs(batch)
    originals = prepared_holes(work_dir=ETL / batch["packages"][0]["prepared_work_dir"])
    with connection("ingest") as conn:
        base_checks, base_members = [], []
        for context in originals:
            with conn.transaction():
                result = import_hole(conn, context)
                base_checks.append(verify_hole(conn, context))
                base_members.append({"dataset_id": context["metadata"]["dataset"]["id"],
                                     "dataset_revision_id": result["dataset_revision_id"]})
        with conn.transaction():
            base_release = stage_release(conn, base_members, "benchmark_base")
            publish_release(conn, base_release, base_checks, __file__, activate=False)
        imported = []
        for item in items:
            with conn.transaction():
                imported.append(import_media(conn, item["package"], item["dataset_id"]))
        with conn.transaction():
            release = stage_release(conn, imported, "benchmark_media", {"source_release_id": base_release})
            install_composites(conn, release, {"orders": {}})
        checks = []
        for item, media in zip(items, imported, strict=True):
            check = verify_dataset(conn, item["unit"], media, release, item["package"])
            check.update(status="passed", dataset_revision_id=media["dataset_revision_id"],
                         input_digest=item["package"]["manifest"]["datasets"][item["dataset_id"]]["content_sha256"])
            checks.append(check)
        publish_release(conn, release, checks, __file__)


def measure(function, batch):
    started = time.perf_counter()
    with FileChecks() as checks:
        function(batch)
        result = checks.stats()
    result["elapsed_seconds"] = time.perf_counter() - started
    with connection() as conn:
        result["revisions"] = conn.execute("SELECT count(*) n FROM core.dataset_revision").fetchone()["n"]
        result["physical_samples"] = conn.execute("SELECT count(*) n FROM core.scan_sample").fetchone()["n"]
    return result


def main():
    parser = StepParser()
    parser.add_argument("--batch", type=Path, required=True)
    args = parser.parse_args()
    configure(args)
    batch = read(args.batch)
    original_database = settings.dbname
    original_work = settings.work_dir
    result = {"scope": 'Use the same existing files for two boreholes, including base and media acceptance; exclude download, preparation, and API startup'}
    for name, function in (("old_two_stage", old_flow), ("single_final", final_entry.run_final_import)):
        trial = create_trial("test")
        try:
            trial_schema(trial)
            trial_work = original_work / "measurement_trials" / trial
            (trial_work / "database/runtime").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original_work / "database/runtime/local_config.json",
                            trial_work / "database/runtime/local_config.json")
            settings.work_dir = trial_work
            settings.dbname = trial
            first = measure(function, batch)
            before = fingerprints()
            replay = measure(function, batch)
            assert fingerprints() == before
            replay["new_business_records"] = 0
            result[name] = {"first_import": first, "replay": replay}
        finally:
            settings.dbname = original_database
            settings.work_dir = original_work
            drop_trial(trial)
    write(settings.reports_dir / "final_flow_measurement.json", result)
    print(result)


if __name__ == "__main__":
    main()
