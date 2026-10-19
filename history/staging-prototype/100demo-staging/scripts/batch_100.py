from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "wa_demo_100.csv"
DEFAULT_SOURCE_CATALOG = PROJECT_ROOT / "config" / "source_wa_boreholes.csv"
DEFAULT_HISTORY = PROJECT_ROOT / "data" / "batch_runs" / "replacement_history.jsonl"
GIB = 1024**3
HOLE_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]+")


def validate_hole_id(value: str) -> str:
    hole_id = value.strip()
    if not hole_id or HOLE_ID_PATTERN.fullmatch(hole_id) is None:
        raise ValueError(f"invalid hole id {value!r}")
    return hole_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty manifest")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_history(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid replacement history line {number}: {exc}") from exc
            if not isinstance(value, dict):
                raise RuntimeError(f"replacement history line {number} is not an object")
            result.append(value)
    return result


def append_history(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def append_log(path: Path, title: str, result: subprocess.CompletedProcess[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n[{utc_now()}] {title}\n")
        handle.write(result.stdout or "")
        handle.write(result.stderr or "")


def run(command: list[str], log: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    append_log(log, " ".join(command), result)
    return result


def validate_manifest(rows: list[dict[str, str]], target_count: int) -> None:
    if len(rows) != target_count:
        raise RuntimeError(f"manifest has {len(rows)} rows; target-count is {target_count}")
    hole_ids = [str(row.get("hole_id") or "").strip() for row in rows]
    if len(set(hole_ids)) != len(hole_ids):
        raise RuntimeError("manifest contains duplicate hole ids")
    for row in rows:
        validate_hole_id(row.get("hole_id") or "")
        try:
            longitude = float(row.get("lon") or "")
            latitude = float(row.get("lat") or "")
        except ValueError as exc:
            raise RuntimeError(f"invalid coordinates for {row.get('hole_id')}") from exc
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise RuntimeError(f"coordinates outside EPSG:4326 for {row.get('hole_id')}")


def database_current_releases() -> dict[str, str]:
    with psycopg.connect(
        host=os.getenv("HYLOGGER_DB_HOST", "localhost"),
        port=int(os.getenv("HYLOGGER_DB_PORT", "5432")),
        dbname=os.getenv("HYLOGGER_DB_NAME", "hylogger_100demo"),
        user=os.environ["HYLOGGER_DB_USER"],
        password=os.environ["HYLOGGER_DB_PASSWORD"],
    ) as connection:
        rows = connection.execute(
            "SELECT hole_id, release_id FROM api.current_holes ORDER BY hole_id"
        ).fetchall()
    return {str(hole_id): str(release_id) for hole_id, release_id in rows}


def reconcile_rows(rows: list[dict[str, str]], current: dict[str, str]) -> int:
    manifest_ids = {row["hole_id"] for row in rows}
    unexpected = sorted(set(current) - manifest_ids)
    if unexpected:
        raise RuntimeError(
            "database contains current holes absent from the target manifest: "
            + ", ".join(unexpected)
        )
    changes = 0
    for row in rows:
        release_id = current.get(row["hole_id"])
        if release_id is not None:
            wanted = ("db_verified", release_id, "")
        elif row.get("status") == "db_verified":
            wanted = ("pending", "", "current database release is missing")
        else:
            continue
        if (row.get("status"), row.get("release_id"), row.get("detail")) != wanted:
            row.update(status=wanted[0], release_id=wanted[1], detail=wanted[2])
            changes += 1
    return changes


def allowed_phases(mode: str) -> set[str]:
    if mode == "pilot":
        return {"pilot"}
    if mode == "remaining":
        return {"remaining"}
    return {"pilot", "remaining"}


def eligible_rows(rows: list[dict[str, str]], mode: str) -> list[dict[str, str]]:
    allowed = allowed_phases(mode)
    return [
        row
        for row in rows
        if row.get("phase") in allowed and row.get("status") != "db_verified"
    ]


def has_valid_local_package(hole_id: str) -> bool:
    package_path = PROJECT_ROOT / "data" / "raw" / hole_id / "package_manifest.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return False
    return package.get("status") != "failed" and not package.get("errors")


def normalised_source_candidates(source_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for source_order, row in enumerate(source_rows, start=1):
        hole_id = str(row.get("nvcl_id") or "").strip()
        try:
            validate_hole_id(hole_id)
            longitude = float(row.get("lon") or "")
            latitude = float(row.get("lat") or "")
        except (TypeError, ValueError):
            continue
        if hole_id in seen or not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            continue
        seen.add(hole_id)
        result.append(
            {
                "source_order": str(source_order),
                "hole_id": hole_id,
                "lon": str(row.get("lon") or "").strip(),
                "lat": str(row.get("lat") or "").strip(),
                "borehole_length_m": str(row.get("boreholeLength_m") or "").strip(),
            }
        )
    return result


def attempted_hole_ids(history: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for event in history:
        for key in ("failed_hole_id", "replacement_hole_id"):
            if event.get(key):
                result.add(str(event[key]))
    return result


def available_candidates(
    source_candidates: list[dict[str, str]],
    rows: list[dict[str, str]],
    history: list[dict[str, Any]],
    current: dict[str, str],
) -> list[dict[str, str]]:
    used = {row["hole_id"] for row in rows}
    used.update(current)
    used.update(attempted_hole_ids(history))
    return [candidate for candidate in source_candidates if candidate["hole_id"] not in used]


def replace_failed_row(
    row: dict[str, str],
    candidate: dict[str, str],
    *,
    run_id: str,
    wave: int,
    failure_stage: str,
    failure_detail: str,
) -> dict[str, Any]:
    failed_hole_id = row["hole_id"]
    event: dict[str, Any] = {
        "recorded_at": utc_now(),
        "run_id": run_id,
        "wave": wave,
        "target_slot": row["order"],
        "failed_hole_id": failed_hole_id,
        "failure_stage": failure_stage,
        "failure_detail": failure_detail,
        "replacement_hole_id": candidate["hole_id"],
        "replacement_source_order": candidate["source_order"],
    }
    row.update(
        hole_id=candidate["hole_id"],
        lon=candidate["lon"],
        lat=candidate["lat"],
        borehole_length_m=candidate["borehole_length_m"],
        phase="remaining",
        status="pending",
        release_id="",
        detail=f"replacement for {failed_hole_id}",
    )
    return event


def exact_completion(
    rows: list[dict[str, str]], current: dict[str, str], target_count: int
) -> bool:
    verified = {row["hole_id"] for row in rows if row.get("status") == "db_verified"}
    return (
        len(rows) == target_count
        and len(verified) == target_count
        and verified == set(current)
    )


def free_space_gib(path: Path = PROJECT_ROOT) -> float:
    return shutil.disk_usage(path.anchor or path).free / GIB


def find_release(hole_id: str, fingerprint: str) -> str | None:
    releases = PROJECT_ROOT / "data" / "processed" / "releases"
    if not releases.is_dir():
        return None
    for root in releases.iterdir():
        manifest_path = root / "release_manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            manifest.get("holes") == [hole_id]
            and manifest.get("source_content_fingerprint") == fingerprint
        ):
            return str(manifest.get("release_id") or root.name)
    return None


def loader_environment() -> dict[str, str]:
    env = dict(os.environ)
    user = env.get("HYLOGGER_LOADER_DB_USER", "")
    password = env.get("HYLOGGER_LOADER_DB_PASSWORD", "")
    if not user or not password:
        raise RuntimeError(
            "HYLOGGER_LOADER_DB_USER and HYLOGGER_LOADER_DB_PASSWORD are required"
        )
    env["HYLOGGER_DB_USER"] = user
    env["HYLOGGER_DB_PASSWORD"] = password
    env["HYLOGGER_DB_SET_ROLE"] = "hylogger_loader"
    return env


def download_holes(
    hole_ids: list[str], workers: int, log: Path, env: dict[str, str]
) -> set[str]:
    pending = list(hole_ids)
    for attempt in range(1, 4):
        if not pending:
            break
        result = run(
            [
                sys.executable,
                "-m",
                "downloader.download",
                *pending,
                "--provider",
                "wa",
                "--out",
                str(PROJECT_ROOT / "data"),
                "--cache",
                str(PROJECT_ROOT / "data" / "cache"),
                "--workers",
                str(workers),
            ],
            log,
            env,
        )
        failed: list[str] = []
        for hole_id in pending:
            package = PROJECT_ROOT / "data" / "raw" / hole_id / "package_manifest.json"
            try:
                value = json.loads(package.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                failed.append(hole_id)
                continue
            if value.get("status") == "failed" or value.get("errors"):
                failed.append(hole_id)
        pending = failed
        if pending and attempt < 3:
            print(
                f"download attempt {attempt} left {len(pending)} failed holes; retrying",
                flush=True,
            )
        if result.returncode == 0 and not pending:
            break
    return set(pending)


def transform_hole(hole_id: str, log: Path, env: dict[str, str]) -> str:
    """Build or reuse an immutable release without validating or loading it."""
    package_path = PROJECT_ROOT / "data" / "raw" / hole_id / "package_manifest.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if package.get("status") == "failed" or package.get("errors"):
        raise RuntimeError("download package contains errors")
    fingerprint = str(package.get("content_fingerprint") or "")
    if not fingerprint:
        raise RuntimeError("download package has no content fingerprint")

    release_id = find_release(hole_id, fingerprint)
    if release_id is None:
        transformed = run(
            [
                sys.executable,
                str(PROJECT_ROOT / "pipeline" / "etl.py"),
                hole_id,
                "--raw-root",
                str(PROJECT_ROOT / "data" / "raw"),
                "--processed-root",
                str(PROJECT_ROOT / "data" / "processed"),
            ],
            log,
            env,
        )
        if transformed.returncode != 0:
            raise RuntimeError("ETL transform failed")
        try:
            release_id = str(json.loads(transformed.stdout)["release_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("ETL transform did not return release_id") from exc

    return release_id


def verify_and_load_hole(
    hole_id: str,
    release_id: str,
    log: Path,
    env: dict[str, str],
) -> None:
    """Validate and load one prepared release during the wave-end validation phase."""
    release_root = PROJECT_ROOT / "data" / "processed" / "releases" / release_id
    verified = run(
        [
            sys.executable,
            str(PROJECT_ROOT / "pipeline" / "verify.py"),
            "--project-root",
            str(PROJECT_ROOT),
            "--release-id",
            release_id,
        ],
        log,
        env,
    )
    if verified.returncode != 0:
        raise RuntimeError("release verification failed")

    loaded = run(
        [
            sys.executable,
            "-m",
            "etl.load_release",
            str(release_root),
            "--set-role",
            "hylogger_loader",
        ],
        log,
        env,
    )
    if loaded.returncode != 0:
        raise RuntimeError("database import failed")

    db_verified = run(
        [
            sys.executable,
            "-m",
            "etl.verify_loaded",
            hole_id,
            "--data-root",
            str(PROJECT_ROOT / "data" / "processed"),
            "--set-role",
            "hylogger_loader",
        ],
        log,
        env,
    )
    if db_verified.returncode != 0:
        raise RuntimeError("database verification failed")


def manifest_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("status") or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def make_summary(
    *,
    run_id: str,
    mode: str,
    state: str,
    rows: list[dict[str, str]],
    current: dict[str, str],
    waves: int,
    failures: int,
    replacements: int,
    detail: str = "",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": mode,
        "state": state,
        "target_count": len(rows),
        "active_holes": len(current),
        "manifest_counts": manifest_counts(rows),
        "waves_completed": waves,
        "failures": failures,
        "replacements": replacements,
        "free_space_gib": round(free_space_gib(), 2),
        "detail": detail,
        "updated_at": utc_now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resume-safe downloader, ETL and loader for the 100-hole demo"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-catalog", type=Path, default=DEFAULT_SOURCE_CATALOG)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--mode", choices=("pilot", "remaining", "all"), default="pilot")
    parser.add_argument("--workers", type=int, default=2, choices=range(1, 9))
    parser.add_argument("--wave-size", type=int, default=10)
    parser.add_argument("--target-count", type=int, default=100)
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument("--min-free-gib", type=float, default=50.0)
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="process one wave using valid local packages only; never call the downloader",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.wave_size < 1:
        parser.error("--wave-size must be at least 1")
    if args.target_count < 1:
        parser.error("--target-count must be at least 1")
    if args.max_consecutive_failures < 1:
        parser.error("--max-consecutive-failures must be at least 1")
    if args.min_free_gib < 0:
        parser.error("--min-free-gib cannot be negative")

    load_dotenv(PROJECT_ROOT / ".env")
    env = loader_environment()
    manifest_path = args.manifest.resolve()
    source_catalog_path = args.source_catalog.resolve()
    history_path = args.history.resolve()
    rows = read_rows(manifest_path)
    validate_manifest(rows, args.target_count)
    current = database_current_releases()
    reconciliation_changes = reconcile_rows(rows, current)
    history = read_history(history_path)
    source_candidates = normalised_source_candidates(read_rows(source_catalog_path))
    candidates = available_candidates(source_candidates, rows, history, current)
    mode_selected = eligible_rows(rows, args.mode)
    selected = (
        [row for row in mode_selected if has_valid_local_package(row["hole_id"])]
        if args.no_download
        else mode_selected
    )
    non_selected_pending = [
        row["hole_id"]
        for row in rows
        if row.get("status") != "db_verified" and row not in mode_selected
    ]

    dry_run_result = {
        "mode": args.mode,
        "target_count": args.target_count,
        "active_holes": len(current),
        "db_verified_after_reconciliation": sum(
            row.get("status") == "db_verified" for row in rows
        ),
        "pending_selected": len(selected),
        "pending_in_mode": len(mode_selected),
        "no_download": args.no_download,
        "non_selected_pending": non_selected_pending,
        "reconciliation_changes": reconciliation_changes,
        "wave_size": args.wave_size,
        "first_wave": [row["hole_id"] for row in selected[: args.wave_size]],
        "standby_candidates": len(candidates),
        "first_standby": candidates[0]["hole_id"] if candidates else None,
        "free_space_gib": round(free_space_gib(), 2),
        "min_free_gib": args.min_free_gib,
    }
    if args.dry_run:
        print(json.dumps(dry_run_result, ensure_ascii=False, indent=2))
        return 0

    if non_selected_pending:
        raise RuntimeError(
            "target cannot complete in this mode; pending holes outside selection: "
            + ", ".join(non_selected_pending)
        )
    if free_space_gib() < args.min_free_gib:
        raise RuntimeError("free disk space is below --min-free-gib before the run")
    if reconciliation_changes:
        write_rows(manifest_path, rows)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{args.mode}"
    run_root = PROJECT_ROOT / "data" / "batch_runs" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    write_json(run_root / "preflight.json", dry_run_result)
    print(
        f"batch {run_id}: active={len(current)} pending={len(selected)} "
        f"workers={args.workers} wave_size={args.wave_size}",
        flush=True,
    )

    waves = 0
    failures = 0
    replacements = 0
    state = "running"
    detail = ""

    while True:
        current = database_current_releases()
        if reconcile_rows(rows, current):
            write_rows(manifest_path, rows)
        if exact_completion(rows, current, args.target_count):
            state = "completed"
            break
        mode_selected = eligible_rows(rows, args.mode)
        selected = (
            [row for row in mode_selected if has_valid_local_package(row["hole_id"])]
            if args.no_download
            else mode_selected
        )
        if not selected:
            state = "local_data_exhausted" if args.no_download else "blocked"
            detail = (
                "no valid local pending package remains; downloader was disabled"
                if args.no_download
                else "no eligible pending holes remain before exact completion"
            )
            break
        if free_space_gib() < args.min_free_gib:
            state = "disk_paused"
            detail = f"free disk space fell below {args.min_free_gib:.1f} GiB"
            break

        waves += 1
        consecutive_failures = 0
        wave_rows = selected[: args.wave_size]
        wave_root = run_root / f"wave_{waves:03d}"
        wave_root.mkdir(parents=True, exist_ok=False)
        wave_log = wave_root / "download.log"
        attempted = [row["hole_id"] for row in wave_rows]
        if args.no_download:
            print(
                f"wave {waves}: local-only ETL for {len(attempted)} holes: "
                + ", ".join(attempted),
                flush=True,
            )
            failed_downloads: set[str] = set()
        else:
            print(
                f"wave {waves}: downloading {len(attempted)} holes: "
                + ", ".join(attempted),
                flush=True,
            )
            failed_downloads = download_holes(attempted, args.workers, wave_log, env)
        wave_verified: list[str] = []
        wave_failed: list[dict[str, str]] = []
        wave_replacements: list[dict[str, Any]] = []
        outcomes: dict[str, dict[str, str]] = {}
        prepared: list[tuple[dict[str, str], str]] = []
        breaker = False

        for row in wave_rows:
            hole_id = row["hole_id"]
            if hole_id in failed_downloads:
                outcomes[hole_id] = {
                    "stage": "download",
                    "detail": "failed after 3 batch attempts",
                }
            else:
                package_path = (
                    PROJECT_ROOT / "data" / "raw" / hole_id / "package_manifest.json"
                )
                package = json.loads(package_path.read_text(encoding="utf-8"))
                row.update(
                    status="downloaded",
                    detail=f"warnings={len(package.get('warnings') or [])}",
                )
                write_rows(manifest_path, rows)
                try:
                    release_id = transform_hole(
                        hole_id, wave_root / f"{hole_id}.log", env
                    )
                    row.update(
                        status="release_ready",
                        release_id=release_id,
                        detail="awaiting wave validation",
                    )
                    write_rows(manifest_path, rows)
                    prepared.append((row, release_id))
                    print(f"[{hole_id}] release_ready as {release_id}", flush=True)
                except Exception as exc:  # one hole must not contaminate another
                    outcomes[hole_id] = {"stage": "etl", "detail": str(exc)}

        print(
            f"wave {waves}: validating {len(prepared)} prepared releases as one wave",
            flush=True,
        )
        for row, release_id in prepared:
            hole_id = row["hole_id"]
            try:
                verify_and_load_hole(
                    hole_id,
                    release_id,
                    wave_root / f"{hole_id}.log",
                    env,
                )
                outcomes[hole_id] = {"release_id": release_id}
            except Exception as exc:  # collect every result before resolving the wave
                outcomes[hole_id] = {
                    "stage": "wave_validation",
                    "detail": str(exc),
                }

        for row in wave_rows:
            hole_id = row["hole_id"]
            outcome = outcomes[hole_id]
            release_id = outcome.get("release_id", "")
            if release_id:
                row.update(status="db_verified", release_id=release_id, detail="")
                write_rows(manifest_path, rows)
                wave_verified.append(hole_id)
                consecutive_failures = 0
                print(f"[{hole_id}] db_verified as {release_id}", flush=True)
                continue

            failure_stage = outcome["stage"]
            failure_detail = outcome["detail"]

            failures += 1
            consecutive_failures += 1
            row.update(status="failed", release_id="", detail=failure_detail)
            write_rows(manifest_path, rows)
            wave_failed.append(
                {
                    "hole_id": hole_id,
                    "stage": failure_stage,
                    "detail": failure_detail,
                }
            )
            print(
                f"[{hole_id}] FAILED at {failure_stage}: {failure_detail}",
                file=sys.stderr,
                flush=True,
            )

            if consecutive_failures >= args.max_consecutive_failures:
                state = "circuit_breaker"
                detail = (
                    f"{consecutive_failures} consecutive failures in wave {waves}; "
                    f"last hole {hole_id} retained for retry"
                )
                breaker = True
                break

            if args.no_download:
                continue

            history = read_history(history_path)
            current = database_current_releases()
            candidates = available_candidates(source_candidates, rows, history, current)
            if not candidates:
                state = "blocked"
                detail = "no unused valid standby candidate remains"
                breaker = True
                break
            event = replace_failed_row(
                row,
                candidates[0],
                run_id=run_id,
                wave=waves,
                failure_stage=failure_stage,
                failure_detail=failure_detail,
            )
            append_history(history_path, event)
            write_rows(manifest_path, rows)
            replacements += 1
            wave_replacements.append(event)
            print(
                f"[{hole_id}] replaced by {event['replacement_hole_id']}", flush=True
            )

        if args.no_download and not breaker:
            state = "local_only_complete"
            detail = "processed one wave from existing valid raw packages; no downloads"
            breaker = True

        current = database_current_releases()
        wave_summary = {
            "run_id": run_id,
            "wave": waves,
            "attempted": attempted,
            "verified": wave_verified,
            "failed": wave_failed,
            "replacements": wave_replacements,
            "active_holes": len(current),
            "manifest_counts": manifest_counts(rows),
            "free_space_gib": round(free_space_gib(), 2),
            "state": state,
            "finished_at": utc_now(),
        }
        write_json(wave_root / "summary.json", wave_summary)
        write_json(
            run_root / "summary.json",
            make_summary(
                run_id=run_id,
                mode=args.mode,
                state=state,
                rows=rows,
                current=current,
                waves=waves,
                failures=failures,
                replacements=replacements,
                detail=detail,
            ),
        )
        if breaker:
            break

    current = database_current_releases()
    final_summary = make_summary(
        run_id=run_id,
        mode=args.mode,
        state=state,
        rows=rows,
        current=current,
        waves=waves,
        failures=failures,
        replacements=replacements,
        detail=detail,
    )
    final_summary["finished_at"] = utc_now()
    final_summary["exact_completion"] = exact_completion(
        rows, current, args.target_count
    )
    write_json(run_root / "summary.json", final_summary)
    print(json.dumps(final_summary, ensure_ascii=False, indent=2))
    return 0 if final_summary["exact_completion"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
