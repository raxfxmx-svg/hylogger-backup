"""Import prepared results transactionally; skip an already imported revision on reruns."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _run_reports import main_guard, report
from _settings import StepParser
from _settings import configure
from _ingest import run_import


def main():
    p = StepParser()
    p.add_argument("--holes", nargs="+", help='Import all boreholes in the current input manifest by default')
    args = p.parse_args()
    configure(args)
    selected = list(dict.fromkeys(args.holes)) if args.holes is not None else None
    result = run_import(selected)
    names = selected or [h["hole_id"] for h in result["holes"]]
    report("9_import_" + "_".join(names) + ".json", result)
    print("Staged import complete; publication requires step 10 verification", flush=True)


if __name__ == "__main__":
    main_guard(main)
