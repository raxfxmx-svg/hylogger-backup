"""Measure per-reference scanning against within-check deduplication on the same asset manifest; do not extrapolate whole-workflow speedups."""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _db_common import ETL, REPORTS, read, report
from _file_checks import FileChecks, hash_file
from _settings import StepParser


def main():
    StepParser().parse_args()
    manifest = read(REPORTS / "deployment_asset_manifest.json")
    paths = [
        ETL / item["object_key"] for item in manifest["locations"] if item["backend"] == "local"
    ]
    assert paths
    started = time.perf_counter()
    original = [hash_file(path) for path in paths]
    before = {
        "sha256_file_scans": len(paths),
        "sha256_bytes_read": sum(path.stat().st_size for path in paths),
        "elapsed_seconds": time.perf_counter() - started,
    }
    print("Uncached reference-by-reference scan complete", flush=True)
    with FileChecks() as check:
        revised = [hash_file(path) for path in paths]
        after = check.stats()
    assert original == revised
    report(
        "refactor_file_scan_measurement.json",
        {
            "status": "passed",
            "release_id": manifest["release_id"],
            "workload": 'Request SHA256 once per local asset reference in the same release, preserving input order',
            "before_without_deduplication": before,
            "after_with_one_check_deduplication": after,
            "limitation": 'Results depend on the OS file cache. This compares file validation, not total runtime of the old and new workflows.',
        },
    )
    print({"before": before, "after": after}, flush=True)


if __name__ == "__main__":
    main()
