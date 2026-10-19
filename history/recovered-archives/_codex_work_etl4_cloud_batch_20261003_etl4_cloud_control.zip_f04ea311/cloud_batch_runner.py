"""Deployment entry point for twelve boreholes; temporary IAM credentials remain inside the CloudShell process."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import ssl
import sys
import time

ROOT = Path(__file__).resolve().parent
CODE = ROOT / "etl4/database"
sys.path[:0] = [str(CODE), str(CODE.parent)]
BATCH = "8039f5a6c2c5711141bb201eaa1fb96636924d23c48faddd66edb782253519cd"
EXPORT = ROOT / "export" / BATCH
HOST = "db.example.com"
REGION = "ap-southeast-2"
ACCOUNT = "000000000000"
BUCKET = "hyloggerdemo-000000000000-ap-southeast-2-an"


def module(name):
    spec = importlib.util.spec_from_file_location(name, CODE / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def connection():
    import boto3
    import psycopg
    from psycopg.conninfo import make_conninfo
    from psycopg.rows import dict_row
    session = boto3.Session(region_name=REGION)
    if session.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise ValueError("Unexpected AWS account")
    ca = ssl.get_default_verify_paths().cafile
    if not ca or not Path(ca).is_file():
        raise ValueError("Trusted system CA is required")
    token = session.client("rds").generate_db_auth_token(DBHostname=HOST, Port=5432, DBUsername="postgres")
    params = dict(host=HOST, port=5432, dbname="etl4_core", user="postgres", password=token,
                  sslmode="verify-full", sslrootcert=ca, connect_timeout=30)
    os.environ["ETL4_CLOUD_DSN"] = make_conninfo(**params)
    return psycopg.connect(**params, autocommit=True, row_factory=dict_row)


def audit(label):
    from _batch_files import DATA_TABLES, write_json
    from psycopg import sql
    with connection() as conn, conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        result = {"host": HOST, "dbname": "etl4_core", "label": label}
        result["migrations"] = conn.execute("SELECT name,sha256 FROM core.schema_migration ORDER BY name").fetchall()
        result["table_counts"] = {name: conn.execute(sql.SQL("SELECT count(*) n FROM core.{}").format(sql.Identifier(name))).fetchone()["n"] for name in DATA_TABLES}
        result["release_id"] = str(conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()["release_id"])
        members = conn.execute("""SELECT d.id dataset_id,rd.dataset_revision_id,b.source_hole_id,d.source_dataset_id
            FROM core.active_release ar JOIN core.release_dataset rd ON rd.release_id=ar.release_id
            JOIN core.dataset d ON d.id=rd.dataset_id JOIN core.borehole b ON b.id=d.borehole_id
            ORDER BY d.id""").fetchall()
        result["members"] = members
        result["holes"] = len({row["source_hole_id"] for row in members})
        result["datasets"] = len(members)
        revisions = [row["dataset_revision_id"] for row in members]
        result["samples"] = conn.execute("SELECT sum(sample_count) n FROM core.sample_axis WHERE dataset_revision_id=ANY(%s::uuid[])", (revisions,)).fetchone()["n"]
        for name in ("image_region", "spectral_array"):
            result[name] = conn.execute(sql.SQL("SELECT count(*) n FROM core.{} WHERE dataset_revision_id=ANY(%s::uuid[])").format(sql.Identifier(name)), (revisions,)).fetchone()["n"]
        result["s3_asset_locations"] = conn.execute("SELECT count(*) n FROM core.asset_location WHERE backend='s3'").fetchone()["n"]
    write_json(ROOT / (label + ".json"), result)
    print(json.dumps({key: value for key, value in result.items() if key not in ("members", "table_counts", "migrations")}, default=str), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("sign", "audit-before", "merge", "audit-after", "replay"))
    args = parser.parse_args()
    started = time.monotonic()
    if args.action == "sign":
        result = module("39_upload_batch").sign_upload_urls(EXPORT, BUCKET, REGION, "etl4", ROOT / "private_upload_urls.json", expected_account=ACCOUNT)
        print(json.dumps(result), flush=True)
    elif args.action.startswith("audit"):
        audit(args.action.replace("-", "_"))
    else:
        with connection():
            pass
        result = module("40_merge_cloud_batch").merge_batch(EXPORT, apply_migrations=True, finalize=ROOT / "final_selection.json")
        print(json.dumps(result), flush=True)
        audit("audit_after" if args.action == "merge" else "audit_replay")
    print(f"elapsed_seconds={time.monotonic()-started:.3f}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, ValueError) else f"Failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        raise SystemExit(1)
