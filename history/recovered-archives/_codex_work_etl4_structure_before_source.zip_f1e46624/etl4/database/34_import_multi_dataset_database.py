"""Import complete dataset and media revisions, then create a combined release pending validation."""

import uuid
from pathlib import Path
from _db_common import (
    assert_schema,
    CODE,
    LOCK_KEY,
    ROOT,
    connection,
    digest,
    insert,
    main_guard,
    pick,
    read,
    schema_hash,
    uid,
    write,
)
from _multi_common import MULTI, MULTI_EVIDENCE, MULTI_HOLES, require
from _multi_db import baseline_backup, install_composites
from _settings import StepParser
from psycopg.types.json import Jsonb


def main():
    parser = StepParser()
    parser.add_argument("--source-release")
    parser.add_argument("--package", type=Path)
    args = parser.parse_args()
    baseline = baseline_backup(args.source_release)
    decisions = read(CODE / "multi_dataset_decisions.json")
    require(decisions["confirmed_by"] == "project_owner", "Unconfirmed succession policy")
    import _media_common as mc
    import _media_import as mi

    if args.package:
        dest = args.package.resolve()
        manifest = read(dest / "manifest.json")
        key = digest(manifest)
        mi.check_package(dest, manifest)
    else:
        require(
            read(MULTI / "33_media_ready.json")["status"] == "passed",
            "Media is not reviewed and prepared",
        )
        key, dest, manifest = mi.prepare_package(work=MULTI / "media", evidence_dir=MULTI_EVIDENCE)
    selected = [mi.prepared_context(u) for u in mi.package_step(dest, 20)["datasets"]]
    import _ingest as ingest

    results = []
    run_id = str(uuid.uuid4())
    with connection("ingest") as conn:
        assert_schema(conn)
        require(
            conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"],
            "Another importer or validator is active",
        )
        insert(
            conn,
            "ingest_run",
            {
                "id": run_id,
                "input_digest": key,
                "code_sha256": mi.media_code_hash(),
                "schema_sha256": schema_hash(),
                "holes": Jsonb(list(MULTI_HOLES)),
                "status": "running",
            },
        )
        try:
            with conn.transaction():
                for h in selected:
                    u = h["summary"]
                    print(f"Import complete dataset {u['source_dataset_name']}", flush=True)
                    # Pass the context and input manifest for one dataset at a time.

                    ingest.import_hole(conn, h)
                    seg = uid("full-source-segment", u["dataset_revision_id"])
                    if not conn.execute(
                        "SELECT 1 FROM core.dataset_segment WHERE id=%s", (seg,)
                    ).fetchone():
                        insert(
                            conn,
                            "dataset_segment",
                            {
                                "id": seg,
                                "dataset_revision_id": u["dataset_revision_id"],
                                "borehole_id": h["metadata"]["borehole"]["id"],
                                "branch_id": None,
                                "axis_id": u["axis_id"],
                                "sample_no_from": 0,
                                "sample_no_to": u["sample_count"] - 1,
                                "sequence_no": None,
                                "evidence": {
                                    "scope": "complete independent dataset; no 3D clipping",
                                    "source_dataset_id": u["source_dataset_id"],
                                },
                            },
                        )
                for u in mi.package_step(dest, 20)["datasets"]:
                    print(f"Import row images and spectra {u['source_dataset_name']}", flush=True)
                    results.append(mi.import_media(conn, u, key, dest, manifest))
                members = [
                    pick(r, "dataset_id", "dataset_revision_id") for r in baseline["members"]
                ] + [pick(r, "dataset_id", "dataset_revision_id") for r in results]
                members.sort(key=lambda x: str(x["dataset_id"]))
                require(
                    len({str(r["dataset_id"]) for r in members}) == len(members),
                    "Duplicate dataset in combined release",
                )
                from _publication import stage_release

                release = stage_release(
                    conn,
                    members,
                    "local_multi_dataset_v2",
                    {
                        "source_release_id": baseline["release_id"],
                        "succession_decisions": decisions,
                    },
                )
                groups = install_composites(conn, release, decisions)
            conn.execute(
                "UPDATE core.ingest_run SET status='staged',finished_at=now(),detail=%s WHERE id=%s",
                (Jsonb({"release_id": release, "datasets": results}), run_id),
            )
        except Exception as exc:
            conn.execute(
                "UPDATE core.ingest_run SET status='failed',finished_at=now(),detail=%s WHERE id=%s",
                (Jsonb({"error_type": type(exc).__name__, "message": str(exc)}), run_id),
            )
            raise
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    staged = {
        "status": "staged",
        "release_id": release,
        "datasets": results,
        "media_package_sha256": key,
        "package_directory": dest.relative_to(ROOT).as_posix(),
        "previous_release_id": baseline["release_id"],
        "composites": groups,
        "source_units": mi.package_step(dest, 20)["datasets"],
        "run_id": run_id,
    }
    mc.save_stage(28, staged, work=MULTI / "media")
    write(MULTI / "34_import.json", staged)
    print(f"Staged {len(members)} datasets in {len(groups)} holes; active release awaits step 35.")


if __name__ == "__main__":
    main_guard(main)
