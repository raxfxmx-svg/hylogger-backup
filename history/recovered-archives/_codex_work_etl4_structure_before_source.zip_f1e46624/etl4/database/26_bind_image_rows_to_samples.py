"""Link image rows to actual sample intervals and retain the approximate-position explanation."""

from _db_common import main_guard
from _media_common import DIRECTION, INDICATOR, require, save_stage, stage, units


def main():
    reviewed = stage(25)
    require(reviewed["status"] == "reviewed", "Image regions need recorded visual review")
    rows = []
    covered = {u["dataset_id"]: 0 for u in units()}
    for r in reviewed["rows"]:
        s = r["section"]
        a = s["sample_no_from"]
        b = s["sample_no_to"]
        require(
            s["axis_id"] == r["source_axis_id"]
            and s["parent_interval_id"] == r["core_interval_id"],
            "Wrong tray/axis",
        )
        covered[r["dataset_id"]] += b - a + 1
        rows.append(
            {
                **r,
                "sample_no_from": a,
                "sample_no_to": b,
                "mapping_level": "section_interval",
                "mapping_status": "metadata_associated",
                "mapping_method": "source_section_order_with_layout_template",
                **DIRECTION,
                "indicator_method": "sample_index_linear",
                "indicator_version": 1,
                "indicator_status": "approximate",
                "indicator_parameters": INDICATOR,
                "anchor_points": None,
                "error_px": None,
                "error_depth_m": None,
            }
        )
    for u in units():
        require(
            covered[u["dataset_id"]] == u["sample_count"],
            "Incomplete or repeated row sample coverage",
        )
    save_stage(
        26, {"status": "passed", "rows": rows, "sample_counts": covered, "direction": DIRECTION}
    )


if __name__ == "__main__":
    from _settings import StepParser

    StepParser().parse_args()
    main_guard(main)
