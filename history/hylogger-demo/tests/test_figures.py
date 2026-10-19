from pathlib import Path

import pytest

from src.data import load_depth_bins
from src.figures import build_tray_profile, group_style


ROOT = Path(__file__).resolve().parents[1]
BINS = load_depth_bins(ROOT / "data" / "05GJD001_depth_bins.csv")


def test_tray_profile_uses_absolute_recorded_depth():
    figure = build_tray_profile(BINS, "0001")
    assert figure.layout.yaxis.range[0] == pytest.approx(154.679159, abs=1e-6)
    assert figure.layout.yaxis.range[1] == pytest.approx(150.0, abs=1e-6)
    assert sum(len(trace.y) for trace in figure.data) == len(BINS.loc[BINS["tray_id"] == "0001"])


def test_profile_hover_discloses_aggregation_not_confidence():
    figure = build_tray_profile(BINS, "0001")
    templates = " ".join(str(trace.hovertemplate) for trace in figure.data)
    assert "Within-bin share" in templates
    assert "Source field" in templates
    assert "Confidence" not in templates


def test_non_results_have_distinct_patterns():
    assert group_style("NO RESULT")["pattern"] == "/"
    assert group_style("INVALID")["pattern"] == "x"
    assert group_style("CHLORITE")["pattern"] == ""
