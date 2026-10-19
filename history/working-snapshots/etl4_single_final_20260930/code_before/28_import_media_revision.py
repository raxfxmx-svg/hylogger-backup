"""Import media revisions from a sealed package; publish after independent validation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _db_common import LOCK_KEY, connection, assert_schema
from _run_reports import main_guard, report
from _db_files import read
from _media_common import require, save_stage
from _media_import import prepare_package, import_media, check_package
from _publication import stage_release
from _settings import StepParser
from _settings import settings, configure


def import_batch(conn, package):
    """Commit each dataset independently and create the pending release after the full batch completes."""
    source = package["source"]
    results = []
    save_stage(28, {"status": "running", "datasets": []})
    try:
        for index, unit in enumerate(source["datasets"], 1):
            print(f"[{index}/{len(source['datasets'])}] Import media {unit['hole_id']}", flush=True)
            with conn.transaction():
                result = import_media(conn, package, unit["dataset_id"])
            results.append(result)
            save_stage(28, {"status": "running", "datasets": results})
        with conn.transaction():
            release = stage_release(
                conn, results, "local_media_v2", {"source_release_id": source["source_release_id"]}
            )
    except Exception as error:
        save_stage(28, {"status": "failed", "datasets": results, "error": str(error)})
        raise
    return release, results


def main():
    parser = StepParser()
    parser.add_argument("--package", type=Path, help='Existing sealed package directory; supports reruns without the media work directory')
    args = parser.parse_args()
    configure(args)
    if args.package:
        destination = args.package.resolve()
        manifest = read(destination / "manifest.json")
        package = check_package(destination, manifest)
    else:
        package = prepare_package()
    key, destination = package["key"], package["directory"]
    source = package["source"]
    with connection() as conn:
        assert_schema(conn)
        require(
            conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"],
            "Another import is active",
        )
        try:
            release, results = import_batch(conn, package)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    staged = {
        "status": "staged",
        "release_id": release,
        "datasets": results,
        "media_package_sha256": key,
        "package_directory": destination.relative_to(settings.database_dir).as_posix(),
        "previous_release_id": source["source_release_id"],
    }
    save_stage(28, staged)
    report("28_media_import.json", staged)


if __name__ == "__main__":
    main_guard(main)
