"""Legacy base-import publication and API acceptance for old numbered entry points and historical tests."""

import csv
import hashlib
from pathlib import Path

import pyarrow.parquet as pq

from _db_common import LOCK_KEY, assert_schema, connection
from _db_files import read, sha
from _file_checks import fresh_file_checks
from _prepared_inputs import prepared_holes
from _run_reports import report
from _settings import raw_path
from _verification import require, verify_hole


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
