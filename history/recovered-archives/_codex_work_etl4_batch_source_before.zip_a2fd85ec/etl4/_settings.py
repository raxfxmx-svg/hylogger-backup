"""Initialize run settings in numbered entry points; importing this module does not parse arguments."""

import argparse
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent
BASE_HOLES = ("05KCD001", "07THD002", "07THD003", "09ATD015", "09ATD019")


def validate_hole_names(holes):
    """Validate explicitly selected borehole IDs so directory paths cannot be mistaken for IDs."""
    if not isinstance(holes, (list, tuple)) or not holes:
        raise ValueError('Explicitly select at least one borehole')
    if any(not isinstance(h, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", h) for h in holes):
        raise ValueError('Borehole IDs may contain only letters, digits, underscores, and hyphens')
    if len(holes) != len(set(holes)):
        raise ValueError('The input list contains duplicate borehole IDs')
    return list(holes)


@dataclass
class RunSettings:
    """Run one step per process with shared utilities using its selected directories and database."""

    work_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("ETL4_WORK_DIR", SOURCE_ROOT / "refactor_work")
        ).resolve()
    )
    dbname: str = field(
        default_factory=lambda: os.environ.get("ETL4_DBNAME", "etl4_refactor_check")
    )

    @property
    def database_dir(self):
        return self.work_dir / "database"

    @property
    def processing_dir(self):
        return self.work_dir / "processing"

    @property
    def prepared_dir(self):
        return self.processing_dir / "outputs"

    @property
    def runtime_dir(self):
        return self.database_dir / "runtime"

    @property
    def reports_dir(self):
        return self.database_dir / "reports"

    @property
    def media_work_dir(self):
        return self.database_dir / "media_work"

    @property
    def media_evidence_dir(self):
        return self.database_dir / "media_evidence"

    @property
    def multi_work_dir(self):
        return self.database_dir / "multi_work"

    @property
    def multi_evidence_dir(self):
        return self.multi_work_dir / "evidence"

    @property
    def multi_media_dir(self):
        return self.multi_work_dir / "media"


settings = RunSettings()


def configure(options):
    """Configure once after parsing arguments; subsequent processing functions receive directories as needed."""
    work = Path(options.work_dir).resolve()
    if not work.is_relative_to(SOURCE_ROOT) or work == SOURCE_ROOT:
        raise ValueError('The work directory must be a separate subdirectory within etl4')
    if work in (SOURCE_ROOT / "database", SOURCE_ROOT / "processing"):
        raise ValueError('The work directory must not overlap historical database or processing directories')
    database = options.dbname
    if database == "etl4_core":
        raise ValueError('This refactor uses a separate database; specify a different database name')
    settings.work_dir = work
    settings.dbname = database
    return settings


class StepParser(argparse.ArgumentParser):
    """Give numbered entry points the same working-directory and database arguments."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_argument("--work-dir", type=Path, default=settings.work_dir, help='Separate working directory')
        self.add_argument("--dbname", default=settings.dbname, help='Separate database name')
