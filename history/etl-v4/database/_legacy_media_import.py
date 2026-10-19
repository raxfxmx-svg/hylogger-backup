"""Legacy two-stage media import for old numbered entry points and historical comparison tests."""

from psycopg import sql
from psycopg.types.json import Jsonb

from _db_common import insert, uid
from _db_files import read, sha
from _settings import local_asset_path
from _media_common import require
from _media_import import insert_media_records, package_step, remap, verify_media_sources


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
    existing = conn.execute(
        "SELECT input_digest FROM core.dataset_revision WHERE id=%s", (newrev,)
    ).fetchone()
    if existing:
        require(existing["input_digest"] == input_digest, "Revision identity conflict")
        # Reruns need only the target axis, without rereading all records to copy.
        axis_new = uid("media-clone", newrev, "sample_axis", axis)
        require(
            conn.execute(
                "SELECT 1 FROM core.sample_axis WHERE id=%s AND dataset_revision_id=%s",
                (axis_new, newrev),
            ).fetchone(),
            "Existing media revision has no matching axis",
        )
        return {old: newrev, axis: axis_new}, False
    rows = {t: select_revision(conn, t, old, axis) for t in CLONE_TABLES}
    for table, records in rows.items():
        for r in records:
            if "id" in r:
                ids[str(r["id"])] = uid("media-clone", newrev, table, r["id"])
    axis_new = ids[axis]
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
        "SELECT a.sha256,a.byte_size,l.object_key,l.root_key FROM core.asset a "
        "JOIN core.asset_location l ON l.asset_id=a.id WHERE a.dataset_revision_id=%s AND l.backend='local'",
        (unit["source_revision_id"],),
    ).fetchall()
    require(assets, "Source revision has no local assets")
    for asset in assets:
        path = local_asset_path(asset)
        require(
            path.stat().st_size == asset["byte_size"] and sha(path) == asset["sha256"],
            "Referenced source asset changed: " + asset["object_key"],
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
    return insert_media_records(conn, package, dataset_id, rev, ids)
