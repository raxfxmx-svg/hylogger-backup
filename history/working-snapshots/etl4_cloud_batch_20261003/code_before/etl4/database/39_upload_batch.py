"""Upload the batch manifest from step 38 and save per-object progress without recalculating business data in the cloud."""

import importlib.util
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _settings import StepParser, configure


def upload_tools():
    path = Path(__file__).resolve().parents[1] / 'handoff/tools/handoff.py'
    spec = importlib.util.spec_from_file_location("etl4_handoff_upload", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean_prefix(value):
    prefix = value.strip("/")
    if "\\" in prefix or any(part in ("", ".", "..") for part in prefix.split("/")):
        if prefix:
            raise ValueError('The S3 prefix must use ordinary directory names without empty segments, backslashes, or ..')
    return prefix


def transfer_items(directory, manifest, manifest_sha256, sources, prefix):
    """Deduplicate assets by content and place manifest files in the batch-specific directory."""
    items = []
    for key, source in sorted(sources.items()):
        items.append({"path": Path(source["path"]), "source_key": key, "kind": "asset",
                      "object_key": "/".join(filter(None, (prefix, key))),
                      "sha256": source["sha256"], "byte_size": source["byte_size"]})
    batch_prefix = "/".join(filter(None, (prefix, "batches", manifest["batch_id"], manifest_sha256)))
    for relative, row in sorted(manifest["files"].items()):
        items.append({"path": directory / relative, "source_key": relative, "kind": row["kind"],
                      "object_key": batch_prefix + "/" + relative,
                      "sha256": row["sha256"], "byte_size": row["byte_size"]})
    items.append({"path": directory / "manifest.json", "source_key": "manifest.json", "kind": "manifest",
                  "object_key": batch_prefix + "/manifest.json", "sha256": manifest_sha256,
                  "byte_size": (directory / "manifest.json").stat().st_size})
    keys = [item["object_key"] for item in items]
    if len(keys) != len(set(keys)):
        raise ValueError('This batch contains duplicate upload object keys')
    return items


def make_progress(index, total, key):
    last_percent = [-10]

    def progress(sent, size):
        percent = min(100, int(sent * 100 / size)) if size else 100
        if percent >= last_percent[0] + 10:
            print(f"[{index}/{total}] file read/transfer {percent}%: {key}", flush=True)
            last_percent[0] = percent

    return progress


def upload_batch(directory, bucket, region, prefix="etl4", receipt_path=None, *, client=None):
    # Load the SDK only for uploads; --help and offline tests do not require boto3.
    from _batch_files import load_export, load_sources, read_json, write_json

    directory = Path(directory).resolve()
    manifest, manifest_sha256 = load_export(directory)
    sources = load_sources(directory, manifest, manifest_sha256)
    prefix = clean_prefix(prefix)
    items = transfer_items(directory, manifest, manifest_sha256, sources, prefix)
    receipt_path = Path(receipt_path).resolve() if receipt_path else directory / "upload_receipt.json"
    protected = {item["path"].resolve() for item in items}
    protected.add((directory / "local_sources.json").resolve())
    if receipt_path in protected or receipt_path == directory:
        raise ValueError('The upload receipt must not overwrite sealed files or original assets')
    receipt_identity = {"format": "etl4-batch-upload-v1", "batch_id": manifest["batch_id"],
                        "manifest_sha256": manifest_sha256, "bucket": bucket,
                        "region": region, "prefix": prefix}
    if receipt_path.exists():
        previous = read_json(receipt_path)
        if any(previous.get(key) != value for key, value in receipt_identity.items()):
            raise ValueError('The existing receipt belongs to another batch or upload target; choose another --receipt path')
    ops = upload_tools()
    if client is None:
        try:
            import boto3
        except ImportError as exc:
            raise ValueError('Uploads require boto3; install the AWS dependencies from the handoff directory') from exc
        client = boto3.client("s3", region_name=region)
        ops.check_upload_sdk(client)
    receipt = {**receipt_identity, "status": "partial",
               "expected_objects": len(items), "objects": [],
               "resume_scope": "completed_objects; interrupted_file_restarts",
               "started_at": datetime.now(timezone.utc).isoformat()}
    write_json(receipt_path, receipt)
    try:
        for index, item in enumerate(items, 1):
            receipt["current_object"] = item["object_key"]
            write_json(receipt_path, receipt)
            result = ops.upload_object(client, item["path"], bucket, item["object_key"],
                                       item["sha256"], item["byte_size"],
                                       progress=make_progress(index, len(items), item["object_key"]))
            receipt["objects"].append({**result, "source_key": item["source_key"], "kind": item["kind"]})
            receipt["completed_objects"] = len(receipt["objects"])
            write_json(receipt_path, receipt)
            action = 'reused' if result["reused"] else 'uploaded'
            print(f"[{index}/{len(items)}] {action} and verified: {item['object_key']}", flush=True)
    except BaseException as exc:
        receipt["error_type"] = type(exc).__name__
        write_json(receipt_path, receipt)
        raise
    receipt.pop("current_object", None)
    receipt.update(status="complete", completed_at=datetime.now(timezone.utc).isoformat())
    write_json(receipt_path, receipt)
    return receipt


def main():
    parser = StepParser(description=__doc__)
    parser.add_argument("--export-dir", type=Path, required=True, help='Export directory from step 38')
    parser.add_argument("--bucket", required=True, help='Target S3 bucket')
    parser.add_argument("--region", required=True, help='Target AWS region')
    parser.add_argument("--prefix", default="etl4", help='S3 object prefix')
    parser.add_argument("--receipt", type=Path, help='Progress receipt; defaults to export-directory/upload_receipt.json')
    args = parser.parse_args()
    configure(args)
    result = upload_batch(args.export_dir, args.bucket, args.region, args.prefix, args.receipt)
    print(f"Batch upload complete: {result['completed_objects']} objects; receipt status complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Omit full SDK, connection and authorisation exceptions from logs to avoid sensitive request details.
        print(str(exc) if isinstance(exc, ValueError) else f"Upload incomplete: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)
