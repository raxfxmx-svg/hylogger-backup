"""Check refactor equivalence against real sealed outputs, including the full multi-dataset preparation path."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

root = Path('etl4').resolve()
sys.path.insert(0, str(root))
sys.path.insert(0, str(root/'database'))
from _settings import settings
from _file_checks import FileChecks

out = Path('_codex_work/etl4_structure')

def hashes(folder):
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob('*') if path.is_file()}

def single_dataset():
    outputs = settings.prepared_dir
    summary_path = outputs/'latest_verified.json'
    old_summary = summary_path.read_bytes()
    pointer = outputs/'05KCD001/latest_processing.json'
    old_pointer = pointer.read_bytes()
    folder = outputs/json.loads(old_pointer)['relative_directory']
    before = hashes(folder)
    start = time.perf_counter()
    try:
        for script in sorted((root/'processing').glob('[1-6]_*.py')):
            subprocess.run([sys.executable,'-X','utf8',str(script),'--holes','05KCD001'],check=True)
        assert hashes(folder)==before, 'Single-dataset artifacts changed'
        assert pointer.read_bytes()==old_pointer, 'Single-dataset identity changed'
        return {'status':'passed','hole':'05KCD001','identities_unchanged':True,
                'byte_identical_files':len(before),'elapsed_seconds':time.perf_counter()-start}
    finally:
        summary_path.write_bytes(old_summary)

def multi_dataset():
    prepare = importlib.import_module('32_prepare_multi_dataset_payloads')
    source = json.loads((settings.multi_work_dir/'31_source_audit.json').read_text(encoding='utf-8'))
    prepared = json.loads((settings.multi_work_dir/'32_prepared.json').read_text(encoding='utf-8'))
    selected = min(prepared['datasets'],key=lambda dataset:dataset['sample_count'])
    unit = next(dataset for dataset in source['datasets'] if dataset['source_dataset_id']==selected['source_dataset_id'])
    folder = root/selected['prepared_directory']
    before = hashes(folder)
    start = time.perf_counter()
    # Only tests bypass reuse to exercise parsing, normalisation, alignment and columnar output.
    # Production writes still verify sealed contents and reject different replacements.
    with patch.object(prepare,'reuse_prepared_result',return_value=None), FileChecks():
        result = prepare.prepare_unit(unit,source,settings.prepared_dir,settings.database_dir)
    after = hashes(folder)
    changed = [name for name in before.keys()|after.keys() if before.get(name)!=after.get(name)]
    assert not changed, changed
    assert result==selected, 'Multi-dataset version or summary changed'
    return {'status':'passed','hole':selected['hole_id'],'source_dataset_id':selected['source_dataset_id'],
            'samples':selected['sample_count'],'cache_bypassed':True,'byte_identical_files':len(before),
            'elapsed_seconds':time.perf_counter()-start}

report = {'single':single_dataset(),'multi':multi_dataset()}
(out/'preparation_replay.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
