"""Merge validated new boreholes into the active release; switch only when existing records are unchanged."""

from pathlib import Path
import uuid
from preserve import AUDIT, setup, snapshot, read, encoded, connection
from _db_common import LOCK_KEY, assert_schema, insert, Jsonb, schema_hash
from _db_files import sha
from _file_checks import FileChecks
from _media_common import stage
from _media_import import check_package, import_media, package_step
from _prepared_inputs import prepared_holes
from _ingest import import_hole
from _publication import release_members, stage_release, publish_release
from _multi_db import install_composites, verify_composites
from _multi_reader import read_borehole_layout
from _media_reader import read_sample
from _settings import settings

selection = setup()
baseline = read(AUDIT / "original_scope.json")
old_release = baseline["active"]["release_id"]
verified = read(settings.reports_dir / "29_media_verification.json")
staged = stage(28)
assert verified["status"] == "passed" and not verified["activated"]
assert staged["status"] == "staged" and staged["release_id"] == verified["release_id"]
result = {"hole": selection["hole"], "database": selection["database"], "previous_release": old_release}

with connection("ingest") as conn:
    assert_schema(conn)
    assert conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"]
    try:
        with conn.transaction(), FileChecks() as checks:
            assert str(conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()["release_id"]) == old_release
            assert snapshot(conn, baseline["scopes"]) == baseline["tables"], 'Existing business records changed; stop the merge'
            members = release_members(conn, old_release)
            added = release_members(conn, staged["release_id"])
            assert len(added) == 1 and not {str(x["dataset_id"]) for x in added} & {str(x["dataset_id"]) for x in members}
            definition = conn.execute("SELECT manifest FROM core.data_release WHERE id=%s", (old_release,)).fetchone()["manifest"]
            decisions = definition["succession_decisions"]
            combined = stage_release(conn, members + added, "local_merged_v2", {
                "source_release_id": old_release, "incoming_release_id": staged["release_id"],
                "succession_decisions": decisions,
            })
            groups = install_composites(conn, combined, decisions)
            verify_composites(conn, combined, decisions)
            assert len(groups) == 12
            # Preserve every field in existing borehole display intervals and selected revisions.
            columns = "borehole_id,sequence_no,dataset_id,dataset_revision_id,axis_id,predecessor_relation_id,selection_from_md_m,selection_to_md_m,upper_inclusive,sample_no_from,sample_no_to,selection_status"
            old_parts = conn.execute("SELECT " + columns + " FROM core.borehole_composite_part WHERE release_id=%s ORDER BY borehole_id,sequence_no", (old_release,)).fetchall()
            old_holes = list({row["borehole_id"] for row in old_parts})
            new_parts = conn.execute("SELECT " + columns + " FROM core.borehole_composite_part WHERE release_id=%s AND borehole_id=ANY(%s::uuid[]) ORDER BY borehole_id,sequence_no", (combined, old_holes)).fetchall()
            assert old_parts == new_parts
            readings = []
            for group in groups:
                read_borehole_layout(conn, combined, group["hole_id"])
                for member in group["datasets"]:
                    logs = conn.execute("SELECT id FROM core.scan_log WHERE dataset_revision_id=%s AND log_kind='spectral' AND availability_status='payload_present' ORDER BY id", (member["dataset_revision_id"],)).fetchall()
                    for sample in (0, member["sample_count"]-1):
                        value = read_sample(conn, combined, member["dataset_id"], member["axis_id"], sample, [str(row["id"]) for row in logs])
                        assert value["image_status"] == "available"
                        assert all(item["status"] == "available" for item in value["results"])
                        readings.append({"hole": group["hole_id"], "dataset": member["dataset_id"], "sample": sample, "spectra": len(value["results"])})
            assert snapshot(conn, baseline["scopes"]) == baseline["tables"]
            assets, locations = publish_release(conn, combined, verified["datasets"], Path(__file__), expected_previous=old_release)
            counts = conn.execute("""SELECT
                (SELECT count(*) FROM core.borehole) holes,
                (SELECT count(*) FROM core.dataset) datasets,
                (SELECT count(*) FROM core.dataset_revision) revisions,
                (SELECT sum(a.sample_count) FROM core.sample_axis a JOIN core.release_dataset rd ON rd.dataset_revision_id=a.dataset_revision_id WHERE rd.release_id=%s) samples,
                (SELECT count(*) FROM core.image_region r JOIN core.release_dataset rd ON rd.dataset_revision_id=r.dataset_revision_id WHERE rd.release_id=%s) image_rows,
                (SELECT count(*) FROM core.spectral_array a JOIN core.release_dataset rd ON rd.dataset_revision_id=a.dataset_revision_id WHERE rd.release_id=%s) spectral_arrays,
                (SELECT count(*) FROM core.v_borehole_composite_samples WHERE release_id=%s) display_samples""", (combined,) * 4).fetchone()
            assert counts["holes"] == 12 and counts["datasets"] == 17 and counts["revisions"] == 34
            run_id = str(uuid.uuid4())
            insert(conn, "ingest_run", {"id": run_id, "input_digest": sha(AUDIT / "selection.json"),
                "code_sha256": sha(Path(__file__)), "schema_sha256": schema_hash(), "holes": Jsonb([selection["hole"]]),
                "status": "staged", "detail": Jsonb({"kind": "verified_append", "release_id": combined, "activated": True})})
            conn.execute("UPDATE core.ingest_run SET finished_at=now() WHERE id=%s", (run_id,))
            conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
            result.update(status="passed", release=combined, counts=counts, original_tables_preserved=35,
                old_display_parts_unchanged=True, sample_reads=readings, assets=len(assets), locations=len(locations), scans=checks.stats())
        # Reread the pointer after commit to confirm the merge took effect.
        assert str(conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()["release_id"]) == combined
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
(AUDIT / "merge_result.json").write_bytes(encoded(result))
print("Merged and activated", result["release"], result["counts"], flush=True)
