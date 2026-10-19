"""Run the selected numbered steps and save logs; stop immediately on failure."""

import json
import subprocess
import sys
import time
from pathlib import Path

AUDIT = Path(__file__).resolve().parent
ETL = AUDIT.parents[1] / "etl4"
selection = json.loads((AUDIT / "selection.json").read_text(encoding="utf-8"))
phase, *numbers = sys.argv[1:]
timings = []
for value in numbers:
    step = int(value)
    folder = "processing" if step <= 6 else "database"
    script, = (ETL / folder).glob(f"{step}_*.py")
    args = [sys.executable, "-B", "-X", "utf8", str(script), "--work-dir", selection["work_dir"], "--dbname", selection["database"]]
    if step == 1:
        args += ["--holes-file", str(AUDIT / "selected_holes.txt")]
    if step == 7:
        args += ["--inputs-only"]
    if step == 10:
        args += ["--no-publish", "--check-api"]
    if step == 20:
        report = json.loads((Path(selection["work_dir"]) / "database/reports/10_verification.json").read_text(encoding="utf-8"))
        args += ["--source-release", report["release_id"]]
    if step == 21:
        args += ["--fetch-reference"]
    if step == 25 and phase == "reviewed":
        args += ["--record-reviewed"]
    if step == 29:
        args += ["--no-activate"]
    print(f"Start {phase} step {step}: {selection['hole']}", flush=True)
    start = time.perf_counter()
    with (AUDIT / f"{phase}_step_{step}.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT)
    timings.append({"step": step, "seconds": round(time.perf_counter() - start, 3), "exit_code": result.returncode})
    (AUDIT / f"{phase}_timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
    print(f"Finish step {step}: {result.returncode}, {timings[-1]['seconds']} seconds", flush=True)
    if result.returncode:
        print((AUDIT / f"{phase}_step_{step}.log").read_text(encoding="utf-8")[-10000:], flush=True)
        raise SystemExit(result.returncode)
