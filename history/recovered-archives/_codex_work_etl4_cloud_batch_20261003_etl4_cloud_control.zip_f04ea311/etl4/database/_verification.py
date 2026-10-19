"""Compare prepared outputs with the database; enable API checks separately."""

import csv
import pyarrow.parquet as pq
import hashlib
from _db_common import ETL, LOCK_KEY, assert_schema, connection
from _db_files import encoded, inside, read, sha
from _prepared_inputs import prepared_document, prepared_holes
from _run_reports import report
from pathlib import Path
from psycopg import sql
from _ingest import input_digest
from _file_checks import fresh_file_checks
from _settings import local_asset_path, raw_path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_hole(conn, h, verify_assets=True, *, content_digest=None, media_asset_count=0):
    m = h["metadata"]
    rev = m["dataset_revision"]["id"]
    axis = h["alignment"]["axis_id"]
    folder = h["folder"]
    row = conn.execute("SELECT * FROM core.dataset_revision WHERE id=%s", (rev,)).fetchone()
    require(row is not None, "Expected revision not imported")
    fingerprint = input_digest(h) if content_digest is None else content_digest
    require(row["input_digest"] == fingerprint, "Import identity mismatch")
    require(
        row["normalized_metadata"] == m["dataset_revision"], "Dataset revision metadata differs"
    )
    br = conn.execute(
        "SELECT normalized_metadata FROM core.borehole_revision WHERE id=%s",
        (m["borehole"]["metadata_revision_id"],),
    ).fetchone()
    require(br["normalized_metadata"] == m["borehole"], "Borehole metadata lost")
    logs = conn.execute(
        "SELECT * FROM core.scan_log WHERE dataset_revision_id=%s", (rev,)
    ).fetchall()
    require(len(logs) == len(m["logs"]), "Metadata log count differs")
    indexed = {str(x["id"]): x for x in logs}
    for log in m["logs"]:
        require(indexed[log["id"]]["normalized_metadata"] == log, "Normalized log metadata differs")
    for name, raw in m["raw_metadata"].items():
        doc = conn.execute(
            "SELECT content_json FROM core.source_document WHERE dataset_revision_id=%s AND document_name=%s",
            (rev, name),
        ).fetchone()
        require(doc is not None and doc["content_json"] == raw, "Raw metadata document differs")
    for table, key in [
        ("spectral_stream", "spectral_streams"),
        ("interpretation_set", "interpretation_sets"),
        ("metric_definition", "metric_definitions"),
    ]:
        actual = conn.execute(
            sql.SQL("SELECT * FROM core.{} WHERE dataset_revision_id=%s").format(
                sql.Identifier(table)
            ),
            (rev,),
        ).fetchall()
        required = m[key]
        identity = "metric_key" if table == "metric_definition" else "id"
        bykey = {str(x[identity]): x for x in actual}
        require(len(actual) == len(required), f"{table} row count differs")
        for expected in required:
            got = bykey[expected[identity]]
            require(
                encoded({k: got[k] for k in expected}) == encoded(expected),
                f"{table} typed fields differ",
            )
    intervals = prepared_document(h, "4_core_intervals.json")
    byordinal = {(i["interval_kind"], i["ordinal"]): i["id"] for i in intervals}
    for expected in intervals:
        got = conn.execute(
            "SELECT * FROM core.core_interval WHERE id=%s", (expected["id"],)
        ).fetchone()
        require(encoded(got) == encoded(expected), "Core interval differs")
    for expected in prepared_document(h, "4_axis_bindings.json"):
        got = conn.execute(
            """SELECT b.* FROM core.log_axis_binding b JOIN core.scan_log l ON l.id=b.log_id
           WHERE l.dataset_revision_id=%s AND l.source_log_id=%s""",
            (rev, expected["source_log_id"]),
        ).fetchone()
        require(
            str(got["axis_id"]) == expected["axis_id"]
            and got["status"] == expected["status"]
            and got["basis"] == expected["basis"],
            "Verified binding differs",
        )
    samples_compared = 0
    with conn.transaction():
        with conn.cursor(name="axis_validation") as cur, pq.ParquetFile(
            folder / "5_canonical/sample_axis.parquet"
        ) as pf:
            cur.execute(
                "SELECT * FROM core.scan_sample WHERE axis_id=%s ORDER BY sample_no", (axis,)
            )
            for batch in pf.iter_batches(batch_size=4096):
                rows = batch.to_pylist()
                actual = cur.fetchmany(len(rows))
                require(len(actual) == len(rows), "Sample count lost")
                for source, got in zip(rows, actual):
                    expected = {
                        k: source[k]
                        for k in (
                            "sample_no",
                            "md_m",
                            "tray_sample_no",
                            "section_sample_no",
                            "section_distance_mm",
                        )
                    }
                    expected.update(
                        axis_id=axis,
                        tray_interval_id=byordinal[("tray", source["tray_index"])],
                        section_interval_id=byordinal[("section", source["section_index"])],
                    )
                    require(
                        encoded(got) == encoded(expected),
                        "Sample identity, depth or interval position differs",
                    )
                samples_compared += len(rows)
            require(cur.fetchone() is None, "Unexpected extra samples")
    assets = conn.execute(
        "SELECT * FROM core.asset WHERE dataset_revision_id=%s", (rev,)
    ).fetchall()
    raw = [a for a in assets if a["representation"] == "raw"]
    canonical = [a for a in assets if a["representation"] == "canonical"]
    require(len(raw) == h["summary"]["source_file_count"], "Raw asset inventory incomplete")
    require(
        len(canonical) == h["summary"]["canonical_file_count"] + media_asset_count,
        "Canonical asset inventory incomplete",
    )
    asset_map = {a["logical_path"]: a for a in canonical}
    chunks_compared = 0
    for expected in h["storage"]["assets"]:
        a = asset_map[expected["relative_path"]]
        require(
            a["sha256"] == expected["sha256"] and a["byte_size"] == expected["byte_size"],
            "Canonical identity differs",
        )
        chunks = conn.execute(
            "SELECT * FROM core.data_chunk WHERE asset_id=%s ORDER BY row_group", (a["id"],)
        ).fetchall()
        require(len(chunks) == len(expected["row_groups"]), "Chunk count mismatch")
        for got, wanted, logical in zip(
            chunks, expected["row_groups"], expected["logical_group_sha256"]
        ):
            require(
                {k: got[k] for k in wanted} == wanted and got["logical_sha256"] == logical,
                "Chunk coordinates or logical hash differ",
            )
        chunks_compared += len(chunks)
    checked_bytes = 0
    if verify_assets:
        for asset in assets:
            loc = conn.execute(
                "SELECT * FROM core.asset_location WHERE asset_id=%s AND backend='local'",
                (asset["id"],),
            ).fetchone()
            require(loc is not None, "Missing local location")
            path = local_asset_path(loc)
            require(
                path.is_file()
                and path.stat().st_size == asset["byte_size"]
                and sha(path) == asset["sha256"],
                "Asset file checksum or location differs",
            )
            checked_bytes += asset["byte_size"]
    frames = prepared_document(h, "4_image_frames.json")
    for expected in frames:
        got = conn.execute(
            "SELECT * FROM core.image_frame WHERE id=%s", (expected["id"],)
        ).fetchone()
        keys = [k for k in expected if k not in ("source_log_id", "source_path")]
        require(
            encoded({k: got[k] for k in keys}) == encoded({k: expected[k] for k in keys}),
            "Image association differs",
        )
    invalid = conn.execute(
        """SELECT count(*) AS n FROM core.scan_sample s
       JOIN core.core_interval t ON t.id=s.tray_interval_id JOIN core.core_interval c ON c.id=s.section_interval_id
       WHERE s.axis_id=%s AND (t.interval_kind<>'tray' OR c.interval_kind<>'section' OR c.parent_interval_id<>t.id
       OR s.sample_no NOT BETWEEN t.sample_no_from AND t.sample_no_to OR s.sample_no NOT BETWEEN c.sample_no_from AND c.sample_no_to
       OR s.tray_sample_no<>s.sample_no-t.sample_no_from+1 OR s.section_sample_no<>s.sample_no-c.sample_no_from+1)""",
        (axis,),
    ).fetchone()["n"]
    require(invalid == 0, "Sample position consistency failed")
    return {
        "hole_id": h["summary"]["hole_id"],
        "dataset_revision_id": rev,
        "samples_compared": samples_compared,
        "logs_compared": len(logs),
        "chunks_compared": chunks_compared,
        "images_compared": len(frames),
        "assets_hashed": len(assets) if verify_assets else 0,
        "asset_bytes_hashed": checked_bytes,
        "input_digest": fingerprint,
        "status": "passed",
    }


def profile_window(parquet):
    """Check boundaries between row groups; sample short files according to their actual row count."""
    count = parquet.metadata.num_rows
    require(count > 0, 'The profile file contains no samples')
    boundary = parquet.metadata.row_group(0).num_rows
    start = max(0, boundary - 2) if parquet.num_row_groups > 1 else max(0, count // 2 - 2)
    stop = min(count - 1, start + 4)
    groups, offset = [], 0
    first_offset = 0
    for group in range(parquet.num_row_groups):
        size = parquet.metadata.row_group(group).num_rows
        if offset <= stop and offset + size > start:
            if not groups:
                first_offset = offset
            groups.append(group)
        offset += size
    expected = parquet.read_row_groups(groups).slice(start - first_offset, stop - start + 1).to_pylist()
    return start, stop, expected


def api_checks(holes, release_id, dbname=None):
    from fastapi.testclient import TestClient
    from api.app import create_app

    results = []
    with TestClient(create_app(dbname)) as client:
        params = {"release_id": str(release_id)}
        listing = client.get("/v1/boreholes", params=params)
        require(listing.status_code == 200, listing.text[:500])
        require(
            {r["source_hole_id"] for r in listing.json()["items"]}
            == {h["summary"]["hole_id"] for h in holes},
            "Release membership differs in API",
        )
        require(
            client.get("/v1/boreholes", params={**params, "bbox": "0,0,1,1"}).json()["items"] == [],
            "Spatial filter failed",
        )
        require(
            client.get("/v1/boreholes", params={**params, "bbox": "nan,0,1,1"}).status_code == 422,
            "Nonfinite bbox accepted",
        )
        for h in holes:
            m = h["metadata"]
            rev = m["dataset_revision"]["id"]
            rawhole = h["summary"]["hole_id"]
            q = h["summary"]["depth_range_query"]
            api_log = next(l for l in m["logs"] if l["source_log_id"] == q["source_log_id"])
            lo, hi = q["from_m"], q["to_m"]
            response = client.get(
                f"/v1/logs/{api_log['id']}/values",
                params={**params, "from_m": lo, "to_m": hi, "limit": 5000},
            )
            require(response.status_code == 200, response.text[:500])
            payload = response.json()
            expected = []
            with raw_path(rawhole, api_log["payload_paths"][0]).open(
                encoding="utf-8-sig", newline=""
            ) as f:
                reader = csv.reader(f)
                next(reader)
                for i, row in enumerate(reader):
                    if lo <= float(row[0]) <= hi:
                        expected.append((i, row[2]))
            require(
                [(r["source_row"], r["value_raw"]) for r in payload["items"]] == expected,
                "API range differs from original CSV",
            )
            repeat = h["summary"]["duplicate_depth_query"]
            dup = repeat["depth_m"] if repeat else None
            all_ids = []
            after = -1
            while repeat:
                page = client.get(
                    f"/v1/datasets/{rev}/samples",
                    params={
                        **params,
                        "from_m": dup,
                        "to_m": dup,
                        "limit": 3,
                        "after_sample": after,
                    },
                )
                require(page.status_code == 200, page.text[:300])
                p = page.json()
                all_ids.extend(r["sample_no"] for r in p["items"])
                if p["next_after_sample"] is None:
                    break
                require(p["next_after_sample"] > after, "Pagination failed to advance")
                after = p["next_after_sample"]
            if repeat:
                require(all_ids == repeat["sample_ids"], "Duplicate-depth pagination lost samples")
            catalog = client.get(f"/v1/datasets/{rev}/logs", params=params).json()["items"]
            require(len(catalog) == len(m["logs"]), "API log catalog incomplete")
            for kind in ("spectral-streams", "interpretation-sets", "intervals", "issues"):
                require(
                    client.get(f"/v1/datasets/{rev}/{kind}", params=params).status_code == 200,
                    f"{kind} endpoint failed",
                )
            missing = next((
                x
                for x in m["logs"]
                if x["log_kind"] == "spectral" and x["availability_status"] == "metadata_only"
            ), None)
            if missing:
                require(
                    client.get(f"/v1/logs/{missing['id']}/values", params=params).json()["status"]
                    == "metadata_only",
                    "Missing payload status lost",
                )
            spectrum = next(
                x
                for x in m["logs"]
                if x["log_kind"] == "spectral" and x["availability_status"] == "payload_present"
            )
            require(
                client.get(f"/v1/logs/{spectrum['id']}/values", params=params).json()["reason"]
                == "sample_wavelength_order_unconfirmed",
                "Unconfirmed spectrum published",
            )
            profile = next(x for x in m["logs"] if x["log_kind"] == "profile")
            profile_asset = next(
                a
                for a in h["storage"]["assets"]
                if a.get("source_log_id") == profile["source_log_id"]
            )
            with pq.ParquetFile(h["folder"] / profile_asset["relative_path"]) as pf:
                start, stop, profile_expected = profile_window(pf)
            profile_response = client.get(
                f"/v1/logs/{profile['id']}/values",
                params={**params, "from_sample": start, "to_sample": stop, "limit": 10},
            )
            require(profile_response.status_code == 200, profile_response.text[:500])
            require(
                profile_response.json()["items"] == profile_expected,
                "Profile cross-row-group reading differs",
            )
            image_list = client.get(
                f"/v1/datasets/{rev}/images", params={**params, "limit": 500}
            ).json()["items"]
            require(len(image_list) == h["summary"]["thumbnail_count"], "Image count differs")
            content = client.get(image_list[0]["content_path"])
            image_source = read(h["folder"] / "4_image_frames.json")[0]["source_path"]
            require(
                content.status_code == 200
                and hashlib.sha256(content.content).hexdigest()
                == sha(raw_path(rawhole, image_source)),
                "Image bytes differ",
            )
            require(
                client.get(
                    f"/v1/logs/{api_log['id']}/values", params={**params, "from_m": hi, "to_m": lo}
                ).status_code
                == 422,
                "Reversed depth accepted",
            )
            results.append(
                {
                    "hole_id": rawhole,
                    "range_rows": len(expected),
                    "duplicate_samples_returned": len(all_ids),
                    "profile_boundary_checked": True,
                    "image_bytes_checked": True,
                    "read_stats": payload["read_stats"],
                }
            )
    return results


@fresh_file_checks
def verify_and_publish(holes=None, dbname=None, publish=True, check_api=False):
    from _publication import stage_release, publish_release

    selected = prepared_holes(holes)
    checks = []
    with connection("ingest", dbname=dbname) as conn:
        assert_schema(conn)
        require(
            conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (LOCK_KEY,)).fetchone()["ok"],
            "Importer/validator is already active",
        )
        try:
            for hole in selected:
                print(f"Verify {hole['summary']['hole_id']}", flush=True)
                checks.append(verify_hole(conn, hole))
            members = [
                {
                    "dataset_id": h["metadata"]["dataset"]["id"],
                    "dataset_revision_id": h["metadata"]["dataset_revision"]["id"],
                }
                for h in selected
            ]
            with conn.transaction():
                release = stage_release(conn, members, "local_base_v2")
            api = (
                api_checks(selected, release, dbname) if check_api else {"status": "not_requested"}
            )
            publish_release(conn, release, checks, __file__, activate=publish)
            return report(
                "10_verification.json",
                {
                    "status": "passed",
                    "release_id": release,
                    "holes": checks,
                    "http_checks": api,
                    "activated": publish,
                    "verification_code_sha256": sha(Path(__file__)),
                },
            )
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
