"""Twelve-borehole rerun helper: inspect existing identities and record stage results without modifying business source."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ETL = ROOT / "etl4"
CODE = ETL / "database"
WORK = ETL / "single_final_check_20260930"
CONFIG = ETL / "refactor_work/database/runtime/local_config.json"
BATCH = WORK / "batch.json"
REPORTS = Path(__file__).resolve().parent
DATABASE = "etl4_test_single_final_20260930"
sys.path[:0] = [str(CODE), str(ETL)]

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from _batch_files import DATA_TABLES, RELEASE_TABLES
from _db_common import uid
from _db_files import digest, encoded, read
from _media_manifest import unpack_document
from _prepared_inputs import prepared_holes
from _settings import raw_asset_path, settings

settings.raw_dir = ETL
settings.work_dir = WORK
settings.db_config = CONFIG
settings.dbname = DATABASE


def save(name, value):
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / name).write_bytes(encoded(value))


def connect():
    config = read(CONFIG)
    role = config["roles"]["owner"]
    return psycopg.connect(host=config["host"], port=config["port"], dbname=DATABASE,
                           user=role["user"], password=role["password"],
                           row_factory=dict_row, autocommit=True, connect_timeout=3,
                           options="-c default_transaction_read_only=on -c statement_timeout=10000")


def database_snapshot():
    with connect() as conn:
        actual = conn.execute("SELECT current_database() name, encode(current_setting('data_directory')::bytea,'hex') directory_hex").fetchone()
        raw_directory = bytes.fromhex(actual.pop("directory_hex"))
        try:
            actual["directory"] = raw_directory.decode("utf-8")
        except UnicodeDecodeError:
            actual["directory"] = raw_directory.decode("mbcs")
        expected_cluster = ETL / "refactor_work/database/runtime/pgdata"
        if actual["name"] != DATABASE or Path(actual["directory"]).resolve() != expected_cluster.resolve():
            raise ValueError("Target database or existing cluster differs")
        current = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()
        revisions = conn.execute("SELECT id,dataset_id,input_digest FROM core.dataset_revision ORDER BY dataset_id,id").fetchall()
        members = conn.execute("SELECT dataset_id,dataset_revision_id FROM core.release_dataset WHERE release_id=%s ORDER BY dataset_id",
                               (current["release_id"],)).fetchall()
        counts = {}
        for name in DATA_TABLES + RELEASE_TABLES:
            counts[name] = conn.execute(sql.SQL("SELECT count(*) n FROM core.{}").format(sql.Identifier(name))).fetchone()["n"]
        return json.loads(encoded({"database": actual["name"], "cluster": actual["directory"],
                                  "release_id": current["release_id"], "revisions": revisions,
                                  "members": members, "counts": counts}))


def planned_inputs():
    batch = read(BATCH)
    identities, package_reports, files = [], [], {}

    def record_file(path, size=None):
        path = path.resolve()
        if path in files:
            if size is not None and files[path] != size:
                raise ValueError("Conflicting expected file sizes: " + str(path))
            return
        if not path.is_file():
            raise ValueError("Missing declared source: " + str(path))
        actual_size = path.stat().st_size
        if size is not None and actual_size != size:
            raise ValueError("Declared source size differs: " + str(path))
        files[path] = actual_size

    for package_input in batch["packages"]:
        folder = ETL / package_input["directory"]
        prepared_work = ETL / package_input["prepared_work_dir"]
        manifest = read(folder / "manifest.json")
        if digest(manifest) != folder.name:
            raise ValueError("Existing package manifest identity differs: " + str(folder))
        units = unpack_document(read(folder / "steps/20.json"))["datasets"]
        legacy = None
        for name, file in manifest["files"].items():
            record_file(folder / name, file["byte_size"])
        for unit in units:
            if "prepared_hashes" in unit:
                prepared = prepared_work / "processing/outputs" / unit["prepared_directory"]
                context = {"folder": prepared, "prepared_hashes": unit["prepared_hashes"],
                           "metadata": read(prepared / "3_normalized_metadata.json"),
                           "storage": read(prepared / "5_storage_report.json")}
            else:
                if legacy is None:
                    legacy = {item["metadata"]["dataset"]["id"]: item
                              for item in prepared_holes(work_dir=prepared_work, verify_files=False)}
                context = legacy[unit["dataset_id"]]
                prepared = context["folder"]
            original = context["metadata"]["dataset_revision"]
            for name in context["prepared_hashes"]:
                record_file(prepared / name)
            for asset in context["storage"]["raw_assets"]:
                record_file(raw_asset_path(unit["hole_id"], asset), asset["byte_size"])
            for asset in context["storage"]["assets"]:
                record_file(prepared / asset["relative_path"], asset["byte_size"])
            identity = {"dataset_id": unit["dataset_id"], "source_snapshot_id": original["source_snapshot_id"],
                        "preparation_rules": original["pipeline_id"],
                        "media_input_key": manifest["datasets"][unit["dataset_id"]]["input_key"],
                        "final_rules": batch.get("rule_versions", {}).get(unit["source_dataset_id"], "single-final-v1"),
                        "raw_files": sorted([a["source_relative_path"], a["byte_size"], a["sha256"]]
                                            for a in context["storage"]["raw_assets"])}
            key = digest(identity)
            names = ["3_normalized_metadata.json", "4_sample_axis.parquet", "4_core_intervals.json", "4_image_frames.json"]
            names.extend(a["relative_path"] for a in context["storage"]["assets"])
            prepared_hashes = {name: context["prepared_hashes"][name] for name in sorted(set(names))
                               if (prepared / name).is_file()}
            content = digest({"prepared": prepared_hashes, "bindings": context["prepared_hashes"]["4_axis_bindings.json"],
                              "media": manifest["datasets"][unit["dataset_id"]]["content_sha256"]})
            identities.append({"hole_id": unit["hole_id"], "dataset_id": unit["dataset_id"],
                               "dataset_revision_id": uid("final-revision", unit["dataset_id"], key),
                               "input_digest": content})
        package_reports.append({**package_input, "datasets": len(units), "package_files": len(manifest["files"])})
    if len(identities) != 17 or len({i["hole_id"] for i in identities}) != 12:
        raise ValueError("Expected exactly twelve holes and seventeen datasets")
    return {"packages": package_reports, "datasets": identities, "unique_declared_files": len(files),
            "unique_declared_bytes": sum(files.values()), "file_check": "existence and size only; acceptance performs hashes"}


def preflight():
    started = time.perf_counter()
    try:
        snapshot = database_snapshot()
    except Exception as exc:
        result = {"status": "database_unavailable", "error_type": type(exc).__name__, "elapsed_seconds": time.perf_counter() - started}
        save("local_preflight.json", result)
        print(json.dumps(result), flush=True)
        return 2
    inputs = planned_inputs()
    existing = {row["id"]: row for row in snapshot["revisions"]}
    expected_members = []
    for item in inputs["datasets"]:
        stored = existing.get(item["dataset_revision_id"])
        if stored is None or stored["dataset_id"] != item["dataset_id"] or stored["input_digest"] != item["input_digest"]:
            raise ValueError("Input identity would create or change a version: " + item["hole_id"] + " / " + item["dataset_id"])
        expected_members.append({key: item[key] for key in ("dataset_id", "dataset_revision_id")})
    if sorted(expected_members, key=lambda row: row["dataset_id"]) != snapshot["members"]:
        raise ValueError("The twelve-hole batch differs from current release members")
    result = {"status": "passed", "database": snapshot, "inputs": inputs, "elapsed_seconds": time.perf_counter() - started}
    save("local_preflight.json", result)
    print(json.dumps({"status": "passed", "database": DATABASE, "release_id": snapshot["release_id"],
                      "holes": 12, "datasets": 17, "files": inputs["unique_declared_files"],
                      "existing_versions_only": True, "elapsed_seconds": result["elapsed_seconds"]}), flush=True)
    return 0


def compare():
    before = read(REPORTS / "local_preflight.json")["database"]
    after = database_snapshot()
    result = {"status": "passed" if before == after else "changed", "before": before, "after": after}
    save("local_after_replay.json", result)
    print(json.dumps({"status": result["status"], "business_counts_unchanged": before["counts"] == after["counts"],
                      "revision_members_unchanged": before["members"] == after["members"], "release_id": after["release_id"]}), flush=True)
    return 0 if before == after else 1


def run_stage(name, script, arguments):
    command = [sys.executable, "-B", "-X", "utf8", str(CODE / script), *arguments]
    started = time.perf_counter()
    log_path = REPORTS / (name + ".log")
    print("START " + name, flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        child = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    result = {"stage": name, "exit_code": child.returncode, "elapsed_seconds": time.perf_counter() - started,
              "command": command, "log": str(log_path)}
    save(name + ".json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if child.returncode:
        print(log_path.read_text(encoding="utf-8")[-4000:], flush=True)
        raise RuntimeError("Stage failed: " + name)


def acceptance_and_export():
    initial = read(REPORTS / "local_preflight.json")
    if initial["status"] != "passed":
        raise ValueError("Successful version identity preflight required")
    common = ["--raw-dir", str(ETL), "--work-dir", str(WORK), "--dbname", DATABASE, "--db-config", str(CONFIG)]
    for index, package in enumerate(read(BATCH)["packages"], 1):
        run_stage(f"local_28_{index}", "28_import_media_revision.py",
                  common + ["--package-only", "--package", str(ETL / package["directory"]),
                            "--prepared-work-dir", str(ETL / package["prepared_work_dir"])])
    run_stage("local_37", "37_import_final_version.py", common + ["--batch", str(BATCH)])
    if compare():
        raise ValueError("Business data changed during intended replay; export stopped")
    run_stage("local_38", "38_export_batch.py", common + ["--output-dir", str(WORK / "database/exports")])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "compare", "acceptance_and_export"))
    args = parser.parse_args()
    try:
        function = globals()[args.action]
        raise SystemExit(function())
    except Exception as exc:
        save("local_stopped.json", {"status": "stopped", "action": args.action,
                                   "error_type": type(exc).__name__, "detail": str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "See stage log"})
        print(str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
