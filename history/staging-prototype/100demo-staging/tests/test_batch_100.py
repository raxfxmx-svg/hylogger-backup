from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import batch_100  # noqa: E402


FIELDS = [
    "order", "hole_id", "lon", "lat", "borehole_length_m",
    "phase", "status", "release_id", "detail",
]


def row(order: int, hole_id: str, *, phase: str = "remaining", status: str = "pending") -> dict[str, str]:
    return {
        "order": str(order),
        "hole_id": hole_id,
        "lon": "120.0",
        "lat": "-30.0",
        "borehole_length_m": "100",
        "phase": phase,
        "status": status,
        "release_id": "",
        "detail": "",
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_source(path: Path, hole_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["nvcl_id", "lon", "lat", "boreholeLength_m"],
        )
        writer.writeheader()
        for hole_id in hole_ids:
            writer.writerow(
                {"nvcl_id": hole_id, "lon": "121", "lat": "-29", "boreholeLength_m": "120"}
            )


def test_database_reconciliation_is_authoritative() -> None:
    rows = [
        row(1, "H001", status="pending"),
        row(2, "H002", status="db_verified"),
        row(3, "H003", status="pending"),
    ]
    rows[1]["release_id"] = "stale"
    changes = batch_100.reconcile_rows(rows, {"H001": "R1", "H003": "R3"})
    assert changes == 3
    assert [(item["status"], item["release_id"]) for item in rows] == [
        ("db_verified", "R1"),
        ("pending", ""),
        ("db_verified", "R3"),
    ]


def test_wave_selection_and_exact_completion() -> None:
    rows = [row(1, "SEED", phase="seed", status="db_verified")]
    rows.extend(row(index + 2, f"H{index:03d}") for index in range(12))
    selected = batch_100.eligible_rows(rows, "remaining")
    assert [item["hole_id"] for item in selected[:10]] == [f"H{index:03d}" for index in range(10)]

    for item in rows:
        item["status"] = "db_verified"
        item["release_id"] = "R-" + item["hole_id"]
    current = {item["hole_id"]: item["release_id"] for item in rows}
    assert batch_100.exact_completion(rows, current, len(rows))
    assert not batch_100.exact_completion(rows, {"SEED": "R-SEED"}, len(rows))


def test_standby_selection_never_reuses_attempted_holes() -> None:
    rows = [row(1, "H001"), row(2, "H002")]
    candidates = batch_100.normalised_source_candidates(
        [
            {"nvcl_id": hole, "lon": "121", "lat": "-29", "boreholeLength_m": "100"}
            for hole in ("H001", "H002", "H003", "H004", "H005")
        ]
    )
    history = [{"failed_hole_id": "H003", "replacement_hole_id": "H004"}]
    available = batch_100.available_candidates(candidates, rows, history, {"H001": "R1"})
    assert [item["hole_id"] for item in available] == ["H005"]


def test_dry_run_reconciles_in_memory_without_writing(tmp_path, monkeypatch, capsys) -> None:
    project = tmp_path / "project"
    manifest = project / "config" / "wa_demo_100.csv"
    source = project / "config" / "source.csv"
    original = [row(1, "SEED", phase="seed"), row(2, "H001")]
    write_csv(manifest, original)
    write_source(source, ["SEED", "H001", "H002"])
    before = manifest.read_bytes()

    monkeypatch.setattr(batch_100, "PROJECT_ROOT", project)
    monkeypatch.setattr(batch_100, "loader_environment", lambda: {})
    monkeypatch.setattr(batch_100, "database_current_releases", lambda: {"SEED": "R-SEED"})
    monkeypatch.setattr(batch_100, "free_space_gib", lambda path=project: 100.0)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_100.py",
            "--manifest", str(manifest),
            "--source-catalog", str(source),
            "--history", str(project / "history.jsonl"),
            "--mode", "remaining",
            "--target-count", "2",
            "--dry-run",
        ],
    )

    assert batch_100.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["db_verified_after_reconciliation"] == 1
    assert output["pending_selected"] == 1
    assert manifest.read_bytes() == before
    assert not (project / "data" / "batch_runs").exists()


def test_whole_wave_is_transformed_before_validation(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    manifest = project / "config" / "wa_demo_100.csv"
    source = project / "config" / "source.csv"
    history = project / "data" / "batch_runs" / "replacement_history.jsonl"
    rows = [row(1, "H001"), row(2, "H002")]
    write_csv(manifest, rows)
    write_source(source, ["H001", "H002", "H003"])
    for item in rows:
        package = project / "data" / "raw" / item["hole_id"] / "package_manifest.json"
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_text('{"warnings": []}', encoding="utf-8")

    events: list[str] = []
    current: dict[str, str] = {}

    def transform(hole_id, log, env):
        events.append(f"transform:{hole_id}")
        return f"R-{hole_id}"

    def verify_and_load(hole_id, release_id, log, env):
        events.append(f"verify:{hole_id}")
        current[hole_id] = release_id

    monkeypatch.setattr(batch_100, "PROJECT_ROOT", project)
    monkeypatch.setattr(batch_100, "loader_environment", lambda: {})
    monkeypatch.setattr(batch_100, "database_current_releases", lambda: dict(current))
    monkeypatch.setattr(batch_100, "free_space_gib", lambda path=project: 100.0)
    def forbid_download(*args):
        raise AssertionError("downloader must not run in --no-download mode")

    monkeypatch.setattr(batch_100, "download_holes", forbid_download)
    monkeypatch.setattr(batch_100, "transform_hole", transform)
    monkeypatch.setattr(batch_100, "verify_and_load_hole", verify_and_load)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_100.py",
            "--manifest", str(manifest),
            "--source-catalog", str(source),
            "--history", str(history),
            "--mode", "remaining",
            "--target-count", "2",
            "--wave-size", "2",
            "--min-free-gib", "0",
            "--no-download",
        ],
    )

    assert batch_100.main() == 0
    assert events == [
        "transform:H001",
        "transform:H002",
        "verify:H001",
        "verify:H002",
    ]


def test_three_consecutive_failures_trip_breaker_and_preserve_third(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    manifest = project / "config" / "wa_demo_100.csv"
    source = project / "config" / "source.csv"
    history = project / "data" / "batch_runs" / "replacement_history.jsonl"
    write_csv(manifest, [row(1, "H001"), row(2, "H002"), row(3, "H003")])
    write_source(source, ["H001", "H002", "H003", "H004", "H005", "H006"])

    monkeypatch.setattr(batch_100, "PROJECT_ROOT", project)
    monkeypatch.setattr(batch_100, "loader_environment", lambda: {})
    monkeypatch.setattr(batch_100, "database_current_releases", lambda: {})
    monkeypatch.setattr(batch_100, "free_space_gib", lambda path=project: 100.0)
    monkeypatch.setattr(
        batch_100,
        "download_holes",
        lambda hole_ids, workers, log, env: set(hole_ids),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "batch_100.py",
            "--manifest", str(manifest),
            "--source-catalog", str(source),
            "--history", str(history),
            "--mode", "remaining",
            "--target-count", "3",
            "--wave-size", "3",
            "--max-consecutive-failures", "3",
            "--min-free-gib", "0",
        ],
    )

    assert batch_100.main() == 1
    final_rows = batch_100.read_rows(manifest)
    assert [item["hole_id"] for item in final_rows] == ["H004", "H005", "H003"]
    assert final_rows[2]["status"] == "failed"
    events = batch_100.read_history(history)
    assert len(events) == 2
    summary_path = next((project / "data" / "batch_runs").glob("*_remaining/summary.json"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["state"] == "circuit_breaker"
    assert summary["replacements"] == 2
