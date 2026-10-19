"""Owner-authorized BSDD023 publication using independently verified S3 evidence.

--prepare verifies S3 and writes a concrete plan without DB mutations.
--apply requires that exact plan, rechecks object versions and active membership,
then calls the owner's unchanged Step 40. It never grants permissions or migrates.
"""
import argparse
import base64
import gzip
import hashlib
import importlib.util
import json
import ssl
import sys
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import boto3
import psycopg
from psycopg.rows import dict_row

HERE=Path(__file__).resolve().parent
CODE=HERE/'code'
sys.path[:0]=[str(CODE/'database'),str(CODE)]
from _batch_files import load_export,read_json,write_json,file_info
from _db_files import digest,encoded
from _db_common import LOCK_KEY
spec=importlib.util.spec_from_file_location('owner_step40',CODE/'database/40_merge_cloud_batch.py')
step=importlib.util.module_from_spec(spec);spec.loader.exec_module(step)
BUCKET='hyloggerdemo-000000000000-ap-southeast-2-an'
REGION='ap-southeast-2'
HOST='db.example.com'
DB='etl4_core'
BATCH='e704df799acda67aa438cabf30d6a227dffd12b6ab84f7131021b3cbdeb1781d'
MANIFEST_SHA='0e5d68eefbe628f18ed2c79c6a42299cc5fe6d58bdfb898feeeccadc7aa0301e'
RID='7711c92e-8698-5657-af71-308c382e4902'
DID='6f167916-b51d-584a-84b2-3fbc4a8dcde8'
BID='c1484f00-0d44-560b-b47c-a15f39229207'
ROOT_KEY='etl4_s3_a22098dedb6798558858'
EXPORT=Path.home()/'audit_BSDD023_20261011/export'
OUT=HERE/'results';OUT.mkdir(exist_ok=True)
SESSION=boto3.Session(region_name=REGION)
S3=SESSION.client('s3')
def require(ok,message):
    if not ok:raise ValueError(message)
def now():return datetime.now(timezone.utc).isoformat()
def plain(x):return json.loads(encoded(x))
def connect(user='postgres',readonly=False):
    token=SESSION.client('rds').generate_db_auth_token(DBHostname=HOST,Port=5432,DBUsername=user)
    return psycopg.connect(host=HOST,port=5432,dbname=DB,user=user,password=token,sslmode='verify-full',sslrootcert=ssl.get_default_verify_paths().cafile,connect_timeout=60,autocommit=True,row_factory=dict_row,options='-c statement_timeout=180000 -c lock_timeout=15000'+(' -c default_transaction_read_only=on' if readonly else ''))
def active(conn):
    row=conn.execute('SELECT release_id::text FROM core.active_release WHERE singleton').fetchone()
    require(bool(row),'Expected a nonempty existing active release')
    rid=row['release_id']
    members=step.members_of(conn,rid)
    holes=conn.execute('SELECT count(distinct d.borehole_id) n FROM core.release_dataset rd JOIN core.dataset d ON d.id=rd.dataset_id WHERE rd.release_id=%s',(rid,)).fetchone()['n']
    return {'release_id':rid,'members':members,'holes':holes,'datasets':len(members)}
def check_code():
    expected=read_json(HERE/'code_manifest.json')
    for rel,h in expected.items():
        require(hashlib.sha256((HERE/rel).read_bytes()).hexdigest()==h,'Owner code changed: '+rel)
    return digest(expected)
def export_check():
    m,sha=load_export(EXPORT)
    require(m['batch_id']==BATCH and sha==MANIFEST_SHA,'Unexpected batch/manifest identity')
    require(len(m['datasets'])==1 and m['datasets'][0]['dataset_id']==DID and m['datasets'][0]['dataset_revision_id']==RID and m['datasets'][0]['borehole_id']==BID and m['datasets'][0]['source_hole_id']=='BSDD023','Unexpected incoming scope')
    step.local_acceptance_evidence(EXPORT,m)
    return m
def expected_objects(m):
    base='etl4/batches/'+BATCH+'/'+MANIFEST_SHA
    entries={a['object_key']:{'source_key':a['object_key'],'object_key':'etl4/'+a['object_key'],'sha256':a['sha256'],'byte_size':a['byte_size'],'kind':'asset'} for a in m['assets']}
    entries.update({k:{'source_key':k,'object_key':base+'/'+k,'sha256':v['sha256'],'byte_size':v['byte_size'],'kind':v['kind']} for k,v in m['files'].items()})
    entries['manifest.json']={'source_key':'manifest.json','object_key':base+'/manifest.json','sha256':MANIFEST_SHA,'byte_size':(EXPORT/'manifest.json').stat().st_size,'kind':'manifest'}
    require(len(entries)==315,'Unexpected object scope')
    return list(entries.values())
def generate_owner_evidence(m):
    def verify(w):
        h=S3.head_object(Bucket=BUCKET,Key=w['object_key'],ChecksumMode='ENABLED')
        require(h['ContentLength']==w['byte_size'],'S3 size mismatch: '+w['object_key'])
        if h.get('ChecksumType')=='FULL_OBJECT' and h.get('ChecksumSHA256')==base64.b64encode(bytes.fromhex(w['sha256'])).decode():
            observed=w['sha256'];method='S3 native FULL_OBJECT SHA256'
        else:
            hasher=hashlib.sha256();n=0
            body=S3.get_object(Bucket=BUCKET,Key=w['object_key'],IfMatch=h['ETag'])['Body']
            try:
                for chunk in body.iter_chunks(chunk_size=1024*1024):
                    n+=len(chunk);require(n<=w['byte_size'],'S3 object exceeded declared size');hasher.update(chunk)
            finally:body.close()
            require(n==w['byte_size'],'S3 body was truncated')
            observed=hasher.hexdigest();method='Owner independently streamed and hashed full S3 object'
        require(observed==w['sha256'],'S3 content mismatch: '+w['object_key'])
        return {**w,'checksum_type':'FULL_OBJECT','checksum_algorithm':'SHA256','checksum':base64.b64encode(bytes.fromhex(observed)).decode(),'checksum_source':method,'etag':h['ETag'],'last_modified':h['LastModified'].isoformat(),'verified_at':now(),'status':'verified_existing_remote'}
    print('Revalidating 315 S3 objects independently',flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:objects=list(pool.map(verify,expected_objects(m)))
    receipt={'format':'etl4-batch-upload-v1','evidence_origin':'owner-independent-s3-verification-v1','provenance_notice':'Generated by the owner from direct S3 verification. This is NOT the teammate original Step 39 upload receipt and does not claim to identify the uploader. The format is compatible with the unchanged Step 40 evidence validator.','authorization':'Owner requested direct merge without waiting for teammate upload_receipt.json on 2026-10-11.','batch_id':BATCH,'manifest_sha256':MANIFEST_SHA,'bucket':BUCKET,'region':REGION,'prefix':'etl4','status':'complete','expected_objects':len(objects),'completed_objects':len(objects),'objects':objects,'completed_at':now()}
    path=OUT/'owner_verified_upload_evidence.json';write_json(path,receipt)
    step.upload_evidence(EXPORT,m,MANIFEST_SHA,path)
    print('Owner evidence verified by unchanged Step 40 validator',flush=True)
    return file_info(path,'owner_verified_evidence')['sha256']
def recheck_remote(receipt):
    def check(row):
        h=S3.head_object(Bucket=BUCKET,Key=row['object_key'])
        require(h['ContentLength']==row['byte_size'] and h['ETag']==row['etag'] and h['LastModified'].isoformat()==row['last_modified'],'S3 object changed after verification: '+row['object_key'])
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(check,receipt['objects']))
def check_new_scope(conn):
    require(not conn.execute('SELECT 1 FROM core.borehole WHERE id=%s OR (provider_code=%s AND source_hole_id=%s)',(BID,'wa','BSDD023')).fetchone(),'Incoming borehole already exists; inspect before proceeding')
    require(not conn.execute('SELECT 1 FROM core.dataset WHERE id=%s OR borehole_id=%s',(DID,BID)).fetchone(),'Incoming dataset already exists')
    require(not conn.execute('SELECT 1 FROM core.dataset_revision WHERE id=%s OR dataset_id=%s',(RID,DID)).fetchone(),'Incoming revision already exists')
def candidate_guard(conn,before):
    accumulated,sources,replacements=step.accumulated_members(conn,[])
    require(accumulated==before['members'] and not replacements,'Latest staged candidate differs from current approved release; refusing to carry it forward')
    return sources
def prepare():
    code_hash=check_code();m=export_check();evidence_sha=generate_owner_evidence(m)
    with connect(readonly=True) as conn:
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            step.ensure_schema(conn,m,False)
            before=active(conn);sources=candidate_guard(conn,before);check_new_scope(conn)
            step.check_storage_root(conn,{'bucket':BUCKET,'region':REGION,'prefix':'etl4','root_key':ROOT_KEY})
            prior=plain(conn.execute('SELECT manifest_sha256,manifest FROM core.data_release WHERE id=%s',(before['release_id'],)).fetchone())
            parts=plain(conn.execute('SELECT to_jsonb(p)-\'release_id\'-\'composite_id\' value FROM core.borehole_composite_part p WHERE release_id=%s ORDER BY borehole_id,sequence_no',(before['release_id'],)).fetchall())
    selected=sorted(before['members']+[{'dataset_id':DID,'dataset_revision_id':RID}],key=lambda x:x['dataset_id'])
    selection={'expected_active_release_id':before['release_id'],'datasets':selected,'omitted_dataset_ids':[],'source_release_ids':[before['release_id']]}
    write_json(OUT/'finalize_selection.json',selection)
    plan={'batch_id':BATCH,'manifest_sha256':MANIFEST_SHA,'code_manifest_sha256':code_hash,'owner_evidence_sha256':evidence_sha,'before':before,'after_expected':{'holes':before['holes']+1,'datasets':before['datasets']+1},'source_releases':sources,'prior_release':prior,'prior_display_parts':parts,'prepared_at':now(),'selection_sha256':file_info(OUT/'finalize_selection.json','selection')['sha256'],'scope':'All currently approved members unchanged, plus BSDD023 only. No omission/replacement/migration/permission change.'}
    write_json(OUT/'publication_plan.json',plan)
    print('PREPARED '+json.dumps({'before':{k:v for k,v in before.items() if k!='members'},'after_expected':plan['after_expected'],'objects':315,'all_previous_members_preserved':True,'new_hole':'BSDD023','owner_evidence_sha256':evidence_sha}),flush=True)
def verify_reader(expected_release,plan):
    with connect('etl4_reader',True) as conn:
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            state=active(conn);require(state['release_id']==expected_release,'Reader sees unexpected active release')
            row=plain(conn.execute('SELECT v.* FROM core.active_release a JOIN core.v_borehole_dataset_full v ON v.release_id=a.release_id WHERE v.borehole_id=%s',(BID,)).fetchone())
            require(row and row['dataset_id']==DID and row['dataset_revision_id']==RID and row['sample_count']==8040,'Reader cannot see new complete dataset')
            count=conn.execute('SELECT count(*) n FROM core.active_release a JOIN core.v_borehole_composite_samples v ON v.release_id=a.release_id WHERE v.borehole_id=%s',(BID,)).fetchone()['n']
            require(count==8040,'Reader composite sample count mismatch')
            locations=plain(conn.execute('SELECT a.asset_kind,l.object_key,l.root_key FROM core.asset a JOIN core.asset_location l ON l.asset_id=a.id WHERE a.dataset_revision_id=%s AND l.backend=\'s3\' ORDER BY a.asset_kind,a.id',(RID,)).fetchall())
            require(len(locations)==289 and all(x['root_key']==ROOT_KEY for x in locations),'Reader asset location scope mismatch')
            samples=[]
            for kind in ('scalar','spectral','image','core_row_image'):
                target=next(x for x in locations if x['asset_kind']==kind)
                response=S3.get_object(Bucket=BUCKET,Key=target['object_key'],Range='bytes=0-63')
                with response['Body'] as body:data=body.read()
                require(bool(data),'Empty S3 range response')
                samples.append({'kind':kind,'key':target['object_key'],'bytes_read':len(data),'http_status':response['ResponseMetadata']['HTTPStatusCode']})
            old=plan['before']['members'][0]
            old_count=conn.execute('SELECT count(*) n FROM core.active_release a JOIN core.release_dataset rd ON rd.release_id=a.release_id WHERE rd.dataset_id=%s AND rd.dataset_revision_id=%s',(old['dataset_id'],old['dataset_revision_id'])).fetchone()['n']
            require(old_count==1,'Old reader dataset missing')
    return {'database_user':'etl4_reader','active_release_id':expected_release,'new_dataset':row,'composite_samples':count,'asset_locations':len(locations),'s3_range_reads':samples,'s3_request_identity':'Owner AWS identity; tests actual reader-visible S3 keys, not teammate IAM identity','old_dataset_readable':True,'api_http_test':'Not performed: no live teammate API endpoint was supplied.'}
def apply():
    code_hash=check_code();m=export_check();plan=read_json(OUT/'publication_plan.json');selection=read_json(OUT/'finalize_selection.json')
    require(plan['batch_id']==BATCH and plan['manifest_sha256']==MANIFEST_SHA and plan['code_manifest_sha256']==code_hash,'Plan identity/code changed')
    evidence_path=OUT/'owner_verified_upload_evidence.json'
    require(file_info(evidence_path,'evidence')['sha256']==plan['owner_evidence_sha256'],'Owner verification evidence changed')
    require(file_info(OUT/'finalize_selection.json','selection')['sha256']==plan['selection_sha256'],'Finalize selection changed')
    receipt=read_json(evidence_path);step.upload_evidence(EXPORT,m,MANIFEST_SHA,evidence_path);recheck_remote(receipt)
    with connect() as conn:
        require(conn.execute('SELECT pg_try_advisory_lock(%s) ok',(LOCK_KEY,)).fetchone()['ok'],'Another import/publication is running')
        try:
            before=active(conn)
            require(before==plan['before'],'Active release/membership changed; prepare a new current-plus-batch plan')
            candidate_guard(conn,before);check_new_scope(conn)
            @contextmanager
            def borrowed():yield conn
            print('LOCKED: importing BSDD023 and finalizing the exact planned member list',flush=True)
            result=step.merge_batch(EXPORT,upload_receipt=evidence_path,receipt_path=OUT/'merge_receipt.json',root_key=ROOT_KEY,finalize=OUT/'finalize_selection.json',apply_migrations=False,connect=borrowed)
            write_json(OUT/'merge_result.json',result)
            after=active(conn)
            require(after['members']==selection['datasets'],'Final release member set differs from approved plan')
            require(after['holes']==plan['after_expected']['holes'] and after['datasets']==plan['after_expected']['datasets'],'Final release counts differ')
            require(after['release_id']==result['finalized_release_id'],'Active release differs from merge result')
            prior=plain(conn.execute('SELECT manifest_sha256,manifest FROM core.data_release WHERE id=%s',(before['release_id'],)).fetchone())
            require(prior==plan['prior_release'],'Prior release manifest changed')
            old_holes=conn.execute('SELECT distinct d.borehole_id FROM core.release_dataset rd JOIN core.dataset d ON d.id=rd.dataset_id WHERE rd.release_id=%s',(before['release_id'],)).fetchall()
            parts=plain(conn.execute('SELECT to_jsonb(p)-\'release_id\'-\'composite_id\' value FROM core.borehole_composite_part p WHERE release_id=%s AND borehole_id=ANY(%s::uuid[]) ORDER BY borehole_id,sequence_no',(after['release_id'],[x['borehole_id'] for x in old_holes])).fetchall())
            require(parts==plan['prior_display_parts'],'An existing borehole display selection changed')
            counts={name:conn.execute('SELECT count(*) n FROM core.'+name+' WHERE dataset_revision_id=%s',(RID,)).fetchone()['n'] for name in ('asset','sample_axis','image_frame','image_region','image_region_asset','image_sample_mapping','spectral_array','spectral_sample_map','scan_log','data_chunk')}
            require(all(counts[name]==m['tables'][name]['rows'] for name in counts),'Imported table counts differ from manifest')
            replay=step.merge_batch(EXPORT,upload_receipt=evidence_path,receipt_path=OUT/'replay_receipt.json',root_key=ROOT_KEY,apply_migrations=False,connect=borrowed)
            require(replay['reused'] and not replay['active_release_changed'] and active(conn)==after,'Repeat submission was not idempotent')
            verification={'status':'passed','batch_id':BATCH,'before':{k:v for k,v in before.items() if k!='members'},'after':{k:v for k,v in after.items() if k!='members'},'all_previous_members_unchanged':True,'prior_release_manifest_unchanged':True,'existing_display_selections_unchanged':True,'imported_table_counts':counts,'repeat_submission_reused':True,'verified_at':now()}
            write_json(OUT/'publication_verification.json',verification)
        finally:conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_KEY,))
    reader=verify_reader(after['release_id'],plan);write_json(OUT/'reader_verification.json',reader)
    print('PUBLISHED '+json.dumps(verification),flush=True)
    print('READER_VERIFIED '+json.dumps({'samples':reader['composite_samples'],'asset_locations':reader['asset_locations'],'s3_range_reads':len(reader['s3_range_reads']),'database_user':'etl4_reader'}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();g=parser.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--apply',action='store_true');args=parser.parse_args()
    try:
        if args.prepare:prepare()
        else:apply()
    except Exception as exc:
        write_json(OUT/('apply_error.json' if args.apply else 'prepare_error.json'),{'type':type(exc).__name__,'message':str(exc),'time':now()})
        traceback.print_exc();sys.exit(1)
    finally:
        package=Path.home()/'publish_BSDD023_20261011_results.zip'
        with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
            for p in OUT.rglob('*'):
                if p.is_file():z.write(p,p.relative_to(OUT).as_posix())
        print('RESULT_ARCHIVE '+json.dumps({'path':str(package),'bytes':package.stat().st_size,'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}),flush=True)
