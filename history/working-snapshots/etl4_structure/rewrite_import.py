from pathlib import Path

Path('etl4/database/34_import_multi_dataset_database.py').write_text("""\"\"\"Read the complete input package, import datasets and media, and create a release pending validation.\"\"\"

import uuid
from pathlib import Path

from psycopg.types.json import Jsonb
from _db_common import (
    CODE, assert_schema, LOCK_KEY, ROOT, connection, digest, insert, main_guard,
    pick, read, schema_hash, uid, write,
)
from _ingest import import_hole
from _media_common import media_code_hash, require, save_stage
from _media_import import check_package, import_media, package_step, prepare_package, prepared_context
from _multi_common import MULTI, MULTI_EVIDENCE, MULTI_HOLES
from _multi_db import load_or_record_source_release, install_composites
from _publication import stage_release
from _settings import StepParser


def parse_arguments():
    parser = StepParser()
    parser.add_argument("--source-release")
    parser.add_argument("--package", type=Path)
    return parser.parse_args()


def load_input_package(package_dir, media_work_dir, evidence_dir):
    if package_dir is not None:
        package_dir = package_dir.resolve()
        manifest = read(package_dir / "manifest.json")
        check_package(package_dir, manifest)
        return digest(manifest), package_dir, manifest
    require(
        read(media_work_dir.parent / "33_media_ready.json")["status"] == "passed",
        "Media is not reviewed and prepared",
    )
    return prepare_package(work=media_work_dir, evidence_dir=evidence_dir)


def add_complete_segment(conn, dataset_context):
    \"\"\"Preserve all dataset samples and record display intervals separately.\"\"\"
    summary = dataset_context["summary"]
    segment_id = uid("full-source-segment", summary["dataset_revision_id"])
    if conn.execute("SELECT 1 FROM core.dataset_segment WHERE id=%s", (segment_id,)).fetchone():
        return
    insert(conn, "dataset_segment", {
        "id": segment_id,
        "dataset_revision_id": summary["dataset_revision_id"],
        "borehole_id": dataset_context["metadata"]["borehole"]["id"],
        "branch_id": None,
        "axis_id": summary["axis_id"],
        "sample_no_from": 0,
        "sample_no_to": summary["sample_count"] - 1,
        "sequence_no": None,
        "evidence": {
            "scope": "complete independent dataset; no 3D clipping",
            "source_dataset_id": summary["source_dataset_id"],
        },
    })


def import_complete_datasets(conn, datasets):
    for dataset in datasets:
        dataset_context = prepared_context(dataset)
        print(f"Import complete dataset {dataset['source_dataset_name']}", flush=True)
        import_hole(conn, dataset_context)
        add_complete_segment(conn, dataset_context)


def import_dataset_media(conn, datasets, package_key, package_dir, manifest):
    results = []
    for dataset in datasets:
        print(f"Import row images and spectra {dataset['source_dataset_name']}", flush=True)
        results.append(import_media(conn, dataset, package_key, package_dir, manifest))
    return results


def combine_release_members(source_release, results):
    members = [
        pick(dataset, "dataset_id", "dataset_revision_id")
        for dataset in source_release["members"] + results
    ]
    members.sort(key=lambda dataset: str(dataset["dataset_id"]))
    require(
        len({str(dataset["dataset_id"]) for dataset in members}) == len(members),
        "Duplicate dataset in combined release",
    )
    return members


def start_import_record(conn, package_key):
    run_id = str(uuid.uuid4())
    insert(conn, "ingest_run", {
        "id": run_id,
        "input_digest": package_key,
        "code_sha256": media_code_hash(),
        "schema_sha256": schema_hash(),
        "holes": Jsonb(list(MULTI_HOLES)),
        "status": "running",
    })
    return run_id


def finish_import_record(conn, run_id, status, detail):
    conn.execute(
        "UPDATE core.ingest_run SET status=%s,finished_at=now(),detail=%s WHERE id=%s",
        (status, Jsonb(detail), run_id),
    )


def import_release(conn, source_release, datasets, package_key, package_dir, manifest, decisions):
    assert_schema(conn)
    require(
        conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"],
        "Another importer or validator is active",
    )
    try:
        run_id = start_import_record(conn, package_key)
        try:
            # Samples, media, and the pending release share one import transaction; roll back on any failure.
            with conn.transaction():
                import_complete_datasets(conn, datasets)
                results = import_dataset_media(conn, datasets, package_key, package_dir, manifest)
                members = combine_release_members(source_release, results)
                release_id = stage_release(conn, members, "local_multi_dataset_v2", {
                    "source_release_id": source_release["release_id"],
                    "succession_decisions": decisions,
                })
                groups = install_composites(conn, release_id, decisions)
            finish_import_record(conn, run_id, "staged", {"release_id": release_id, "datasets": results})
        except Exception as error:
            finish_import_record(conn, run_id, "failed", {
                "error_type": type(error).__name__, "message": str(error),
            })
            raise
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    return {
        "status": "staged", "release_id": release_id, "datasets": results,
        "previous_release_id": source_release["release_id"], "composites": groups, "run_id": run_id,
    }


def save_import_result(result, datasets, package_key, package_dir, database_dir, work_dir):
    result = {
        **result,
        "media_package_sha256": package_key,
        "package_directory": package_dir.relative_to(database_dir).as_posix(),
        "source_units": datasets,
    }
    save_stage(28, result, work=work_dir / "media")
    write(work_dir / "34_import.json", result)
    return result


def main():
    args = parse_arguments()
    source_release = load_or_record_source_release(args.source_release, work=MULTI, dbname=args.dbname)
    decisions = read(CODE / "multi_dataset_decisions.json")
    require(decisions["confirmed_by"] == "project_owner", "Unconfirmed succession policy")
    package_key, package_dir, manifest = load_input_package(args.package, MULTI / "media", MULTI_EVIDENCE)
    datasets = package_step(package_dir, 20)["datasets"]
    with connection("ingest", dbname=args.dbname) as conn:
        result = import_release(conn, source_release, datasets, package_key, package_dir, manifest, decisions)
    save_import_result(result, datasets, package_key, package_dir, ROOT, MULTI)
    dataset_count = len(source_release["members"]) + len(result["datasets"])
    print(f"Staged {dataset_count} datasets in {len(result['composites'])} holes; active release awaits step 35.")


if __name__ == "__main__":
    main_guard(main)
""", encoding='utf-8')
