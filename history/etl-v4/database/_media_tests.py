"""Independently test media constraints using synthetic data that can be rolled back."""

import numpy as np
import psycopg
from PIL import Image
from _db_common import ETL, insert, pick, uid
from _db_files import digest, sha
from _settings import settings
from _media_common import DIRECTION, INDICATOR, marker, require, units
from _media_reader import read_sample
from _legacy_media_import import clone_revision


def rejected(conn, name, fn, results):
    try:
        with conn.transaction():
            fn()
            conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    except (psycopg.Error, ValueError) as exc:
        results.append({"case": name, "rejected": True, "error": type(exc).__name__})
        return
    raise ValueError("Invalid case accepted: " + name)


def fixture(conn, label, release, base, work=None):
    """Create distinct datasets with the same borehole, labels, sample numbers, and depths to detect cross-dataset associations."""
    work = settings.media_work_dir if work is None else work

    def ident(kind):
        return uid("media-synthetic", label, kind)

    dataset = ident("dataset")
    rev = ident("revision")
    axis = ident("axis")
    tray = ident("tray")
    sections = [ident("section0"), ident("section1")]
    insert(
        conn,
        "dataset",
        {
            "id": dataset,
            "borehole_id": base["borehole_id"],
            "source_dataset_id": "synthetic-" + label,
        },
    )
    dr = {k: v for k, v in base.items()}
    dr.update(
        id=rev,
        dataset_id=dataset,
        source_dataset_name="synthetic",
        source_snapshot_id=ident("snapshot"),
        pipeline_id="synthetic-test",
        input_digest="synthetic-test",
        normalized_metadata={"synthetic": True},
    )
    insert(conn, "dataset_revision", dr)
    insert(
        conn,
        "sample_axis",
        {
            "id": axis,
            "dataset_revision_id": rev,
            "sample_count": 4,
            "depth_min_m": 1.5,
            "depth_max_m": 2.5,
            "alignment_evidence": {"synthetic": True},
        },
    )
    common = {
        "axis_id": axis,
        "observed_depth_min_m": 1.5,
        "observed_depth_max_m": 2.5,
        "source_log_id": "synthetic",
        "source_data_row": 0,
        "source_interval_convention": "closed",
    }
    insert(
        conn,
        "core_interval",
        {
            **common,
            "id": tray,
            "interval_kind": "tray",
            "ordinal": 0,
            "source_label": "0001",
            "parent_interval_id": None,
            "sample_no_from": 0,
            "sample_no_to": 3,
        },
    )
    for i, section in enumerate(sections):
        insert(
            conn,
            "core_interval",
            {
                **common,
                "id": section,
                "interval_kind": "section",
                "ordinal": i,
                "source_label": str(i + 1),
                "parent_interval_id": tray,
                "sample_no_from": i * 2,
                "sample_no_to": i * 2 + 1,
            },
        )
    for s, md in enumerate([1.5, 1.5, 2.0, 2.5]):
        insert(
            conn,
            "scan_sample",
            {
                "axis_id": axis,
                "sample_no": s,
                "md_m": md,
                "tray_interval_id": tray,
                "section_interval_id": sections[s // 2],
                "tray_sample_no": s + 1,
                "section_sample_no": s % 2 + 1,
                "section_distance_mm": None,
            },
        )

    def asset(kind, data, media="application/octet-stream"):
        path = work / "synthetic" / label / (kind + ".bin")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        aid = ident(kind)
        checksum = sha(path)
        insert(
            conn,
            "asset",
            {
                "id": aid,
                "dataset_revision_id": rev,
                "asset_kind": kind,
                "representation": "raw",
                "logical_path": kind + ".bin",
                "sha256": checksum,
                "byte_size": len(data),
                "media_type": media,
                "semantic_status": "synthetic_test",
                "provenance": {"synthetic": True},
            },
        )
        insert(
            conn,
            "asset_location",
            {
                "id": ident(kind + "location"),
                "asset_id": aid,
                "backend": "local",
                "root_key": "etl4",
                "object_key": path.relative_to(ETL).as_posix(),
                "access_status": "verified_local",
                "verified_sha256": checksum,
            },
        )
        return aid, checksum

    evidence, evhash = asset("evidence", b"{}", "application/json")
    stream = ident("stream")
    insert(
        conn,
        "spectral_stream",
        {
            "id": stream,
            "dataset_revision_id": rev,
            "region_code": "SYNTHETIC",
            "wavelength_unit": "nm",
            "wavelength_count": 2,
            "wavelengths": [400.0, 500.0],
            "classification_basis": "synthetic",
        },
    )
    logs = []
    for i, kind in enumerate(["image", "image", "spectral"]):
        log = ident("log" + str(i))
        logs.append(log)
        insert(
            conn,
            "scan_log",
            {
                "id": log,
                "dataset_revision_id": rev,
                "source_log_id": "same-source-label-" + str(i),
                "source_log_name": "same log name",
                "log_kind": kind,
                "spectral_stream_id": stream if kind == "spectral" else None,
                "availability_status": "payload_present",
                "definition_status": "synthetic",
                "source_metadata_file": "synthetic",
                "normalized_metadata": {"synthetic": True},
                "per_sample_publication_allowed": kind == "spectral",
            },
        )
        insert(
            conn,
            "log_axis_binding",
            {
                "log_id": log,
                "dataset_revision_id": rev,
                "axis_id": axis if kind == "spectral" else None,
                "status": "verified" if kind == "spectral" else "not_a_dense_axis",
                "basis": "synthetic",
            },
        )
    from io import BytesIO

    im = Image.new("RGB", (4, 4), (10 if label == "A" else 90, 20, 30))
    buf = BytesIO()
    im.save(buf, format="PNG")
    photo, photo_hash = asset("same-photo-name", buf.getvalue(), "image/png")
    frames = []
    regions = []
    rowassets = []
    for j in range(2):
        log = logs[j]
        frame = ident("frame" + str(j))
        frames.append(frame)
        insert(
            conn,
            "log_asset",
            {"log_id": log, "asset_id": photo, "dataset_revision_id": rev, "role": "raw_source"},
        )
        insert(
            conn,
            "image_frame",
            {
                "id": frame,
                "dataset_revision_id": rev,
                "axis_id": axis,
                "core_interval_id": tray,
                "log_id": log,
                "asset_id": photo,
                "image_kind": "tray_thumbnail",
                "image_ordinal": 0,
                "source_tray_label": "0001",
                "width_px": 4,
                "height_px": 4,
                "depth_from_m": 1.5,
                "depth_to_m": 2.5,
                "depth_from_difference_m": 0.0,
                "depth_to_difference_m": 0.0,
                "depth_comparison_tolerance_m": 0.0,
                "association_basis": "synthetic",
            },
        )
        for i in range(2):
            region = ident(f"region{j}_{i}")
            regions.append(region)
            insert(
                conn,
                "image_region",
                {
                    "id": region,
                    "dataset_revision_id": rev,
                    "image_frame_id": frame,
                    "region_kind": "core_row",
                    "region_ordinal": i,
                    "x_px": 0,
                    "y_px": i * 2,
                    "width_px": 4,
                    "height_px": 2,
                    "coordinate_basis": "native",
                    "region_status": "reviewed",
                    "detection_method": "synthetic",
                    "review_basis": "synthetic",
                    "evidence_asset_id": evidence,
                },
            )
            # Deliberately omit the sample mapping for row two of the second log.
            if j == 1 and i == 1:
                continue
            insert(
                conn,
                "image_sample_mapping",
                {
                    "id": ident(f"map{j}_{i}"),
                    "dataset_revision_id": rev,
                    "image_region_id": region,
                    "axis_id": axis,
                    "section_interval_id": sections[i],
                    "sample_no_from": i * 2,
                    "sample_no_to": i * 2 + 1,
                    **pick(
                        DIRECTION, "source_depth_direction", "direction_status", "direction_basis"
                    ),
                    "direction_evidence_asset_id": evidence,
                    "mapping_level": "section_interval",
                    "mapping_status": "metadata_associated",
                    "mapping_method": "synthetic",
                    "indicator_method": "sample_index_linear",
                    "indicator_version": 1,
                    "indicator_status": "approximate",
                    "indicator_parameters": INDICATOR,
                    "evidence_asset_id": evidence,
                },
            )
            # Deliberately omit the crop file for row two of the first log.
            if i == 1:
                continue
            buf = BytesIO()
            im.crop((0, 0, 4, 2)).save(buf, format="PNG")
            crop, crop_hash = asset("row" + str(j), buf.getvalue(), "image/png")
            rowassets.append(crop)
            insert(
                conn,
                "log_asset",
                {
                    "log_id": log,
                    "asset_id": crop,
                    "dataset_revision_id": rev,
                    "role": "derived_core_row",
                },
            )
            insert(
                conn,
                "image_region_asset",
                {
                    "region_id": region,
                    "dataset_revision_id": rev,
                    "asset_id": crop,
                    "log_id": log,
                    "representation_kind": "native_lossless_png",
                    "width_px": 4,
                    "height_px": 2,
                    "recipe_version": 1,
                    "transform": {"crop_box_half_open": [0, 0, 4, 2], "source_sha256": photo_hash},
                },
            )
    matrix = np.arange(8, dtype="<f4").reshape(4, 2) + (0 if label == "A" else 100)
    binary, checksum = asset("spectra", matrix.tobytes())
    array = ident("array")
    insert(
        conn,
        "log_asset",
        {"log_id": logs[2], "asset_id": binary, "dataset_revision_id": rev, "role": "raw_source"},
    )
    insert(
        conn,
        "spectral_array",
        {
            "id": array,
            "dataset_revision_id": rev,
            "log_id": logs[2],
            "asset_id": binary,
            "spectral_stream_id": stream,
            "sample_count": 4,
            "channel_count": 2,
            "dtype_code": "<f4",
            "matrix_order": "C",
            "data_offset_bytes": 0,
            "sample_stride_bytes": 8,
            "channel_stride_bytes": 4,
            "layout_status": "verified_sample_major",
            "scaling_applied": False,
            "evidence_asset_id": evidence,
            "evidence": {"synthetic": True},
        },
    )
    insert(
        conn,
        "spectral_sample_map",
        {
            "id": ident("specmap"),
            "dataset_revision_id": rev,
            "spectral_array_id": array,
            "axis_id": axis,
            "source_row_from": 0,
            "source_row_to": 3,
            "sample_no_from": 0,
            "sample_no_to": 3,
            "mapping_kind": "identity_range",
            "binding_status": "verified",
            "evidence_asset_id": evidence,
            "basis": "synthetic",
        },
    )
    insert(
        conn,
        "spectral_block",
        {
            "spectral_array_id": array,
            "block_no": 0,
            "source_row_from": 0,
            "source_row_to_exclusive": 4,
            "byte_offset": 0,
            "byte_length": 32,
            "sha256": checksum,
        },
    )
    insert(
        conn,
        "release_dataset",
        {"release_id": release, "dataset_id": dataset, "dataset_revision_id": rev},
    )
    return {
        "dataset_id": dataset,
        "revision": rev,
        "axis": axis,
        "frames": frames,
        "regions": regions,
        "logs": logs,
        "rowassets": rowassets,
        "array": array,
    }


def behavior_checks(conn, source_units=None, work=None):
    work = settings.media_work_dir if work is None else work
    source_units = units() if source_units is None else source_units
    results = []
    require(
        marker(0, 0, 0, 1)["x_px"] == 0 and marker(9, 9, 9, 11)["x_px"] == 5,
        "Singleton indicator failed",
    )
    for bad in [-1, 10]:
        try:
            marker(bad, 0, 9, 400)
        except ValueError:
            pass
        else:
            raise ValueError("Invalid marker was clamped")
    with conn.transaction(force_rollback=True):
        base = conn.execute(
            "SELECT * FROM core.dataset_revision WHERE id=%s",
            (source_units[0]["source_revision_id"],),
        ).fetchone()
        release = uid("synthetic-media-release")
        insert(
            conn,
            "data_release",
            {
                "id": release,
                "manifest_sha256": digest("synthetic-media-release"),
                "manifest": {"synthetic": True},
            },
        )
        a = fixture(conn, "A", release, base, work)
        b = fixture(conn, "B", release, base, work)
        read_a = read_sample(
            conn, release, a["dataset_id"], a["axis"], 0, [a["logs"][2]], a["logs"][0]
        )
        read_b = read_sample(
            conn, release, b["dataset_id"], b["axis"], 0, [b["logs"][2]], b["logs"][0]
        )
        require(
            read_a["md_m"] == read_b["md_m"]
            and read_a["results"][0]["spectra"] != read_b["results"][0]["spectra"],
            "Synthetic datasets were conflated",
        )
        require(
            read_a["images"][0]["image_asset_id"] != read_b["images"][0]["image_asset_id"],
            "Images crossed datasets",
        )
        duplicate = read_sample(conn, release, a["dataset_id"], a["axis"], 1, [], a["logs"][0])
        require(
            duplicate["md_m"] == read_a["md_m"] and duplicate["images"][0]["indicator"]["p"] == 1,
            "Duplicate depth merged",
        )
        missing = read_sample(
            conn, release, a["dataset_id"], a["axis"], 2, [a["logs"][2]], a["logs"][0]
        )
        require(
            missing["image_status"] == "image_unavailable"
            and missing["images"][0]["indicator"] is None
            and missing["results"][0]["status"] == "available",
            "Missing image lost results or retained marker",
        )
        candidates = read_sample(conn, release, a["dataset_id"], a["axis"], 0, [])
        require(
            candidates["image_status"] == "selection_required" and len(candidates["images"]) == 2,
            "Multiple logs were silently selected",
        )
        unmapped = read_sample(conn, release, a["dataset_id"], a["axis"], 2, [], a["logs"][1])
        require(not unmapped["images"], "Unmapped row fabricated a sample indicator")
        results.extend(
            {"case": name, "passed": True}
            for name in [
                "same_hole_two_datasets_same_labels",
                "different_spectra_and_images",
                "duplicate_depth_distinct_samples",
                "missing_image_preserves_results",
                "multiple_image_logs_require_selection",
                "unmapped_region_no_indicator",
                "single_sample_single_pixel",
            ]
        )
        rejected(
            conn,
            "cross_dataset_selection",
            lambda: read_sample(conn, release, a["dataset_id"], b["axis"], 0, []),
            results,
        )
        rejected(
            conn,
            "cross_dataset_result_log",
            lambda: read_sample(conn, release, a["dataset_id"], a["axis"], 0, [b["logs"][2]]),
            results,
        )
        rejected(
            conn,
            "invalid_sample_no",
            lambda: read_sample(conn, release, a["dataset_id"], a["axis"], 4, []),
            results,
        )
        region = conn.execute(
            "SELECT * FROM core.image_region WHERE id=%s", (a["regions"][0],)
        ).fetchone()
        rejected(
            conn,
            "cross_revision_frame",
            lambda: insert(
                conn,
                "image_region",
                {
                    **region,
                    "id": uid("badregion1"),
                    "image_frame_id": b["frames"][0],
                    "region_ordinal": 3,
                },
            ),
            results,
        )
        rejected(
            conn,
            "overlapping_regions",
            lambda: insert(
                conn, "image_region", {**region, "id": uid("badregion2"), "region_ordinal": 3}
            ),
            results,
        )
        rejected(
            conn,
            "out_of_bounds_crop",
            lambda: insert(
                conn,
                "image_region",
                {**region, "id": uid("badregion3"), "region_ordinal": 3, "y_px": 4},
            ),
            results,
        )
        mapping = conn.execute(
            "SELECT * FROM core.image_sample_mapping WHERE image_region_id=%s", (a["regions"][0],)
        ).fetchone()
        rejected(
            conn,
            "cross_revision_mapping",
            lambda: insert(
                conn,
                "image_sample_mapping",
                {**mapping, "id": uid("badmap1"), "image_region_id": b["regions"][0]},
            ),
            results,
        )
        rejected(
            conn,
            "split_or_discontinuous_index_mapping",
            lambda: insert(
                conn, "image_sample_mapping", {**mapping, "id": uid("badmap2"), "sample_no_from": 1}
            ),
            results,
        )
        ra = conn.execute(
            "SELECT * FROM core.image_region_asset WHERE region_id=%s", (a["regions"][0],)
        ).fetchone()
        rejected(
            conn,
            "wrong_image_log",
            lambda: insert(conn, "image_region_asset", {**ra, "region_id": a["regions"][2]}),
            results,
        )
        rejected(
            conn,
            "immutable_media",
            lambda: conn.execute(
                "UPDATE core.image_region SET width_px=width_px WHERE id=%s", (a["regions"][0],)
            ),
            results,
        )
        block = conn.execute(
            "SELECT * FROM core.spectral_block WHERE spectral_array_id=%s", (a["array"],)
        ).fetchone()
        rejected(
            conn,
            "invalid_spectral_byte_offset",
            lambda: insert(conn, "spectral_block", {**block, "block_no": 1, "byte_offset": 4}),
            results,
        )
        # Interrupt after copying samples and verify rollback of the entire new revision.
        u = source_units[0]
        new = uid("synthetic-interruption-revision")
        rejected(
            conn,
            "interrupted_revision_import",
            lambda: clone_revision(conn, u, new, "synthetic", "synthetic", {}, True),
            results,
        )
        require(
            not conn.execute("SELECT 1 FROM core.dataset_revision WHERE id=%s", (new,)).fetchone(),
            "Interrupted import left a partial revision",
        )
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    require(
        not conn.execute(
            "SELECT 1 FROM core.data_release WHERE id=%s", (uid("synthetic-media-release"),)
        ).fetchone(),
        "Synthetic fixture persisted",
    )
    return results
