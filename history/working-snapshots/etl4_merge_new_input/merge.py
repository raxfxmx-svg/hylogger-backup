"""Copy three boreholes in one transaction and create an eleven-borehole release pending validation."""

import uuid
from pathlib import Path
from merge_common import AUDIT, SOURCE, TARGET, NON_BUSINESS, connection, lock, assert_schema, read, write, encoded, row_hashes, summarize, signature, active_release, copy_business, sha
from _db_common import insert, Jsonb, schema_hash
from _publication import release_members, stage_release
from _multi_db import install_composites

before = read(AUDIT / "preflight.json")
with connection(dbname=SOURCE) as source, connection(dbname=TARGET) as target:
    lock(source)
    lock(target)
    assert_schema(source)
    assert_schema(target)
    with source.transaction(), target.transaction():
        source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        target.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        assert active_release(target) == before["target_active"], 'Target release changed'
        assert signature(source) == signature(target) == read(AUDIT / "schema_before.json")
        print("Checking snapshots before writing", flush=True)
        assert summarize(row_hashes(source, list(before["source_tables"]))) == before["source_tables"], 'Source database changed'
        assert summarize(row_hashes(target, list(before["target_tables"]))) == before["target_tables"], 'Target database changed'
        incoming = source.execute("SELECT dataset_id::text,dataset_revision_id::text FROM core.release_dataset WHERE dataset_revision_id IN (SELECT id FROM core.dataset_revision WHERE normalized_metadata ? 'derived_from_revision_id') ORDER BY dataset_id").fetchall()
        assert len(incoming) == 3 and len({item["dataset_id"] for item in incoming}) == 3
        for member in incoming:
            checked = source.execute("SELECT r.input_digest,v.input_digest verified_digest,v.result->>'status' status FROM core.dataset_revision r JOIN core.revision_validation v ON v.dataset_revision_id=r.id WHERE r.id=%s", (member["dataset_revision_id"],)).fetchone()
            assert checked and checked["status"] == "passed" and checked["input_digest"] == checked["verified_digest"]
        original_members = release_members(target, before["target_active"])
        assert not {str(item["dataset_id"]) for item in original_members} & {item["dataset_id"] for item in incoming}
        copied = copy_business(source, target, before["business_tables"])
        decisions = before["target_manifest"]["succession_decisions"]
        combined = stage_release(target, original_members + incoming, "local_merged_v2", {"source_release_id": before["target_active"], "merged_from_database": SOURCE, "incoming_revisions": incoming, "succession_decisions": decisions})
        groups = install_composites(target, combined, decisions)
        assert len(groups) == 11
        target.execute("SET CONSTRAINTS ALL IMMEDIATE")
        assert active_release(target) == before["target_active"]
        run_id = str(uuid.uuid4())
        insert(target, "ingest_run", {"id": run_id, "input_digest": sha(AUDIT / "preflight.json"), "code_sha256": sha(Path(__file__)), "schema_sha256": schema_hash(), "holes": Jsonb(before["source_holes"]), "status": "staged", "detail": Jsonb({"source_database": SOURCE, "copied_rows": copied, "release_id": combined})})
        result = {"status": "staged", "run_id": run_id, "release_id": combined, "previous_release_id": before["target_active"], "incoming": incoming, "original_members": original_members, "copied_rows": copied, "holes": [group["hole_id"] for group in groups], "active_unchanged": True}
    write(AUDIT / "merged_staged.json", result)
    print(f"Staged merge {combined}; {sum(copied.values())} rows copied; original active release retained", flush=True)
