"""Compare both databases read-only and save source digests and pre-merge backups."""

import json
from merge_common import AUDIT, SOURCE, TARGET, NON_BUSINESS, settings, connection, lock, assert_schema, signature, active_release, tables, row_hashes, save_hashes, write, summarize, backup

if (AUDIT / "preflight.json").exists():
    raise ValueError('Pre-merge records already exist; do not overwrite')
with connection(dbname=SOURCE) as source, connection(dbname=TARGET) as target:
    lock(source)
    lock(target)
    assert_schema(source)
    assert_schema(target)
    with source.transaction(), target.transaction():
        source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        target.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        source_signature, target_signature = signature(source), signature(target)
        assert source_signature == target_signature, 'Database schemas differ'
        source_holes = [r["source_hole_id"] for r in source.execute("SELECT source_hole_id FROM core.borehole ORDER BY source_hole_id")]
        target_holes = [r["source_hole_id"] for r in target.execute("SELECT source_hole_id FROM core.borehole ORDER BY source_hole_id")]
        assert source_holes == ["09ATRCD025", "09THD028", "12BRDDH003"]
        assert len(target_holes) == 8 and not set(source_holes) & set(target_holes), 'Borehole scope does not match this merge'
        old_release = active_release(target)
        old_definition = target.execute("SELECT manifest FROM core.data_release WHERE id=%s", (old_release,)).fetchone()["manifest"]
        names = tables(target)
        print("Saving existing target rows", flush=True)
        target_rows = row_hashes(target, names)
        print("Saving source rows", flush=True)
        source_rows = row_hashes(source, names)
        save_hashes(AUDIT / "target_before.json.gz", target_rows)
        save_hashes(AUDIT / "source_before.json.gz", source_rows)
        write(AUDIT / "schema_before.json", target_signature)
        result = {"status": "passed", "source": SOURCE, "target": TARGET, "source_holes": source_holes, "target_holes": target_holes, "target_active": old_release, "source_active": active_release(source), "target_manifest": old_definition, "source_tables": summarize(source_rows), "target_tables": summarize(target_rows), "business_tables": [name for name in names if name not in NON_BUSINESS]}
    print("Backing up target and source databases", flush=True)
    result["backups"] = [backup(name, settings.database_dir / "backups" / f"{name}_before_three_hole_merge_20260929.dump") for name in (TARGET, SOURCE)]
    write(AUDIT / "preflight.json", result)
    print(json.dumps({"source_holes": source_holes, "target_holes": target_holes, "backups": result["backups"]}, ensure_ascii=False), flush=True)
