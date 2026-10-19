"""Validate and publish the legacy base import; enable HTTP checks separately through an argument."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _run_reports import main_guard, report
from _db_files import write
from _settings import StepParser
from _settings import settings, configure, add_hole_arguments, selected_holes, batch_label
from _legacy_verification import verify_and_publish


def main():
    p = StepParser()
    add_hole_arguments(p)
    p.add_argument("--no-publish", action="store_true")
    p.add_argument("--check-api", action="store_true")
    a = p.parse_args()
    configure(a)
    selected = selected_holes(a)
    result = verify_and_publish(selected, publish=not a.no_publish, check_api=a.check_api)
    names = [h["hole_id"] for h in result["holes"]]
    report("10_verified_" + batch_label(names) + ".json", result)
    if not a.no_publish:
        write(settings.reports_dir / "latest_verified_database.json", result)
    print(f"Verified {len(names)} holes; local release {result['release_id']}")


if __name__ == "__main__":
    main_guard(main)
