"""Compare the database with prepared outputs before publication; enable HTTP checks separately."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _db_common import ALLOWED
from _run_reports import main_guard, report
from _db_files import write
from _settings import StepParser
from _settings import settings, configure
from _verification import verify_and_publish


def main():
    p = StepParser()
    p.add_argument("--holes", nargs="+", choices=ALLOWED, default=list(ALLOWED))
    p.add_argument("--no-publish", action="store_true")
    p.add_argument("--check-api", action="store_true")
    a = p.parse_args()
    configure(a)
    result = verify_and_publish(
        list(dict.fromkeys(a.holes)), publish=not a.no_publish, check_api=a.check_api
    )
    report("10_verified_" + ("_".join(a.holes)) + ".json", result)
    if set(a.holes) == set(ALLOWED) and not a.no_publish:
        write(settings.reports_dir / "latest_verified_database.json", result)
    print(f"Verified {len(a.holes)} holes; local release {result['release_id']}")


if __name__ == "__main__":
    main_guard(main)
