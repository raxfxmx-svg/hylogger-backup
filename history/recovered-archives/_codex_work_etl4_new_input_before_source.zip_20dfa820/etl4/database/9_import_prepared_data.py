"""Import prepared results transactionally; skip an already imported revision on reruns."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _db_common import ALLOWED
from _run_reports import main_guard, report
from _settings import StepParser
from _settings import configure
from _ingest import run_import


def main():
    p = StepParser()
    p.add_argument("--holes", nargs="+", choices=ALLOWED, default=list(ALLOWED))
    args = p.parse_args()
    configure(args)
    result = run_import(list(dict.fromkeys(args.holes)))
    report("9_import_" + ("_".join(args.holes)) + ".json", result)
    print("Staged import complete; publication requires step 10 verification", flush=True)


if __name__ == "__main__":
    main_guard(main)
