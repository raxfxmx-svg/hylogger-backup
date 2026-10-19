"""Validate step 40 PostgreSQL staging SQL with the existing reader role; roll back all temporary tables."""
import importlib
import json
import sys
import time
from pathlib import Path

import local_delivery as local
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from _batch_files import DATA_TABLES, load_export

merge = importlib.import_module("40_merge_cloud_batch")


class CapturedCursor:
    rowcount = 0

    def __init__(self, text):
        self.text = text

    def fetchone(self):
        return {"n": 0} if "SELECT count(*) n" in self.text else None


class CaptureSQL:
    def __init__(self):
        self.statements = []

    def execute(self, statement, parameters=()):
        text = statement.as_string() if hasattr(statement, "as_string") else statement
        self.statements.append((text, parameters))
        return CapturedCursor(text)


def main():
    started = time.perf_counter()
    completed = local.read(local.REPORTS / "local_completion.json")
    directory = Path(completed["export_directory"])
    manifest, manifest_sha = load_export(directory)
    before = local.database_snapshot()
    config = local.read(local.CONFIG)
    role = config["roles"]["reader"]
    result = {"status": "running", "manifest_sha256": manifest_sha, "database": local.DATABASE,
              "operations": "session temporary tables and read-only core SELECT; forced transaction rollback",
              "row_counts": {}, "phases_seconds": {}}
    local.save("local_40_temp_check.json", result)
    try:
        with psycopg.connect(host=config["host"], port=config["port"], dbname=local.DATABASE,
                              user=role["user"], password=role["password"], connect_timeout=3,
                              autocommit=True, row_factory=dict_row,
                              options="-c default_transaction_read_only=off -c statement_timeout=60000") as conn:
            writable = conn.execute("""SELECT tablename FROM pg_tables WHERE schemaname='core' AND
                (has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'INSERT')
                 OR has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'UPDATE')
                 OR has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'DELETE')
                 OR has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'TRUNCATE'))""").fetchall()
            if writable:
                raise ValueError("Test reader unexpectedly has core write privileges")
            with conn.transaction():
                conn.execute("SET LOCAL search_path TO core,public")
                conn.execute("SET LOCAL TIME ZONE 'UTC'")
                conn.execute("SET LOCAL DateStyle TO 'ISO, YMD'")
                conn.execute("SET LOCAL extra_float_digits TO 3")
                if merge.plain(merge.inspect_columns(conn)) != manifest["schema"]["tables"]:
                    raise ValueError("Actual schema differs from exported manifest")
                result["schema_matches"] = True
                print("SCHEMA passed; loading 29 temporary tables", flush=True)
                mark = time.perf_counter()
                merge.load_staging(conn, directory, manifest)
                result["phases_seconds"]["load_staging"] = time.perf_counter() - mark
                print("LOAD passed", flush=True)
                for table in DATA_TABLES:
                    count = conn.execute(sql.SQL("SELECT count(*) n FROM pg_temp.{}").format(sql.Identifier(merge.stage_name(table)))).fetchone()["n"]
                    if count != manifest["tables"][table]["rows"]:
                        raise ValueError("Temporary table count differs: " + table)
                    result["row_counts"][table] = count
                mark = time.perf_counter()
                merge.check_staging_scope(conn, manifest)
                result["phases_seconds"]["check_staging_scope"] = time.perf_counter() - mark
                print("SCOPE passed", flush=True)
                mark = time.perf_counter()
                checked = 0
                for item in manifest["identity"]["datasets"]:
                    merge.check_source_identity(conn, item["dataset_revision_id"])
                    for table in DATA_TABLES:
                        capture = CaptureSQL()
                        merge.insert_table(capture, table, item["dataset_revision_id"], manifest)
                        for statement, parameters in capture.statements:
                            if "INSERT INTO core." in statement:
                                continue
                            if not statement.lstrip().startswith(("SELECT", "WITH RECURSIVE")):
                                raise ValueError("Unexpected non-read comparison statement")
                            actual = conn.execute(statement, parameters).fetchone()
                            if actual is not None and actual != {"n": 0}:
                                raise ValueError("Source record differs after JSON COPY: " + table)
                            checked += 1
                result["comparison_queries"] = checked
                result["phases_seconds"]["compare_records"] = time.perf_counter() - mark
                geometry = conn.execute("""SELECT count(*) rows,
                    count(*) FILTER(WHERE s.collar_geom IS NOT NULL) nonnull,
                    count(*) FILTER(WHERE ST_AsEWKB(s.collar_geom) IS DISTINCT FROM ST_AsEWKB(t.collar_geom)) differs,
                    array_agg(DISTINCT ST_SRID(s.collar_geom)) FILTER(WHERE s.collar_geom IS NOT NULL) srids
                    FROM pg_temp.etl4_batch_borehole_revision s JOIN core.borehole_revision t USING(id)""").fetchone()
                if geometry["differs"]:
                    raise ValueError("EWKB roundtrip differs")
                result["geometry"] = geometry
                print("COMPARE and EWKB passed; rollback", flush=True)
                raise psycopg.Rollback()
            result["temporary_tables_after_rollback"] = conn.execute(
                "SELECT count(*) n FROM pg_class WHERE relnamespace=pg_my_temp_schema() AND relkind='r'").fetchone()["n"]
            if result["temporary_tables_after_rollback"]:
                raise ValueError("Temporary tables remain after rollback")
        after = local.database_snapshot()
        if before != after:
            raise ValueError("Business snapshot changed during temp-only check")
        result.update(status="passed", core_write_permissions=False, core_snapshot_unchanged=True,
                      elapsed_seconds=time.perf_counter() - started)
    except Exception as exc:
        result.update(status="failed", error_type=type(exc).__name__,
                      sqlstate=getattr(exc, "sqlstate", None),
                      error_detail=str(exc) if isinstance(exc, (ValueError, psycopg.Error)) else type(exc).__name__,
                      elapsed_seconds=time.perf_counter() - started)
        local.save("local_40_temp_check.json", result)
        print(json.dumps({key: value for key, value in result.items() if key != "row_counts"}, ensure_ascii=False), flush=True)
        return 1
    local.save("local_40_temp_check.json", result)
    print(json.dumps({key: value for key, value in result.items() if key != "row_counts"}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
