"""Check media revisions against actual sources, then publish through the shared entry point."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _db_common import LOCK_KEY, assert_schema, connection, schema_hash
from _db_files import read, write
from _run_reports import main_guard, report
from _media_common import (
    media_code_hash,
    require,
    stage,
)
from _settings import StepParser
from _settings import settings, configure
from _media_import import check_package
from _legacy_media_import import release_context
from _media_verification import read_parquet_samples, verify_crops, verify_dataset


def write_manifest(conn, release):
    from _publication import write_asset_manifest

    return write_asset_manifest(conn, release)


def main():
    from _publication import publish_release

    parser = StepParser()
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--release")
    args = parser.parse_args()
    configure(args)
    if args.package or args.release:
        require(args.package and args.release, "Use --package and --release together")
        release, destination = args.release, args.package.resolve()
        with connection("reader") as conn:
            staged = release_context(conn, release, destination)
    else:
        staged = stage(28)
        require(staged["status"] == "staged", 'The media batch is not fully imported and cannot be published')
        release = staged["release_id"]
        destination = settings.database_dir / staged["package_directory"]
    manifest = read(destination / "manifest.json")
    package = check_package(destination, manifest)
    checks = []
    with connection() as conn:
        require(
            conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"],
            "Another import or validator is active",
        )
        try:
            assert_schema(conn)
            for unit in package["source"]["datasets"]:
                new = next(
                    item for item in staged["datasets"] if item["dataset_id"] == unit["dataset_id"]
                )
                print(f"Verify media {unit['hole_id']}", flush=True)
                result = verify_dataset(conn, unit, new, release, package)
                result.update(
                    status="passed",
                    dataset_revision_id=new["dataset_revision_id"],
                    input_digest=manifest["datasets"][unit["dataset_id"]]["content_sha256"],
                )
                checks.append(result)
            assets, locations = publish_release(
                conn,
                release,
                checks,
                __file__,
                activate=not args.no_activate,
                expected_previous=staged["previous_release_id"],
            )
            result = {
                "status": "passed",
                "release_id": release,
                "activated": not args.no_activate,
                "datasets": checks,
                "previous_release_id": staged["previous_release_id"],
                "schema_sha256": schema_hash(),
                "code_sha256": media_code_hash(),
            }
            report("29_media_verification.json", result)
            write(settings.reports_dir / "latest_verified_media.json", result)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    print(f'Verified {sum(item["sample_count"] for item in checks):,} samples.')


if __name__ == "__main__":
    main_guard(main)
