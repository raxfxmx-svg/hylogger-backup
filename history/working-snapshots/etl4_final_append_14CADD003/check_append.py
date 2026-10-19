"""Add 14CADD003 incrementally through the new entry point, compare twelve-borehole releases and check reruns."""

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "etl4/database"), str(ROOT / "etl4/database/tests"),
    str(ROOT / "_codex_work/etl4_structure_20260930"),
]
from _db_common import ETL, PG_BIN, config, connection
from _db_files import encoded, read, sha, write
from _file_checks import FileChecks
from _final_import import load_final_inputs, run_final_import
from _media_reader import read_sample
from _publication import release_members
from _settings import settings
from _trial_support import create_trial, drop_trial, fingerprints
from compare_reference import compare, query_hash, release_datasets
from preserve import capture_scopes, snapshot

OUT = Path(__file__).parent
settings.work_dir = ETL / "single_final_check_20260930"
settings.dbname = "etl4_test_single_final_20260930"
REFERENCE = "etl4_refactor_check"
REPORTS = settings.reports_dir


def save(name, value):
    (OUT / name).write_bytes(encoded(value))


def counts(conn):
    release = str(conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()["release_id"])
    result = {"release_id": release}
    for table in ("borehole", "dataset", "dataset_revision", "scan_sample", "image_region", "spectral_array", "data_release"):
        result[table] = conn.execute("SELECT count(*) n FROM core." + table).fetchone()["n"]
    result["complete_samples"] = conn.execute(
        "SELECT sum(a.sample_count) n FROM core.sample_axis a JOIN core.release_dataset r ON r.dataset_revision_id=a.dataset_revision_id WHERE r.release_id=%s",
        (release,),
    ).fetchone()["n"]
    result["display_samples"] = conn.execute(
        "SELECT count(*) n FROM core.v_borehole_composite_samples WHERE release_id=%s", (release,),
    ).fetchone()["n"]
    return result


def preflight():
    path = OUT / "before.json"
    if path.exists():
        return read(path)
    with connection("reader") as target, connection("reader", dbname=REFERENCE) as reference:
        before = {"target": counts(target), "reference": counts(reference)}
        assert before["target"]["dataset_revision"] == before["target"]["dataset"] == 16
        assert before["target"]["borehole"] == 11
        assert before["reference"]["dataset"] == 17 and before["reference"]["borehole"] == 12
        before["scopes"] = capture_scopes(target)
        before["original_records"] = snapshot(target, before["scopes"])
        before["members"] = release_members(target, before["target"]["release_id"])
        before["reference_fingerprints"] = fingerprints(REFERENCE)
        definition = target.execute("SELECT manifest FROM core.data_release WHERE id=%s", (before["target"]["release_id"],)).fetchone()["manifest"]
        batch = {
            "source_release_id": before["target"]["release_id"],
            "decisions": definition["succession_decisions"],
            "packages": [{
                "directory": "structure_input_20260930/database/media_releases/ec89f56974ca834b7769d7cf578a10b685f999c56541e5937f916fe7356eef05",
                "prepared_work_dir": "structure_input_20260930",
            }],
        }
        with FileChecks():
            items = load_final_inputs(batch)
        assert len(items) == 1 and items[0]["unit"]["hole_id"] == "14CADD003"
        assert items[0]["unit"]["sample_count"] == 1584
        assert not target.execute("SELECT 1 FROM core.dataset WHERE id=%s", (items[0]["dataset_id"],)).fetchone()
        old = reference.execute(
            "SELECT rd.dataset_revision_id FROM core.release_dataset rd WHERE release_id=%s AND dataset_id=%s",
            (before["reference"]["release_id"], items[0]["dataset_id"]),
        ).fetchone()
        assert old
        before["incoming"] = {
            "dataset_id": items[0]["dataset_id"], "source_dataset_id": items[0]["unit"]["source_dataset_id"],
            "old_media_revision": str(old["dataset_revision_id"]),
            "new_final_revision": items[0]["dataset_revision_id"],
        }
    save("before.json", before)
    (settings.work_dir / "append_14CADD003.json").write_bytes(encoded(batch))
    return before


def extra_comparisons(current, reference, new_revision, old_revision):
    queries = {
        "borehole_metadata_and_coordinates": """SELECT (to_jsonb(b)-'id')::text, public.ST_AsEWKT(b.collar_geom)
            FROM core.dataset_revision r JOIN core.borehole_revision b ON b.id=r.borehole_revision_id WHERE r.id=%s""",
        "dataset_business_metadata": """SELECT (to_jsonb(r)-ARRAY['id','pipeline_id','mapping_version','input_digest','normalized_metadata','created_at']::text[])::text
            FROM core.dataset_revision r WHERE r.id=%s""",
        "original_documents": """SELECT document_name,content_json::text,content_text FROM core.source_document
            WHERE dataset_revision_id=%s ORDER BY document_name""",
        "resolved_source_relations": """SELECT r.role,r.source_target_id,r.status,l.source_log_id,l.log_kind
            FROM core.source_reference r LEFT JOIN core.scan_log l ON l.id=r.target_log_id
            WHERE r.dataset_revision_id=%s ORDER BY r.role,r.source_target_id""",
    }
    result = {}
    for name, query in queries.items():
        old = query_hash(reference, query, (old_revision,))
        new = query_hash(current, query, (new_revision,))
        assert old == new, name + " differs"
        result[name] = new
    return result


def backup_and_restore():
    helper = importlib.import_module("36_backup_multi_dataset_database")
    cfg = config()
    env = os.environ.copy()
    env.update(PGHOST=cfg["host"], PGPORT=str(cfg["port"]), PGUSER=cfg["roles"]["owner"]["user"],
               PGPASSWORD=cfg["roles"]["owner"]["password"], PGCLIENTENCODING="UTF8")
    backup = settings.database_dir / "backups/final_12_holes_20260930.dump"
    helper.backup_command([PG_BIN / "pg_dump.exe", "--format=custom", "--no-owner", "--file", backup, "--dbname", settings.dbname], env)
    original = fingerprints()
    trial = create_trial("restore")
    try:
        helper.backup_command([PG_BIN / "pg_restore.exe", "--no-owner", "--exit-on-error", "--dbname", trial, backup], env)
        assert fingerprints(trial) == original
        with connection("reader") as current, connection(dbname=trial) as restored:
            assert helper.view_definitions(current) == helper.view_definitions(restored)
            assert counts(current) == counts(restored)
    finally:
        drop_trial(trial)
    return {"path": str(backup), "bytes": backup.stat().st_size, "sha256": sha(backup), "restored_and_compared": True}


def main():
    before = preflight()
    batch = read(settings.work_dir / "append_14CADD003.json")
    print("Preflight passed; append one complete dataset using the final-version flow", flush=True)
    if (OUT / "import.json").exists():
        imported = read(OUT / "import.json")
        import_scans = read(OUT / "import_scans.json") if (OUT / "import_scans.json").exists() else {}
    else:
        with FileChecks() as files:
            imported = run_final_import(batch)
            import_scans = files.stats()
        save("import.json", imported)
        save("import_scans.json", import_scans)
    with connection("reader") as current, connection("reader", dbname=REFERENCE) as reference:
        after = counts(current)
        assert after["borehole"] == 12 and after["dataset_revision"] == after["dataset"] == 17
        assert after["scan_sample"] == after["complete_samples"] == 732206
        assert after["image_region"] == 4738 and after["spectral_array"] == 31
        assert after["display_samples"] == 715759
        assert snapshot(current, before["scopes"]) == before["original_records"]
        members = {str(m["dataset_id"]): str(m["dataset_revision_id"]) for m in release_members(current, after["release_id"])}
        assert all(members[str(m["dataset_id"])] == str(m["dataset_revision_id"]) for m in before["members"])
        with FileChecks() as files:
            comparison = compare(current, reference, release=after["release_id"], reference_release=before["reference"]["release_id"])
            comparison["file_checks"] = files.stats()
        comparison["14CADD003_metadata"] = extra_comparisons(
            current, reference, before["incoming"]["new_final_revision"], before["incoming"]["old_media_revision"],
        )
    write(REPORTS / "final_12_holes_comparison.json", comparison)
    print("All 12 holes match the old database; original 11-hole records preserved", flush=True)
    unchanged = fingerprints()
    with FileChecks() as files:
        replay = run_final_import(batch)
        replay_scans = files.stats()
    assert all(item["action"] == "already_present" for item in replay["datasets"])
    assert replay["release_id"] == imported["release_id"] and fingerprints() == unchanged
    save("replay.json", replay)
    print("Incremental replay passed: no new business records or releases", flush=True)
    backup = backup_and_restore()
    assert fingerprints(REFERENCE) == before["reference_fingerprints"]
    with connection("reader", dbname=REFERENCE) as reference:
        assert counts(reference) == before["reference"]
    # Preserve the original eleven-borehole batch; default to the current twelve-borehole scope to avoid switching back.
    full = read(settings.work_dir / "batch.json")
    original_batch = settings.work_dir / "batch_11_holes.json"
    if not original_batch.exists():
        original_batch.write_bytes(encoded(full))
    if batch["packages"][0] not in full["packages"]:
        full["packages"].extend(batch["packages"])
        (settings.work_dir / "batch.json").write_bytes(encoded(full))
    result = {
        "status": "passed", "database": settings.dbname, "reference_database": REFERENCE,
        "before": before["target"], "after": after, "reference": before["reference"],
        "incoming": before["incoming"], "original_11_hole_business_records_unchanged": True,
        "reference_database_unchanged": True,
        "import": {"elapsed_seconds": imported["elapsed_seconds"], **import_scans},
        "replay": {"new_business_records": 0, "new_releases": 0, "elapsed_seconds": replay["elapsed_seconds"], **replay_scans},
        "backup": backup,
    }
    write(REPORTS / "final_append_14CADD003.json", result)
    save("result.json", result)
    print(encoded(result).decode("utf-8"))


if __name__ == "__main__":
    main()
