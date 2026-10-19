"""Prepare each dataset with an explicitly supplied parsing context."""

import copy
import sys
from _db_common import ETL, PREPARED, ROOT, digest, inside, main_guard, read, sha, write
from _multi_common import MULTI, MULTI_HOLES, PROCESSING, audit, module, raw_metadata, require
from _settings import StepParser


def selected_metadata(raw, u):
    r = copy.deepcopy(raw)
    did = u["source_dataset_id"]
    ids = u["log_ids"]
    r["datasets.json"] = [d for d in r["datasets.json"] if d["dataset_id"] == did]
    for kind, names in {
        "scalar": ("logs_scalar.json", "scalar_manifest.json"),
        "spectral": ("logs_spectral.json", "spectral_manifest.json"),
        "profile": ("logs_profilometer.json", "profilometer_manifest.json"),
        "image": ("logs_image.json", "image_logs_by_dataset.json"),
    }.items():
        for name in names:
            r[name] = [x for x in r[name] if x["log_id"] in ids[kind]]
    r["images_manifest.json"] = {
        k: [x for x in v if x["dataset_id"] == did] for k, v in r["images_manifest.json"].items()
    }
    r["tray_depths.json"] = {k: v for k, v in r["tray_depths.json"].items() if k in ids["image"]}
    return r


def dataset_input_identity(r, u, files):
    # Changes to other datasets in a shared manifest do not affect this dataset identity.
    projected = {name: value for name, value in r.items() if name != "package_manifest.json"}
    return digest(
        {
            "dataset": u["source_dataset_id"],
            "metadata": projected,
            "membership": {
                kind: {key: value for key, value in proof.items() if key != "path"}
                for kind, proof in u["membership_evidence"].items()
            },
            "payloads": [
                {k: f[k] for k in ("path", "size_bytes", "expected_sha256")}
                for f in files
                if f["kind"] != "metadata"
            ],
        }
    )


def inventory(hole, r, u, code):
    references = {}
    for kind, name in [
        ("scalar", "scalar_manifest.json"),
        ("spectral", "spectral_manifest.json"),
        ("profile", "profilometer_manifest.json"),
        ("image", "images_manifest.json"),
    ]:
        entries = r[name]["files"] if kind == "image" else r[name]
        for e in entries:
            if e.get("file"):
                require(e["file"] not in references, "Duplicate raw file reference")
                references[e["file"]] = {"kind": kind, "manifest": name, "entry": e}
    files = []
    for rel in sorted(set(references) | set(r) | {"download-report.txt"}):
        path = inside(ETL / hole, ETL / hole / rel)
        require(path.is_file() and not path.is_symlink(), "Missing or indirect source file")
        stat = path.stat()
        ref = references.get(rel)
        if ref:
            require(stat.st_size == ref["entry"]["nbytes"], "Source size differs from manifest")
        files.append(
            {
                "path": rel,
                "size_bytes": stat.st_size,
                "kind": ref["kind"] if ref else "metadata",
                "manifest_reference": ref,
                "expected_sha256": ref["entry"]["sha256"] if ref else sha(path),
            }
        )
    source_id = dataset_input_identity(r, u, files)
    folder = PREPARED / "multidataset" / hole / u["source_dataset_id"] / source_id[:16] / code[:16]
    return folder, {
        "step": 1,
        "hole_id": hole,
        "status": "passed",
        "pipeline_id": code,
        "source_snapshot_id": source_id,
        "source_dataset_id": u["source_dataset_id"],
        "file_count": len(files),
        "source_bytes": sum(f["size_bytes"] for f in files),
        "files": files,
        "membership_evidence": u["membership_evidence"],
        "raw_metadata_scope": "Full hole-level documents; parsers receive an explicit dataset projection",
    }


def prepare_unit(unit, source, ec):
    hole = unit["hole_id"]
    raw = raw_metadata(hole)
    for name, checksum in source["raw_metadata_sha256"][hole].items():
        require(sha(ETL / hole / name) == checksum, "Raw metadata changed since step 31")
    for proof in unit["membership_evidence"].values():
        if "path" in proof:
            require(sha(ROOT / proof["path"]) == proof["sha256"], "Membership evidence changed")
    projected = selected_metadata(raw, unit)
    code = ec.pipeline_id(
        {"image_depth_policy": "decimal_1e-5_or_same_float32"}, unit["source_dataset_id"]
    )
    folder, inv = inventory(hole, projected, unit, code)
    # Seal small source documents with each version so older versions do not reference changing hole manifests.
    for item in inv["files"]:
        if item["kind"] == "metadata":
            snapshot_path = folder / "source_metadata" / item["path"]
            item["source_object_key"] = snapshot_path.relative_to(ETL).as_posix()
    completed = folder / "32_unit.json"
    if completed.exists():
        cached = read(completed)
        require(
            all(
                sha(folder / rel) == checksum for rel, checksum in cached["prepared_hashes"].items()
            ),
            "Cached prepared bytes changed",
        )
        for item in inv["files"]:
            require(
                sha(ETL / hole / item["path"]) == item["expected_sha256"], "Source content changed"
            )
        print(f"Reuse verified dataset {unit['source_dataset_name']}", flush=True)
        return cached
    baseline = {
        **unit,
        "scalar_log_count": len(projected["scalar_manifest.json"]),
        "spectral_array_count": sum(
            bool(x.get("file")) for x in projected["spectral_manifest.json"]
        ),
    }
    context = ec.DatasetContext(hole, folder, inv, projected, baseline)
    print(f"Prepare {hole}/{unit['source_dataset_name']}", flush=True)
    for item in inv["files"]:
        if "source_object_key" in item:
            ec.atomic_bytes(
                ETL / item["source_object_key"], (ETL / hole / item["path"]).read_bytes()
            )
    ec.write_json(folder / "1_inventory.json", inv)
    module("multi_validate", PROCESSING / "2_validate_payloads.py").validate_hole(
        hole, context=context
    )
    module("multi_normalize", PROCESSING / "3_normalize_metadata.py").normalize_hole(
        hole, context=context
    )
    module("multi_align", PROCESSING / "4_align_samples.py").align_hole(
        hole, image_depth_policy="decimal_1e-5_or_same_float32", context=context
    )
    # Parse only the selected dataset while retaining all raw evidence.
    metadata = read(folder / "3_normalized_metadata.json")
    metadata["raw_metadata"] = raw
    metadata["selected_dataset_context"] = {
        "source_dataset_id": unit["source_dataset_id"],
        "log_ids": unit["log_ids"],
        "membership_evidence": unit["membership_evidence"],
    }
    metadata["borehole"]["orientation_missing_reason"] = "downhole_survey_not_provided"
    metadata["borehole"][
        "orientation_missing_reason_source"
    ] = "source_package_inspection; dataset XML orientation retained separately"
    ec.write_json(folder / "3_normalized_metadata.json", metadata)
    report3 = read(folder / "3_metadata_report.json")
    report3["normalized_metadata_sha256"] = sha(folder / "3_normalized_metadata.json")
    ec.write_json(folder / "3_metadata_report.json", report3)
    module("multi_columnar", PROCESSING / "5_build_columnar.py").build_hole(hole, context=context)
    hashes = {
        p.relative_to(folder).as_posix(): sha(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.name != "32_unit.json"
    }
    summary = {
        **unit,
        "status": "passed",
        "prepared_directory": folder.relative_to(ETL).as_posix(),
        "pipeline_id": code,
        "dataset_id": metadata["dataset"]["id"],
        "dataset_revision_id": metadata["dataset_revision"]["id"],
        "axis_id": metadata["proposed_axis_id"],
        "source_snapshot_id": inv["source_snapshot_id"],
        "prepared_hashes": hashes,
        "report_sha256": {
            n: hashes[n]
            for n in (
                "2_integrity.json",
                "3_metadata_report.json",
                "4_alignment_report.json",
                "5_storage_report.json",
            )
        },
    }
    ec.write_json(completed, summary)
    return summary


def main():
    parser = StepParser()
    parser.add_argument("--holes", nargs="+", choices=MULTI_HOLES, default=list(MULTI_HOLES))
    args = parser.parse_args()
    source = audit()
    sys.path.insert(0, str(PROCESSING))
    import _etl_common as ec

    units = []
    for unit in source["datasets"]:
        if unit["hole_id"] in args.holes:
            units.append(prepare_unit(unit, source, ec))
            write(MULTI / "32_progress.json", {"status": "in_progress", "datasets": units})
    require(units, "No selected datasets")
    write(
        MULTI / "32_prepared.json",
        {
            "status": "passed",
            "source_audit_sha256": sha(MULTI / "31_source_audit.json"),
            "datasets": units,
        },
    )
    print(f"Prepared {len(units)} independent datasets.")


if __name__ == "__main__":
    main_guard(main)
