from pathlib import Path

import pandas as pd
import pytest

from src.data import load_depth_bins, load_holes, load_sample_groups, load_trays


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_only_supplied_hole_is_registered_and_coordinates_are_blank():
    holes = load_holes(DATA / "holes.csv")
    assert holes["hole_id"].tolist() == ["05GJD001"]
    assert holes["coordinate_status"].tolist() == ["not_supplied"]
    assert holes[["latitude", "longitude"]].isna().all().all()


def test_tray_0001_uses_recorded_absolute_depth():
    trays = load_trays(DATA / "05GJD001_trays.csv")
    first = trays.iloc[0]
    assert len(trays) == 33
    assert first["tray_id"] == "0001"
    assert float(first["depth_from_m"]) == pytest.approx(150.0, abs=1e-6)
    assert float(first["depth_to_m"]) == pytest.approx(154.679159, abs=1e-6)
    assert float(first["depth_from_m"]) != 0


def test_sample_export_matches_supplied_scan_depth_and_count():
    samples = load_sample_groups(DATA / "05GJD001_sample_groups.csv")
    assert len(samples) == 25938
    assert samples["hole_id"].unique().tolist() == ["05GJD001"]
    assert samples["depth_m"].min() == pytest.approx(150.0, abs=1e-6)
    assert samples["depth_m"].max() == pytest.approx(316.000009, abs=1e-6)
    assert not samples["hole_id"].str.contains("SYN", case=False).any()
    assert "confidence" not in samples.columns


def test_depth_bins_are_derived_from_all_samples_without_confidence():
    bins = load_depth_bins(DATA / "05GJD001_depth_bins.csv")
    assert bins["sample_count"].sum() == 25938
    assert bins["depth_from_m"].min() == pytest.approx(150.0, abs=1e-6)
    assert bins["depth_to_m"].max() == pytest.approx(316.000009, abs=1e-6)
    assert set(bins["algorithm_field"]) == {"Grp1 sTSAS"}
    assert "confidence" not in bins.columns
    assert bins["dominant_share_pct"].between(0, 100, inclusive="both").all()


def test_no_fabricated_hole_names_remain_in_active_csv_files():
    forbidden = {"Golden Mile North", "Boulder South", "SYN-KAL-02", "SYN-KAL-03"}
    csv_text = "\n".join(path.read_text(encoding="utf-8") for path in DATA.glob("*.csv"))
    assert not any(value in csv_text for value in forbidden)
