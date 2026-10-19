"""Rerun complete sealed packages in a validation database to confirm independence from temporary directories and no new business records."""

from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg import sql
from _db_common import CODE, config, connection
from _run_reports import main_guard, report
from _db_files import read
from _media_common import stage
from _settings import StepParser
from _settings import settings, configure
from _trial_support import fingerprints


def counts():
    with connection("reader") as conn:
        names = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='core'").fetchall()
        return {
            r["tablename"]: conn.execute(
                sql.SQL("SELECT count(*) n FROM core.{}").format(sql.Identifier(r["tablename"]))
            ).fetchone()["n"]
            for r in names
            if r["tablename"]
            not in ("ingest_run", "revision_validation", "active_release", "schema_migration")
        }


def run(script, *arguments):
    started = time.perf_counter()
    subprocess.run(
        [
            sys.executable,
            str(CODE / script),
            "--work-dir",
            str(settings.work_dir),
            "--dbname",
            config()["database"],
            *map(str, arguments),
        ],
        check=True,
    )
    return {"script": script, "elapsed_seconds": time.perf_counter() - started}


def main():
    args = StepParser().parse_args()
    configure(args)
    media = stage(28)
    multi = read(settings.database_dir / "multi_work/34_import.json")
    before = counts()
    before_hash = fingerprints()
    runs = []
    with tempfile.TemporaryDirectory(prefix="replay_", dir=settings.database_dir) as temporary:
        saved = Path(temporary).resolve()
        assert saved.is_relative_to(settings.database_dir.resolve())
        paths = [settings.database_dir / "media_work", settings.database_dir / "multi_work"]
        try:
            for path in paths:
                assert path.resolve().is_relative_to(settings.database_dir.resolve())
                path.rename(saved / path.name)
            runs.append(run("9_import_prepared_data.py"))
            runs.append(
                run(
                    "28_import_media_revision.py",
                    "--package",
                    settings.database_dir / media["package_directory"],
                )
            )
            runs.append(
                run(
                    "29_verify_media_grain.py",
                    "--package",
                    settings.database_dir / media["package_directory"],
                    "--release",
                    media["release_id"],
                    "--no-activate",
                )
            )
            runs.append(
                run(
                    "34_import_multi_dataset_database.py",
                    "--package",
                    settings.database_dir / multi["package_directory"],
                    "--source-release",
                    multi["previous_release_id"],
                )
            )
            runs.append(
                run(
                    "35_verify_multi_dataset_database.py",
                    "--package",
                    settings.database_dir / multi["package_directory"],
                    "--release",
                    multi["release_id"],
                )
            )
        finally:
            for path in paths:
                original = saved / path.name
                if original.exists():
                    if path.exists():
                        assert path.resolve().is_relative_to(settings.database_dir.resolve())
                        path.rename(saved / ("generated_" + path.name))
                    original.rename(path)
    after = counts()
    assert before == after, "Replay added business rows"
    assert before_hash == fingerprints(), "Replay changed business content"
    report(
        "refactor_replay_check.json",
        {
            "status": "passed",
            "temporary_directories_unavailable": True,
            "business_rows_before": before,
            "business_rows_after": after,
            "new_business_rows": sum(after.values()) - sum(before.values()),
            "business_hashes_unchanged": True,
            "runs": runs,
        },
    )
    print("Sealed-package replay passed; 0 new business rows.", flush=True)


if __name__ == "__main__":
    main_guard(main)
