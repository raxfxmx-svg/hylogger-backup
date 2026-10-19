"""Local settings keep source code, raw inputs and generated outputs separate."""

import argparse
import os
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent


def common_options():
    # Parse only common options here; each step handles its own arguments.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--dbname")
    options, _ = parser.parse_known_args()
    work = options.work_dir or Path(os.environ.get("ETL4_WORK_DIR", SOURCE_ROOT / "refactor_work"))
    work = work.resolve()
    if not work.is_relative_to(SOURCE_ROOT) or work == SOURCE_ROOT:
        raise ValueError('The work directory must be a separate subdirectory within etl4')
    if work in (SOURCE_ROOT / "database", SOURCE_ROOT / "processing"):
        raise ValueError('The work directory must not overlap historical database or processing directories')
    database = options.dbname or os.environ.get("ETL4_DBNAME", "etl4_refactor_check")
    if database == "etl4_core":
        raise ValueError('This refactor uses a separate database; specify a different database name')
    return work, database


WORK_DIR, DB_NAME = common_options()


class StepParser(argparse.ArgumentParser):
    """Give numbered entry points the same working-directory and database arguments."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_argument("--work-dir", type=Path, default=WORK_DIR, help='Separate working directory')
        self.add_argument("--dbname", default=DB_NAME, help='Separate database name')
