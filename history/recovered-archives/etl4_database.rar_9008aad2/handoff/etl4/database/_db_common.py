"""Shared IO and database helpers. Executable workflow steps are numbered 7-12."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg import sql

ROOT = Path(__file__).resolve().parent
ETL = ROOT.parent
PREPARED = ETL / 'processing' / 'outputs'
RUNTIME = ROOT / 'runtime'
REPORTS = ROOT / 'reports'
ALLOWED = ('05KCD001','07THD002','07THD003','09ATD015','09ATD019')
PG_BIN = Path(os.environ.get('ETL4_PG_BIN', 'C:/Program Files/PostgreSQL/17/bin'))
LOCK_KEY = 470040001

def now(): return datetime.now(timezone.utc).isoformat()
def uid(*parts): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'etl4-db:' + ':'.join(map(str, parts))))
def serial(value):
    if isinstance(value, (datetime,date,uuid.UUID,Path)): return str(value)
    if isinstance(value, Decimal): return int(value) if value==value.to_integral_value() else str(value)
    raise TypeError(type(value).__name__)
def encoded(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False, default=serial)+'\n').encode('utf-8')
def digest(value): return hashlib.sha256(encoded(value)).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()
def inside(root, path):
    root,path=Path(root).resolve(),Path(path).resolve()
    if path==root or not path.is_relative_to(root): raise ValueError('Path outside permitted root')
    return path
def write(path,value):
    path=inside(ROOT,path); path.parent.mkdir(parents=True,exist_ok=True)
    data=value.encode('utf-8') if isinstance(value,str) else encoded(value)
    fd,name=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as f: f.write(data)
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)
def config(): return read(RUNTIME/'local_config.json')
def connection(role='owner', dbname=None, autocommit=True):
    c=config(); role_data=c['roles'][role]
    key={'owner':'ETL4_ADMIN_DSN','ingest':'ETL4_INGEST_DSN','reader':'ETL4_READ_DSN'}[role]
    overrides={'row_factory':dict_row,'autocommit':autocommit,'connect_timeout':5}
    if os.environ.get(key):
        if dbname is not None: overrides['dbname']=dbname
        conn=psycopg.connect(os.environ[key],**overrides)
    else:
        conn=psycopg.connect(host=c['host'],port=c['port'],user=role_data['user'],password=role_data['password'],dbname=dbname or c['database'],**overrides)
    conn.execute("SET search_path TO core, public")
    conn.execute("SET statement_timeout TO '60s'")
    return conn
def command(args,env=None):
    # File-backed output avoids pg_ctl daemon descendants keeping PIPE handles open.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result=subprocess.run([str(a) for a in args],stdout=stdout,stderr=stderr,stdin=subprocess.DEVNULL,env=env,timeout=60,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        stdout.seek(0); stderr.seek(0)
        out=stdout.read().decode('utf-8',errors='replace'); err=stderr.read().decode('utf-8',errors='replace')
    if result.returncode: raise RuntimeError(f'{Path(str(args[0])).name} failed ({result.returncode}): {err[-3000:]} {out[-1000:]}')
    return out
def report(name,value):
    value={'recorded_at':now(),**value}; write(REPORTS/name,value); return value
def main_guard(fn):
    try: fn()
    except Exception as exc:
        # Do not print connection strings or configuration contents.
        msg=str(exc)
        if (RUNTIME/'local_config.json').exists():
            try:
                for r in config()['roles'].values(): msg=msg.replace(r['password'],'[redacted]')
            except OSError:
                msg='Local credential configuration is inaccessible; check file permissions'
        report('last_failure.json',{'script':Path(sys.argv[0]).name,'error_type':type(exc).__name__,'detail':msg,'status':'failed'})
        print(f'STOP: {type(exc).__name__}: {msg}',file=sys.stderr,flush=True); raise SystemExit(1)
def insert(conn,table,data):
    values=[Jsonb(v) if isinstance(v,dict) else v for v in data.values()]
    query=sql.SQL('INSERT INTO core.{} ({}) VALUES ({})').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,data)),sql.SQL(',').join(sql.Placeholder() for _ in data))
    conn.execute(query,values)
def pick(obj,*keys): return {k:obj.get(k) for k in keys}
def load_lock():
    lock=read(REPORTS/'7_input_lock.json')
    if sha(PREPARED/lock['summary_path'])!=lock['summary_sha256']: raise ValueError('Locked input summary changed')
    if tuple(lock['holes'])!=ALLOWED: raise ValueError('Input scope changed')
    return lock
def prepared_holes(holes=None):
    lock=load_lock(); summary=read(PREPARED/lock['summary_path'])
    selected=holes or list(ALLOWED)
    if not set(selected)<=set(ALLOWED): raise ValueError('Hole outside approved scope')
    result=[]
    for h in summary['holes']:
        if h['hole_id'] not in selected: continue
        folder=inside(PREPARED,PREPARED/h['directory'])
        for relative,expected in lock['prepared_hashes'][h['hole_id']].items():
            if sha(inside(folder,folder/relative))!=expected: raise ValueError(f'Prepared input changed: {h["hole_id"]}/{relative}')
        result.append({'summary':h,'folder':folder,'metadata':read(folder/'3_normalized_metadata.json'),
                       'alignment':read(folder/'4_alignment_report.json'),'storage':read(folder/'5_storage_report.json')})
    return result
def schema_hash(): return digest({p.name:sha(p) for p in sorted((ROOT/'migrations').glob('*.sql'))})
def importer_hash(): return digest({p.name:sha(p) for p in [ROOT/'_ingest.py',ROOT/'_db_common.py']})
def assert_schema(conn):
    for p in sorted((ROOT/'migrations').glob('*.sql')):
        row=conn.execute('SELECT sha256 FROM core.schema_migration WHERE name=%s',(p.name,)).fetchone()
        if not row or row['sha256']!=sha(p): raise ValueError('Migration is missing or checksum differs')
