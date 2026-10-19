from pathlib import Path

root = Path('etl4/database')

def edit(name, before, after):
    path = root / name
    source = path.read_text(encoding='utf-8')
    assert before in source, (name, before[:80])
    path.write_text(source.replace(before, after), encoding='utf-8')

# Preserve the base-data manifest inside the package; restoration needs the package and referenced durable files.
edit('33_prepare_multi_dataset_media.py',
     '"prepared_directory": h["folder"].relative_to(PREPARED).as_posix(),',
     '"prepared_directory": h["folder"].relative_to(PREPARED).as_posix(),\n            "prepared_hashes": h["prepared_hashes"],\n            "prepared_summary": h["summary"],')

path = root / '33_prepare_multi_dataset_media.py'
source = path.read_text(encoding='utf-8')
start = source.index('    frames = []')
end = source.index('    chosen = ', start)
frames = source[start:end] + '    return frames, rows, templates\n'
sheet_end = source.index('    if args.record_reviewed:', end)
sheets = source[end:sheet_end] + '    return sheets\n'
map_start = source.index('    mapped = []', sheet_end)
map_end = source.index('    mc.save_stage(\n        26', map_start)
mapping = source[map_start:map_end] + '    return mapped, covered\n'
source = source[:map_start] + '    mapped, covered = bind_rows(rows, datasets, mc)\n' + source[map_end:]
source = source[:start] + '    frames, rows, templates = detect_rows(datasets, mc)\n    sheets = make_review_sheets(templates, mc)\n' + source[sheet_end:]
index = source.index('def main():')
source = source[:index] + 'def detect_rows(datasets, mc):\n    """Find row boundaries from the source section count and preserve all image pixels and gaps."""\n' + frames + '\n\ndef make_review_sheets(templates, mc):\n    """Select the first and last images for each size and row count for visual review."""\n' + sheets + '\n\ndef bind_rows(rows, datasets, mc):\n    """Use source section sample ranges and check the coverage count for each dataset."""\n' + mapping + '\n\n' + source[index:]
path.write_text(source, encoding='utf-8')

edit('34_import_multi_dataset_database.py', 'import shutil', 'import shutil\nfrom pathlib import Path\nfrom _db_common import assert_schema')
edit('34_import_multi_dataset_database.py', 'parser.add_argument("--source-release")', 'parser.add_argument("--source-release")\n    parser.add_argument("--package", type=Path)')
edit('34_import_multi_dataset_database.py', '''    require(
        read(MULTI / "33_media_ready.json")["status"] == "passed",
        "Media is not reviewed and prepared",
    )
    selected = prepared()
''', '')
edit('34_import_multi_dataset_database.py', '''    # Migration 006 is additive. Existing scientific rows and old release remain.
    module("multi_schema", CODE / "8_apply_schema.py").main()
''', '')
edit('34_import_multi_dataset_database.py', '''    for p in (MULTI / "media").glob("33_review_*.png"):
        dest = MULTI_EVIDENCE / "review" / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
    key, dest, manifest = mi.prepare_package(work=MULTI / "media", evidence_dir=MULTI_EVIDENCE)
''', '''    if args.package:
        dest = args.package.resolve()
        manifest = read(dest / "manifest.json")
        key = digest(manifest)
        mi.check_package(dest, manifest)
    else:
        require(read(MULTI / "33_media_ready.json")["status"] == "passed",
                "Media is not reviewed and prepared")
        key, dest, manifest = mi.prepare_package(work=MULTI / "media", evidence_dir=MULTI_EVIDENCE)
    selected = [mi.prepared_context(u) for u in mi.package_step(dest, 20)["datasets"]]
''')
edit('34_import_multi_dataset_database.py', '    with connection("ingest") as conn:\n', '    with connection("ingest") as conn:\n        assert_schema(conn)\n')

edit('_media_import.py', 'def check_package(destination, manifest):', """def prepared_context(unit):
    \"\"\"Rebuild base import arguments from the package manifest and use its file references.\"\"\"
    from _media_common import source_folder
    folder = source_folder(unit)
    for relative, checksum in unit["prepared_hashes"].items():
        require(sha(inside(folder, folder / relative)) == checksum,
                f"Prepared artifact changed: {relative}")
    return {
        "prepared_hashes": unit["prepared_hashes"],
        "summary": unit["prepared_summary"], "folder": folder,
        "metadata": read(folder / "3_normalized_metadata.json"),
        "alignment": read(folder / "4_alignment_report.json"),
        "storage": read(folder / "5_storage_report.json"),
    }


def verify_source_assets(conn, unit):
    \"\"\"Reread referenced source files at the import boundary; reruns must still validate contents.\"\"\"
    source = conn.execute(
        "SELECT a.id FROM core.dataset_revision r JOIN core.sample_axis a ON a.dataset_revision_id=r.id "
        "WHERE r.id=%s AND r.dataset_id=%s AND r.source_snapshot_id=%s AND a.id=%s",
        (unit["source_revision_id"], unit["dataset_id"], unit["source_snapshot_id"], unit["source_axis_id"])
    ).fetchone()
    require(source, "Package dataset/axis does not match the source revision")
    assets = conn.execute(
        "SELECT a.sha256,a.byte_size,l.object_key FROM core.asset a "
        "JOIN core.asset_location l ON l.asset_id=a.id WHERE a.dataset_revision_id=%s AND l.backend='local'",
        (unit["source_revision_id"],)).fetchall()
    require(assets, "Source revision has no local assets")
    for asset in assets:
        path = inside(ETL, ETL / asset["object_key"])
        require(path.stat().st_size == asset["byte_size"] and sha(path) == asset["sha256"],
                "Referenced source asset changed: " + asset["object_key"])


def release_context(conn, release, destination):
    \"\"\"Locate revisions by the specified release and sealed package, without current-release or temporary-step state.\"\"\"
    from _publication import release_members
    members = release_members(conn, release)
    definition = conn.execute("SELECT manifest FROM core.data_release WHERE id=%s", (release,)).fetchone()["manifest"]
    manifest = read(destination / "manifest.json")
    results = []
    for unit in package_step(destination, 20)["datasets"]:
        identity = manifest["datasets"][unit["dataset_id"]]
        revision = uid("media-revision-v2", unit["dataset_id"], identity["input_key"])
        require(any(str(m["dataset_id"]) == unit["dataset_id"] and str(m["dataset_revision_id"]) == revision
                    for m in members), "Package revision is not in this release")
        axis = conn.execute("SELECT id FROM core.sample_axis WHERE dataset_revision_id=%s", (revision,)).fetchone()
        results.append({"dataset_id": unit["dataset_id"], "dataset_revision_id": revision, "axis_id": str(axis["id"])})
    return {"release_id": release, "datasets": results, "previous_release_id": definition["source_release_id"],
            "decisions": definition.get("succession_decisions")}


def check_package(destination, manifest):""")
edit('_media_import.py', '    identity = manifest["datasets"][u["dataset_id"]]\n', '    verify_source_assets(conn, u)\n    identity = manifest["datasets"][u["dataset_id"]]\n')

edit('29_verify_media_grain.py', 'from _media_import import import_media, package_step, check_package', 'from _media_import import package_step, check_package, release_context\nfrom pathlib import Path')
edit('29_verify_media_grain.py', '    parser.add_argument("--no-activate", action="store_true")', '    parser.add_argument("--no-activate", action="store_true")\n    parser.add_argument("--package", type=Path)\n    parser.add_argument("--release")')
edit('29_verify_media_grain.py', '''    staged = stage(28)
    release = staged["release_id"]
    destination = ROOT / staged["package_directory"]''', '''    if args.package or args.release:
        require(args.package and args.release, "Use --package and --release together")
        release, destination = args.release, args.package.resolve()
        with connection("reader") as conn:
            staged = release_context(conn, release, destination)
    else:
        staged = stage(28)
        release = staged["release_id"]
        destination = ROOT / staged["package_directory"]''')

edit('35_verify_multi_dataset_database.py', 'def main():\n    staged = read(MULTI / "34_import.json")\n    baseline = read(MULTI / "34_baseline.json")', '''def main():
    from _settings import StepParser
    from pathlib import Path
    parser = StepParser()
    parser.add_argument("--package", type=Path)
    parser.add_argument("--release")
    args = parser.parse_args()''')
edit('35_verify_multi_dataset_database.py', '''    release = staged["release_id"]
    dest = ROOT / staged["package_directory"]''', '''    if args.package or args.release:
        require(args.package and args.release, "Use --package and --release together")
        release, dest = args.release, args.package.resolve()
        with connection("reader") as conn:
            staged = mi.release_context(conn, release, dest)
    else:
        staged = read(MULTI / "34_import.json")
        release = staged["release_id"]
        dest = ROOT / staged["package_directory"]
    baseline = {"release_id": staged["previous_release_id"]}''')
path = root / '35_verify_multi_dataset_database.py'
source = path.read_text(encoding='utf-8')
a = source.index('                expected = set().union(')
b = source.index('                actual = {', a)
source = source[:a] + '''                metadata = read(mi.prepared_context(u)["folder"] / "3_normalized_metadata.json")
                expected = {log["source_log_id"] for log in metadata["logs"]}
''' + source[b:]
a = source.index('            old = conn.execute(')
b = source.index('            groups = install_composites', a)
source = source[:a] + '''            from _publication import release_members
            inherited = release_members(conn, baseline["release_id"])
            current = release_members(conn, release)
            require(all(any(m["dataset_id"] == old["dataset_id"] and m["dataset_revision_id"] == old["dataset_revision_id"]
                            for m in current) for old in inherited), "Source release membership changed")
            definition = conn.execute("SELECT manifest FROM core.data_release WHERE id=%s", (release,)).fetchone()["manifest"]
            decisions = definition["succession_decisions"]
''' + source[b:]
source = source.replace('    from _db_common import StepParser\n\n    StepParser().parse_args()\n    main_guard(main)', '    main_guard(main)')
path.write_text(source, encoding='utf-8')

edit('tests/test_refactor.py', "patch.object(media, 'clone_revision', return_value=({'axis': 'derived-axis'}, False)):", "patch.object(media, 'clone_revision', return_value=({'axis': 'derived-axis'}, False)), \\\n                     patch.object(media, 'verify_source_assets'):")
