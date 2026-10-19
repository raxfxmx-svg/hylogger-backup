"""Remove only obsolete delivery objects after the approved replacement commits.
Clean up old delivery objects only after the authorised replacement has committed.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
import sys

from cloud_english_delivery import HERE, BUCKET, aws_session, connection
from _batch_files import read_json, write_json

CONTROL_KEY = "etl4/control/english-20261004/etl4_english_control.zip"
PLAN = HERE / "cleanup_plan.json"


def build_plan(export_dir):
    receipt = read_json(HERE / "replacement_receipt.json")
    if receipt.get("database_commit") != "complete":
        raise ValueError("The database replacement has not committed")
    upload = read_json(export_dir / "upload_receipt.json")
    if upload["status"] != "complete" or upload["batch_id"] != receipt["batch_id"]:
        raise ValueError("Unexpected upload receipt")
    keep = {row["object_key"] for row in upload["objects"]} | {CONTROL_KEY}
    session = aws_session()
    with connection(session) as conn:
        current = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()
        if str(current["release_id"]) != receipt["release_id"]:
            raise ValueError("The active release changed before cleanup")
        locations = conn.execute("SELECT object_key FROM core.asset_location WHERE backend='s3'").fetchall()
        if any(row["object_key"] not in keep for row in locations):
            raise ValueError("An active database asset is missing from the retained delivery")
    s3 = session.client("s3")
    remove, retained = [], []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="etl4/"):
        for row in page.get("Contents", []):
            key = row["Key"]
            if not any(key.startswith("etl4/" + name + "/") for name in ("batches", "control", "objects", "releases")):
                raise ValueError("Unexpected ETL object prefix: " + key)
            entry = {"object_key": key, "byte_size": row["Size"], "etag": row["ETag"]}
            (retained if key in keep else remove).append(entry)
    present = {row["object_key"] for row in retained}
    if not ({row["object_key"] for row in upload["objects"]} <= present):
        raise ValueError("The retained delivery is missing uploaded objects")
    result = {"bucket": BUCKET, "batch_id": receipt["batch_id"], "release_id": receipt["release_id"],
              "retained_count": len(retained), "delete_count": len(remove),
              "delete_bytes": sum(row["byte_size"] for row in remove),
              "delete_groups": dict(Counter(row["object_key"].split('/')[1] for row in remove)),
              "objects": remove}
    write_json(PLAN, result)
    return result


def clean(export_dir):
    approved = read_json(PLAN)
    current = build_plan(export_dir)
    if approved != current:
        raise ValueError("The exact cleanup list changed; review the updated plan")
    s3 = aws_session().client("s3")
    removed = 0
    for start in range(0, len(current["objects"]), 1000):
        rows = current["objects"][start:start + 1000]
        response = s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": r["object_key"], "ETag": r["etag"]} for r in rows], "Quiet": False})
        removed += len(response.get("Deleted", []))
        if response.get("Errors"):
            write_json(HERE / "cleanup_receipt.json", {"status": "partial", "removed_count": removed, "errors": response["Errors"]})
            raise ValueError("Some obsolete objects could not be deleted; see cleanup receipt")
    result = {k: v for k, v in current.items() if k != "objects"}
    result.update(status="complete", removed_count=removed)
    write_json(HERE / "cleanup_receipt.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "delete"])
    parser.add_argument("--export-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "plan":
        result = build_plan(args.export_dir.resolve())
        print(json.dumps({k: v for k, v in result.items() if k != "objects"}), flush=True)
    else:
        clean(args.export_dir.resolve())
