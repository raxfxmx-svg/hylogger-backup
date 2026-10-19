"""Repeated merges must not add business records; save the final backup and report."""

from merge_common import AUDIT, SOURCE, TARGET, settings, connection, lock, assert_schema, read, write, row_hashes, load_hashes, summarize, signature, active_release, tables, copy_business, backup, sha
from _publication import stage_release
from _multi_db import install_composites
from fastapi.testclient import TestClient
from api.app import create_app

before = read(AUDIT / "preflight.json")
staged = read(AUDIT / "merged_staged.json")
verified = read(AUDIT / "activated.json")
with connection(dbname=SOURCE) as source, connection(dbname=TARGET) as target:
    lock(source)
    lock(target)
    assert_schema(source)
    assert_schema(target)
    with source.transaction(), target.transaction():
        source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        target.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        assert active_release(target) == staged["release_id"]
        inserted = copy_business(source, target, before["business_tables"])
        assert sum(inserted.values()) == 0
        release = stage_release(target, staged["original_members"] + staged["incoming"], "local_merged_v2", {"source_release_id": before["target_active"], "merged_from_database": SOURCE, "incoming_revisions": staged["incoming"], "succession_decisions": before["target_manifest"]["succession_decisions"]})
        assert release == staged["release_id"]
        install_composites(target, release, before["target_manifest"]["succession_decisions"])
        target.execute("SET CONSTRAINTS ALL IMMEDIATE")
        print("Comparing business contents after repeated merge", flush=True)
        current = row_hashes(target, before["business_tables"])
        assert current == load_hashes(AUDIT / "merged_before_replay.json.gz"), 'Repeated merge changed business content'
        assert summarize(row_hashes(source, tables(source))) == before["source_tables"], 'Source database changed'
        assert signature(target) == read(AUDIT / "schema_before.json")
    with TestClient(create_app(TARGET)) as client:
        response = client.get("/v1/boreholes")
        assert response.status_code == 200
        api_holes = sorted(row["source_hole_id"] for row in response.json()["items"])
        assert api_holes == sorted(staged["holes"])
    print("Backing up merged target database", flush=True)
    after_backup = backup(TARGET, settings.database_dir / "backups" / "etl4_refactor_check_after_three_hole_merge_20260929.dump")
    report = {
        **verified,
        "replay_new_business_rows": 0,
        "replay_new_revisions": 0,
        "replay_new_releases": 0,
        "business_table_count": len(current),
        "business_table_hashes": summarize(current),
        "source_database_unchanged": True,
        "schema_unchanged": True,
        "default_api_holes": api_holes,
        "before_backups": before["backups"],
        "after_backup": after_backup,
        "physical_files_reused": True,
        "source_file_directories_must_be_preserved": ["etl4/new_input_check", "etl4/09ATRCD025", "etl4/12BRDDH003", "etl4/09THD028"],
        "database_bytes": target.execute("SELECT pg_database_size(current_database()) n").fetchone()["n"],
    }
    write(AUDIT / "result.json", report)
    write(settings.reports_dir / "merge_new_input_check.json", report)
    write(settings.reports_dir / "latest_verified_merge.json", {"report": "merge_new_input_check.json", "release_id": release, "counts": verified["counts"]})
    write(settings.reports_dir / "latest_database_backup.json", {"report": "merge_new_input_check.json", "release_id": release, "backup_relative_path": str(__import__('pathlib').Path(after_backup["path"]).relative_to(settings.database_dir)).replace('\\','/'), "backup_sha256": after_backup["sha256"], "restore_test_performed": False})
    print(f"Merge complete and repeatable: {verified['counts']}; backup {after_backup['bytes']} bytes", flush=True)
