"""Back up the active release and compare business content and schema in an isolated restored database."""

import os
import subprocess
import tempfile
from _db_common import (
    CODE,
    LOCK_KEY,
    PG_BIN,
    REPORTS,
    ROOT,
    assert_schema,
    config,
    connection,
    main_guard,
    pick,
    read,
    report,
    schema_hash,
    sha,
    write,
)
from _multi_common import MULTI, module, require
from datetime import datetime, timezone
from pathlib import Path
from _trial_support import create_trial, drop_trial, fingerprints


def backup_command(args, env):
    # Allow a longer timeout for full restoration while the main workflow reports progress.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        result = subprocess.run(
            [str(a) for a in args],
            stdout=output,
            stderr=errors,
            stdin=subprocess.DEVNULL,
            env=env,
            timeout=900,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode:
            errors.seek(0)
            raise RuntimeError(
                f"{Path(args[0]).name} failed: "
                + errors.read().decode("utf-8", errors="replace")[-3000:]
            )


def view_definitions(conn):
    return conn.execute(
        "SELECT viewname,definition FROM pg_views WHERE schemaname='core' ORDER BY viewname"
    ).fetchall()


def main():
    from _settings import StepParser

    parser = StepParser()
    parser.add_argument("--check-failures", action="store_true", help='Run failure cases in the restored copy')
    args = parser.parse_args()
    fault_checks = None
    result = read(MULTI / "35_verification.json")
    require(result["status"] == "passed" and result["activated"], "New release not verified")
    release = result["release_id"]
    c = config()
    env = os.environ.copy()
    env.update(
        PGHOST=c["host"],
        PGPORT=str(c["port"]),
        PGUSER=c["roles"]["owner"]["user"],
        PGPASSWORD=c["roles"]["owner"]["password"],
        PGCLIENTENCODING="UTF8",
    )
    with connection() as guard:
        require(
            guard.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"],
            "Another import is active",
        )
        try:
            require(
                str(
                    guard.execute("SELECT release_id FROM core.active_release").fetchone()[
                        "release_id"
                    ]
                )
                == release,
                "Active release changed",
            )
            assert_schema(guard)
            original = fingerprints()
            views = view_definitions(guard)
            audit_module = module("multi_schema_audit", CODE / "13_audit_database.py")
            structure = audit_module.schema_signature(guard)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = ROOT / "backups" / f"etl4_multi_{release}_{stamp}.dump"
            backup.parent.mkdir(exist_ok=True)
            backup_command(
                [
                    PG_BIN / "pg_dump.exe",
                    "--format=custom",
                    "--no-owner",
                    "--file",
                    backup,
                    "--dbname",
                    c["database"],
                ],
                env=env,
            )
            trial = create_trial("restore")
            try:
                backup_command(
                    [
                        PG_BIN / "pg_restore.exe",
                        "--no-owner",
                        "--exit-on-error",
                        "--dbname",
                        trial,
                        backup,
                    ],
                    env=env,
                )
                restored = fingerprints(trial)
                require(restored == original, "Restored table data differs")
                with connection(dbname=trial) as conn:
                    require(
                        audit_module.schema_signature(conn) == structure,
                        "Restored database structure differs",
                    )
                    require(view_definitions(conn) == views, "Restored views differ")
                    require(
                        str(
                            conn.execute("SELECT release_id FROM core.active_release").fetchone()[
                                "release_id"
                            ]
                        )
                        == release,
                        "Restored active release differs",
                    )
                    require(
                        conn.execute(
                            "SELECT count(*) n FROM core.v_borehole_composite_samples WHERE release_id=%s",
                            (release,),
                        ).fetchone()["n"]
                        == result["counts"]["overview_samples"],
                        "Restored 3D selection differs",
                    )
                    if args.check_failures:
                        from _media_import import package_step
                        from _media_tests import behavior_checks
                        from _multi_db import composite_rows

                        staged = read(MULTI / "34_import.json")
                        units = package_step(ROOT / staged["package_directory"], 20)["datasets"]
                        definition = conn.execute(
                            "SELECT manifest FROM core.data_release WHERE id=%s", (release,)
                        ).fetchone()["manifest"]
                        groups = composite_rows(conn, release, definition["succession_decisions"])
                        verifier = module(
                            "restore_composite_tests", CODE / "35_verify_multi_dataset_database.py"
                        )
                        with tempfile.TemporaryDirectory(prefix="faults_", dir=ROOT) as directory:
                            folder = Path(directory).resolve()
                            require(
                                folder.is_relative_to(ROOT.resolve()), "Unexpected test directory"
                            )
                            fault_checks = {
                                "media": behavior_checks(conn, units, folder),
                                "composite": verifier.composite_fault_checks(conn, groups),
                            }
                        require(
                            fingerprints(trial) == restored,
                            "Fault tests changed restored business rows",
                        )
            finally:
                drop_trial(trial)
            manifest = read(REPORTS / "deployment_asset_manifest.json")
            require(manifest["release_id"] == release, "Deployment manifest is stale")
            report_data = {
                "status": "passed",
                "release_id": release,
                "backup_relative_path": backup.relative_to(ROOT).as_posix(),
                "backup_sha256": sha(backup),
                "backup_bytes": backup.stat().st_size,
                "schema_sha256": schema_hash(),
                "business_table_hashes": original,
                "restored_table_hashes": restored,
                "restored_views_match": True,
                "restored_schema_matches": True,
                "restored_active_release_matches": True,
                "runtime_credentials_included": False,
                "independent_fault_checks": fault_checks,
            }
            write(
                backup.with_suffix(".manifest.json"),
                {
                    **report_data,
                    "asset_manifest": manifest,
                    "requires": "Restore database plus separately preserved object files; install compatible PostGIS and roles; no cloud operations performed",
                },
            )
            report("36_multi_dataset_restore.json", report_data)
            report(
                "latest_database_backup.json",
                {
                    "report": "36_multi_dataset_restore.json",
                    **pick(
                        report_data,
                        "release_id",
                        "backup_relative_path",
                        "backup_sha256",
                        "schema_sha256",
                    ),
                },
            )
        finally:
            guard.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    print(
        f"Full restore verified: {len(original)} business tables; backup {backup.stat().st_size:,} bytes."
    )


if __name__ == "__main__":
    main_guard(main)
