from pathlib import Path
import re

ROOT = Path('etl4')


def edit(relative, old, new):
    p = ROOT / relative
    text = p.read_text(encoding='utf-8-sig')
    if old not in text:
        raise ValueError(f'Not found in {relative}: {old[:90]}')
    p.write_text(text.replace(old, new), encoding='utf-8')


# Separate database source and runtime directories; load migrations from the original source directory.
for p in (ROOT / 'database').glob('*.py'):
    text = p.read_text(encoding='utf-8-sig')
    text = re.sub(r"ROOT\s*/\s*(['\"])([^'\"]+\.(?:py|sql))\1", r"CODE / '\2'", text)
    text = re.sub(r"ROOT\s*/\s*(['\"])migrations\1", "CODE / 'migrations'", text)
    text = re.sub(r"ROOT\s*/\s*(['\"])multi_dataset_decisions.json\1", "CODE / 'multi_dataset_decisions.json'", text)
    text = text.replace("ROOT.glob('*.py')", "CODE.glob('*.py')")
    text = text.replace('argparse.ArgumentParser()', 'StepParser()')
    if 'StepParser(' in text and 'import *' not in text:
        text = 'from _db_common import StepParser\n' + text
    p.write_text(text, encoding='utf-8')

edit('database/_db_common.py', "ROOT = Path(__file__).resolve().parent\nETL = ROOT.parent\nPREPARED = ETL / 'processing' / 'outputs'", """CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE.parent))
from _settings import SOURCE_ROOT, WORK_DIR, DB_NAME, StepParser

ROOT = WORK_DIR / 'database'
ETL = SOURCE_ROOT
PREPARED = WORK_DIR / 'processing' / 'outputs'""")
edit('database/_db_common.py', "def config(): return read(RUNTIME/'local_config.json')", """def config():
    value = read(RUNTIME / 'local_config.json')
    return {**value, 'database': DB_NAME}
""")
edit('database/_db_common.py', "if dbname is not None: overrides['dbname']=dbname", "overrides['dbname'] = dbname or c['database']")
edit('database/_db_common.py', "if tuple(lock['holes'])!=ALLOWED: raise ValueError('Input scope changed')", "if not lock['holes'] or not set(lock['holes']) <= set(ALLOWED): raise ValueError('Input scope changed')")
edit('database/_db_common.py', "selected=holes or list(ALLOWED)", "selected = holes or lock['holes']")
edit('database/_db_common.py', "result.append({'summary':h,'folder':folder", "result.append({'prepared_hashes': lock['prepared_hashes'][h['hole_id']], 'summary':h,'folder':folder")

edit('database/_multi_common.py', "PROCESSING = ETL / 'processing'", "PROCESSING = CODE.parent / 'processing'")
edit('database/_multi_common.py', "result.append({'summary': u, 'folder': folder,", "result.append({'prepared_hashes': u['prepared_hashes'], 'summary': u, 'folder': folder,")

edit('processing/_etl_common.py', 'WORK = Path(__file__).resolve().parent\nSOURCE = WORK.parent\nBASELINE = WORK / "preparation_baseline.json"', '''CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE.parent))
from _settings import SOURCE_ROOT, WORK_DIR, StepParser
from dataclasses import dataclass
import copy

WORK = WORK_DIR / "processing"
SOURCE = SOURCE_ROOT
BASELINE = CODE / "preparation_baseline.json"
PROCESSING_RULE_VERSION = "etl4-preparation-v2"
SOURCE_HOLES = ("05KCD001", "07THD002", "07THD003", "09ATD015", "09ATD019", "12CADD001", "14KDD001", "15EIS001")''')
edit('processing/_etl_common.py', 'if hole not in ALLOWED:', 'if hole not in SOURCE_HOLES:')
start = (ROOT / 'processing/_etl_common.py').read_text(encoding='utf-8')
a = start.index('def pipeline_id():'); b = start.index('\ndef environment()', a)
start = start[:a] + """def pipeline_id(parameters=None):
    # Bump versions for rule changes; record source code and environment only in separate run records.
    return digest({"rules": PROCESSING_RULE_VERSION, "parameters": parameters or {}})


@dataclass
class DatasetContext:
    \"\"\"Provide parsing inputs for one dataset without temporarily changing other modules.\"\"\"
    hole: str
    folder: Path
    inventory: dict
    metadata: dict
    baseline: dict

    def check_hole(self, hole):
        if hole != self.hole:
            raise ValueError("Dataset context belongs to another hole")


""" + start[b:]
(ROOT / 'processing/_etl_common.py').write_text(start, encoding='utf-8')
edit('processing/_etl_common.py', 'def baseline_for(hole):\n    baseline', 'def baseline_for(hole, context=None):\n    if context is not None:\n        context.check_hole(hole)\n        return context.baseline\n    baseline')
edit('processing/_etl_common.py', 'parser = argparse.ArgumentParser(description=description)', 'parser = StepParser(description=description)')
edit('processing/_etl_common.py', 'def source_json(hole, name):\n    return', 'def source_json(hole, name, context=None):\n    if context is not None:\n        context.check_hole(hole)\n        return copy.deepcopy(context.metadata[name])\n    return')
edit('processing/_etl_common.py', 'def snapshot(hole):\n    latest', 'def snapshot(hole, context=None):\n    if context is not None:\n        context.check_hole(hole)\n        return context.folder, context.inventory\n    latest')
edit('processing/_etl_common.py', '    for entry in inventory["files"]:\n        path = source_path(hole, entry["path"])\n        stat = path.stat()\n        if stat.st_size != entry["size_bytes"] or stat.st_mtime_ns != entry["mtime_ns"]:\n            raise ValueError(f"Source changed after inventory: {hole}/{entry[\'path\']}")\n', '')
edit('processing/_etl_common.py', '        "python_version": platform.python_version(),\n        "previous_report_sha256": sha_file(previous) if previous else None,', '        "report_format": 2,\n        "previous_step": read_json(previous)["step"] if previous else None,')

for filename, function in [('2_validate_payloads.py','validate_hole'), ('3_normalize_metadata.py','normalize_hole'), ('4_align_samples.py','align_hole'), ('5_build_columnar.py','build_hole')]:
    p = ROOT / 'processing' / filename
    text = p.read_text(encoding='utf-8')
    if function == 'align_hole':
        text = text.replace('def align_hole(hole, image_depth_policy="decimal_1e-5"):', 'def align_hole(hole, image_depth_policy="decimal_1e-5", context=None):')
        if 'context=None' not in text:
            text = re.sub(r'def align_hole\((.*?)\):', r'def align_hole(\1, context=None):', text)
    else:
        text = text.replace(f'def {function}(hole):', f'def {function}(hole, context=None):')
    text = text.replace('snapshot(hole)', 'snapshot(hole, context)')
    text = text.replace('baseline_for(hole)', 'baseline_for(hole, context)')
    text = re.sub(r'source_json\(hole, ([^)]+)\)', r'source_json(hole, \1, context)', text)
    p.write_text(text, encoding='utf-8')

# Omit modification times from input manifests to prevent timestamp-only identity changes.
edit('processing/1_inventory.py', '                      "mtime_ns": stat.st_mtime_ns,\n', '')
edit('processing/6_verify_prepared_data.py', '        if i and report["previous_report_sha256"] != sha_file(folder / report_files[i - 1]):\n            raise ValueError("Step report dependency hash mismatch")', '        if i and report.get("previous_step") != i:\n            raise ValueError("Step report dependency differs")')
edit('processing/6_verify_prepared_data.py', '    if all_five:\n        write_json(OUTPUT / "latest_verified.json",', '    if args.holes:\n        write_json(OUTPUT / "latest_verified.json",')

# Step 7 locks only explicitly selected data; source identity is content-based.
edit('database/7_preflight_database.py', "if not summary['all_five_verified'] or tuple(summary['active_holes'])!=ALLOWED: raise ValueError('Input is not the verified five-hole release')", "if not summary['active_holes'] or not set(summary['active_holes']) <= set(ALLOWED): raise ValueError('Invalid prepared scope')")
edit('database/7_preflight_database.py', "if last and r['previous_report_sha256']!=sha(folder/last): raise ValueError('Broken report chain')", "if last and r.get('previous_step') != int(last.split('_')[0]): raise ValueError('Broken step order')")
edit('database/7_preflight_database.py', "'holes':list(ALLOWED)", "'holes':summary['active_holes']")
edit('database/7_preflight_database.py', "RUNTIME.mkdir(exist_ok=True)", "RUNTIME.mkdir(parents=True, exist_ok=True)")
edit('database/7_preflight_database.py', "'port':55432,'database':'etl4_core'", "'port':55433,'database':DB_NAME")
edit('database/7_preflight_database.py', 'port = 55432', 'port = 55433')
edit('database/7_preflight_database.py', '127.0.0.1:55432', '127.0.0.1:55433')

# Each prepared output carries its own manifest; multiple datasets do not require replacing load_lock.
edit('database/_ingest.py', "for rel,checksum in load_lock()['prepared_hashes'][hole].items():", "for rel,checksum in h['prepared_hashes'].items():")
a = (ROOT / 'database/_ingest.py').read_text(encoding='utf-8')
x=a.index('def input_digest(h):');y=a.index('\ndef add_asset(',x)
a=a[:x]+"""def input_digest(h):
    return digest({
        'source_snapshot_id': h['metadata']['dataset_revision']['source_snapshot_id'],
        'pipeline_id': h['metadata']['dataset_revision']['pipeline_id'],
        'mapping_version': MAPPING_VERSION,
        'content': prepared_content(h),
    })


def prepared_content(h):
    \"\"\"Compare data content separately; run reports do not define import identity.\"\"\"
    folder = h['folder']
    paths = ['3_normalized_metadata.json', '4_sample_axis.parquet',
             '4_core_intervals.json', '4_image_frames.json']
    paths.extend(a['relative_path'] for a in h['storage']['assets'])
    return {name: sha(folder / name) for name in sorted(set(paths)) if (folder / name).is_file()}

""" + a[y:]
(ROOT / 'database/_ingest.py').write_text(a,encoding='utf-8')

print('Core edits complete')
