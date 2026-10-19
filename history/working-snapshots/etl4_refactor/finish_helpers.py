from pathlib import Path

p=Path('etl4/database/11_measure_capacity.py');s=p.read_text(encoding='utf-8')
s=s.replace('from fastapi.testclient import TestClient\n','').replace('from api.app import create_app, verify_file\n','')
s=s.replace('def measure(label="five_holes"):', 'def measure(label="current", check_api=False):')
s=s.replace('for h in (prepared[0], prepared[1]):','for h in prepared[:2]:')
s=s.replace('            rev = h["metadata"]["dataset_revision"]["id"]\n','')
a=s.index('    with TestClient(create_app()) as client:');b=s.index('    empty = read(',a)
block=s[a:b]
block=block.replace('            q = h["summary"]["depth_range_query"]', '''            with connection("reader") as conn:
                current_log = conn.execute(
                    "SELECT l.id FROM core.scan_log l JOIN core.release_dataset d ON d.dataset_revision_id=l.dataset_revision_id "
                    "WHERE d.release_id=%s AND d.dataset_id=%s AND l.source_log_id=%s",
                    (active["release_id"], h["metadata"]["dataset"]["id"], log["source_log_id"])).fetchone()
                if current_log is None:
                    continue
                log = {**log, "id": str(current_log["id"])}
            q = h["summary"]["depth_range_query"]''')
s=s[:a]+'''    if check_api:
        from fastapi.testclient import TestClient
        from api.app import create_app, verify_file
'''+''.join('    '+line if line.strip() else line for line in block.splitlines(True))+s[b:]
a=s.index('    write(\n        REPORTS / "deployment_asset_manifest.json"');b=s.index('    lines = [',a)
s=s[:a]+s[b:]
s=s.replace('choices=["five_holes", "after_restore"], default="five_holes"','default="current"')
s=s.replace('    a = p.parse_args()','    p.add_argument("--check-api", action="store_true")\n    a = p.parse_args()').replace('r = measure(a.label)','r = measure(a.label, a.check_api)')
p.write_text(s,encoding='utf-8')

p=Path('etl4/database/_media_tests.py');s=p.read_text(encoding='utf-8')
s=s.replace('def fixture(conn, label, release, base):','def fixture(conn, label, release, base, work=WORK):').replace('path = WORK / "synthetic"','path = work / "synthetic"')
s=s.replace('def behavior_checks(conn):\n    results = []','def behavior_checks(conn, source_units=None, work=WORK):\n    source_units = units() if source_units is None else source_units\n    results = []')
s=s.replace('units()[0]', 'source_units[0]').replace('fixture(conn, "A", release, base)', 'fixture(conn, "A", release, base, work)').replace('fixture(conn, "B", release, base)', 'fixture(conn, "B", release, base, work)')
p.write_text(s,encoding='utf-8')

# Split large field mappings into regular functions while the caller controls one transaction.
p=Path('etl4/database/_ingest.py');s=p.read_text(encoding='utf-8')
a=s.index('    raw_asset_ids = {}');b=s.index('    for a in storage["assets"]:',a);c=s.index('    for rel, checksum in h["prepared_hashes"].items():',b)
raw=s[a:b]+'    return raw_asset_ids\n'
canonical=s[b:c]
s=s[:a]+'''    raw_asset_ids = import_source_assets(conn, h)
    import_canonical_assets(conn, h, logs)
'''+s[c:]
i=s.index('def import_hole(')
prefix='''    m = h["metadata"]
    storage = h["storage"]
    r = m["dataset_revision"]
    rev = r["id"]
'''
s=s[:i]+"""def import_source_assets(conn, h):
    \"\"\"Register source files, original documents, and their log relationships.\"\"\"
"""+prefix+'''    hole = h["summary"]["hole_id"]
'''+raw+"""

def import_canonical_assets(conn, h, logs):
    \"\"\"Register Parquet files and row-group indexes without changing scientific values.\"\"\"
"""+prefix+'''    folder = h["folder"]
    axis = h["alignment"]["axis_id"]
'''+canonical+'\n\n'+s[i:]
p.write_text(s,encoding='utf-8')

# Remove unused locals without side effects; preserve calls with side effects.
for filename, before, after in [
 ('etl4/database/34_import_multi_dataset_database.py','                    hole = u["hole_id"]\n',''),
 ('etl4/database/35_verify_multi_dataset_database.py','    tests = []\n    layouts = []','    layouts = []'),
 ('etl4/database/8_apply_schema.py','        owner = c["roles"]["owner"]["user"]\n',''),
 ('etl4/processing/_etl_common.py','        header = next(reader)','        next(reader)'),
 ('etl4/database/7_preflight_database.py','            output = command(', '            command('),
]:
    p=Path(filename);s=p.read_text(encoding='utf-8');s=s.replace(before,after);p.write_text(s,encoding='utf-8')
