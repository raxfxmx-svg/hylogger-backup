"""Shared IO and provenance helpers; processing entry points are numbered files."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
import time
import uuid
from pathlib import Path

WORK = Path(__file__).resolve().parent
SOURCE = WORK.parent
BASELINE = WORK / "preparation_baseline.json"
OUTPUT = WORK / "outputs"
ALLOWED = ("05KCD001", "07THD002", "07THD003", "09ATD015", "09ATD019")
METADATA = (
    "borehole.json", "datasets.json", "logs_scalar.json", "scalar_manifest.json",
    "logs_spectral.json", "spectral_manifest.json", "logs_profilometer.json",
    "profilometer_manifest.json", "logs_image.json", "image_logs_by_dataset.json",
    "images_manifest.json", "tray_depths.json", "package_manifest.json",
)


def _pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError(f"Duplicate JSON key: {k}")
        result[k] = v
    return result


def parse_json(text):
    def invalid(value):
        raise ValueError(f"Non-finite JSON token: {value}")
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid)


def read_json(path):
    return parse_json(Path(path).read_text(encoding="utf-8-sig"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inside(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError(f"Path leaves the permitted directory: {path}")
    return path


def source_path(hole, relative):
    if hole not in ALLOWED:
        raise ValueError(f"Hole is outside the approved scope: {hole}")
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"Source path must be relative without traversal: {relative}")
    return inside(SOURCE / hole, SOURCE / hole / relative_path)


def atomic_bytes(path, data):
    path = inside(WORK, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    atomic_bytes(path, json_bytes(value))


def write_text(path, value):
    atomic_bytes(path, value.encode("utf-8"))


def pipeline_id():
    # Step 6 verifies outputs without changing them; it records its own code hash.
    scripts = sorted(WORK.glob("[1-5]_*.py")) + [Path(__file__), BASELINE]
    return digest({"files": {p.name: sha_file(p) for p in scripts}, "environment": environment()})


def environment():
    return {"python": platform.python_version(), **{
        name: importlib.metadata.version(name) for name in ("numpy", "Pillow", "pyarrow")}}


def baseline_for(hole):
    baseline = read_json(BASELINE)
    if tuple(baseline["active_holes"]) != ALLOWED:
        raise ValueError("Baseline allowlist differs from the approved five-hole scope")
    return next(x for x in baseline["holes"] if x["hole_id"] == hole)


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--holes", nargs="+", choices=ALLOWED, default=list(ALLOWED))
    args = parser.parse_args()
    args.holes = list(dict.fromkeys(args.holes))
    return args


def source_json(hole, name):
    return read_json(source_path(hole, name))


def snapshot(hole):
    latest = read_json(OUTPUT / hole / "latest_processing.json")
    folder = inside(OUTPUT, OUTPUT / latest["relative_directory"])
    if not folder.is_relative_to((OUTPUT / hole).resolve()):
        raise ValueError("Processing pointer belongs to another hole")
    inventory = read_json(folder / "1_inventory.json")
    if inventory["pipeline_id"] != pipeline_id():
        raise ValueError("Processing code or baseline changed. Run step 1 again.")
    for entry in inventory["files"]:
        path = source_path(hole, entry["path"])
        stat = path.stat()
        if stat.st_size != entry["size_bytes"] or stat.st_mtime_ns != entry["mtime_ns"]:
            raise ValueError(f"Source changed after inventory: {hole}/{entry['path']}")
    return folder, inventory


def require_report(folder, name):
    report = read_json(folder / name)
    if report["status"] not in ("passed", "passed_with_issues"):
        raise ValueError(f"Prerequisite has not passed: {name}")
    return report


def report_base(inventory, step, previous=None):
    return {
        "hole_id": inventory["hole_id"], "step": step,
        "pipeline_id": inventory["pipeline_id"],
        "source_snapshot_id": inventory["source_snapshot_id"],
        "python_version": platform.python_version(),
        "previous_report_sha256": sha_file(previous) if previous else None,
    }


def stable_id(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "etl4:" + ":".join(map(str, parts))))


def issue(code, scope, detail, severity="warning", evidence=None):
    return {"code": code, "scope": scope, "severity": severity,
            "detail": detail, "evidence": evidence}


class HashedLines:
    def __init__(self, stream):
        self.stream, self.sha256, self.first = stream, hashlib.sha256(), True

    def __iter__(self):
        for line in self.stream:
            self.sha256.update(line)
            text = line.decode("utf-8-sig" if self.first else "utf-8")
            self.first = False
            yield text


def scalar_rows(hole, entry):
    """Small selective rereads for alignment; full integrity was checked in step 2."""
    with source_path(hole, entry["file"]).open("rb") as stream:
        lines = HashedLines(stream)
        reader = csv.reader(lines, strict=True)
        header = next(reader)
        for index, row in enumerate(reader):
            if len(row) != 3:
                raise ValueError(f"Malformed scalar row: {entry['file']} / {index}")
            yield index, row
        if lines.sha256.hexdigest() != entry["sha256"]:
            raise ValueError(f"Source hash changed: {entry['file']}")


def run_holes(description, fn):
    args = arguments(description)
    for hole in args.holes:
        print(f"{hole}: {description}", flush=True)
        try:
            fn(hole)
        except Exception as exc:
            write_json(OUTPUT / "failures" / f"{hole}_{time.time_ns()}.json", {
                "hole_id": hole, "step_description": description,
                "exception_type": type(exc).__name__, "detail": str(exc),
                "pipeline_id": pipeline_id(), "status": "failed",
            })
            raise
    print("Completed: " + ", ".join(args.holes), flush=True)


def fail_main(fn):
    try:
        fn()
    except Exception as exc:
        print(f"STOP: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
