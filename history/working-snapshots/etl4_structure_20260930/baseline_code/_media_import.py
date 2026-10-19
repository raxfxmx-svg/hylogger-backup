"""Package media evidence and import an independent revision for each dataset."""

import shutil
import hashlib
import uuid
from _db_common import ETL, insert, pick, uid
from _db_files import digest, encoded, inside, read, sha, write
from _run_reports import report
from _settings import settings
from _media_common import media_code_hash, require, stage
from psycopg import sql
from psycopg.types.json import Jsonb
from _ingest import add_asset

CLONE_TABLES = (
    "sample_axis",
    "core_interval",
    "spectral_stream",
    "interpretation_set",
    "interpretation_input",
    "metric_definition",
    "scan_log",
    "log_axis_binding",
    "asset",
    "asset_location",
    "log_asset",
    "data_chunk",
    "image_frame",
    "source_document",
    "source_reference",
    "quality_issue",
    "dataset_segment",
)


def remap(value, ids):
    if isinstance(value, uuid.UUID):
        return ids.get(str(value), str(value))
    if isinstance(value, str):
        return ids.get(value, value)
    if isinstance(value, list):
        return [remap(v, ids) for v in value]
    if isinstance(value, dict):
        return {k: remap(v, ids) for k, v in value.items()}
    return value


def select_revision(conn, table, rev, axis):
    if table == "core_interval":
        return conn.execute(
            "SELECT * FROM core.core_interval WHERE axis_id=%s ORDER BY (interval_kind='section'),ordinal",
            (axis,),
        ).fetchall()
    if table == "asset_location":
        return conn.execute(
            "SELECT l.* FROM core.asset_location l JOIN core.asset a ON a.id=l.asset_id WHERE a.dataset_revision_id=%s",
            (rev,),
        ).fetchall()
    return conn.execute(
        sql.SQL("SELECT * FROM core.{} WHERE dataset_revision_id=%s").format(sql.Identifier(table)),
        (rev,),
    ).fetchall()


def clone_revision(conn, u, newrev, pipeline, input_digest, verified, fail=False):
    old = u["source_revision_id"]
    axis = u["source_axis_id"]
    ids = {old: newrev}
    previous = conn.execute("SELECT * FROM core.dataset_revision WHERE id=%s", (old,)).fetchone()
    require(previous, "Source revision missing")
    rows = {t: select_revision(conn, t, old, axis) for t in CLONE_TABLES}
    for table, records in rows.items():
        for r in records:
            if "id" in r:
                ids[str(r["id"])] = uid("media-clone", newrev, table, r["id"])
    axis_new = ids[axis]
    existing = conn.execute(
        "SELECT input_digest FROM core.dataset_revision WHERE id=%s", (newrev,)
    ).fetchone()
    if existing:
        require(existing["input_digest"] == input_digest, "Revision identity conflict")
        return ids, False
    r = remap(previous, ids)
    r.update(pipeline_id=pipeline, input_digest=input_digest, mapping_version=2)
    # Base revisions share borehole metadata; preserve existing references when copying.
    r["borehole_revision_id"] = previous["borehole_revision_id"]
    r["normalized_metadata"] = {
        **r["normalized_metadata"],
        "pipeline_id": pipeline,
        "derived_from_revision_id": old,
        "media_contract": "sample-media-v1",
        "input_digest": input_digest,
    }
    insert(conn, "dataset_revision", r)
    for table, records in rows.items():
        json_columns = {
            c["column_name"]
            for c in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='core' AND table_name=%s AND data_type='jsonb'",
                (table,),
            )
        }
        for oldrow in records:
            row = remap(oldrow, ids)
            if table == "source_document":
                row["content_json"] = (
                    Jsonb(oldrow["content_json"]) if oldrow["content_json"] is not None else None
                )
                row["content_text"] = oldrow["content_text"]
            if table == "scan_log" and str(oldrow["id"]) in verified:
                row.update(
                    array_layout_status="verified_sample_major", per_sample_publication_allowed=True
                )
                row["normalized_metadata"].update(
                    array_layout_status="verified_sample_major",
                    per_sample_publication_allowed=True,
                    axis_binding_status="verified",
                    binding_basis=verified[str(oldrow["id"])]["binding_basis"],
                )
            if table == "log_axis_binding" and str(oldrow["log_id"]) in verified:
                row.update(
                    axis_id=axis_new,
                    status="verified",
                    basis=verified[str(oldrow["log_id"])]["binding_basis"],
                )
            if table == "asset" and row["logical_path"].endswith(".f32"):
                row["semantic_status"] = "verified_sample_major_float32"
            if table == "asset":
                row["provenance"].update(
                    reused_from_asset_id=str(oldrow["id"]),
                    source_revision_id=old,
                    source_axis_id=axis,
                    physical_file_metadata_preserved=True,
                )
            for col in json_columns:
                if row[col] is not None and not isinstance(row[col], Jsonb):
                    row[col] = Jsonb(row[col])
            insert(conn, table, row)
        if table == "core_interval":
            # SQL preserves sample values while replacing internal relationship IDs; source checks still run.
            conn.execute(
                "CREATE TEMP TABLE IF NOT EXISTS media_id_map(old_id uuid PRIMARY KEY,new_id uuid NOT NULL) ON COMMIT DROP"
            )
            conn.execute("TRUNCATE pg_temp.media_id_map")
            with conn.cursor().copy("COPY pg_temp.media_id_map(old_id,new_id) FROM STDIN") as copy:
                for a, b in ids.items():
                    copy.write_row((a, b))
            conn.execute(
                """INSERT INTO core.scan_sample
              SELECT %s,s.sample_no,s.md_m,t.new_id,c.new_id,s.tray_sample_no,s.section_sample_no,s.section_distance_mm
              FROM core.scan_sample s JOIN pg_temp.media_id_map t ON t.old_id=s.tray_interval_id
              JOIN pg_temp.media_id_map c ON c.old_id=s.section_interval_id WHERE s.axis_id=%s""",
                (axis_new, axis),
            )
            if fail:
                raise ValueError("Injected media interruption after sample copy")
    return ids, True


MEDIA_RULE_VERSION = "sample-media-v2"
MEDIA_RULE_VERSIONS = {}  # Key overrides by source dataset ID and change only the affected processing rules.


def media_rule_version(unit):
    return MEDIA_RULE_VERSIONS.get(unit.get("source_dataset_id"), MEDIA_RULE_VERSION)


def media_identity(unit, arrays, rows, rule_version=None):
    """Derive identity only from dataset inputs and rules; store the actual output digest separately."""
    identity = digest(
        {
            "dataset_id": unit["dataset_id"],
            "source_revision_id": unit["source_revision_id"],
            "source_snapshot_id": unit["source_snapshot_id"],
            "rules": rule_version or media_rule_version(unit),
        }
    )
    spectra = [
        pick(
            a,
            "log_id",
            "sha256",
            "shape",
            "dtype_code",
            "matrix_order",
            "sample_map",
            "blocks",
            "value_unit",
            "scaling_applied",
        )
        for a in arrays
    ]
    crops = [
        pick(
            r,
            "source_log_id",
            "source_frame_id",
            "source_section_id",
            "region_ordinal",
            "source_sha256",
            "x_px",
            "y_px",
            "width_px",
            "height_px",
            "crop_sha256",
            "pixel_sha256",
            "recipe",
            "sample_no_from",
            "sample_no_to",
            "region_status",
            "indicator_method",
            "indicator_version",
            "indicator_parameters",
            "source_depth_direction",
            "direction_status",
        )
        for r in rows
    ]
    return {
        "input_key": identity,
        "content_sha256": digest(
            {
                "arrays": sorted(spectra, key=lambda a: a["log_id"]),
                "rows": sorted(
                    crops,
                    key=lambda r: (r["source_log_id"], r["source_frame_id"], r["region_ordinal"]),
                ),
            }
        ),
    }


def package_step(destination, number):
    return read(destination / "steps" / f"{number}.json")


def prepared_context(unit):
    """Rebuild base import arguments from the package manifest and use its file references."""
    from _media_common import source_folder

    folder = source_folder(unit)
    for relative, checksum in unit["prepared_hashes"].items():
        require(
            sha(inside(folder, folder / relative)) == checksum,
            f"Prepared artifact changed: {relative}",
        )
    return {
        "prepared_hashes": unit["prepared_hashes"],
        "summary": unit["prepared_summary"],
        "folder": folder,
        "metadata": read(folder / "3_normalized_metadata.json"),
        "alignment": read(folder / "4_alignment_report.json"),
        "storage": read(folder / "5_storage_report.json"),
    }


def verify_source_assets(conn, unit):
    """Reread original referenced files at the import boundary; reruns must also validate content."""
    source = conn.execute(
        "SELECT a.id FROM core.dataset_revision r JOIN core.sample_axis a ON a.dataset_revision_id=r.id "
        "WHERE r.id=%s AND r.dataset_id=%s AND r.source_snapshot_id=%s AND a.id=%s",
        (
            unit["source_revision_id"],
            unit["dataset_id"],
            unit["source_snapshot_id"],
            unit["source_axis_id"],
        ),
    ).fetchone()
    require(source, "Package dataset/axis does not match the source revision")
    assets = conn.execute(
        "SELECT a.sha256,a.byte_size,l.object_key FROM core.asset a "
        "JOIN core.asset_location l ON l.asset_id=a.id WHERE a.dataset_revision_id=%s AND l.backend='local'",
        (unit["source_revision_id"],),
    ).fetchall()
    require(assets, "Source revision has no local assets")
    for asset in assets:
        path = inside(ETL, ETL / asset["object_key"])
        require(
            path.stat().st_size == asset["byte_size"] and sha(path) == asset["sha256"],
            "Referenced source asset changed: " + asset["object_key"],
        )


def verify_media_sources(conn, unit, arrays, rows):
    """Check package media declarations against actual logs, images, and sample sources in the base version."""
    for array in arrays:
        source = conn.execute(
            """SELECT a.sha256,a.byte_size,s.wavelength_count FROM core.scan_log l
            JOIN core.log_asset la ON la.log_id=l.id JOIN core.asset a ON a.id=la.asset_id
            JOIN core.spectral_stream s ON s.id=l.spectral_stream_id
            WHERE l.id=%s AND l.dataset_revision_id=%s AND l.source_log_id=%s
            AND a.representation='raw' AND a.logical_path=%s""",
            (array["source_log_pk"], unit["source_revision_id"], array["log_id"], array["file"]),
        ).fetchone()
        require(
            source
            and source["sha256"] == array["sha256"]
            and source["wavelength_count"] == array["band_count"]
            and array["sample_count"] == unit["sample_count"]
            and source["byte_size"] == array["sample_count"] * array["band_count"] * 4,
            "Spectral source, dimensions or dataset differs",
        )
    for row in rows:
        source = conn.execute(
            """SELECT a.sha256,a.logical_path,l.source_log_id,f.image_ordinal
            FROM core.image_frame f JOIN core.asset a ON a.id=f.asset_id
            JOIN core.scan_log l ON l.id=f.log_id
            WHERE f.id=%s AND f.dataset_revision_id=%s""",
            (row["source_frame_id"], unit["source_revision_id"]),
        ).fetchone()
        require(
            source
            and source["logical_path"] == row["source_path"]
            and source["source_log_id"] == row["source_log_id"]
            and source["image_ordinal"] == row["image_ordinal"]
            and source["sha256"] == row["source_sha256"] == row["recipe"]["source_sha256"],
            "Crop refers to a different source frame",
        )


def release_context(conn, release, destination):
    """Resolve revisions from the specified release and sealed package, without reading the active release or temporary steps."""
    from _publication import release_members

    members = release_members(conn, release)
    definition = conn.execute(
        "SELECT manifest FROM core.data_release WHERE id=%s", (release,)
    ).fetchone()["manifest"]
    manifest = read(destination / "manifest.json")
    results = []
    for unit in package_step(destination, 20)["datasets"]:
        identity = manifest["datasets"][unit["dataset_id"]]
        revision = uid("media-revision-v2", unit["dataset_id"], identity["input_key"])
        require(
            any(
                str(m["dataset_id"]) == unit["dataset_id"]
                and str(m["dataset_revision_id"]) == revision
                for m in members
            ),
            "Package revision is not in this release",
        )
        axis = conn.execute(
            "SELECT id FROM core.sample_axis WHERE dataset_revision_id=%s", (revision,)
        ).fetchone()
        results.append(
            {
                "dataset_id": unit["dataset_id"],
                "dataset_revision_id": revision,
                "axis_id": str(axis["id"]),
            }
        )
    return {
        "release_id": release,
        "datasets": results,
        "previous_release_id": definition["source_release_id"],
        "decisions": definition.get("succession_decisions"),
    }


def check_package(destination, manifest):
    """Check the selected input package and organize the required manifests by dataset."""
    require(destination.name == digest(manifest), "Package manifest identity differs")
    for relative, item in manifest["files"].items():
        path = inside(destination, destination / relative)
        require(
            path.is_file()
            and path.stat().st_size == item["byte_size"]
            and sha(path) == item["sha256"],
            f"Packaged file differs: {relative}",
        )
    source = package_step(destination, 20)
    units = source["datasets"]
    dataset_ids = [unit["dataset_id"] for unit in units]
    require(
        dataset_ids
        and len(dataset_ids) == len(set(dataset_ids))
        and set(dataset_ids) == set(manifest["datasets"]),
        "Package dataset membership differs",
    )
    arrays = package_step(destination, 22)["arrays"]
    rows = package_step(destination, 27)["rows"]
    datasets = {unit["dataset_id"]: {"unit": unit, "arrays": [], "rows": []} for unit in units}
    for field, items in (("arrays", arrays), ("rows", rows)):
        for item in items:
            require(item["dataset_id"] in datasets, "Media belongs to an unlisted dataset")
            datasets[item["dataset_id"]][field].append(item)
    for unit in units:
        dataset = unit["dataset_id"]
        selected = datasets[dataset]
        recorded = manifest["datasets"][dataset]
        # Without an individual override, recheck historical versions using the shared rules saved in the package.
        rules = recorded.get("rule_version", manifest["contract"])
        identity = media_identity(
            unit,
            selected["arrays"],
            selected["rows"],
            rules,
        )
        require(
            identity == pick(recorded, "input_key", "content_sha256"),
            "Package content identity differs",
        )
    return {
        "key": destination.name,
        "directory": destination,
        "manifest": manifest,
        "source": source,
        "datasets": datasets,
    }


def prepare_package(work=None, evidence_dir=None):
    work = settings.media_work_dir if work is None else work
    evidence_dir = settings.media_evidence_dir if evidence_dir is None else evidence_dir
    require(
        stage(22, work)["status"] == "passed" and stage(27, work)["status"] == "passed",
        "Incomplete media preparation",
    )
    payloads = {}
    steps = {n: stage(n, work) for n in range(20, 28)}
    # Sealed references point to evidence inside the package without relying on temporary preparation directories.
    for number, field in ((21, "spectra"), (22, "arrays")):
        for array in steps[number][field]:
            for proof in array.get("references", []):
                original = inside(settings.database_dir, settings.database_dir / proof["path"])
                relative = original.relative_to(evidence_dir).as_posix()
                proof["path"] = "evidence/" + relative
    for number, value in steps.items():
        payloads[f"steps/{number}.json"] = encoded(value)
    files = {
        f"evidence/{p.relative_to(evidence_dir).as_posix()}": p
        for p in evidence_dir.rglob("*")
        if p.is_file()
    }
    for path in work.glob("*_review_*.png"):
        files["review/" + path.name] = path
    for row in steps[27]["rows"]:
        files[row["crop_work_path"]] = inside(work, work / row["crop_work_path"])
    inventory = {
        name: {"sha256": hashlib.sha256(data).hexdigest(), "byte_size": len(data)}
        for name, data in payloads.items()
    }
    inventory.update(
        {
            name: {"sha256": sha(path), "byte_size": path.stat().st_size}
            for name, path in sorted(files.items())
        }
    )
    datasets = {}
    for unit in steps[20]["datasets"]:
        dataset = unit["dataset_id"]
        arrays = [a for a in steps[22]["arrays"] if a["dataset_id"] == dataset]
        rows = [r for r in steps[27]["rows"] if r["dataset_id"] == dataset]
        datasets[dataset] = {
            **media_identity(unit, arrays, rows),
            "rule_version": media_rule_version(unit),
        }
    manifest = {
        "contract": MEDIA_RULE_VERSION,
        "datasets": datasets,
        "source_release_id": steps[20]["source_release_id"],
        "files": inventory,
    }
    key = digest(manifest)
    destination = settings.database_dir / "media_releases" / key
    for relative, data in payloads.items():
        target = inside(destination, destination / relative)
        if target.exists():
            require(sha(target) == inventory[relative]["sha256"], "Packaged evidence was changed")
        else:
            write(target, data.decode("utf-8"))
    for relative, source in files.items():
        target = inside(destination, destination / relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            require(sha(target) == inventory[relative]["sha256"], "Packaged artifact was changed")
        else:
            shutil.copyfile(source, target)
    write(destination / "manifest.json", manifest)
    package = check_package(destination, manifest)
    report(
        "media_package_run.json",
        {
            "package": key,
            "code_sha256": media_code_hash(),
            "datasets": datasets,
            "status": "passed",
        },
    )
    return package


def import_media(conn, package, dataset_id, fail=False):
    """Use the package validated for this run and still check database provenance for the current dataset."""
    key, dest, manifest = package["key"], package["directory"], package["manifest"]
    selected = package["datasets"][dataset_id]
    u = selected["unit"]
    verify_source_assets(conn, u)
    identity = manifest["datasets"][u["dataset_id"]]
    rev = uid("media-revision-v2", u["dataset_id"], identity["input_key"])
    spectra = selected["arrays"]
    rows = selected["rows"]
    verify_media_sources(conn, u, spectra, rows)
    verified = {a["source_log_pk"]: a for a in spectra}
    ids, created = clone_revision(
        conn,
        u,
        rev,
        identity.get("rule_version", manifest["contract"]),
        identity["content_sha256"],
        verified,
        fail,
    )
    if not created:
        return {
            "dataset_id": u["dataset_id"],
            "dataset_revision_id": rev,
            "axis_id": ids[u["source_axis_id"]],
            "action": "already_present",
        }
    axis = ids[u["source_axis_id"]]
    # Evidence files may be shared, but asset records still belong to their respective data versions.
    evidence = {}
    for relative, meta in manifest["files"].items():
        if relative.startswith("crops/"):
            continue
        evidence[relative] = add_asset(
            conn,
            rev,
            "evidence",
            "media/" + relative,
            "media_evidence",
            meta["byte_size"],
            meta["sha256"],
            (dest / relative).relative_to(ETL).as_posix(),
            "processing_evidence",
            {"media_package_sha256": key},
        )
    for a in spectra:
        oldasset = conn.execute(
            "SELECT id FROM core.asset WHERE dataset_revision_id=%s AND representation='raw' AND logical_path=%s",
            (u["source_revision_id"], a["file"]),
        ).fetchone()["id"]
        array = uid("spectral-array", rev, a["log_id"])
        asset = ids[str(oldasset)]
        log = ids[a["source_log_pk"]]
        insert(
            conn,
            "spectral_array",
            {
                "id": array,
                "dataset_revision_id": rev,
                "log_id": log,
                "asset_id": asset,
                "spectral_stream_id": ids[a["spectral_stream_id"]],
                "sample_count": a["sample_count"],
                "channel_count": a["band_count"],
                **pick(
                    a,
                    "dtype_code",
                    "matrix_order",
                    "data_offset_bytes",
                    "sample_stride_bytes",
                    "channel_stride_bytes",
                    "layout_status",
                    "value_unit",
                    "scaling_applied",
                ),
                "evidence_asset_id": evidence["steps/21.json"],
                "evidence": {
                    "binding_basis": a["binding_basis"],
                    "references": a["references"],
                    "official_commit": a["contract_commit"],
                    "verification_scope": a["verification_scope"],
                },
            },
        )
        sm = a["sample_map"]
        insert(
            conn,
            "spectral_sample_map",
            {
                "id": uid("spectral-map", array, 0),
                "dataset_revision_id": rev,
                "spectral_array_id": array,
                "axis_id": axis,
                **pick(sm, "source_row_from", "source_row_to", "sample_no_from", "sample_no_to"),
                "mapping_kind": "identity_range",
                "binding_status": "verified",
                "evidence_asset_id": evidence["steps/21.json"],
                "basis": a["binding_basis"],
            },
        )
        for block in a["blocks"]:
            insert(conn, "spectral_block", {"spectral_array_id": array, **block})
    for r in rows:
        region = uid(
            "image-region", rev, r["source_log_id"], r["source_frame_id"], r["region_ordinal"]
        )
        log = ids[
            conn.execute(
                "SELECT id FROM core.scan_log WHERE dataset_revision_id=%s AND source_log_id=%s AND log_kind=%s",
                (u["source_revision_id"], r["source_log_id"], "image"),
            )
            .fetchone()["id"]
            .__str__()
        ]
        insert(
            conn,
            "image_region",
            {
                "id": region,
                "dataset_revision_id": rev,
                "image_frame_id": ids[r["source_frame_id"]],
                "region_kind": "core_row",
                **pick(
                    r,
                    "region_ordinal",
                    "x_px",
                    "y_px",
                    "width_px",
                    "height_px",
                    "coordinate_basis",
                    "region_status",
                    "detection_method",
                    "review_basis",
                ),
                "valid_area": None,
                "evidence_asset_id": evidence["steps/25.json"],
            },
        )
        insert(
            conn,
            "image_sample_mapping",
            {
                "id": uid("image-map", region, 0),
                "dataset_revision_id": rev,
                "image_region_id": region,
                "axis_id": axis,
                "section_interval_id": ids[r["source_section_id"]],
                **pick(
                    r,
                    "sample_no_from",
                    "sample_no_to",
                    "anchor_points",
                    "source_depth_direction",
                    "direction_status",
                    "direction_basis",
                    "mapping_level",
                    "mapping_status",
                    "mapping_method",
                    "indicator_method",
                    "indicator_version",
                    "indicator_status",
                    "indicator_parameters",
                    "error_px",
                    "error_depth_m",
                ),
                "direction_evidence_asset_id": evidence["steps/26.json"],
                "evidence_asset_id": evidence["steps/26.json"],
            },
        )
        rel = r["crop_work_path"]
        meta = manifest["files"][rel]
        asset = add_asset(
            conn,
            rev,
            "canonical",
            rel,
            "core_row_image",
            meta["byte_size"],
            meta["sha256"],
            (dest / rel).relative_to(ETL).as_posix(),
            "lossless_source_crop",
            {
                "region_id": region,
                "source_frame_id": ids[r["source_frame_id"]],
                "recipe": r["recipe"],
                "pixel_sha256": r["pixel_sha256"],
            },
        )
        insert(
            conn,
            "log_asset",
            {
                "log_id": log,
                "asset_id": asset,
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
                "asset_id": asset,
                "log_id": log,
                "representation_kind": "native_lossless_png",
                "width_px": r["width_px"],
                "height_px": r["height_px"],
                "transform": r["recipe"],
                "recipe_version": 1,
            },
        )
    return {
        "dataset_id": u["dataset_id"],
        "dataset_revision_id": rev,
        "axis_id": axis,
        "action": "inserted",
    }
