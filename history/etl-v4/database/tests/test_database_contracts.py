"""Integration tests use only an owned disposable database and approved five-hole data."""

import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from fastapi import HTTPException
from fastapi.testclient import TestClient
from _db_common import ETL, LOCK_KEY, connection, insert, uid
from _db_files import digest, inside, sha
from _prepared_inputs import prepared_holes
from _run_reports import report
from _ingest import run_import
from _trial_support import create_trial, drop_trial, trial_schema, fingerprints, OperationSampler
from api.app import create_app, verify_file, choose_axis
from _legacy_verification import verify_and_publish


def make_synthetic(conn, base, n):
    bid = base["metadata"]["borehole"]["id"]
    br = base["metadata"]["borehole"]["metadata_revision_id"]
    d = uid("test-dataset", n)
    r = uid("test-revision", n)
    axis = uid("test-axis", n)
    tray = uid("test-tray", n)
    section = uid("test-section", n)
    insert(conn, "dataset", {"id": d, "borehole_id": bid, "source_dataset_id": f"SYNTHETIC_{n}"})
    insert(
        conn,
        "dataset_revision",
        {
            "id": r,
            "dataset_id": d,
            "borehole_id": bid,
            "borehole_revision_id": br,
            "source_dataset_name": f"SYNTHETIC_{n}",
            "source_snapshot_id": "synthetic",
            "pipeline_id": "synthetic",
            "input_digest": "synthetic",
            "mapping_version": 1,
            "normalized_metadata": {"synthetic_test_fixture": True},
        },
    )
    insert(
        conn,
        "sample_axis",
        {
            "id": axis,
            "dataset_revision_id": r,
            "sample_count": 1,
            "depth_min_m": 10.0,
            "depth_max_m": 10.0,
            "alignment_evidence": {"synthetic": True},
        },
    )
    for iid, kind, parent in ((tray, "tray", None), (section, "section", tray)):
        insert(
            conn,
            "core_interval",
            {
                "id": iid,
                "axis_id": axis,
                "interval_kind": kind,
                "ordinal": 0,
                "source_label": "0010",
                "parent_interval_id": parent,
                "sample_no_from": 0,
                "sample_no_to": 0,
                "observed_depth_min_m": 10.0,
                "observed_depth_max_m": 10.0,
                "source_log_id": "synthetic",
                "source_data_row": 0,
                "source_interval_convention": "closed",
            },
        )
    insert(
        conn,
        "scan_sample",
        {
            "axis_id": axis,
            "sample_no": 0,
            "md_m": 10.0,
            "tray_interval_id": tray,
            "section_interval_id": section,
            "tray_sample_no": 1,
            "section_sample_no": 1,
        },
    )
    return {"dataset": d, "revision": r, "axis": axis, "tray": tray, "section": section}


class DatabaseContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab = create_trial("test")
        trial_schema(cls.lab)
        cls.prepared = prepared_holes()
        cls.first = cls.prepared[0]
        # A real source-COPY interruption must roll back all business rows of that hole.
        try:
            run_import(["05KCD001"], dbname=cls.lab, failure_hole="05KCD001")
        except ValueError as e:
            if "Injected interruption" not in str(e):
                raise
        else:
            raise AssertionError("Injected import unexpectedly succeeded")
        with connection(dbname=cls.lab) as c:
            cls.failed_state = {
                "samples": c.execute("SELECT count(*) AS n FROM core.scan_sample").fetchone()["n"],
                "revisions": c.execute(
                    "SELECT count(*) AS n FROM core.dataset_revision"
                ).fetchone()["n"],
                "audit": c.execute(
                    "SELECT count(*) AS n FROM core.ingest_run WHERE status='failed'"
                ).fetchone()["n"],
            }
        with OperationSampler(cls.lab) as sampler:
            run_import(dbname=cls.lab)
        report("test_full_import_operation_sampling.json", sampler.result())
        cls.before = fingerprints(cls.lab)
        cls.repeat = run_import(dbname=cls.lab)
        cls.after = fingerprints(cls.lab)
        with connection(dbname=cls.lab) as c:
            with c.transaction():
                from _publication import stage_release

                members = [
                    {
                        "dataset_id": h["metadata"]["dataset"]["id"],
                        "dataset_revision_id": h["metadata"]["dataset_revision"]["id"],
                    }
                    for h in cls.prepared
                ]
                cls.base_release = stage_release(c, members, "local_base_v2")
                cls.single_release = stage_release(c, members[:1], "local_base_v2")
                cls.a = make_synthetic(c, cls.first, 1)
                cls.b = make_synthetic(c, cls.first, 2)
                cls.release = uid("synthetic-release")
                insert(
                    c,
                    "data_release",
                    {
                        "id": cls.release,
                        "manifest_sha256": digest({"synthetic": True}),
                        "release_kind": "synthetic_test_only",
                        "manifest": {"synthetic_test_fixture": True},
                    },
                )
                for item in (cls.a, cls.b):
                    insert(
                        c,
                        "release_dataset",
                        {
                            "release_id": cls.release,
                            "dataset_id": item["dataset"],
                            "dataset_revision_id": item["revision"],
                        },
                    )

    @classmethod
    def tearDownClass(cls):
        drop_trial(cls.lab)

    def test_failed_copy_rolls_back_business_rows_but_preserves_audit(self):
        self.assertEqual(self.failed_state, {"samples": 0, "revisions": 0, "audit": 1})

    def test_repeat_import_is_byte_logically_identical(self):
        self.assertEqual(self.before, self.after)
        self.assertTrue(all(h["action"] == "already_present" for h in self.repeat["holes"]))

    def test_concurrent_import_lock_rejects_second_writer(self):
        with connection(dbname=self.lab) as c:
            c.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
            try:
                with self.assertRaisesRegex(RuntimeError, "Another importer"):
                    run_import(["05KCD001"], dbname=self.lab)
            finally:
                c.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))

    def test_reader_cannot_write_even_when_readonly_setting_disabled(self):
        with connection("reader", dbname=self.lab) as c:
            c.execute("SET default_transaction_read_only=off")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                c.execute(
                    "INSERT INTO core.borehole(id,provider_code,source_hole_id) VALUES (%s,%s,%s)",
                    (str(uuid4()), "test", "forbidden"),
                )

    def test_existing_sample_values_are_immutable(self):
        with connection(dbname=self.lab) as c:
            with self.assertRaises(psycopg.errors.ObjectNotInPrerequisiteState):
                with c.transaction():
                    c.execute(
                        "UPDATE core.scan_sample SET md_m=999 WHERE axis_id=%s AND sample_no=0",
                        (self.a["axis"],),
                    )

    def test_same_sample_number_cannot_be_inserted_twice(self):
        with connection(dbname=self.lab) as c:
            with self.assertRaises(psycopg.errors.UniqueViolation):
                with c.transaction():
                    c.execute(
                        "INSERT INTO core.scan_sample SELECT * FROM core.scan_sample WHERE axis_id=%s",
                        (self.a["axis"],),
                    )

    def test_same_hole_multiple_datasets_and_overlapping_depth_are_retained(self):
        with TestClient(create_app(self.lab)) as client:
            response = client.get(
                "/v1/boreholes/05KCD001/datasets", params={"release_id": self.release}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["items"]), 2)
            for item in (self.a, self.b):
                r = client.get(
                    f"/v1/datasets/{item['revision']}/samples", params={"release_id": self.release}
                )
                self.assertEqual(r.status_code, 200)
                rows = r.json()["items"]
                self.assertEqual(
                    [(x["axis_id"], x["sample_no"], x["md_m"]) for x in rows],
                    [(item["axis"], 0, 10.0)],
                )

    def test_cross_revision_axis_binding_is_rejected(self):
        with connection(dbname=self.lab) as c:
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with c.transaction():
                    lid = str(uuid4())
                    insert(
                        c,
                        "scan_log",
                        {
                            "id": lid,
                            "dataset_revision_id": self.a["revision"],
                            "source_log_id": "synthetic",
                            "source_log_name": "synthetic",
                            "log_kind": "scalar",
                            "availability_status": "payload_present",
                            "definition_status": "unconfirmed",
                            "source_metadata_file": "synthetic",
                            "normalized_metadata": {},
                        },
                    )
                    insert(
                        c,
                        "log_axis_binding",
                        {
                            "log_id": lid,
                            "dataset_revision_id": self.a["revision"],
                            "axis_id": self.b["axis"],
                            "status": "verified",
                            "basis": "intentionally invalid fixture",
                        },
                    )

    def test_interval_endpoint_must_reference_a_real_sample(self):
        with connection(dbname=self.lab) as c:
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with c.transaction():
                    insert(
                        c,
                        "core_interval",
                        {
                            "id": str(uuid4()),
                            "axis_id": self.a["axis"],
                            "interval_kind": "tray",
                            "ordinal": 1,
                            "source_label": "0011",
                            "sample_no_from": 0,
                            "sample_no_to": 100,
                            "source_log_id": "synthetic",
                            "source_data_row": 1,
                            "source_interval_convention": "closed",
                        },
                    )

    def test_holes_outside_input_manifest_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "absent from this input manifest"):
            run_import(["12CADD001"], dbname=self.lab)

    def test_unpublished_revision_cannot_be_read_through_another_release(self):
        first_rev = self.first["metadata"]["dataset_revision"]["id"]
        with TestClient(create_app(self.lab)) as client:
            r = client.get(f"/v1/datasets/{first_rev}/logs", params={"release_id": self.release})
            self.assertEqual(r.status_code, 404)
            self.assertEqual(client.get("/v1/boreholes").status_code, 503)

    def test_axis_selection_never_silently_combines_different_axes(self):
        with self.assertRaises(HTTPException) as e:
            choose_axis([{"id": self.a["axis"]}, {"id": self.b["axis"]}], None)
        self.assertEqual(e.exception.status_code, 422)

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            inside(ETL, ETL / "../outside")
        with connection(dbname=self.lab) as c:
            asset = c.execute("SELECT id,sha256 FROM core.asset LIMIT 1").fetchone()
            with self.assertRaises(psycopg.errors.CheckViolation):
                with c.transaction():
                    insert(
                        c,
                        "asset_location",
                        {
                            "id": str(uuid4()),
                            "asset_id": asset["id"],
                            "backend": "local",
                            "root_key": "etl4",
                            "object_key": "../../outside",
                            "access_status": "verified_local",
                            "verified_sha256": asset["sha256"],
                        },
                    )

    def test_checksum_rejects_corrupted_fixture_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "payload"
            p.write_bytes(b"original")
            expected = sha(p)
            p.write_bytes(b"changed!")
            with self.assertRaises(HTTPException) as e:
                verify_file(str(p), expected, p.stat().st_size, p.stat().st_mtime_ns)
            self.assertEqual(e.exception.status_code, 503)

    def test_special_labels_weights_and_nulls_survive_actual_api(self):
        active = self.base_release
        with TestClient(create_app(self.lab)) as client:
            for name in ("Tray", "Wt2 sjCLST"):
                log = next(
                    x for x in self.first["metadata"]["logs"] if x["source_log_name"] == name
                )
                asset = next(
                    x
                    for x in self.first["storage"]["assets"]
                    if x.get("source_log_id") == log["source_log_id"]
                )
                with __import__("pyarrow.parquet", fromlist=["ParquetFile"]).ParquetFile(
                    self.first["folder"] / asset["relative_path"]
                ) as pf:
                    expected = pf.read_row_group(0).slice(0, 5).to_pylist()
                r = client.get(
                    f"/v1/logs/{log['id']}/values", params={"release_id": active, "limit": 5}
                )
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["items"], expected)

    def test_failed_api_validation_keeps_the_previous_release(self):
        with connection(dbname=self.lab) as c:
            c.execute(
                "INSERT INTO core.active_release(singleton,release_id) VALUES (true,%s)",
                (self.base_release,),
            )
        try:
            with patch(
                "_legacy_verification.api_checks",
                side_effect=ValueError("simulated API verification failure"),
            ):
                with self.assertRaisesRegex(ValueError, "simulated API verification failure"):
                    verify_and_publish(["05KCD001"], dbname=self.lab, check_api=True)
            with connection(dbname=self.lab) as c:
                after = str(
                    c.execute("SELECT release_id FROM core.active_release").fetchone()["release_id"]
                )
            self.assertEqual(self.base_release, after)
        finally:
            with connection(dbname=self.lab) as c:
                c.execute("DELETE FROM core.active_release")

    def test_previous_single_hole_release_remains_readable(self):
        previous = self.single_release
        with TestClient(create_app(self.lab)) as client:
            r = client.get("/v1/boreholes", params={"release_id": previous})
            self.assertEqual(r.status_code, 200)
            self.assertEqual([x["source_hole_id"] for x in r.json()["items"]], ["05KCD001"])


if __name__ == "__main__":
    unittest.main()
