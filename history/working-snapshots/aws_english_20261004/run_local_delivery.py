"""Run the current numbered workflow for the English AWS delivery.
Run the current numbered pipeline to produce the English AWS delivery.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ETL = ROOT / "etl4"
WORK = ROOT / "etl4_english_delivery_20261004"
CONFIG = ETL / "refactor_work/database/runtime/local_config.json"
DATABASE = "etl4_english_delivery_20261004"
SINGLE = ["05KCD001", "07THD002", "07THD003", "09ATD015", "09ATD019", "09ATRCD025", "09THD028", "12BRDDH003", "14CADD003"]
MULTI = ["12CADD001", "14KDD001", "15EIS001"]


def write(name, data):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def run(name, script, extra=(), configure=True):
    command = [sys.executable, "-B", "-X", "utf8", str(ETL / script)]
    if configure:
        command += ["--raw-dir", str(ETL), "--work-dir", str(WORK), "--dbname", DATABASE, "--db-config", str(CONFIG)]
    command += list(map(str, extra))
    started = time.monotonic()
    print("START " + name, flush=True)
    with (HERE / (name + ".log")).open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    record = {"stage": name, "exit_code": result.returncode, "seconds": round(time.monotonic() - started, 3), "command": command}
    write(name + ".json", record)
    print(json.dumps({k: v for k, v in record.items() if k != "command"}), flush=True)
    if result.returncode:
        print((HERE / (name + ".log")).read_text(encoding="utf-8")[-5000:], flush=True)
        raise RuntimeError("Stage failed: " + name)


def copy_evidence(source, target):
    if not source.is_dir():
        raise ValueError("Missing existing evidence directory: " + str(source))
    for path in source.rglob("*"):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if destination.read_bytes() != path.read_bytes():
                    raise ValueError("Conflicting cached reference: " + str(destination))
            else:
                shutil.copyfile(path, destination)


def prepare():
    WORK.mkdir(exist_ok=True)
    for hole in SINGLE + MULTI:
        count = len(json.loads((ETL / hole / "datasets.json").read_text(encoding="utf-8-sig")))
        if (count == 1) != (hole in SINGLE):
            raise ValueError("Unexpected dataset route: " + hole)
    for previous in ["refactor_work", "new_input_check", "new_input_check/random_09THD028", "structure_input_20260930"]:
        copy_evidence(ETL / previous / "database/media_evidence/spectra", WORK / "database/media_evidence/spectra")
    for kind in ["membership", "spectra"]:
        copy_evidence(ETL / "refactor_work/database/multi_work/evidence" / kind, WORK / "database/multi_work/evidence" / kind)
    for name, script in [("01_inventory", "1_inventory.py"), ("02_validate", "2_validate_payloads.py"),
                         ("03_metadata", "3_normalize_metadata.py"), ("04_alignment", "4_align_samples.py"),
                         ("05_columnar", "5_build_columnar.py"), ("06_prepared", "6_verify_prepared_data.py")]:
        run(name, "processing/" + script, ["--holes", *SINGLE] if name.startswith("01") else [])
    run("07_inputs", "database/7_preflight_database.py", ["--inputs-only"])
    steps = [(20, "audit_spectral_sources"), (21, "verify_spectral_bindings"), (22, "prepare_spectral_access"),
             (23, "audit_dataset_image_groups"), (24, "detect_image_rows"), (25, "review_image_row_regions")]
    for number, name in steps:
        run(f"{number}_{name}", f"database/{number}_{name}.py", ["--files-only"] if number == 20 else [])
    run("31_sources", "database/31_audit_multi_dataset_sources.py", ["--holes", *MULTI])
    run("32_payloads", "database/32_prepare_multi_dataset_payloads.py")
    run("33_media_candidates", "database/33_prepare_multi_dataset_media.py")
    write("preparation_status.json", {"status": "awaiting_crop_review", "work_dir": str(WORK)})


def finish():
    run("25_reviewed", "database/25_review_image_row_regions.py", ["--record-reviewed"])
    run("26_bindings", "database/26_bind_image_rows_to_samples.py")
    run("27_crops", "database/27_build_image_row_assets.py")
    run("28_single", "database/28_import_media_revision.py")
    single = json.loads((WORK / "database/reports/28_media_package.json").read_text(encoding="utf-8"))["package_object_key"]
    run("33_reviewed", "database/33_prepare_multi_dataset_media.py", ["--record-reviewed"])
    run("28_multi", "database/28_import_media_revision.py", ["--media-work-dir", WORK / "database/multi_work/media", "--evidence-dir", WORK / "database/multi_work/evidence"])
    multi = json.loads((WORK / "database/reports/28_media_package.json").read_text(encoding="utf-8"))["package_object_key"]
    old = json.loads((ETL / "single_final_check_20260930/batch.json").read_text(encoding="utf-8"))
    decisions = old["decisions"]
    decisions["confirmation_text"] = "The project owner confirmed the stated order and display switch points."
    batch = {"packages": [{"directory": directory, "prepared_work_dir": str(WORK)} for directory in [single, multi]], "decisions": decisions}
    (WORK / "batch.json").write_text(json.dumps(batch, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    run("07_runtime", "database/7_preflight_database.py", ["--runtime-only", "--work-dir", ETL / "refactor_work", "--dbname", DATABASE], configure=False)
    import_export()


def import_export():
    # Reuse the confirmed running cluster when process-status access is unavailable.
    sys.path[:0] = [str(ETL / "database"), str(ETL)]
    from _settings import settings
    from _db_common import connection
    settings.work_dir, settings.raw_dir, settings.db_config, settings.dbname = WORK, ETL, CONFIG, DATABASE
    with connection(dbname="postgres") as conn:
        raw = bytes.fromhex(conn.execute("SELECT encode(current_setting('data_directory')::bytea,'hex') value").fetchone()["value"])
        try:
            actual = raw.decode("utf-8")
        except UnicodeDecodeError:
            actual = raw.decode("mbcs")
        if Path(actual).resolve() != (ETL / "refactor_work/database/runtime/pgdata").resolve():
            raise ValueError("Connected to an unexpected local cluster")
    write("07_existing_runtime.json", {"status": "passed", "mode": "reuse_confirmed_running_cluster"})
    run("08_schema", "database/8_apply_schema.py")
    from schema_comments import apply_comments
    with connection() as conn, conn.transaction():
        apply_comments(conn)
    run("37_import", "database/37_import_final_version.py", ["--batch", WORK / "batch.json"])
    run("38_export", "database/38_export_batch.py", ["--acceptance", WORK / "database/reports/local_acceptance_2.json", "--output-dir", WORK / "database/exports"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "finish", "import_export"])
    args = parser.parse_args()
    HERE.mkdir(exist_ok=True)
    {"prepare": prepare, "finish": finish, "import_export": import_export}[args.phase]()
