"""Import once after complete preparation, creating one final revision per dataset."""

import copy
import json
import time
import uuid
from pathlib import Path

from psycopg.types.json import Jsonb
from _db_common import LOCK_KEY, assert_schema, connection, insert, schema_hash, uid
from _db_files import digest, encoded, read, sha, write
from _file_checks import fresh_file_checks
from _ingest import import_hole, prepared_content
from _media_common import require
from _media_import import (
    check_package, insert_media_records, remap, verify_media_sources,
    package_contexts, prepared_acceptance_content,
)
from _media_verification import verify_dataset
from _multi_db import install_composites, verify_composites
from _publication import publish_release, release_identity, release_members, stage_release
from _settings import settings, input_directory

FINAL_RULE_VERSION = "single-final-v1"


def load_final_inputs(batch):
    """Read explicitly listed sealed packages; locate older preparation manifests through the specified work directory."""
    result = []
    seen = set()
    require(batch.get("packages"), 'The batch has no input packages')
    for item in batch["packages"]:
        destination = input_directory(item["directory"])
        package = check_package(destination, read(destination / "manifest.json"))
        work = input_directory(item["prepared_work_dir"])
        contexts = package_contexts(package, work)
        content = prepared_acceptance_content(package, contexts)
        acceptance_path = settings.reports_dir / f"local_acceptance_1_{package['key']}.json"
        if not acceptance_path.exists():
            acceptance_path = destination.parent.parent / "reports" / acceptance_path.name
        require(acceptance_path.is_file(), 'First local acceptance is missing; run step 28 --package-only first')
        acceptance = read(acceptance_path)
        require(acceptance.get("stage") == 1 and acceptance.get("status") == "passed"
                and acceptance.get("content") == content
                and acceptance.get("content_sha256") == digest(content),
                'First local acceptance does not match the current inputs; rerun step 28 --package-only')
        for dataset_id, selected in package["datasets"].items():
            require(dataset_id not in seen, 'The batch contains a duplicate dataset')
            seen.add(dataset_id)
            unit = selected["unit"]
            context = contexts[dataset_id]
            rules = batch.get("rule_versions", {}).get(unit["source_dataset_id"], FINAL_RULE_VERSION)
            require(isinstance(rules, str) and bool(rules.strip()), 'The processing rule version must not be empty')
            result.append(make_final_context(context, package, dataset_id, rules))
    unknown = set(batch.get("rule_versions", {})) - {x["unit"]["source_dataset_id"] for x in result}
    require(not unknown, 'Rule version overrides include datasets outside this batch')
    return result


def make_final_context(source, package, dataset_id, rules=FINAL_RULE_VERSION):
    """Replace only internal relation IDs; preserve source documents and scientific values in Parquet files."""
    selected = package["datasets"][dataset_id]
    unit = selected["unit"]
    media = package["manifest"]["datasets"][dataset_id]
    original = source["metadata"]["dataset_revision"]
    identity = {
        "dataset_id": dataset_id,
        "source_snapshot_id": original["source_snapshot_id"],
        "preparation_rules": original["pipeline_id"],
        "media_input_key": media["input_key"],
        "final_rules": rules,
        "raw_files": sorted(
            [a["source_relative_path"], a["byte_size"], a["sha256"]]
            for a in source["storage"]["raw_assets"]
        ),
    }
    key = digest(identity)
    revision = uid("final-revision", dataset_id, key)
    content = digest({
        "prepared": prepared_content(source),
        "bindings": sha(source["folder"] / "4_axis_bindings.json"),
        "media": media["content_sha256"],
    })
    documents = {
        name: read(source["folder"] / name)
        for name in ("4_core_intervals.json", "4_axis_bindings.json", "4_image_frames.json")
    }
    ids = {original["id"]: revision}
    ids[unit["source_axis_id"]] = uid("final-axis", revision)
    for kind, records in (
        ("log", source["metadata"]["logs"]),
        ("stream", source["metadata"]["spectral_streams"]),
        ("interpretation", source["metadata"]["interpretation_sets"]),
        ("interval", documents["4_core_intervals.json"]),
        ("frame", documents["4_image_frames.json"]),
    ):
        for record in records:
            ids[record["id"]] = uid("final-record", revision, kind, record["id"])
    context = copy.deepcopy(source)
    metadata = context["metadata"]
    for name in metadata:
        # Original NVCL JSON is source evidence; do not replace its identifiers with internal IDs.
        if name not in ("raw_metadata", "borehole", "dataset"):
            metadata[name] = remap(metadata[name], ids)
    metadata["dataset_revision"].update(
        pipeline_id=key, final_identity=identity, content_sha256=content,
        prepared_revision_id=original["id"],
    )
    context["alignment"] = remap(context["alignment"], ids)
    context["summary"] = remap(context["summary"], ids)
    context["summary"].setdefault("source_file_count", len(context["storage"]["raw_assets"]))
    context["summary"].setdefault("canonical_file_count", len(context["storage"]["assets"]))
    context["documents"] = remap(documents, ids)
    context["verified_spectral_paths"] = [a["file"] for a in selected["arrays"]]
    bindings = context["documents"]["4_axis_bindings.json"]
    for array in selected["arrays"]:
        log = next(l for l in metadata["logs"] if l["id"] == ids[array["source_log_pk"]])
        log.update(
            array_layout_status="verified_sample_major", per_sample_publication_allowed=True,
            axis_binding_status="verified", binding_basis=array["binding_basis"],
        )
        bindings[:] = [b for b in bindings if b["source_log_id"] != array["log_id"]]
        bindings.append({
            "source_log_id": array["log_id"], "axis_id": ids[unit["source_axis_id"]],
            "status": "verified", "basis": array["binding_basis"],
        })
    return {
        "context": context, "package": package, "unit": unit, "ids": ids,
        "dataset_id": dataset_id, "dataset_revision_id": revision,
        "axis_id": ids[unit["source_axis_id"]], "input_digest": content,
    }


def import_final_dataset(conn, item, fail_after_samples=False):
    """Use the transaction held by the caller to write one complete version without cloning a base version."""
    selected = item["package"]["datasets"][item["dataset_id"]]
    result = import_hole(
        conn, item["context"], fail_after_samples=fail_after_samples,
        content_digest=item["input_digest"],
    )
    ids = item["ids"]
    verify_media_sources(
        conn, remap(item["unit"], ids), remap(selected["arrays"], ids), remap(selected["rows"], ids),
    )
    if result["action"] == "inserted":
        insert_media_records(conn, item["package"], item["dataset_id"], item["dataset_revision_id"], ids)
        context = item["context"]
        insert(conn, "dataset_segment", {
            "id": uid("full-source-segment", item["dataset_revision_id"]),
            "dataset_revision_id": item["dataset_revision_id"],
            "borehole_id": context["metadata"]["borehole"]["id"],
            "branch_id": None, "axis_id": item["axis_id"],
            "sample_no_from": 0, "sample_no_to": item["unit"]["sample_count"] - 1,
            "sequence_no": None,
            "evidence": {"scope": "complete independent dataset; no 3D clipping",
                         "source_dataset_id": item["unit"]["source_dataset_id"]},
        })
    return {**result, "dataset_id": item["dataset_id"], "axis_id": item["axis_id"]}


@fresh_file_checks
def run_final_import(batch, *, fail_after_samples=False):
    """Run the second local acceptance and prevent failed batches from being exported as successful."""
    path = settings.reports_dir / "local_acceptance_2.json"
    write(path, {"stage": 2, "status": "running"})
    try:
        result = import_checked_batch(batch, fail_after_samples=fail_after_samples)
    except Exception as error:
        write(path, {"stage": 2, "status": "failed", "error_type": type(error).__name__})
        raise
    acceptance = {"stage": 2, "status": "passed", "run_id": result["run_id"],
                  "release_id": result["release_id"], "database": result["database"],
                  "datasets": result["datasets"], "checks": result["checks"],
                  "dataset_contents": result["dataset_contents"],
                  "content_sha256": digest(result["dataset_contents"])}
    write(settings.reports_dir / f"local_acceptance_2_{result['run_id']}.json", acceptance)
    write(path, acceptance)
    return result


def import_checked_batch(batch, *, fail_after_samples=False):
    """Commit each dataset after complete insertion and validation; switch the release after the full batch finishes."""
    require(settings.dbname != "etl4_core", 'Use an explicitly selected local batch database; do not overwrite the previous delivery database')
    started = time.perf_counter()
    items = load_final_inputs(batch)
    run_id = str(uuid.uuid4())
    decisions = batch.get("decisions", {"orders": {}})
    results, checks = [], []
    with connection("ingest") as conn:
        assert_schema(conn)
        require(conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"],
                'Another import or acceptance is running')
        try:
            insert(conn, "ingest_run", {
                "id": run_id, "input_digest": digest([i["dataset_revision_id"] for i in items]),
                "code_sha256": sha(Path(__file__)), "schema_sha256": schema_hash(),
                "holes": Jsonb(sorted({i["unit"]["hole_id"] for i in items})), "status": "running",
            })
            current = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()
            previous = str(current["release_id"]) if current else None
            members = {}
            if batch.get("source_release_id"):
                for member in release_members(conn, batch["source_release_id"]):
                    members[str(member["dataset_id"])] = member
            for item in items:
                members[item["dataset_id"]] = {
                    "dataset_id": item["dataset_id"], "dataset_revision_id": item["dataset_revision_id"],
                }
            release_metadata = {"flow": FINAL_RULE_VERSION, "succession_decisions": decisions}
            planned_release, _ = release_identity(list(members.values()), release_metadata)
            if batch.get("source_release_id"):
                require(previous in (batch["source_release_id"], planned_release), 'The source release for the incremental batch has changed')
            for item in items:
                print(f"Final import and verify {item['unit']['hole_id']} / {item['unit']['source_dataset_id']}", flush=True)
                with conn.transaction():
                    imported = import_final_dataset(conn, item, fail_after_samples)
                    check = verify_dataset(
                        conn, item["unit"], item, None, item["package"],
                        storage=item["context"]["storage"], source_context=item["context"],
                        content_digest=item["input_digest"],
                    )
                    check.update(status="passed", dataset_revision_id=item["dataset_revision_id"],
                                 input_digest=item["input_digest"])
                    conn.execute(
                        """INSERT INTO core.revision_validation
                        (dataset_revision_id,input_digest,verification_code_sha256,result) VALUES (%s,%s,%s,%s)
                        ON CONFLICT(dataset_revision_id) DO UPDATE SET validated_at=now(),
                        input_digest=EXCLUDED.input_digest,verification_code_sha256=EXCLUDED.verification_code_sha256,
                        result=EXCLUDED.result""",
                        (item["dataset_revision_id"], item["input_digest"], sha(Path(__file__)), Jsonb(json.loads(encoded(check)))),
                    )
                results.append(imported)
                checks.append(check)
            with conn.transaction():
                release = stage_release(conn, list(members.values()), "single_final", release_metadata)
                install_composites(conn, release, decisions)
                verify_composites(conn, release, decisions)
                publish_release(conn, release, checks, __file__, expected_previous=previous, update_latest=False)
                conn.execute(
                    "UPDATE core.ingest_run SET status='staged',finished_at=now(),detail=%s WHERE id=%s",
                    (Jsonb({"status": "passed", "release_id": release, "datasets": results}), run_id),
                )
            # Update the entry point after committing the release and before unlocking to preserve the latest manifest.
            try:
                write(settings.reports_dir / "deployment_asset_manifest.json",
                      read(settings.reports_dir / f"asset_manifest_{release}.json"))
            except OSError as error:
                print(f"Final version committed; the latest manifest entry needs rebuilding: {type(error).__name__}", flush=True)
        except Exception as error:
            conn.execute(
                "UPDATE core.ingest_run SET status='failed',finished_at=now(),detail=%s WHERE id=%s",
                (Jsonb({"error_type": type(error).__name__, "message": str(error), "completed_datasets": results}), run_id),
            )
            raise
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    result = {
        "status": "passed", "run_id": run_id, "release_id": release,
        "database": settings.dbname, "datasets": results, "checks": checks,
        "dataset_contents": {item["dataset_id"]: {
            "dataset_revision_id": item["dataset_revision_id"], "input_digest": item["input_digest"]
        } for item in items},
        "elapsed_seconds": time.perf_counter() - started,
    }
    write(settings.reports_dir / f"final_run_{run_id}.json", result)
    return result
