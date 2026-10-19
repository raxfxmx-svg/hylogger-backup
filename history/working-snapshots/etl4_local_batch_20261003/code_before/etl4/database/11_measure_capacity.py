"""Measure database size, files, and read overhead separately."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time
from collections import defaultdict
from _db_common import assert_schema, connection
from _run_reports import main_guard, report
from _prepared_inputs import prepared_holes
from _db_files import read, write
from _settings import StepParser
from _settings import settings, configure
from psycopg import sql


def measure(label="current", check_api=False):
    prepared = prepared_holes()
    with connection() as conn:
        assert_schema(conn)
        active = conn.execute("SELECT release_id FROM core.active_release").fetchone()
        if not active:
            raise ValueError("No verified local release")
        conn.execute("ANALYZE")
        tables = conn.execute(
            """SELECT c.relname AS table_name,pg_table_size(c.oid) AS table_bytes,
             pg_indexes_size(c.oid) AS index_bytes,pg_total_relation_size(c.oid) AS total_bytes,
             CASE WHEN c.reltoastrelid=0 THEN 0 ELSE pg_total_relation_size(c.reltoastrelid) END AS toast_bytes_included
             FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='core' AND c.relkind='r' ORDER BY c.relname"""
        ).fetchall()
        for t in tables:
            t["row_count"] = conn.execute(
                sql.SQL("SELECT count(*) AS n FROM core.{}").format(sql.Identifier(t["table_name"]))
            ).fetchone()["n"]
        system = conn.execute(
            """SELECT current_database() AS database,version() AS postgres_version,postgis_full_version() AS postgis_version,
            pg_database_size(current_database()) AS database_bytes,pg_current_wal_lsn()::text AS wal_lsn,
            (SELECT sum(size)::bigint FROM pg_ls_waldir()) AS current_wal_directory_bytes,
            (SELECT temp_bytes FROM pg_stat_database WHERE datname=current_database()) AS cumulative_query_temp_bytes"""
        ).fetchone()
        assets = conn.execute(
            """SELECT a.* FROM core.asset a JOIN core.release_dataset rd ON rd.dataset_revision_id=a.dataset_revision_id
             WHERE rd.release_id=%s ORDER BY a.representation,a.logical_path""",
            (active["release_id"],),
        ).fetchall()
        # Generate only the deployment file manifest here.
        categories = defaultdict(
            lambda: {"logical_asset_count": 0, "logical_bytes": 0, "unique": {}}
        )
        for a in assets:
            if a["representation"] == "canonical":
                category = "canonical_payloads"
            elif a["representation"] == "evidence":
                category = "processing_evidence"
            elif a["logical_path"].endswith(".jpg"):
                category = "tray_thumbnails"
            elif a["logical_path"].endswith(".f32"):
                category = "original_spectral_arrays"
            else:
                category = "other_original_archive"
            c = categories[category]
            c["logical_asset_count"] += 1
            c["logical_bytes"] += a["byte_size"]
            c["unique"][a["sha256"]] = a["byte_size"]
        totals = {}
        for k, v in categories.items():
            totals[k] = {k2: v2 for k2, v2 in v.items() if k2 != "unique"} | {
                "unique_files_by_sha256": len(v["unique"]),
                "unique_bytes_by_sha256": sum(v["unique"].values()),
            }
        plans = []
        for h in prepared[:2]:
            axis = h["alignment"]["axis_id"]
            q = h["summary"]["depth_range_query"]
            explain = conn.execute(
                """EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT * FROM core.scan_sample
               WHERE axis_id=%s AND md_m BETWEEN %s AND %s ORDER BY md_m,sample_no""",
                (axis, q["from_m"], q["to_m"]),
            ).fetchone()
            plans.append(
                {"hole_id": h["summary"]["hole_id"], "sample_query_plan": explain["QUERY PLAN"]}
            )
    benchmarks = []
    if check_api:
        from fastapi.testclient import TestClient
        from api.app import create_app, verify_file

        with TestClient(create_app()) as client:
            for h in prepared[:2]:
                log = next(l for l in h["metadata"]["logs"] if l["source_log_name"] == "Min1 sTSAS")
                with connection("reader") as conn:
                    current_log = conn.execute(
                        "SELECT l.id FROM core.scan_log l JOIN core.release_dataset d ON d.dataset_revision_id=l.dataset_revision_id "
                        "WHERE d.release_id=%s AND d.dataset_id=%s AND l.source_log_id=%s",
                        (
                            active["release_id"],
                            h["metadata"]["dataset"]["id"],
                            log["source_log_id"],
                        ),
                    ).fetchone()
                    if current_log is None:
                        continue
                    log = {**log, "id": str(current_log["id"])}
                q = h["summary"]["depth_range_query"]
                asset = next(
                    a
                    for a in h["storage"]["assets"]
                    if a.get("source_log_id") == log["source_log_id"]
                )
                for name, depths in [
                    ("narrow", (q["from_m"], q["to_m"])),
                    (
                        "wide",
                        (
                            h["alignment"]["observed_depth_min_m"],
                            h["alignment"]["observed_depth_max_m"],
                        ),
                    ),
                ]:
                    verify_file.cache_clear()
                    for iteration in range(2):
                        start = time.perf_counter()
                        response = client.get(
                            f"/v1/logs/{log['id']}/values",
                            params={
                                "release_id": str(active["release_id"]),
                                "from_m": depths[0],
                                "to_m": depths[1],
                                "limit": 5000,
                            },
                        )
                        if response.status_code != 200:
                            raise ValueError(response.text[:500])
                        data = response.json()
                        benchmarks.append(
                            {
                                "hole_id": h["summary"]["hole_id"],
                                "range": name,
                                "iteration": iteration,
                                "checksum_cache": "empty" if iteration == 0 else "warm",
                                "os_cache": "uncontrolled; not a physical cold-disk measurement",
                                "checksum_bytes_read": asset["byte_size"] if iteration == 0 else 0,
                                "elapsed_ms": (time.perf_counter() - start) * 1000,
                                "returned_rows": len(data["items"]),
                                "response_bytes": len(response.content),
                                "pagination_required": data["next_after_row"] is not None,
                                **data["read_stats"],
                            }
                        )
    empty = read(settings.reports_dir / "8_empty_database.json")
    result = {
        "status": "measured_local_only",
        "label": label,
        "release_id": active["release_id"],
        "system": system,
        "empty_extension_database_bytes": empty["database_bytes"],
        "increase_over_empty_bytes": system["database_bytes"] - empty["database_bytes"],
        "tables": tables,
        "core_total_relation_bytes": sum(t["total_bytes"] for t in tables),
        "asset_categories": totals,
        "asset_count": len(assets),
        "all_asset_logical_bytes": sum(a["byte_size"] for a in assets),
        "all_asset_unique_bytes_by_sha256": sum(
            {a["sha256"]: a["byte_size"] for a in assets}.values()
        ),
        "minimum_scalar_thumbnail_payload_bytes": sum(
            totals[k]["logical_bytes"] for k in ("canonical_payloads", "tray_thumbnails")
        ),
        "benchmarks": benchmarks,
        "query_plans": plans,
        "limitations": [
            "WAL directory is a current allocation, not an observed historical peak",
            "Query temp_bytes does not cover every index-build or OS temporary allocation",
            "First timed reads include full-file checksum validation; payload byte counters exclude that separate pass",
            "No cloud transfer, latency or egress has been measured",
            "Five holes do not determine the final size of 2000 holes; full original archive retention and revision retention change storage needs",
        ],
    }
    report("11_capacity_" + label + ".json", result)
    lines = [
        '# Measured local database capacity',
        "",
        f"Database: {system['database_bytes']:,}  bytes; core tables and indexes total  {result['core_total_relation_bytes']:,}  bytes.",
        f"Empty database and PostGIS baseline: {empty['database_bytes']:,}  bytes; total increase after import: {result['increase_over_empty_bytes']:,}  bytes.",
        "",
        '| File category | Logical files | Logical bytes | Bytes deduplicated by SHA256 |',
        "|---|---:|---:|---:|",
    ]
    lines.extend(
        f"| {k} | {v['logical_asset_count']} | {v['logical_bytes']:,} | {v['unique_bytes_by_sha256']:,} |"
        for k, v in totals.items()
    )
    lines += [
        "",
        f"All registered assets total  {result['all_asset_logical_bytes']:,}  bytes. Canonical payloads and thumbnails total  {result['minimum_scalar_thumbnail_payload_bytes']:,}  bytes; this excludes the complete source archive.",
        "",
        'Database size already includes tables and indexes; do not add per-table totals again. WAL, exported backups, and object files are listed separately. The JSON report retains per-table counts, TOAST, indexes, query plans, and bounded-read measurements.',
        'Current WAL directory size and cumulative temporary query bytes do not capture peak import usage. Initial SHA256 verification reads each entire file; the report lists that overhead separately.',
        'No cloud platform selection, upload, or deployment was performed. Capacity for approximately 2000 boreholes still depends on actual sample, log, and image counts and version-retention policy.',
    ]
    write(settings.reports_dir / ("11_capacity_" + label + ".md"), "\n".join(lines) + "\n")
    return result


def main():
    p = StepParser()
    p.add_argument("--label", default="current")
    p.add_argument("--check-api", action="store_true")
    a = p.parse_args()
    configure(a)
    r = measure(a.label, a.check_api)
    print(
        f"Database {r['system']['database_bytes']:,} bytes; all asset references {r['all_asset_logical_bytes']:,} bytes"
    )


if __name__ == "__main__":
    main_guard(main)
