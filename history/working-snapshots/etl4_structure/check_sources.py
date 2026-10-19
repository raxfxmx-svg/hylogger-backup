import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

sys.path.insert(0, '_codex_work/etl4_refactor/vendor')
from pyflakes.api import checkPath
from pyflakes.reporter import Reporter

root = Path('etl4')
out = Path('_codex_work/etl4_structure')
files = list(root.glob('*.py')) + list((root/'processing').glob('*.py')) + list((root/'database').glob('*.py'))
tests = list((root/'processing/tests').glob('*.py')) + list((root/'database/tests').glob('*.py'))
issues = sum(checkPath(str(path), Reporter(sys.stdout,sys.stderr)) for path in files+tests)
entries = [path for path in files if path.name[0].isdigit()]

def check_entry(path):
    result = subprocess.run([sys.executable,str(path),'--help'],capture_output=True, env={**__import__("os").environ, "PYTHONUTF8":"1"})
    if result.returncode:
        print(path, result.stderr.decode(errors='replace'))
    return {'entry':str(path), 'returncode':result.returncode,
            'common_options':b'--work-dir' in result.stdout and b'--dbname' in result.stdout}

with ThreadPoolExecutor(max_workers=4) as pool:
    entry_results = list(pool.map(check_entry,entries))
before = json.loads((out/'before_hashes.json').read_text(encoding='utf-8'))
migrations = {str(path):hashlib.sha256(path.read_bytes()).hexdigest()==before[path.as_posix()]
              for path in (root/'database/migrations').glob('*.sql')}
with zipfile.ZipFile(out/'before_source.zip') as archive:
    signatures = {}
    for filename in ('_media_reader.py','_multi_reader.py'):
        path=root/'database'/filename
        def functions(source):
            return {node.name:ast.dump(node.args) for node in ast.parse(source).body if isinstance(node,ast.FunctionDef)}
        signatures[filename]=functions(archive.read(path.as_posix()).decode('utf-8-sig'))==functions(path.read_text(encoding='utf-8'))
report={'source_files':len(files),'test_files':len(tests),'lint_issues':issues,
        'entries':entry_results,'migration_bytes_unchanged':migrations,'reader_signatures_unchanged':signatures}
(out/'static_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
assert issues==0, report
assert all(item['returncode']==0 and item['common_options'] for item in entry_results), report
assert all(migrations.values()) and all(signatures.values()), report
print('Passed:',len(entries),'entrypoints,',len(files),'sources,',len(tests),'test files; migrations and reader signatures unchanged.')
