from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_100_hole_manifest_is_deterministic() -> None:
    with (ROOT / "config" / "wa_demo_100.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 100
    assert rows[0]["hole_id"] == "05GJD001"
    assert len({row["hole_id"] for row in rows}) == 100
    assert [row["hole_id"] for row in rows if row["phase"] == "pilot"] == [
        "05KCD001",
        "07THD002",
        "07THD003",
        "09ATD015",
        "09ATD019",
    ]
    for row in rows:
        assert -180 <= float(row["lon"]) <= 180
        assert -90 <= float(row["lat"]) <= 90
