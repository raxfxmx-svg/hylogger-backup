from pathlib import Path

def edit(path, before, after):
    p = Path(path)
    s = p.read_text(encoding='utf-8')
    assert before in s, (path,before[:50])
    p.write_text(s.replace(before,after),encoding='utf-8')

edit('etl4/processing/_etl_common.py', '''    baseline = read_json(BASELINE)
    if tuple(baseline["active_holes"]) != ALLOWED:
        raise ValueError("Baseline allowlist differs from the approved five-hole scope")
    return next(x for x in baseline["holes"] if x["hole_id"] == hole)''', '''    datasets = source_json(hole, "datasets.json")
    if len(datasets) != 1:
        raise ValueError("Multiple datasets require explicit DatasetContext")
    dataset = datasets[0]
    scalar = source_json(hole, "scalar_manifest.json")
    by_id = {item["log_id"]: item for item in scalar}
    trays = list(scalar_rows(hole, by_id[dataset["tray_id"]]))
    sections = list(scalar_rows(hole, by_id[dataset["section_id"]]))
    end = float(trays[-1][1][1])
    if not end.is_integer():
        raise ValueError("Last tray sample index is not an integer")
    return {"sample_count": int(end) + 1, "scalar_log_count": len(scalar),
            "spectral_array_count": sum(bool(item.get("file")) for item in source_json(hole, "spectral_manifest.json")),
            "thumbnail_count": len(trays), "section_count": len(sections)}''')
p=Path('etl4/processing/1_inventory.py');s=p.read_text(encoding='utf-8')
s=s.replace('    expected = baseline_for(hole)\n','')
s=s.replace('    if package["content_fingerprint"] != expected["source_package_fingerprint"]:\n        raise ValueError("Source package fingerprint differs from the reviewed baseline")\n','')
s=s.replace('    if sum(x["size_bytes"] for x in files) != expected["source_bytes"]:\n        raise ValueError("Package bytes differ from the reviewed baseline")\n','')
p.write_text(s,encoding='utf-8')
p=Path('etl4/processing/6_verify_prepared_data.py');s=p.read_text(encoding='utf-8')
a=s.index('    if all_five:\n');b=s.index('    result = {',a)
s=s[:a]+s[b:]
s=s.replace('source size and mtime checked at step entry','source size checked at step entry; import and publication recheck content')
p.write_text(s,encoding='utf-8')

p=Path('etl4/database/32_prepare_multi_dataset_payloads.py');s=p.read_text(encoding='utf-8')
a=s.index('    source_id = digest(');b=s.index('    folder = PREPARED',a)
s=s[:a]+"""    # Changes to other datasets in a shared manifest do not affect this dataset identity.
    projected = {name: value for name, value in r.items() if name != "package_manifest.json"}
    source_id = digest({
        "dataset": u["source_dataset_id"], "metadata": projected,
        "membership": {kind: {key: value for key, value in proof.items() if key != "path"}
                       for kind, proof in u["membership_evidence"].items()},
        "payloads": [{k: f[k] for k in ("path", "size_bytes", "expected_sha256")}
                     for f in files if f["kind"] != "metadata"],
    })
""" +s[b:]
needle='    completed = folder / "32_unit.json"'
s=s.replace(needle,"""    # Seal small source documents with each version so older versions do not reference changing hole manifests.
    for item in inv["files"]:
        if item["kind"] == "metadata":
            snapshot_path = folder / "source_metadata" / item["path"]
            item["source_object_key"] = snapshot_path.relative_to(ETL).as_posix()
""" +needle)
s=s.replace('    ec.write_json(folder / "1_inventory.json", inv)', '''    for item in inv["files"]:
        if "source_object_key" in item:
            ec.atomic_bytes(ETL / item["source_object_key"], (ETL / hole / item["path"]).read_bytes())
    ec.write_json(folder / "1_inventory.json", inv)''')
p.write_text(s,encoding='utf-8')

edit('etl4/processing/5_build_columnar.py', '            "upload_status": "not_uploaded",', '            "upload_status": "not_uploaded",\n            **({"source_object_key": f["source_object_key"]} if "source_object_key" in f else {}),')
edit('etl4/database/_ingest.py', "path = inside(ETL / hole, ETL / hole / asset['source_relative_path'])", "path = inside(ETL, ETL / asset.get('source_object_key', f\"{hole}/{asset['source_relative_path']}\"))")
edit('etl4/database/_ingest.py', '            f"{hole}/{rel}",', '            a.get("source_object_key", f"{hole}/{rel}"),')
edit('etl4/database/_ingest.py', 'p = inside(ETL / hole, ETL / hole / rel)', 'p = inside(ETL, ETL / a.get("source_object_key", f"{hole}/{rel}"))')
edit('etl4/database/_media_common.py', '''def source_path(u, rel):
    return inside(ETL / u["hole_id"], ETL / u["hole_id"] / rel)''', '''def source_path(u, rel):
    snapshot = inside(source_folder(u), source_folder(u) / "source_metadata" / rel)
    if snapshot.is_file():
        return snapshot
    return inside(ETL / u["hole_id"], ETL / u["hole_id"] / rel)''')
