from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etl"))

from section_minerals import derive_section_minerals, normalise_orientation  # noqa: E402


def test_orientation_normalisation() -> None:
    assert normalise_orientation("90", "-60") == (90.0, -60.0, "reported")
    assert normalise_orientation("0", "-60") == (0.0, -60.0, "reported")
    assert normalise_orientation("0", "0") == (None, None, "source_zero_placeholder")
    assert normalise_orientation("", "-60") == (None, None, "missing")
    assert normalise_orientation("north", "-60") == (None, None, "invalid")
    assert normalise_orientation("360", "-60") == (None, None, "invalid")
    assert normalise_orientation("90", "-91") == (None, None, "invalid")


def test_section_mineral_aggregation(tmp_path) -> None:
    storage_key = "holes/H001/scalars/values.parquet"
    path = tmp_path / storage_key
    path.parent.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "dataset_id": ["D1"] * 8,
                "sample_index": list(range(8)),
                "mineral": [
                    "Chlorite-FeMg", "Muscovite", "Chlorite-FeMg", "Chlorite-FeMg",
                    "null", "Aspectral", None, "",
                ],
            }
        ),
        path,
    )
    sections = [
        {"dataset_id": "D1", "section_index": 0, "sample_index_from": 0, "sample_index_to": 3},
        {"dataset_id": "D1", "section_index": 1, "sample_index_from": 4, "sample_index_to": 7},
        {"dataset_id": "D2", "section_index": 0, "sample_index_from": 0, "sample_index_to": 1},
    ]
    sources = [
        {
            "dataset_id": "D1",
            "source_log_id": "L1",
            "source_log_name": "Min1 sTSAS",
            "source_status": "complete",
            "source_algorithm_id": "108",
            "physical_column": "mineral",
            "physical_storage_key": storage_key,
        }
    ]

    rows = derive_section_minerals(tmp_path, sections, sources)
    classified, unclassified, unavailable = rows
    assert classified["primary_raw"] == "Chlorite-FeMg"
    assert classified["primary_fraction"] == 0.75
    assert classified["secondary_raw"] == "Muscovite"
    assert classified["display_group"] == "Chlorite"
    assert classified["display_color"] == "#2f9e8f"
    assert classified["confidence"] == 0.75
    assert classified["quality"] == "ok"
    assert unclassified["quality"] == "unclassified"
    assert unclassified["classified_sample_count"] == 0
    assert unavailable["quality"] == "source_unavailable"
    assert unavailable["source_log_id"] is None
