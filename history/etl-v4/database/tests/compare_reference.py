"""Restore an explicitly selected old backup and compare all business content by source keys."""

from pathlib import Path
import hashlib
import importlib
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pyarrow.parquet as pq
from PIL import Image
from _db_common import ETL, PG_BIN, config, connection
from _db_files import sha
from _run_reports import main_guard, report
from _settings import StepParser
from _settings import configure
from _trial_support import create_trial, drop_trial


def require(condition, message):
    if not condition:
        raise ValueError(message)


def release_datasets(conn, release=None):
    if release is None:
        release = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()[
            "release_id"
        ]
    rows = conn.execute(
        """SELECT b.source_hole_id,d.source_dataset_id,r.id revision,a.id axis,
        a.sample_count,r.source_dataset_name FROM core.release_dataset rd
        JOIN core.dataset d ON d.id=rd.dataset_id JOIN core.dataset_revision r ON r.id=rd.dataset_revision_id
        JOIN core.borehole b ON b.id=d.borehole_id JOIN core.sample_axis a ON a.dataset_revision_id=r.id
        WHERE rd.release_id=%s""",
        (release,),
    ).fetchall()
    return str(release), {(r["source_hole_id"], r["source_dataset_id"]): r for r in rows}


def query_hash(conn, query, parameters):
    """Deterministic row-by-row COPY digests include nulls and every sample, without comparing internal UUIDs."""
    checksum = hashlib.sha256()
    with conn.cursor().copy("COPY (" + query + ") TO STDOUT", parameters) as stream:
        for block in stream:
            checksum.update(block)
    return checksum.hexdigest()


QUERIES = {
    "samples": (
        """SELECT s.sample_no,s.md_m,t.ordinal,t.source_label,c.ordinal,c.source_label,
        s.tray_sample_no,s.section_sample_no,s.section_distance_mm
        FROM core.scan_sample s JOIN core.core_interval t ON t.id=s.tray_interval_id
        JOIN core.core_interval c ON c.id=s.section_interval_id WHERE s.axis_id=%s ORDER BY s.sample_no""",
        "axis",
    ),
    "intervals": (
        """SELECT c.interval_kind,c.ordinal,c.source_label,p.ordinal,c.sample_no_from,c.sample_no_to,
        c.observed_depth_min_m,c.observed_depth_max_m,c.source_log_id,c.source_data_row,c.source_interval_convention
        FROM core.core_interval c LEFT JOIN core.core_interval p ON p.id=c.parent_interval_id
        WHERE c.axis_id=%s ORDER BY c.interval_kind,c.ordinal""",
        "axis",
    ),
    "logs": (
        """SELECT l.source_log_id,(to_jsonb(l)-ARRAY['id','dataset_revision_id','spectral_stream_id',
        'interpretation_set_id','normalized_metadata']::text[])::text,
        (to_jsonb(s)-ARRAY['id','dataset_revision_id','normalized_metadata']::text[])::text,
        (to_jsonb(i)-ARRAY['id','dataset_revision_id','normalized_metadata']::text[])::text
        FROM core.scan_log l LEFT JOIN core.spectral_stream s ON s.id=l.spectral_stream_id
        LEFT JOIN core.interpretation_set i ON i.id=l.interpretation_set_id
        WHERE l.dataset_revision_id=%s ORDER BY l.log_kind,l.source_log_id""",
        "revision",
    ),
    "image_associations": (
        """SELECT l.source_log_id,f.image_ordinal,r.region_ordinal,r.x_px,r.y_px,r.width_px,r.height_px,
        c.ordinal,m.sample_no_from,m.sample_no_to,m.mapping_level,m.mapping_status,m.mapping_method,
        m.source_depth_direction,m.direction_status,m.indicator_method,m.indicator_version,m.indicator_status,
        m.indicator_parameters::text,m.anchor_points::text,m.error_px,m.error_depth_m,
        a.sha256,a.provenance->>'pixel_sha256',a.provenance->'recipe'
        FROM core.image_region r JOIN core.image_frame f ON f.id=r.image_frame_id
        JOIN core.scan_log l ON l.id=f.log_id JOIN core.image_sample_mapping m ON m.image_region_id=r.id
        JOIN core.core_interval c ON c.id=m.section_interval_id JOIN core.image_region_asset ra ON ra.region_id=r.id
        JOIN core.asset a ON a.id=ra.asset_id WHERE r.dataset_revision_id=%s
        ORDER BY l.source_log_id,f.image_ordinal,r.region_ordinal""",
        "revision",
    ),
    "spectral_layout": (
        """SELECT l.source_log_id,(to_jsonb(a)-ARRAY['id','dataset_revision_id','log_id','asset_id',
        'spectral_stream_id','evidence_asset_id','evidence']::text[])::text,
        (to_jsonb(m)-ARRAY['id','dataset_revision_id','spectral_array_id','axis_id','evidence_asset_id','basis']::text[])::text,
        (to_jsonb(b)-'spectral_array_id')::text FROM core.spectral_array a JOIN core.scan_log l ON l.id=a.log_id
        JOIN core.spectral_sample_map m ON m.spectral_array_id=a.id JOIN core.spectral_block b ON b.spectral_array_id=a.id
        WHERE a.dataset_revision_id=%s ORDER BY l.source_log_id,b.block_no""",
        "revision",
    ),
}


def assets(conn, revision):
    rows = conn.execute(
        """SELECT a.*,l.object_key FROM core.asset a JOIN core.asset_location l ON l.asset_id=a.id
        WHERE a.dataset_revision_id=%s AND l.backend='local' AND a.representation IN ('raw','canonical')""",
        (revision,),
    ).fetchall()
    return {(a["representation"], a["logical_path"]): a for a in rows}


def compare_assets(old, new):
    for asset in list(old.values()) + list(new.values()):
        if asset["asset_kind"] == "core_row_image":
            path = ETL / asset["object_key"]
            require(sha(path) == asset["sha256"], "Crop file bytes changed")
            with Image.open(path) as picture:
                pixel_hash = hashlib.sha256(picture.convert("RGB").tobytes()).hexdigest()
            require(pixel_hash == asset["provenance"]["pixel_sha256"], "Crop pixels changed")
    # Row-image paths include new revision UUIDs, so pair them by pixel digest; pair other assets by logical source path.
    old_crops = sorted(
        a["provenance"]["pixel_sha256"] for a in old.values() if a["asset_kind"] == "core_row_image"
    )
    new_crops = sorted(
        a["provenance"]["pixel_sha256"] for a in new.values() if a["asset_kind"] == "core_row_image"
    )
    require(old_crops == new_crops, "Crop pixel content differs")
    old = {key: a for key, a in old.items() if a["asset_kind"] != "core_row_image"}
    new = {key: a for key, a in new.items() if a["asset_kind"] != "core_row_image"}
    require(old.keys() == new.keys(), "Source/canonical asset membership differs")
    totals = {"raw_files": 0, "parquet_files": 0, "parquet_rows": 0, "crop_images": len(new_crops)}
    for key, before in old.items():
        after = new[key]
        first, second = ETL / before["object_key"], ETL / after["object_key"]
        require(
            sha(first) == before["sha256"] and sha(second) == after["sha256"],
            "Registered file bytes changed",
        )
        if first.suffix == ".parquet":
            with pq.ParquetFile(first) as left, pq.ParquetFile(second) as right:
                require(
                    left.metadata.num_rows == right.metadata.num_rows, "Parquet row count differs"
                )
                for a, b in zip(
                    left.iter_batches(batch_size=32768),
                    right.iter_batches(batch_size=32768),
                    strict=True,
                ):
                    require(
                        a.equals(b, check_metadata=False),
                        "Parquet business values differ: " + str(key),
                    )
                totals["parquet_rows"] += left.metadata.num_rows
            totals["parquet_files"] += 1
        else:
            require(
                before["sha256"] == after["sha256"], "Original source bytes differ: " + str(key)
            )
            totals["raw_files"] += 1
    return totals


def compare(conn, reference, release=None, reference_release=None):
    release, current = release_datasets(conn, release)
    old_release, old = release_datasets(reference, reference_release)
    require(current.keys() == old.keys(), "Source dataset membership differs")
    results = []
    for key in sorted(current):
        before, after = old[key], current[key]
        print("Compare full dataset " + after["source_dataset_name"], flush=True)
        hashes = {}
        for name, (query, field) in QUERIES.items():
            a = query_hash(reference, query, (before[field],))
            b = query_hash(conn, query, (after[field],))
            require(a == b, f"{key}: {name} differs")
            hashes[name] = b
        files = compare_assets(
            assets(reference, before["revision"]), assets(conn, after["revision"])
        )
        results.append(
            {"source_key": key, "sample_count": after["sample_count"], "hashes": hashes, **files}
        )
    overview = """SELECT b.source_hole_id,d.source_dataset_id,s.sample_no,s.md_m
        FROM core.v_borehole_composite_samples s JOIN core.borehole b ON b.id=s.borehole_id
        JOIN core.dataset d ON d.id=s.dataset_id WHERE s.release_id=%s
        ORDER BY b.source_hole_id,d.source_dataset_id,s.sample_no"""
    a = query_hash(reference, overview, (old_release,))
    b = query_hash(conn, overview, (release,))
    require(a == b, "3D overview values/selection differ")
    count = conn.execute(
        "SELECT count(*) n FROM core.v_borehole_composite_samples WHERE release_id=%s", (release,)
    ).fetchone()["n"]
    return {
        "status": "passed",
        "release_id": release,
        "reference_release_id": old_release,
        "dataset_count": len(results),
        "full_samples": sum(r["sample_count"] for r in results),
        "overview_samples": count,
        "overview_sha256": b,
        "datasets": results,
    }


def main():
    parser = StepParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    configure(args)
    require(sha(args.dump) == args.sha256, "Reference backup checksum differs")
    settings = config()
    env = os.environ.copy()
    env.update(
        PGHOST=settings["host"],
        PGPORT=str(settings["port"]),
        PGUSER=settings["roles"]["owner"]["user"],
        PGPASSWORD=settings["roles"]["owner"]["password"],
    )
    restore = importlib.import_module("36_backup_multi_dataset_database")
    trial = create_trial("restore")
    try:
        print("Restore reference backup in isolated database", flush=True)
        restore.backup_command(
            [
                PG_BIN / "pg_restore.exe",
                "--no-owner",
                "--exit-on-error",
                "--dbname",
                trial,
                args.dump,
            ],
            env,
        )
        with connection("reader") as current, connection("reader", dbname=trial) as reference:
            result = compare(current, reference)
        report(
            "refactor_reference_comparison.json", {**result, "reference_backup_sha256": args.sha256}
        )
        print("All source keys, samples, results, media and 3D selections match.", flush=True)
    finally:
        drop_trial(trial)


if __name__ == "__main__":
    main_guard(main)
