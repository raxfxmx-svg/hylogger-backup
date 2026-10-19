"""Run selected steps only in this independent work directory and database; stop on failure."""

import json
from pathlib import Path
import subprocess
import sys
import time

AUDIT = Path(__file__).resolve().parent
ETL = AUDIT.parents[1] / "etl4"
selection = json.loads((AUDIT / "selection.json").read_text(encoding="utf-8"))
phase, *numbers = sys.argv[1:]
timings = []
for number in numbers:
    step = int(number)
    if step == 8:
        raise ValueError('Use only existing databases; do not create databases or alter schemas')
    script, = (ETL / ("processing" if step <= 6 else "database")).glob(f"{step}_*.py")
    args = [sys.executable, "-B", "-X", "utf8", str(script), "--work-dir", selection["work_dir"], "--dbname", selection["database"]]
    if step == 10:
        args += ["--no-publish"]
    if step == 29:
        args += ["--no-activate"]
    if step == 1:
        args += ["--holes-file", str(AUDIT / "selected_holes.txt")]
    if step == 7:
        args += ["--inputs-only"]
    if step == 20:
        report = json.loads((Path(selection["work_dir"]) / "database/reports/10_verification.json").read_text(encoding="utf-8"))
        args += ["--source-release", report["release_id"]]
    if step == 21 and phase != "replay":
        args += ["--fetch-reference"]
    if step == 25 and phase == "reviewed":
        args += ["--record-reviewed"]
    # Use the official sealed package to exercise the modified loading entry point on reruns.
    if step in (28, 29) and phase == "replay":
        staged = json.loads((Path(selection["work_dir"]) / "database/reports/28_media_import.json").read_text(encoding="utf-8"))
        args += ["--package", str(Path(selection["work_dir"]) / "database" / staged["package_directory"])]
        if step == 29:
            args += ["--release", staged["release_id"]]
    log_path = AUDIT / f"{phase}_step_{step}.log"
    if log_path.exists():
        raise ValueError('Log already exists; choose a new run name')
    print(f"Start {phase} step {step}: {selection['hole']}", flush=True)
    start = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as stream:
        result = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT)
    timings.append({"step": step, "seconds": round(time.perf_counter() - start, 3), "exit_code": result.returncode})
    (AUDIT / f"{phase}_timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
    print(f"Finish step {step}: exit={result.returncode}, seconds={timings[-1]['seconds']}", flush=True)
    if result.returncode:
        print(log_path.read_text(encoding="utf-8")[-10000:], flush=True)
        raise SystemExit(result.returncode)
