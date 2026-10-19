"""Import a complete local batch from packages that passed the first acceptance, then run the second acceptance."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _db_files import read
from _final_import import run_final_import
from _run_reports import main_guard
from _settings import StepParser, configure


def main():
    parser = StepParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True, help='Package paths, preparation directories, and segment decisions for multiple datasets')
    args = parser.parse_args()
    configure(args)
    result = run_final_import(read(args.batch))
    print(f"Final release: {result['release_id']}; {len(result['datasets'])} datasets in this batch")


if __name__ == "__main__":
    main_guard(main)
