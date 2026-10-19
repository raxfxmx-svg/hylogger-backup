"""Revalidate added boreholes in the target using the original sealed package; preserve the source database and work reports."""

import importlib.util
import sys
from pathlib import Path
from merge_common import AUDIT, ETL, TARGET, settings, connection, lock, assert_schema, read, write
from _media_import import check_package, package_step, release_context, verify_source_assets
from _prepared_inputs import prepared_holes
from _verification import verify_hole, api_checks

settings.work_dir = Path(sys.argv[1]).resolve()
assert settings.work_dir.is_relative_to(ETL / "new_input_check") or settings.work_dir == ETL / "new_input_check"
settings.dbname = TARGET
staged = read(settings.media_work_dir / "28.json")
destination = settings.database_dir / staged["package_directory"]
manifest = read(destination / "manifest.json")
check_package(destination, manifest)
source_stage = package_step(destination, 20)
spec = importlib.util.spec_from_file_location("merge_media_verification", ETL / "database/29_verify_media_grain.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
base_checks, media_checks = [], []
prepared_units = prepared_holes()
by_revision = {unit["metadata"]["dataset_revision"]["id"]: unit for unit in prepared_units}
with connection("reader") as conn:
    lock(conn)
    assert_schema(conn)
    context = release_context(conn, staged["release_id"], destination)
    for unit in source_stage["datasets"]:
        print("Verify added hole " + unit["hole_id"], flush=True)
        prepared = by_revision[unit["source_revision_id"]]
        base_checks.append(verify_hole(conn, prepared))
        verify_source_assets(conn, unit)
        member = next(item for item in context["datasets"] if item["dataset_id"] == unit["dataset_id"])
        check = verifier.verify_dataset(conn, unit, member, staged["release_id"], destination)
        check.update(status="passed", dataset_revision_id=member["dataset_revision_id"], input_digest=manifest["datasets"][unit["dataset_id"]]["content_sha256"])
        media_checks.append(check)
    api = api_checks([by_revision[unit["source_revision_id"]] for unit in source_stage["datasets"]], source_stage["source_release_id"], TARGET)
result = {"status": "passed", "base_checks": base_checks, "media_checks": media_checks, "api_checks": api, "work_dir": str(settings.work_dir), "media_release": staged["release_id"]}
write(AUDIT / ("verify_" + settings.work_dir.name + ".json"), result)
print("Added holes verified against source data and API", flush=True)
