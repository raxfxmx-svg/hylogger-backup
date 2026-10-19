import json
from pathlib import Path

import pandas as pd

import app as explorer


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_metadata_records_missing_fields_without_inference():
    metadata = json.loads((DATA / "05GJD001_scan_metadata.json").read_text(encoding="utf-8"))
    assert metadata["hole_ids"] == ["05GJD001"]
    assert metadata["sample_count"] == 25938
    assert metadata["tray_count"] == 33
    assert metadata["nir_channels"] == 531
    assert metadata["tir_channels"] == 341
    assert metadata["coordinate_status"] == "not_supplied"
    assert metadata["confidence_status"] == "not_supplied_and_not_inferred"


def test_all_tray_images_have_small_on_demand_assets():
    trays = pd.read_csv(DATA / "05GJD001_trays.csv", dtype={"tray_id": str}, keep_default_na=False)
    assert len(trays) == 33
    assert set(trays["image_status"]) == {"available"}
    for relative_path in trays["image_relpath"]:
        asset = ROOT / "assets" / relative_path
        assert asset.is_file()
        assert 10_000 < asset.stat().st_size < 1_000_000


def test_whole_hole_summary_accounts_for_every_sample():
    summary = pd.read_csv(DATA / "05GJD001_scan_summary.csv")
    assert summary["sample_count"].sum() == 25938
    assert {"NO RESULT", "INVALID", "CHLORITE", "CARBONATE"}.issubset(summary["mineral_group"])


def test_missing_image_record_renders_an_explicit_placeholder(monkeypatch):
    trays = explorer.TRAYS.copy()
    mask = trays["tray_id"] == "0001"
    trays.loc[mask, "image_status"] = "missing"
    trays.loc[mask, "image_relpath"] = ""
    monkeypatch.setattr(explorer, "TRAYS", trays)
    panel = explorer.core_image_panel("0001")
    assert "IMAGE NOT AVAILABLE" in str(panel)
    assert "no replacement image is inferred" in str(panel)
