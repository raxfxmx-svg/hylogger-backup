"""Validate complete sources and display selections, then publish through the shared entry point."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from _db_common import CODE, LOCK_KEY, assert_schema, connection, schema_hash
from _run_reports import main_guard, report
from _db_files import read, write
from _settings import settings, configure
from _multi_common import module, require
from _multi_db import install_composites
from psycopg import sql
from _multi_reader import read_borehole_layout


def must_reject(conn, name, query, params):
    try:
        with conn.transaction():
            conn.execute(query, params)
            raise RuntimeError("Unsafe composite mutation was accepted: " + name)
    except psycopg.Error as exc:
        require(
            exc.sqlstate in ("23503", "23505", "23514", "P0001"), "Unexpected test failure: " + name
        )
        return {"case": name, "status": "rejected", "sqlstate": exc.sqlstate}


def composite_fault_checks(conn, groups):
    tests = []
    target = next(g for g in groups if g["hole_id"] == "14KDD001")
    part = target["parts"][0]
    tests.append(
        must_reject(
            conn,
            "wrong source sample index",
            "UPDATE core.borehole_composite_part SET sample_no_to=sample_no_to-1 WHERE composite_id=%s AND sequence_no=0",
            (part["composite_id"],),
        )
    )
    tests.append(
        must_reject(
            conn,
            "overlap reintroduced into 3D",
            "UPDATE core.borehole_composite_part SET selection_to_md_m=%s,upper_inclusive=true,sample_no_to=%s WHERE composite_id=%s AND sequence_no=0",
            (
                target["datasets"][0]["depth_max_m"],
                target["datasets"][0]["sample_count"] - 1,
                part["composite_id"],
            ),
        )
    )
    other = next(g for g in groups if g["hole_id"] == "12CADD001")["parts"][0]
    tests.append(
        must_reject(
            conn,
            "cross-hole dataset assignment",
            "UPDATE core.borehole_composite_part SET dataset_id=%s,dataset_revision_id=%s WHERE composite_id=%s AND sequence_no=0",
            (other["dataset_id"], other["dataset_revision_id"], part["composite_id"]),
        )
    )
    three = next(g for g in groups if g["hole_id"] == "15EIS001")["parts"]
    tests.append(
        must_reject(
            conn,
            "wrong succession evidence",
            "UPDATE core.borehole_composite_part SET predecessor_relation_id=%s WHERE composite_id=%s AND sequence_no=3",
            (three[1]["predecessor_relation_id"], three[3]["composite_id"]),
        )
    )
    tests.append(
        must_reject(
            conn,
            "missing succession evidence",
            "UPDATE core.borehole_composite_part SET predecessor_relation_id=NULL WHERE composite_id=%s AND sequence_no=1",
            (three[1]["composite_id"],),
        )
    )
    return tests


def main():
    from _settings import StepParser
    from pathlib import Path

    parser = StepParser()
    parser.add_argument("--package", type=Path)
    parser.add_argument("--release")
    args = parser.parse_args()
    configure(args)
    import _media_import as mi

    verifier = module("multi_media_verifier", CODE / "29_verify_media_grain.py")
    if args.package or args.release:
        require(args.package and args.release, "Use --package and --release together")
        release, dest = args.release, args.package.resolve()
        with connection("reader") as conn:
            staged = mi.release_context(conn, release, dest)
    else:
        staged = read(settings.multi_work_dir / "34_import.json")
        release = staged["release_id"]
        dest = settings.database_dir / staged["package_directory"]
    baseline = {"release_id": staged["previous_release_id"]}
    manifest = read(dest / "manifest.json")
    mi.check_package(dest, manifest)
    checks = []
    layouts = []
    with connection() as conn:
        require(
            conn.execute("SELECT pg_try_advisory_lock(%s) ok", (LOCK_KEY,)).fetchone()["ok"],
            "Another import/validation is active",
        )
        try:
            assert_schema(conn)
            # Update statistics for new samples before subsequent joins.
            for table in (
                "scan_sample",
                "core_interval",
                "image_sample_mapping",
                "borehole_composite_part",
            ):
                conn.execute(sql.SQL("ANALYZE core.{}").format(sql.Identifier(table)))
            for u in mi.package_step(dest, 20)["datasets"]:
                print("Verify " + u["source_dataset_name"], flush=True)
                new = next(d for d in staged["datasets"] if d["dataset_id"] == u["dataset_id"])
                check = verifier.verify_dataset(conn, u, new, release, dest)
                check.update(
                    status="passed",
                    dataset_revision_id=new["dataset_revision_id"],
                    input_digest=manifest["datasets"][u["dataset_id"]]["content_sha256"],
                )
                checks.append(check)
                metadata = read(mi.prepared_context(u)["folder"] / "3_normalized_metadata.json")
                expected = {log["source_log_id"] for log in metadata["logs"]}
                actual = {
                    r["source_log_id"]
                    for r in conn.execute(
                        "SELECT source_log_id FROM core.scan_log WHERE dataset_revision_id=%s",
                        (new["dataset_revision_id"],),
                    )
                }
                require(actual == expected, "Dataset source log membership changed")
            from _publication import release_members

            inherited = release_members(conn, baseline["release_id"])
            current = release_members(conn, release)
            require(
                all(
                    any(
                        m["dataset_id"] == old["dataset_id"]
                        and m["dataset_revision_id"] == old["dataset_revision_id"]
                        for m in current
                    )
                    for old in inherited
                ),
                "Source release membership changed",
            )
            definition = conn.execute(
                "SELECT manifest FROM core.data_release WHERE id=%s", (release,)
            ).fetchone()["manifest"]
            decisions = definition["succession_decisions"]
            groups = install_composites(conn, release, decisions)
            for group in groups:
                layout = read_borehole_layout(conn, release, group["hole_id"])
                layouts.append(layout)
                full = layout["datasets_2d_full"]
                chosen = layout["parts_3d_selected"]
                require(len(full) == len(group["datasets"]), "2D dropped a source dataset")
                for d in full:
                    n = conn.execute(
                        "SELECT count(*) n FROM core.scan_sample WHERE axis_id=%s", (d["axis_id"],)
                    ).fetchone()["n"]
                    require(n == d["sample_count"], "2D source samples truncated")
                for i, p in enumerate(chosen):
                    expected_n = (
                        (p["sample_no_to"] - p["sample_no_from"] + 1)
                        if p["sample_no_from"] is not None
                        else 0
                    )
                    require(
                        expected_n == p["selected_sample_count"], "3D sample range/count mismatch"
                    )
                    if i:
                        boundary = p["selection_from_md_m"]
                        at = conn.execute(
                            "SELECT DISTINCT dataset_id FROM core.v_borehole_composite_samples WHERE composite_id=%s AND md_m=%s",
                            (p["composite_id"], boundary),
                        ).fetchall()
                        require(
                            at and all(r["dataset_id"] == p["dataset_id"] for r in at),
                            "Boundary not assigned exclusively to successor",
                        )
                expected_total = sum(p["selected_sample_count"] for p in chosen)
                real = conn.execute(
                    "SELECT count(*) n FROM core.v_borehole_composite_samples WHERE composite_id=%s",
                    (group["composite"]["id"],),
                ).fetchone()["n"]
                require(real == expected_total, "Composite view changed sample multiplicity")
            relations = {"dataset_source_and_mapping_checks": "passed"}
            previous = str(
                conn.execute(
                    "SELECT release_id FROM core.active_release WHERE singleton"
                ).fetchone()["release_id"]
            )
            require(
                previous in (baseline["release_id"], release),
                "Another release was activated; do not overwrite it",
            )
            from _publication import publish_release

            assets, locations = publish_release(
                conn, release, checks, __file__, expected_previous=baseline["release_id"]
            )
            size_by_id = {a["id"]: a["byte_size"] for a in assets}
            physical = {
                l["object_key"]: size_by_id[l["asset_id"]]
                for l in locations
                if l["backend"] == "local"
            }
            counts = conn.execute(
                """SELECT (SELECT count(*) FROM core.borehole) holes,
               (SELECT count(*) FROM core.release_dataset WHERE release_id=%s) datasets,
               (SELECT sum(a.sample_count) FROM core.sample_axis a JOIN core.release_dataset d ON d.dataset_revision_id=a.dataset_revision_id WHERE d.release_id=%s) full_samples,
               (SELECT count(*) FROM core.v_borehole_composite_samples WHERE release_id=%s) overview_samples,
               (SELECT count(*) FROM core.image_region r JOIN core.release_dataset d ON d.dataset_revision_id=r.dataset_revision_id WHERE d.release_id=%s) image_rows,
               (SELECT count(*) FROM core.spectral_array a JOIN core.release_dataset d ON d.dataset_revision_id=a.dataset_revision_id WHERE d.release_id=%s) spectral_arrays""",
                (release,) * 5,
            ).fetchone()
            from _schema_docs import generate

            generate(conn)
            result = {
                "status": "passed",
                "release_id": release,
                "previous_release_id": baseline["release_id"],
                "activated": True,
                "counts": counts,
                "new_dataset_checks": checks,
                "constraint_tests": "see independent tests",
                "legacy_membership_unchanged": True,
                "relation_violations": relations,
                "layouts": layouts,
                "database_bytes_with_history": conn.execute(
                    "SELECT pg_database_size(current_database()) n"
                ).fetchone()["n"],
                "unique_file_count": len(physical),
                "unique_file_bytes": sum(physical.values()),
                "schema_sha256": schema_hash(),
                "cloud_operations": False,
                "api_operations": False,
            }
            write(settings.multi_work_dir / "35_verification.json", result)
            report("35_multi_dataset_verification.json", result)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    print(
        f"Verified and activated {counts['holes']} holes / {counts['datasets']} datasets / {counts['full_samples']:,} full samples."
    )


if __name__ == "__main__":
    main_guard(main)
