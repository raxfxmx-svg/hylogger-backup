from __future__ import annotations

import argparse
import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "config" / "source_wa_boreholes.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "config" / "wa_demo_100.csv"
SEED = "05GJD001"
PILOT = {"05KCD001", "07THD002", "07THD003", "09ATD015", "09ATD019"}


def build(source: Path, output: Path, total: int = 100) -> list[dict[str, str]]:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    by_id = {str(row.get("nvcl_id") or "").strip(): row for row in source_rows}
    if SEED not in by_id:
        raise ValueError(f"seed hole {SEED} is absent from {source}")

    selected = [by_id[SEED]]
    selected.extend(row for row in source_rows if row.get("nvcl_id") != SEED)
    selected = selected[:total]
    if len(selected) != total:
        raise ValueError(f"requested {total} holes but catalog supplied {len(selected)}")

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for order, source_row in enumerate(selected, start=1):
        hole_id = str(source_row.get("nvcl_id") or "").strip()
        if not hole_id or hole_id in seen:
            raise ValueError(f"empty or duplicate hole id at catalog order {order}: {hole_id!r}")
        lon = str(source_row.get("lon") or "").strip()
        lat = str(source_row.get("lat") or "").strip()
        float(lon)
        float(lat)
        seen.add(hole_id)
        phase = "seed" if hole_id == SEED else ("pilot" if hole_id in PILOT else "remaining")
        rows.append(
            {
                "order": str(order),
                "hole_id": hole_id,
                "lon": lon,
                "lat": lat,
                "borehole_length_m": str(source_row.get("boreholeLength_m") or ""),
                "phase": phase,
                "status": "db_verified" if phase == "seed" else "pending",
                "release_id": "",
                "detail": "",
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(output)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic 100-hole WA manifest")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--total", type=int, default=100)
    args = parser.parse_args()
    rows = build(args.source.resolve(), args.output.resolve(), args.total)
    print(f"wrote {len(rows)} holes to {args.output.resolve()}")
    print("pilot=" + ",".join(row["hole_id"] for row in rows if row["phase"] == "pilot"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
