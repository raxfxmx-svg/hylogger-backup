"""Check media revisions against actual sources, then publish through the shared entry point."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time
import numpy as np
import pyarrow.parquet as pq
from _db_common import ETL, LOCK_KEY, assert_schema, connection, schema_hash
from _db_files import inside, read, sha, write
from _run_reports import main_guard, report
from _media_common import (
    decode,
    marker,
    media_code_hash,
    require,
    source_folder,
    source_path,
    stage,
)
from _media_reader import read_sample
from _settings import StepParser
from _settings import settings, configure
from _media_import import package_step, check_package, release_context


def verify_dataset(conn, u, new, release, dest):
    axis = new["axis_id"]
    old = u["source_axis_id"]
    rev = new["dataset_revision_id"]
    n = conn.execute(
        "SELECT count(*) n FROM core.scan_sample WHERE axis_id=%s", (axis,)
    ).fetchone()["n"]
    require(n == u["sample_count"], "Sample count differs")
    mismatch = conn.execute(
        """SELECT count(*) n FROM
      (SELECT * FROM core.scan_sample WHERE axis_id=%s) s FULL JOIN
      (SELECT * FROM core.scan_sample WHERE axis_id=%s) o ON s.sample_no=o.sample_no
      WHERE s.sample_no IS NULL OR o.sample_no IS NULL OR s.md_m IS DISTINCT FROM o.md_m OR
      s.tray_sample_no IS DISTINCT FROM o.tray_sample_no OR s.section_sample_no IS DISTINCT FROM o.section_sample_no OR
      s.section_distance_mm IS DISTINCT FROM o.section_distance_mm""",
        (axis, old),
    ).fetchone()["n"]
    require(mismatch == 0, "Source sample values changed")
    coverage = conn.execute(
        """SELECT count(*) n FROM core.scan_sample s WHERE s.axis_id=%s AND
      (SELECT count(*) FROM core.image_sample_mapping m WHERE m.axis_id=s.axis_id AND m.section_interval_id=s.section_interval_id
       AND s.sample_no BETWEEN m.sample_no_from AND m.sample_no_to)<>1""",
        (axis,),
    ).fetchone()["n"]
    require(coverage == 0, "A real sample does not have exactly one row mapping")
    mappings = conn.execute(
        """SELECT m.*,r.width_px FROM core.image_sample_mapping m JOIN core.image_region r ON r.id=m.image_region_id WHERE m.axis_id=%s""",
        (axis,),
    ).fetchall()
    for m in mappings:
        a = m["sample_no_from"]
        b = m["sample_no_to"]
        w = m["width_px"]
        for s in {a, b, (a + b) // 2}:
            out = marker(s, a, b, w)
            require(0 <= out["x_px"] <= w - 1, "Indicator out of bounds")
        require(
            m["indicator_status"] == "approximate"
            and m["error_px"] is None
            and m["error_depth_m"] is None,
            "False pixel calibration",
        )
    # Check the actual files for reused Parquet assets and newly created row images.
    rows = conn.execute(
        """SELECT a.*,l.object_key,l.verified_sha256 FROM core.asset a JOIN core.asset_location l ON l.asset_id=a.id
      WHERE a.dataset_revision_id=%s AND l.backend='local' """,
        (rev,),
    ).fetchall()
    for a in rows:
        p = inside(ETL, ETL / a["object_key"])
        require(p.stat().st_size == a["byte_size"] and sha(p) == a["sha256"], "Asset bytes differ")
    for r in [r for r in package_step(dest, 27)["rows"] if r["dataset_id"] == u["dataset_id"]]:
        im = decode(source_path(u, r["source_path"]))
        x, y, x2, y2 = r["recipe"]["crop_box_half_open"]
        linked = conn.execute(
            """SELECT a.sha256, loc.object_key, a.provenance, reg.id,
          frame.id frame_id, original.sha256 source_sha256, original.logical_path source_path
          FROM core.image_region reg JOIN core.image_region_asset link ON link.region_id=reg.id
          JOIN core.asset a ON a.id=link.asset_id JOIN core.asset_location loc ON loc.asset_id=a.id
          JOIN core.image_frame frame ON frame.id=reg.image_frame_id
          JOIN core.asset original ON original.id=frame.asset_id
          JOIN core.scan_log log ON log.id=frame.log_id
          WHERE reg.dataset_revision_id=%s AND frame.image_ordinal=%s
          AND log.source_log_id=%s AND reg.region_ordinal=%s AND loc.backend='local'""",
            (rev, r["image_ordinal"], r["source_log_id"], r["region_ordinal"]),
        ).fetchall()
        require(len(linked) == 1, "Image region must have exactly one native crop")
        asset = linked[0]
        require(
            asset["source_path"] == r["source_path"]
            and asset["source_sha256"] == r["source_sha256"] == r["recipe"]["source_sha256"]
            and asset["provenance"]["source_frame_id"] == str(asset["frame_id"])
            and asset["provenance"]["region_id"] == str(asset["id"]),
            "Stored crop is linked to the wrong source frame",
        )
        require(
            asset["sha256"] == r["crop_sha256"] and asset["provenance"]["recipe"] == r["recipe"],
            "Crop source or recipe differs",
        )
        crop_path = inside(ETL, ETL / asset["object_key"])
        actual = decode(crop_path)
        require(
            actual.tobytes() == im.crop((x, y, x2, y2)).tobytes(),
            "Stored crop differs from source pixels",
        )
    # Preserve interpretation algorithm variants and original values when reading results.
    logs = conn.execute(
        "SELECT id,source_log_id,source_log_name FROM core.scan_log WHERE dataset_revision_id=%s AND (log_kind='spectral' OR source_log_name IN ('Min1 sTSAS','Wt1 sTSAS','Min1 uTSAS','Wt1 uTSAS'))",
        (rev,),
    ).fetchall()
    chosen = [str(l["id"]) for l in logs]
    samples = {0, n - 1, n // 2, 129, 130}
    storage = read(source_folder(u) / "5_storage_report.json")
    # Boundary values are often null; also check samples with mineral names and weights.
    for log in [l for l in logs if l["source_log_name"] in ("Min1 sTSAS", "Min1 uTSAS")]:
        payload = next(
            a for a in storage["assets"] if a.get("source_log_id") == log["source_log_id"]
        )
        with pq.ParquetFile(source_folder(u) / payload["relative_path"]) as pf:
            for batch in pf.iter_batches(columns=["sample_no", "value_text"]):
                valid = next(
                    (r["sample_no"] for r in batch.to_pylist() if r["value_text"] is not None), None
                )
                if valid is not None:
                    samples.add(valid)
                    break
    first = mappings[0]
    samples.update({first["sample_no_from"], first["sample_no_to"]})
    outputs = []
    times = []
    for s in sorted(x for x in samples if x < n):
        start = time.perf_counter()
        out = read_sample(conn, release, u["dataset_id"], axis, s, chosen)
        times.append((time.perf_counter() - start) * 1000)
        orig = conn.execute(
            "SELECT md_m FROM core.scan_sample WHERE axis_id=%s AND sample_no=%s", (old, s)
        ).fetchone()
        require(
            out["md_m"] == orig["md_m"] and out["image_status"] == "available",
            "Sample read or linked image differs",
        )
        for result in out["results"]:
            if result["log_kind"] == "scalar" and result.get("value") is not None:
                # Locate prepared files through source logs, then read and compare them independently.
                a = next(
                    a
                    for a in read(source_folder(u) / "5_storage_report.json")["assets"]
                    if a.get("source_log_id") == result["source_log_id"]
                )
                with pq.ParquetFile(source_folder(u) / a["relative_path"]) as pf:
                    expected = pf.read().slice(s, 1).to_pylist()[0]
                require(
                    result["value"] == expected,
                    "Sample result differs from canonical source values",
                )
            if result["log_kind"] == "spectral" and result["status"] == "available":
                a = next(
                    a
                    for a in package_step(dest, 22)["arrays"]
                    if a["dataset_id"] == u["dataset_id"] and a["log_id"] == result["source_log_id"]
                )
                with source_path(u, a["file"]).open("rb") as f:
                    f.seek(s * a["band_count"] * 4)
                    data = f.read(a["band_count"] * 4)
                expected = np.frombuffer(data, dtype="<f4")
                require(
                    result["spectra"] == [float(x) if np.isfinite(x) else None for x in expected],
                    "Sample curve differs from preserved F32",
                )
        outputs.append(out)
    if u["hole_id"] == "05KCD001":
        a = next(o for o in outputs if o["sample_no"] == 129)
        b = next(o for o in outputs if o["sample_no"] == 130)
        require(
            a["images"][0]["image_region_id"] != b["images"][0]["image_region_id"]
            and a["images"][0]["indicator"]["p"] == 1
            and b["images"][0]["indicator"]["p"] == 0,
            "129 to 130 did not change row and marker",
        )
    # Compare official samples and offline reader results as float32 values.
    refs = 0
    for a in [a for a in package_step(dest, 22)["arrays"] if a["dataset_id"] == u["dataset_id"]]:
        log = next(l for l in logs if l["source_log_id"] == a["log_id"])
        for ref in a["references"]:
            for value in read(inside(dest, dest / ref["path"]))["response"]:
                out = read_sample(
                    conn, release, u["dataset_id"], axis, value["sampleNo"], [str(log["id"])]
                )["results"][0]
                require(
                    np.asarray(out["spectra"], dtype="<f4").tobytes()
                    == np.asarray(value["floatspectraldata"], dtype="<f4").tobytes(),
                    "DB reader differs from official reference",
                )
                refs += 1
    return {
        "hole_id": u["hole_id"],
        "sample_count": n,
        "row_count": len(mappings),
        "assets_checked": len(rows),
        "official_reference_spectra_compared": refs,
        "sample_read_ms": times,
        "example_selections": outputs,
    }


def write_manifest(conn, release):
    from _publication import write_asset_manifest

    return write_asset_manifest(conn, release)


def main():
    from _publication import publish_release

    parser = StepParser()
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--release")
    args = parser.parse_args()
    configure(args)
    if args.package or args.release:
        require(args.package and args.release, "Use --package and --release together")
        release, destination = args.release, args.package.resolve()
        with connection("reader") as conn:
            staged = release_context(conn, release, destination)
    else:
        staged = stage(28)
        release = staged["release_id"]
        destination = settings.database_dir / staged["package_directory"]
    manifest = read(destination / "manifest.json")
    check_package(destination, manifest)
    checks = []
    with connection() as conn:
        require(
            conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"],
            "Another import or validator is active",
        )
        try:
            assert_schema(conn)
            for unit in package_step(destination, 20)["datasets"]:
                new = next(
                    item for item in staged["datasets"] if item["dataset_id"] == unit["dataset_id"]
                )
                print(f"Verify media {unit['hole_id']}", flush=True)
                result = verify_dataset(conn, unit, new, release, destination)
                result.update(
                    status="passed",
                    dataset_revision_id=new["dataset_revision_id"],
                    input_digest=manifest["datasets"][unit["dataset_id"]]["content_sha256"],
                )
                checks.append(result)
            assets, locations = publish_release(
                conn,
                release,
                checks,
                __file__,
                activate=not args.no_activate,
                expected_previous=staged["previous_release_id"],
            )
            result = {
                "status": "passed",
                "release_id": release,
                "activated": not args.no_activate,
                "datasets": checks,
                "previous_release_id": staged["previous_release_id"],
                "schema_sha256": schema_hash(),
                "code_sha256": media_code_hash(),
            }
            report("29_media_verification.json", result)
            write(settings.reports_dir / "latest_verified_media.json", result)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    print(f'Verified {sum(item["sample_count"] for item in checks):,} samples.')


if __name__ == "__main__":
    main_guard(main)
