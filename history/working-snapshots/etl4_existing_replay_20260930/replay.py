"""Rerun an existing borehole in the original 11-borehole database; unexpected business changes roll back the transaction."""

import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

AUDIT = Path(__file__).resolve().parent
ETL = AUDIT.parents[1] / "etl4"
SOURCE_WORK = ETL / "new_input_check/random_09THD028"
REPORT_WORK = ETL / "replay_existing_20260930_09THD028"
DATABASE = "etl4_refactor_check"
HOLE = "09THD028"
sys.path[:0] = [str(ETL / "database"), str(ETL)]

from _settings import settings
from _db_common import connection, assert_schema, LOCK_KEY, insert, Jsonb, schema_hash
from _db_files import read, encoded, sha
from _file_checks import FileChecks
from _prepared_inputs import prepared_holes
from _ingest import import_hole
from _media_import import check_package, import_media
from _publication import stage_release, publish_release
import _verification as base_verifier
from psycopg import sql

media_verifier = importlib.import_module("29_verify_media_grain")
phases = []


def save(name, value):
    (AUDIT / name).write_bytes(encoded(value))


def phase(name, function):
    print("Start " + name, flush=True)
    started = time.perf_counter()
    with FileChecks() as checks:
        value = function()
        phases.append({"name": name, "seconds": time.perf_counter() - started, **checks.stats()})
    print(f"Passed {name}: {phases[-1]['seconds']:.3f}s", flush=True)
    return value


def snapshot(conn):
    """Sort by complete row contents so physical row order does not count as a data change."""
    tables = {}
    for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='core' ORDER BY tablename").fetchall():
        name = row["tablename"]
        query = sql.SQL("COPY (SELECT row_to_json(t)::text AS value FROM core.{} t ORDER BY 1) TO STDOUT").format(sql.Identifier(name))
        checksum, count = hashlib.sha256(), 0
        with conn.cursor().copy(query) as stream:
            for block in stream:
                data = bytes(block)
                checksum.update(data)
                count += data.count(b"\n")
        tables[name] = {"count": count, "sha256": checksum.hexdigest()}
    active = conn.execute("SELECT * FROM core.active_release WHERE singleton").fetchone()
    members = conn.execute("SELECT * FROM core.release_dataset WHERE release_id=%s ORDER BY dataset_id", (active["release_id"],)).fetchall()
    return {"database": DATABASE, "tables": tables, "active_release": active, "active_members": members}


def main():
    if (AUDIT / "before.json").exists() or REPORT_WORK.exists():
        raise ValueError('This run directory is already used; do not overwrite the comparison')
    settings.work_dir = SOURCE_WORK
    settings.dbname = DATABASE
    source_stage = read(settings.media_work_dir / "28.json")
    package_dir = settings.database_dir / source_stage["package_directory"]
    manifest = read(package_dir / "manifest.json")
    config = REPORT_WORK / "database/runtime/local_config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(settings.runtime_dir / "local_config.json", config)
    result = {
        "hole": HOLE, "database": DATABASE, "source_work_dir": SOURCE_WORK,
        "report_work_dir": REPORT_WORK, "package_directory": package_dir,
        "scope": 'Call shared import and validation functions from steps 9, 10, 28 and 29; skip steps 1-6 and media preparation, without switching releases',
    }
    try:
        with connection("ingest") as conn:
            assert conn.execute("SELECT current_database() name").fetchone()["name"] == DATABASE
            assert_schema(conn)
            if not conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"]:
                raise ValueError('An import or validation is already running; rerun did not start')
            try:
                with conn.transaction():
                    before = phase("before_snapshot", lambda: snapshot(conn))
                    save("before.json", before)
                    member = conn.execute(
                        """SELECT rd.dataset_id,rd.dataset_revision_id,a.id axis_id,a.sample_count
                        FROM core.release_dataset rd JOIN core.dataset d ON d.id=rd.dataset_id
                        JOIN core.borehole b ON b.id=d.borehole_id
                        JOIN core.sample_axis a ON a.dataset_revision_id=rd.dataset_revision_id
                        WHERE rd.release_id=%s AND b.source_hole_id=%s""",
                        (before["active_release"]["release_id"], HOLE),
                    ).fetchall()
                    assert len(member) == 1
                    member = member[0]
                    run_id = str(uuid.uuid4())
                    insert(conn, "ingest_run", {
                        "id": run_id, "input_digest": sha(package_dir / "manifest.json"),
                        "code_sha256": sha(Path(__file__)), "schema_sha256": schema_hash(),
                        "holes": Jsonb([HOLE]), "status": "running",
                    })

                    def base_import():
                        prepared, = prepared_holes([HOLE])
                        imported = import_hole(conn, prepared)
                        assert imported["action"] == "already_present", 'A base revision was added; stop and roll back'
                        return prepared, imported

                    prepared, imported = phase("base_import", base_import)
                    result["base_import"] = imported
                    base_release = stage_release(conn, [{
                        "dataset_id": prepared["metadata"]["dataset"]["id"],
                        "dataset_revision_id": imported["dataset_revision_id"],
                    }], "local_base_v2")
                    assert base_release == source_stage["previous_release_id"], 'Base release identity changed'

                    def base_verify():
                        settings.work_dir = SOURCE_WORK
                        prepared, = prepared_holes([HOLE])
                        check = base_verifier.verify_hole(conn, prepared)
                        settings.work_dir = REPORT_WORK
                        publish_release(conn, base_release, [check], base_verifier.__file__, activate=False)
                        return check

                    result["base_verification"] = phase("base_verification", base_verify)

                    def media_import():
                        settings.work_dir = SOURCE_WORK
                        package = check_package(package_dir, manifest)
                        assert [u["hole_id"] for u in package["source"]["datasets"]] == [HOLE]
                        unit = package["source"]["datasets"][0]
                        imported = import_media(conn, package, unit["dataset_id"])
                        assert imported["action"] == "already_present", 'A media revision was added; stop and roll back'
                        assert imported["dataset_revision_id"] == str(member["dataset_revision_id"])
                        release = stage_release(conn, [imported], "local_media_v2", {"source_release_id": package["source"]["source_release_id"]})
                        assert release == source_stage["release_id"], 'Media release identity changed'
                        return imported, release

                    imported, media_release = phase("media_import", media_import)
                    result["media_import"] = imported

                    def media_verify():
                        settings.work_dir = SOURCE_WORK
                        package = check_package(package_dir, manifest)
                        unit = package["source"]["datasets"][0]
                        check = media_verifier.verify_dataset(conn, unit, imported, media_release, package)
                        check.update(status="passed", dataset_revision_id=imported["dataset_revision_id"], input_digest=manifest["datasets"][unit["dataset_id"]]["content_sha256"])
                        settings.work_dir = REPORT_WORK
                        publish_release(conn, media_release, [check], media_verifier.__file__, activate=False)
                        return check

                    result["media_verification"] = phase("media_verification", media_verify)
                    result.update(base_release=base_release, media_release=media_release, run_id=run_id)
                    conn.execute("UPDATE core.ingest_run SET status='staged',finished_at=now(),detail=%s WHERE id=%s", (Jsonb({"kind": "existing_hole_replay", "verification_status": "passed", "hole": HOLE, "activated": False}), run_id))
                    after = phase("after_snapshot", lambda: snapshot(conn))
                    save("after_in_transaction.json", after)
                    changed = [name for name in before["tables"] if before["tables"][name] != after["tables"][name]]
                    result["changed_tables"] = changed
                    allowed = {"ingest_run", "revision_validation"}
                    assert not (set(changed) - allowed), 'Business tables changed; stop and roll back: ' + str(changed)
                    assert before["active_release"] == after["active_release"]
                    assert before["active_members"] == after["active_members"]
                    result["table_deltas"] = {name: after["tables"][name]["count"] - before["tables"][name]["count"] for name in changed}
                    result["business_tables_unchanged"] = len(before["tables"]) - 4
                    result["active_release_unchanged"] = str(after["active_release"]["release_id"])
                result["status"] = "passed"
                result["committed"] = 'Only audit and validation records updated; business data and active releases are unchanged'
                print("Committed audit updates; all business tables and active release unchanged.", flush=True)
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    except Exception as error:
        result.update(status="failed", error_type=type(error).__name__, error=str(error))
        save("result.json", {**result, "phases": phases})
        raise
    save("result.json", {**result, "phases": phases})
    print(json.dumps({k: result[k] for k in ("hole", "status", "changed_tables", "table_deltas", "business_tables_unchanged", "active_release_unchanged")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
