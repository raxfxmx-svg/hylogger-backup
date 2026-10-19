"""Read complete datasets and confirmed 3D display composites."""

from _multi_common import require


def read_borehole_layout(conn, release_id, source_hole_id):
    composite = conn.execute(
        """SELECT c.*,b.source_hole_id FROM core.borehole_composite c
      JOIN core.borehole b ON b.id=c.borehole_id WHERE c.release_id=%s AND b.source_hole_id=%s""",
        (release_id, source_hole_id),
    ).fetchone()
    require(composite, "No verified composition for the requested release/hole")
    datasets = conn.execute(
        """SELECT * FROM core.v_borehole_dataset_full
      WHERE composite_id=%s ORDER BY sequence_no""",
        (composite["id"],),
    ).fetchall()
    selected = conn.execute(
        """SELECT p.*,min(s.md_m) first_selected_md_m,max(s.md_m) last_selected_md_m,count(s.sample_no) selected_sample_count
      FROM core.borehole_composite_part p LEFT JOIN core.scan_sample s ON s.axis_id=p.axis_id
      AND s.sample_no BETWEEN p.sample_no_from AND p.sample_no_to WHERE p.composite_id=%s
      GROUP BY p.composite_id,p.sequence_no ORDER BY p.sequence_no""",
        (composite["id"],),
    ).fetchall()
    low = min(d["depth_min_m"] for d in datasets)
    high = max(d["depth_max_m"] for d in datasets)
    for d in datasets:
        d["depth_offset_from_common_origin_m"] = d["depth_min_m"] - low
        d["image_logs"] = conn.execute(
            """SELECT id,source_log_id,source_log_name,availability_status
          FROM core.scan_log WHERE dataset_revision_id=%s AND log_kind='image' ORDER BY source_log_name,id""",
            (d["dataset_revision_id"],),
        ).fetchall()
    return {
        "composite": composite,
        "datasets_2d_full": datasets,
        "parts_3d_selected": selected,
        "depth_reference": {
            "kind": "source_measured_depth",
            "unit": "m",
            "common_min_m": low,
            "common_max_m": high,
        },
        "sample_identity": ["dataset_revision_id", "axis_id", "sample_no"],
        "layout_note": "Use one common depth scale for all 2D columns; each dataset keeps its own image log and sample index. Width and column placement belong to the frontend.",
    }
