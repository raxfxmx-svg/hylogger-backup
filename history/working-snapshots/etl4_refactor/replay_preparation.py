"""Rerun a real sealed dataset after comment and structure cleanup."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

outputs=Path('etl4/refactor_work/processing/outputs')
pointer=outputs/'latest_verified.json'
original=pointer.read_bytes()
selected=json.loads((outputs/'05KCD001/latest_processing.json').read_text())
folder=outputs/selected['relative_directory']
before={str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
started=time.perf_counter()
results=[]
try:
    for script in sorted(Path('etl4/processing').glob('[1-6]_*.py')):
        result=subprocess.run([sys.executable,str(script),'--holes','05KCD001'],check=True)
        results.append(script.name)
    after={str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    assert before==after, 'Sealed preparation outputs changed'
    final=json.loads((outputs/'05KCD001/latest_processing.json').read_text())
    assert selected==final, 'Input/processing version changed'
    report={'status':'passed','scripts':results,'identity_unchanged':True,'sealed_files_unchanged':len(before),
            'elapsed_seconds':time.perf_counter()-started}
    Path('_codex_work/etl4_refactor/preparation_replay.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(report,flush=True)
finally:
    pointer.write_bytes(original)
