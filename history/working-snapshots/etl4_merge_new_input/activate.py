"""Verify merged content and read results before switching the active release through the official publication function."""

from pathlib import Path
from collections import Counter
from merge_common import AUDIT, SOURCE, TARGET, NON_BUSINESS, connection, lock, assert_schema, read, write, row_hashes, load_hashes, save_hashes, summarize, signature, active_release, tables
from _publication import publish_release, release_members
from _multi_reader import read_borehole_layout
from _media_reader import read_sample
from _file_checks import FileChecks
from fastapi.testclient import TestClient
from api.app import create_app

before = read(AUDIT / "preflight.json")
staged = read(AUDIT / "merged_staged.json")
verified = [read(AUDIT / "verify_new_input_check.json"), read(AUDIT / "verify_random_09THD028.json")]
assert all(item["status"] == "passed" for item in verified)
checks = [check for item in verified for check in item["media_checks"]]
assert len(checks) == 3
release = staged["release_id"]
with connection(dbname=SOURCE) as source, connection(dbname=TARGET) as target, FileChecks() as scans:
    lock(source)
    lock(target)
    assert_schema(source)
    assert_schema(target)
    assert signature(target) == read(AUDIT / "schema_before.json")
    with source.transaction(), target.transaction():
        source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        target.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        print("Checking that both original data sets remain intact", flush=True)
        assert summarize(row_hashes(source, tables(source))) == before["source_tables"], 'Source database was modified'
        current = row_hashes(target, before["business_tables"])
        originals = load_hashes(AUDIT / "target_before.json.gz")
        additions = load_hashes(AUDIT / "source_before.json.gz")
        preserved, missing = {}, {}
        for name, rows in current.items():
            expected = Counter(originals[name]) + Counter(additions[name])
            missing[name] = sum((expected - Counter(rows)).values())
            preserved[name] = len(originals[name]) + len(additions[name])
        assert not any(missing.values()), missing
        assert active_release(target) in (staged["previous_release_id"], release)
        counts = target.execute("""SELECT
          (SELECT count(*) FROM core.borehole) holes,
          (SELECT count(*) FROM core.dataset) datasets,
          (SELECT count(*) FROM core.dataset_revision) revisions,
          (SELECT sum(a.sample_count) FROM core.sample_axis a JOIN core.release_dataset rd ON rd.dataset_revision_id=a.dataset_revision_id WHERE rd.release_id=%s) full_samples,
          (SELECT count(*) FROM core.v_borehole_composite_samples WHERE release_id=%s) overview_samples,
          (SELECT count(*) FROM core.image_region r JOIN core.release_dataset rd ON rd.dataset_revision_id=r.dataset_revision_id WHERE rd.release_id=%s) image_rows,
          (SELECT count(*) FROM core.spectral_array a JOIN core.release_dataset rd ON rd.dataset_revision_id=a.dataset_revision_id WHERE rd.release_id=%s) spectral_arrays""", (release,) * 4).fetchone()
        assert counts == {"holes": 11, "datasets": 16, "revisions": 32, "full_samples": 730622, "overview_samples": 714175, "image_rows": 4726, "spectral_arrays": 29}, counts
        layouts = []
        for hole in staged["holes"]:
            layout = read_borehole_layout(target, release, hole)
            layouts.append(layout)
        # Preserve the original eight-borehole display selections; only internal release and composition IDs change.
        columns = "p.borehole_id,p.sequence_no,p.dataset_id,p.dataset_revision_id,p.axis_id,p.predecessor_relation_id,p.selection_from_md_m,p.selection_to_md_m,p.upper_inclusive,p.sample_no_from,p.sample_no_to,p.selection_status"
        old_parts = target.execute("SELECT " + columns + " FROM core.borehole_composite_part p WHERE release_id=%s ORDER BY p.borehole_id,p.sequence_no", (before["target_active"],)).fetchall()
        new_old_parts = target.execute("SELECT " + columns + " FROM core.borehole_composite_part p JOIN core.borehole b ON b.id=p.borehole_id WHERE release_id=%s AND b.source_hole_id=ANY(%s) ORDER BY p.borehole_id,p.sequence_no", (release, before["target_holes"])).fetchall()
        assert old_parts == new_old_parts, 'Original eight-borehole display selections changed'
        selections = []
        for member in release_members(target, release):
            axis = target.execute("SELECT id,sample_count FROM core.sample_axis WHERE dataset_revision_id=%s", (member["dataset_revision_id"],)).fetchone()
            logs = target.execute("SELECT id FROM core.scan_log WHERE dataset_revision_id=%s AND log_kind='spectral' AND availability_status='payload_present' ORDER BY source_log_id", (member["dataset_revision_id"],)).fetchall()
            for sample in (0, axis["sample_count"] - 1):
                output = read_sample(target, release, str(member["dataset_id"]), str(axis["id"]), sample, [str(row["id"]) for row in logs])
                assert output["image_status"] == "available"
                assert all(row["status"] == "available" for row in output["results"])
                selections.append({"dataset_id": str(member["dataset_id"]), "sample_no": sample, "spectra": len(output["results"]), "image_status": output["image_status"]})
    print("Verifying combined API membership", flush=True)
    with TestClient(create_app(TARGET)) as client:
        response = client.get("/v1/boreholes", params={"release_id": release})
        assert response.status_code == 200, response.text[:500]
        api_holes = sorted(row["source_hole_id"] for row in response.json()["items"])
        assert api_holes == sorted(staged["holes"]), api_holes
    # Record actual target-database validation for base and standalone media releases as well.
    print("Saving validation records and checking release files", flush=True)
    for item in verified:
        base_id = target.execute("SELECT manifest->>'source_release_id' id FROM core.data_release WHERE id=%s", (item["media_release"],)).fetchone()["id"]
        publish_release(target, base_id, item["base_checks"], Path(__file__), activate=False)
        publish_release(target, item["media_release"], item["media_checks"], Path(__file__), activate=False)
    assets, locations = publish_release(target, release, checks, Path(__file__), expected_previous=before["target_active"])
    assert active_release(target) == release
    target.execute("UPDATE core.ingest_run SET finished_at=now(),detail=detail || jsonb_build_object('verification_status','passed','activated',true) WHERE id=%s", (staged["run_id"],))
    with target.transaction():
        after = row_hashes(target, before["business_tables"])
    save_hashes(AUDIT / "merged_before_replay.json.gz", after)
    result = {"status": "passed", "activated": True, "release_id": release, "previous_release_id": before["target_active"], "counts": counts, "original_and_source_rows_preserved": preserved, "source_database_unchanged": True, "old_display_parts_unchanged": True, "api_holes": api_holes, "sample_read_checks": selections, "layouts": layouts, "asset_count": len(assets), "location_count": len(locations), "file_checks": scans.stats()}
    write(AUDIT / "activated.json", result)
    print(f"Activated {release}: {counts}", flush=True)
