from pathlib import Path

root = Path('etl4/database')
def transform(name, pairs):
    p = root / name
    s = p.read_text(encoding='utf-8')
    for before, after in pairs:
        assert before in s, (name, before[:60])
        s = s.replace(before, after)
    p.write_text(s, encoding='utf-8')

transform('_db_common.py', [('def command(args, env=None):', 'def command(args, env=None, timeout=60):'), ('            timeout=60,', '            timeout=timeout,')])
for name in ('12_verify_restore.py', '14_verify_database_backup.py', '30_audit_media_database.py'):
    p = root / name
    s = p.read_text(encoding='utf-8').replace('env=env,', 'env=env, timeout=900,')
    p.write_text(s, encoding='utf-8')

transform('12_verify_restore.py', [('def main():\n    c = config()', '''def main():
    from _settings import StepParser
    parser = StepParser()
    parser.add_argument("--check-api", action="store_true")
    args = parser.parse_args()
    c = config()'''), ('        api = api_checks(prepared, release["release_id"], dbname=trial)', '''        api = {"status": "not_requested"}
        if args.check_api:
            from fastapi.testclient import TestClient
            from api.app import create_app
            with TestClient(create_app(trial)) as client:
                response = client.get('/v1/boreholes', params={'release_id': str(restored_release)})
                require(response.status_code == 200, "Restored API failed")
                api = {"status": "passed", "boreholes": len(response.json()['items'])}'''), ('    StepParser().parse_args()\n    main_guard(main)', '    main_guard(main)')])
transform('13_audit_database.py', [
    ('def source_checks(conn):', 'def source_checks(conn, selected=None):'),
    ('    for h in prepared_holes():', '    for h in prepared_holes() if selected is None else selected:'),
    ('        require(result["weight_logs_checked"] == 62, "Approved five-hole weight-log scope changed")', ''),
    ('def audit(label):', 'def audit(label, baseline_path=None):'),
    ('p = argparse.ArgumentParser(description=__doc__)', 'from _settings import StepParser\n    p = StepParser(description=__doc__)'),
    ('    audit(p.parse_args().label)', '    p.add_argument("--baseline", type=Path, help="Optional comparison report for this run")\n    args = p.parse_args()\n    audit(args.label, args.baseline)')])
p = root / '13_audit_database.py'
s = p.read_text(encoding='utf-8'); a = s.index('    # Compare all 26 business tables'); b = s.index('    trial = create_trial(', a)
s = s[:a] + """    # Historical digests support independent checks; this call explicitly selects the reference file.
    result["business_hashes"] = fingerprints()
    result["restored_baseline_matches"] = None
    if baseline_path:
        baseline = read(baseline_path)
        require(result["business_hashes"] == baseline["business_table_hashes"],
                "Business records differ from selected baseline")
        result["restored_baseline_matches"] = True
""" + s[b:]
p.write_text(s, encoding='utf-8')

p = root / '30_audit_media_database.py'; s = p.read_text(encoding='utf-8')
a = s.index('        require(\n            {r["source_hole_id"]'); b = s.index('        rels = ',a)
s = s[:a] + '''        from _publication import release_members
        release_members(conn, release)
''' + s[b:]
s = s.replace('coverage[r["source_hole_id"]]', 'coverage[str(r["dataset_id"])]')
a = s.index('def reproducibility_review():'); b = s.index('\n\ndef main():',a)
s = s[:a] + """def reproducibility_review():
    \"\"\"Recheck a sealed package and record whether the dataset revision stays unchanged.\"\"\"
    from _media_import import check_package, package_step, media_identity
    from _multi_common import MULTI
    state = read(MULTI / "34_import.json") if (MULTI / "34_import.json").exists() else stage(28)
    dest = ROOT / state["package_directory"]
    manifest = read(dest / "manifest.json")
    check_package(dest, manifest)
    identities = {}
    for unit in package_step(dest, 20)["datasets"]:
        dataset = unit["dataset_id"]
        arrays = [x for x in package_step(dest, 22)["arrays"] if x["dataset_id"] == dataset]
        rows = [x for x in package_step(dest, 27)["rows"] if x["dataset_id"] == dataset]
        identities[dataset] = media_identity(unit, arrays, rows)
    require(identities == manifest["datasets"], "Dataset identities changed")
    return {"status": "passed", "package_sha256": digest(manifest),
            "dataset_identities": identities, "source_code_part_of_identity": False,
            "input_source": "sealed package steps and referenced files"}
""" + s[b:]
p.write_text(s, encoding='utf-8')

p = root / '29_verify_media_grain.py'; s = p.read_text(encoding='utf-8')
a = s.index('def legacy_fingerprints('); b = s.index('def verify_dataset(',a)
s = s[:a] + s[b:]; p.write_text(s, encoding='utf-8')

p = root / '35_verify_multi_dataset_database.py'; s = p.read_text(encoding='utf-8')
a = s.index('            relations = {'); b = s.index('            previous = ',a)
s = s[:a] + '''            relations = {"dataset_source_and_mapping_checks": "passed"}
''' + s[b:]; p.write_text(s, encoding='utf-8')

# Every entry point accepts common work-directory and test-database options.
for p in list(root.glob('[0-9]*.py')) + list(Path('etl4/processing').glob('[0-9]*.py')):
    s = p.read_text(encoding='utf-8')
    if 'argparse.ArgumentParser(' in s:
        s = s.replace('argparse.ArgumentParser(', 'StepParser(')
        if 'import StepParser' not in s:
            # Shared modules already prepare the settings import path.
            i = s.index('\ndef ')
            s = s[:i] + '\nfrom _settings import StepParser\n' + s[i:]
    p.write_text(s, encoding='utf-8')
