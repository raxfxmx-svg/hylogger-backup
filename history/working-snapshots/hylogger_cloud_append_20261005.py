"""Append locally accepted public datasets, retaining the original cloud release."""
import argparse
import importlib.util
import json
from pathlib import Path
import ssl
import sys
import time

ROOT = Path(__file__).resolve().parent
CODE = ROOT / 'etl4/database'
sys.path[:0] = [str(CODE), str(CODE.parent)]
ACCOUNT = '000000000000'
REGION = 'ap-southeast-2'
BUCKET = 'hyloggerdemo-000000000000-ap-southeast-2-an'
HOST = 'db.example.com'
DATABASE = 'etl4_core'
S3_ROOT = 'etl4_s3_a22098dedb6798558858'
EXPECTED_RELEASE = '0b2990a6-55d7-5569-8ac4-2b5d9fb346ac'

def module(name):
    spec = importlib.util.spec_from_file_location(name, CODE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def write(path, value):
    path.write_text(json.dumps(value,default=str,indent=2)+'\n',encoding='utf-8')

def connection():
    import boto3
    import psycopg
    from psycopg.rows import dict_row
    session = boto3.Session(region_name=REGION)
    assert session.client('sts').get_caller_identity()['Account'] == ACCOUNT
    ca = ssl.get_default_verify_paths().cafile
    assert ca and Path(ca).is_file()
    token = session.client('rds').generate_db_auth_token(DBHostname=HOST,Port=5432,DBUsername='postgres')
    conn = psycopg.connect(host=HOST,port=5432,dbname=DATABASE,user='postgres',password=token,
        sslmode='verify-full',sslrootcert=ca,connect_timeout=30,autocommit=True,row_factory=dict_row)
    conn.execute("SET statement_timeout TO '20min'")
    return conn

def snapshot(conn):
    release = str(conn.execute('SELECT release_id FROM core.active_release WHERE singleton').fetchone()['release_id'])
    rows = conn.execute('''SELECT d.id dataset_id,rd.dataset_revision_id,b.source_hole_id,d.source_dataset_id
       FROM core.release_dataset rd JOIN core.dataset d ON d.id=rd.dataset_id
       JOIN core.borehole b ON b.id=d.borehole_id WHERE rd.release_id=%s ORDER BY d.id''',(release,)).fetchall()
    return {'release_id':release,'members':module('40_merge_cloud_batch').plain(rows),
        'holes':sorted({r['source_hole_id'] for r in rows}),'dataset_count':len(rows)}

def audit():
    with connection() as conn,conn.transaction():
        conn.execute('SET TRANSACTION READ ONLY')
        value = snapshot(conn)
        assert value['release_id'] == EXPECTED_RELEASE, 'Active release changed before this job'
        assert len(value['holes']) == 12 and value['dataset_count'] == 17
        value['migrations'] = conn.execute('SELECT name,sha256 FROM core.schema_migration ORDER BY name').fetchall()
    path=ROOT/'cloud_before.json'
    if path.exists():
        assert json.loads(path.read_text()) == value, 'Saved cloud baseline differs'
    else:
        write(path,value)
    print(json.dumps({k:v for k,v in value.items() if k not in ('members','migrations')}),flush=True)

def target_export(name):
    path = (ROOT/'exports'/name).resolve()
    assert path.parent == (ROOT/'exports').resolve()
    return path

def merge(name,finalize=False):
    api=module('40_merge_cloud_batch')
    directory=target_export(name)
    manifest,_=api.load_export(directory)
    before=json.loads((ROOT/'cloud_before.json').read_text())
    new_holes={row['source_hole_id'] for row in manifest['datasets']}
    assert not new_holes.intersection(before['holes']), 'Batch must only add new boreholes'
    selection_path=None
    if finalize:
        inventory=json.loads((ROOT/'inventory.json').read_text())
        wanted=set(before['holes']) | set(inventory['new_ready_holes'])
        with connection() as conn,conn.transaction():
            conn.execute('SET TRANSACTION READ ONLY')
            active=snapshot(conn)
            assert active['release_id'] == before['release_id'], 'Concurrent publication detected'
            members,_,_=api.accumulated_members(conn,[])
            for item in before['members']:
                assert {k:item[k] for k in ('dataset_id','dataset_revision_id')} in members, 'Existing version was replaced'
            actual=conn.execute('''SELECT DISTINCT b.source_hole_id FROM core.dataset d
                JOIN core.borehole b ON b.id=d.borehole_id WHERE d.id=ANY(%s::uuid[])''',([r['dataset_id'] for r in members],)).fetchall()
            assert {r['source_hole_id'] for r in actual} == wanted, 'Final release does not match the reviewed inventory'
        selection_path=ROOT/'final_selection.json'
        write(selection_path,{'expected_active_release_id':before['release_id'],'datasets':members,'omitted_dataset_ids':[]})
    result=api.merge_batch(directory,root_key=S3_ROOT,connect=connection,finalize=selection_path)
    print(json.dumps({k:v for k,v in result.items() if k not in ('datasets','replacements')}),flush=True)
    if finalize:
        with connection() as conn,conn.transaction():
            conn.execute('SET TRANSACTION READ ONLY')
            value=snapshot(conn)
        write(ROOT/'cloud_after.json',value)
        print(json.dumps({'holes':len(value['holes']),'datasets':value['dataset_count'],'release_id':value['release_id']}),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['audit','sign','merge','finalize'])
    parser.add_argument('--batch')
    args=parser.parse_args()
    if args.action=='audit':
        audit()
    elif args.action=='sign':
        result=module('39_upload_batch').sign_upload_urls(target_export(args.batch),BUCKET,REGION,'etl4',
            ROOT/(args.batch+'.private.json'),expected_account=ACCOUNT)
        print(json.dumps(result),flush=True)
    else:
        merge(args.batch,args.action=='finalize')

if __name__=='__main__':
    try:
        main()
    except Exception as error:
        diagnostic=getattr(error,'diag',None)
        print(json.dumps({'error_type':type(error).__name__,'message':str(error) if isinstance(error,(ValueError,AssertionError)) else 'Operation failed',
            'sqlstate':getattr(error,'sqlstate',None),'table':getattr(diagnostic,'table_name',None),
            'constraint':getattr(diagnostic,'constraint_name',None)}),flush=True)
        raise SystemExit(1)
