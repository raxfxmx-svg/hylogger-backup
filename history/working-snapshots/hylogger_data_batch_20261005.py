"""Run isolated, resumable data preparation batches without changing raw inputs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('D:/hylogger_aws_batch_20261005')
CODE = ROOT / 'source/etl4'
RAW = Path('D:/100demo/data/raw')
CONFIG = Path('C:/path/to/project/etl4/refactor_work/database/runtime/local_config.json')

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)

def plans():
    inventory = json.loads((ROOT / 'inventory.json').read_text(encoding='utf-8'))
    groups, current, size = [], [], 0
    for hole in inventory['new_ready_holes']:
        amount = inventory['hole_raw_bytes'][hole]
        if current and (len(current) >= 10 or size + amount > 6_000_000_000):
            groups.append(current)
            current, size = [], 0
        current.append(hole)
        size += amount
    if current:
        groups.append(current)
    result = []
    for index, holes in enumerate(groups, 1):
        name = f'batch_{index:02}'
        result.append({'name': name, 'holes': holes, 'raw_bytes': sum(inventory['hole_raw_bytes'][h] for h in holes),
                       'work_dir': str(ROOT / 'batches' / name), 'dbname': f'etl4_20261005_{index:02}'})
    save(ROOT / 'batch_plan.json', result)
    return result

def run(batch, number, script, args=()):
    work = Path(batch['work_dir'])
    logs = work / 'execution'
    logs.mkdir(parents=True, exist_ok=True)
    record_path = logs / f'{number}.json'
    if record_path.exists() and json.loads(record_path.read_text(encoding='utf-8')).get('exit_code') == 0:
        print(f"REUSE {batch['name']} {number}", flush=True)
        return
    command = [sys.executable, '-B', '-X', 'utf8', str(CODE / script), '--raw-dir', str(RAW), '--work-dir', str(work),
               '--dbname', batch['dbname'], '--db-config', str(CONFIG), *map(str,args)]
    print(f"START {batch['name']} {number} ({', '.join(batch['holes'])})", flush=True)
    started = time.monotonic()
    with (logs / f'{number}.log').open('w', encoding='utf-8') as stream:
        completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    result = {'stage': number, 'exit_code': completed.returncode, 'seconds': round(time.monotonic()-started,2), 'command': command}
    save(record_path,result)
    print(f"DONE {batch['name']} {number}: code={completed.returncode}, seconds={result['seconds']}", flush=True)
    if completed.returncode:
        print((logs / f'{number}.log').read_text(encoding='utf-8')[-4000:],flush=True)
        raise RuntimeError(f"{batch['name']} failed at {number}")

def prepare(batch):
    steps = [('01','processing/1_inventory.py',['--holes',*batch['holes']]),
             ('02','processing/2_validate_payloads.py',[]),('03','processing/3_normalize_metadata.py',[]),
             ('04','processing/4_align_samples.py',[]),('05','processing/5_build_columnar.py',[]),
             ('06','processing/6_verify_prepared_data.py',[]),('07','database/7_preflight_database.py',['--inputs-only']),
             ('20','database/20_audit_spectral_sources.py',['--files-only']),
             ('21','database/21_verify_spectral_bindings.py',['--fetch-reference']),
             ('22','database/22_prepare_spectral_access.py',[]),('23','database/23_audit_dataset_image_groups.py',[]),
             ('24','database/24_detect_image_rows.py',[]),('25','database/25_review_image_row_regions.py',[])]
    for number, script, args in steps:
        run(batch,number,script,args)
    save(Path(batch['work_dir'])/'execution/status.json',{'status':'awaiting_visual_review','holes':batch['holes']})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', nargs='*')
    args = parser.parse_args()
    failures = []
    for batch in plans():
        if args.batch and batch['name'] not in args.batch:
            continue
        try:
            prepare(batch)
        except Exception as error:
            failures.append({'batch':batch['name'],'error':str(error)})
            save(ROOT/'preparation_failures.json',failures)
            print(f"FAILED {batch['name']}: {error}",flush=True)
    save(ROOT/'preparation_failures.json',failures)
    return bool(failures)

if __name__ == '__main__':
    sys.exit(main())
