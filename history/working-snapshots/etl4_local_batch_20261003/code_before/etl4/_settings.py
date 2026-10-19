"""Initialize run settings in numbered entry points; importing this module does not parse arguments."""

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent
BASE_HOLES = ("05KCD001", "07THD002", "07THD003", "09ATD015", "09ATD019")


def add_hole_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--holes", nargs="+", help='Explicitly selected borehole IDs')
    group.add_argument("--holes-file", type=Path, help='Borehole list from step 0, one ID per line')


def selected_holes(args, default=None):
    if args.holes_file is not None:
        holes = args.holes_file.read_text(encoding="utf-8-sig").splitlines()
        holes = validate_hole_names([hole.strip() for hole in holes if hole.strip()])
        folder = args.holes_file.parent
        status_file = folder / "0_status.json"
        if status_file.exists():
            status = json.loads(status_file.read_text(encoding="utf-8"))
            report = json.loads((folder / "0_raw_check.json").read_text(encoding="utf-8"))
            group = args.holes_file.stem.removesuffix("_holes")
            if status.get("status") != "complete" or status.get("run_id") != report.get("run_id"):
                raise ValueError('Step 0 is incomplete; rerun the precheck before using the list')
            if group not in ("single", "multi") or holes != report["groups"][group]:
                raise ValueError('The list does not match step 0 classification; pending boreholes cannot enter a normal batch')
        return holes
    if args.holes is not None:
        return validate_hole_names(args.holes)
    return validate_hole_names(default) if default is not None else None


def batch_label(holes):
    """Keep report filenames short; batch labels do not contribute to data version identities."""
    names = sorted(validate_hole_names(holes))
    content = json.dumps(names, ensure_ascii=False).encode("utf-8")
    return "batch_" + hashlib.sha256(content).hexdigest()[:12]


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
