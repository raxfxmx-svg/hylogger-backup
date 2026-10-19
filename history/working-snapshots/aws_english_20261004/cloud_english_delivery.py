"""Replace the approved ETL data in the existing AWS database, preserving schema and access.
Replace the authorised data in the existing AWS database while retaining its structure and access permissions.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import ssl
import sys
import time

HERE = Path(__file__).resolve().parent
CODE = HERE / "etl4/database"
sys.path[:0] = [str(CODE), str(CODE.parent)]
import boto3
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from _batch_files import DATA_TABLES, KNOWN_TABLES, load_export, read_json, write_json
from _db_files import digest
from _db_common import LOCK_KEY, uid
from schema_comments import apply_comments

ACCOUNT = "000000000000"
REGION = "ap-southeast-2"
BUCKET = "hyloggerdemo-000000000000-ap-southeast-2-an"
HOST = "db.example.com"
DATABASE = "etl4_core"
OLD_RELEASE = "292e1573-f868-5494-81a8-0f85bcdbb8ad"
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def module(name):
    spec = importlib.util.spec_from_file_location(name, CODE / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def aws_session():
    session = boto3.Session(region_name=REGION)
    if session.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise ValueError("Unexpected AWS account")
    return session


def connection(session):
    ca = ssl.get_default_verify_paths().cafile
    if not ca or not Path(ca).is_file():
        raise ValueError("A trusted system CA is required")
    token = session.client("rds").generate_db_auth_token(DBHostname=HOST, Port=5432, DBUsername="postgres")
    return psycopg.connect(host=HOST, port=5432, dbname=DATABASE, user="postgres", password=token,
                           sslmode="verify-full", sslrootcert=ca, connect_timeout=30,
                           autocommit=True, row_factory=dict_row)


def english_values(value):
    if isinstance(value, str):
        return HAN.search(value) is None
    if isinstance(value, dict):
        return all(english_values(key) and english_values(item) for key, item in value.items())
    if isinstance(value, list):
        return all(english_values(item) for item in value)
    return True


def check_text(directory, manifest):
    """Reject Chinese delivery records at the import boundary, including escaped JSON text.
Reject Chinese records at the import boundary, including escaped JSON text.
    """
    for table in DATA_TABLES:
        with gzip.open(directory / manifest["tables"][table]["path"], "rt", encoding="utf-8") as stream:
            for index, line in enumerate(stream, 1):
                if not english_values(json.loads(line)):
                    raise ValueError(f"Chinese text remains in {table}, row {index}")
    for name in ["composites.json", "evidence/revision_validation.json"]:
        if not english_values(read_json(directory / name)):
            raise ValueError("Chinese text remains in " + name)


def acl_snapshot(conn):
    return conn.execute("""SELECT c.relname,c.relkind,c.relowner,c.relacl::text privileges
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='core' AND c.relkind IN ('r','v','S') ORDER BY c.relname""").fetchall()


def replace(directory):
    merge = module("40_merge_cloud_batch")
    manifest, manifest_sha = load_export(directory)
    check_text(directory, manifest)
    upload, upload_sha, objects = merge.upload_evidence(directory, manifest, manifest_sha, directory / "upload_receipt.json")
    merge.require(upload["bucket"] == BUCKET and upload["region"] == REGION and upload["prefix"] == "etl4", "Unexpected upload destination")
    validations, composites = merge.local_acceptance_evidence(directory, manifest)
    storage = {key: upload[key] for key in ("bucket", "region", "prefix")}
    root_key = "etl4_s3_" + digest(storage)[:20]
    storage["root_key"] = root_key
    members = [{key: row[key] for key in ("dataset_id", "dataset_revision_id")} for row in manifest["identity"]["datasets"]]
    started = time.monotonic()
    with connection(aws_session()) as conn:
        conn.execute("SET search_path TO core,public")
        conn.execute("SET TIME ZONE 'UTC'")
        conn.execute("SET DateStyle TO 'ISO, YMD'")
        conn.execute("SET extra_float_digits TO 3")
        conn.execute("SET statement_timeout TO '20min'")
        merge.require(conn.info.dbname == DATABASE and conn.info.host == HOST, "Unexpected database destination")
        merge.require(conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"], "Another ETL import is active")
        try:
            merge.ensure_schema(conn, manifest, False)
            before_acl = acl_snapshot(conn)
            before_database = conn.execute("SELECT oid,datdba,datacl::text privileges FROM pg_database WHERE datname=current_database()").fetchone()
            current = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()
            merge.require(current and str(current["release_id"]) == OLD_RELEASE, "The expected source release has changed")
            existing = merge.plain(conn.execute("""SELECT d.id dataset_id,d.source_dataset_id,b.source_hole_id
                FROM core.active_release a JOIN core.release_dataset rd ON rd.release_id=a.release_id
                JOIN core.dataset d ON d.id=rd.dataset_id JOIN core.borehole b ON b.id=d.borehole_id ORDER BY d.id""").fetchall())
            wanted = sorted([{key: row[key] for key in ("dataset_id", "source_dataset_id", "source_hole_id")} for row in manifest["datasets"]], key=lambda row: row["dataset_id"])
            merge.require(existing == wanted, "The incoming borehole and dataset scope differs from the current delivery")
            merge.load_staging(conn, directory, manifest)
            merge.check_staging_scope(conn, manifest)
            run_id = uid("english-replacement", manifest["batch_id"], root_key)
            detail = {"flow": merge.FLOW, "operation": "replace_existing_data", "batch_id": manifest["batch_id"],
                      "manifest_sha256": manifest_sha, "upload_receipt_sha256": upload_sha, "storage": storage,
                      "completed_datasets": manifest["identity"]["datasets"]}
            with conn.transaction():
                conn.execute("SET LOCAL lock_timeout TO '15s'")
                tables = sorted(KNOWN_TABLES - {"schema_migration"})
                # Explicit tables and no CASCADE protect unrelated schemas; any failure rolls back all old records.
                conn.execute(sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(sql.SQL(",").join(sql.Identifier("core", name) for name in tables)))
                locked = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()
                merge.require(locked and str(locked["release_id"]) == OLD_RELEASE, "The active release changed before replacement")
                conn.execute(sql.SQL("TRUNCATE TABLE {}").format(sql.SQL(",").join(sql.Identifier("core", name) for name in tables)))
                apply_comments(conn)
                for item in manifest["identity"]["datasets"]:
                    revision = item["dataset_revision_id"]
                    merge.check_source_identity(conn, revision)
                    for table in DATA_TABLES:
                        merge.insert_table(conn, table, revision, manifest)
                    merge.register_assets(conn, revision, manifest, objects, root_key)
                    merge.record_validation(conn, validations[revision])
                    print("STAGED " + revision, flush=True)
                release = merge.stage_candidate(conn, manifest, members, [], composites)
                detail["release_id"] = release
                conn.execute("""INSERT INTO core.ingest_run(id,input_digest,code_sha256,schema_sha256,holes,status,finished_at,detail)
                    VALUES(%s,%s,%s,%s,%s,'staged',now(),%s)""", (run_id, manifest["batch_id"], hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    digest(manifest["identity"]["schema_migrations"]), Jsonb(sorted({row["source_hole_id"] for row in manifest["datasets"]})), Jsonb(detail)))
                finalized, switched = merge.finalize_release(conn, manifest, {"expected_active_release_id": None, "datasets": members}, [release], composites)
                merge.require(acl_snapshot(conn) == before_acl, "Table/view ownership or permissions changed")
                merge.require(conn.execute("SELECT oid,datdba,datacl::text privileges FROM pg_database WHERE datname=current_database()").fetchone() == before_database, "Database identity or permissions changed")
                merge.require(conn.execute("SELECT count(*) n FROM core.dataset_revision").fetchone()["n"] == len(members), "Old revisions remain")
                merge.ready_members(conn, members)
            result = {"status": "complete", "database_commit": "complete", "host": HOST, "dbname": DATABASE,
                      "database_oid": before_database["oid"], "schema_and_permissions_preserved": True,
                      "batch_id": manifest["batch_id"], "manifest_sha256": manifest_sha, "release_id": finalized,
                      "holes": len({row["source_hole_id"] for row in manifest["datasets"]}), "datasets": len(members),
                      "samples": manifest["tables"]["scan_sample"]["rows"], "old_revisions_removed": True,
                      "seconds": round(time.monotonic() - started, 3), "storage": storage}
            write_json(HERE / "replacement_receipt.json", result)
            print(json.dumps(result), flush=True)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["sign", "replace"])
    parser.add_argument("--export-dir", required=True, type=Path)
    args = parser.parse_args()
    directory = args.export_dir.resolve()
    if args.action == "sign":
        result = module("39_upload_batch").sign_upload_urls(directory, BUCKET, REGION, "etl4", HERE / "upload.private.json", expected_account=ACCOUNT)
        print(json.dumps(result), flush=True)
    else:
        replace(directory)


if __name__ == "__main__":
    main()
