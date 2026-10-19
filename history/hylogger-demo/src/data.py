"""Load and validate the auditable 05GJD001 exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


HOLE_COLUMNS = {
    "hole_id",
    "hole_name",
    "latitude",
    "longitude",
    "coordinate_status",
    "source_bundle_id",
    "notes",
}
TRAY_COLUMNS = {
    "hole_id",
    "tray_id",
    "depth_from_m",
    "depth_to_m",
    "sample_count",
    "image_relpath",
    "image_status",
}
BIN_COLUMNS = {
    "hole_id",
    "tray_id",
    "depth_from_m",
    "depth_to_m",
    "mineral_group",
    "sample_count",
    "dominant_sample_count",
    "dominant_share_pct",
    "bin_size_m",
    "algorithm_field",
}
SAMPLE_COLUMNS = {
    "sample_id",
    "hole_id",
    "tray_id",
    "core_row",
    "position_index",
    "depth_m",
    "along_row_mm",
    "mineral_group",
    "algorithm_field",
}


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{label} is missing required columns: {sorted(missing)}")


def load_holes(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"hole_id": str, "hole_name": str, "coordinate_status": str})
    _require_columns(frame, HOLE_COLUMNS, "Hole registry")
    if frame["hole_id"].duplicated().any():
        raise ValueError("Hole registry contains duplicate hole_id values")

    for column in ["latitude", "longitude"]:
        raw = frame[column].fillna("").astype(str).str.strip()
        parsed = pd.to_numeric(raw.where(raw.ne("")), errors="coerce")
        if (raw.ne("") & parsed.isna()).any():
            raise ValueError(f"{column} contains a non-numeric value")
        frame[column] = parsed
    return frame


def load_trays(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        dtype={"hole_id": str, "tray_id": str, "image_relpath": str, "image_status": str},
        keep_default_na=False,
    )
    _require_columns(frame, TRAY_COLUMNS, "Tray table")
    frame["tray_id"] = frame["tray_id"].str.zfill(4)
    for column in ["depth_from_m", "depth_to_m", "sample_count"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame[["hole_id", "tray_id"]].duplicated().any():
        raise ValueError("Tray table contains duplicate hole/tray records")
    if (frame["depth_to_m"] <= frame["depth_from_m"]).any():
        raise ValueError("Every tray must have a positive depth range")

    ordered = frame.sort_values("depth_from_m").reset_index(drop=True)
    if len(ordered) > 1:
        starts = ordered["depth_from_m"].iloc[1:].reset_index(drop=True)
        previous_ends = ordered["depth_to_m"].iloc[:-1].reset_index(drop=True)
        # The source depth channel carries sub-millimetre floating-point jitter
        # at a few tray boundaries (up to 0.000009 m in this package).
        if (starts < previous_ends - 1e-4).any():
            raise ValueError("Tray depth ranges overlap")
    return ordered


def load_depth_bins(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"hole_id": str, "tray_id": str, "mineral_group": str})
    _require_columns(frame, BIN_COLUMNS, "Depth-bin table")
    if "confidence" in frame.columns:
        raise ValueError("Depth-bin table must not contain inferred confidence")
    frame["tray_id"] = frame["tray_id"].str.zfill(4)
    numeric = [
        "depth_from_m",
        "depth_to_m",
        "sample_count",
        "dominant_sample_count",
        "dominant_share_pct",
        "bin_size_m",
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if (frame["depth_to_m"] <= frame["depth_from_m"]).any():
        raise ValueError("Depth bins must have positive thickness")
    if not frame["dominant_share_pct"].between(0, 100, inclusive="both").all():
        raise ValueError("Dominant share must be between 0 and 100")
    if frame["mineral_group"].fillna("").str.strip().eq("").any():
        raise ValueError("Mineral-group labels cannot be blank")
    return frame.sort_values(["depth_from_m", "tray_id"]).reset_index(drop=True)


def load_sample_groups(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"hole_id": str, "tray_id": str, "mineral_group": str})
    _require_columns(frame, SAMPLE_COLUMNS, "Sample-group table")
    if "confidence" in frame.columns:
        raise ValueError("Sample-group table must not contain inferred confidence")
    frame["tray_id"] = frame["tray_id"].str.zfill(4)
    frame["depth_m"] = pd.to_numeric(frame["depth_m"], errors="raise")
    return frame


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tray_record(trays: pd.DataFrame, tray_id: str) -> pd.Series:
    normalized = str(tray_id).zfill(4)
    rows = trays.loc[trays["tray_id"] == normalized]
    if rows.empty:
        raise KeyError(f"Unknown tray: {normalized}")
    return rows.iloc[0]


def tray_bins(depth_bins: pd.DataFrame, tray_id: str) -> pd.DataFrame:
    normalized = str(tray_id).zfill(4)
    rows = depth_bins.loc[depth_bins["tray_id"] == normalized].copy()
    if rows.empty:
        raise KeyError(f"No depth bins for tray: {normalized}")
    return rows.sort_values("depth_from_m")


def summarize_tray(
    trays: pd.DataFrame, samples: pd.DataFrame, depth_bins: pd.DataFrame, tray_id: str
) -> dict[str, Any]:
    tray = tray_record(trays, tray_id)
    tray_samples = samples.loc[samples["tray_id"] == str(tray_id).zfill(4)]
    counts = tray_samples["mineral_group"].value_counts()
    top_group = str(counts.index[0])
    top_share = float(counts.iloc[0] / len(tray_samples) * 100)
    return {
        "tray_id": str(tray["tray_id"]),
        "depth_from_m": float(tray["depth_from_m"]),
        "depth_to_m": float(tray["depth_to_m"]),
        "sample_count": int(tray["sample_count"]),
        "bin_count": int((depth_bins["tray_id"] == str(tray_id).zfill(4)).sum()),
        "top_group": top_group,
        "top_group_share_pct": top_share,
        "image_status": str(tray["image_status"]),
    }
