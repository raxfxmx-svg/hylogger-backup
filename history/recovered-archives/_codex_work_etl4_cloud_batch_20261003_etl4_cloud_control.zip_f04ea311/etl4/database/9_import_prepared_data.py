"""Import prepared results transactionally; skip an already imported revision on reruns."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _run_reports import main_guard, report
from _settings import StepParser
from _settings import configure, add_hole_arguments, selected_holes, batch_label
from _ingest import run_import


def main():
    p = StepParser()
    add_hole_arguments(p)
    args = p.parse_args()
    configure(args)
    selected = selected_holes(args)
    result = run_import(selected)
    names = selected or [h["hole_id"] for h in result["holes"]]
    report("9_import_" + batch_label(names) + ".json", result)
    print("Staged import complete; publication requires step 10 verification", flush=True)


if __name__ == "__main__":
    main_guard(main)
