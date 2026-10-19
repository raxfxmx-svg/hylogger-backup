BUCKET = 'hyloggerdemo-000000000000-ap-southeast-2-an'
REGION = 'ap-southeast-2'
BATCH = 'e704df799acda67aa438cabf30d6a227dffd12b6ab84f7131021b3cbdeb1781d'
HOST = 'db.example.com'
ROOT = Path.home()/'audit_BSDD023_20261011'
ROOT.mkdir(exist_ok=True)
EXPORT = ROOT/'export'
EXPORT.mkdir(exist_ok=True)
REPORT={'batch_id':BATCH,'bucket':BUCKET,'region':REGION,'started_at':datetime.now(timezone.utc).isoformat(),'mode':'READ ONLY: S3 List/Get/Head; PostgreSQL READ ONLY transaction','checks':[],'limitations':['No cloud merge/publication performed.','Uploader identity is not inferred from S3 LastModified.','Local scientific acceptance is verified as delivered evidence; raw scientific computations are not rerun.','The teammate upload receipt is not automatically uploaded by Step 39 and has not been supplied.']}
def check(name,condition,detail=None):
    REPORT['checks'].append({'name':name,'passed':bool(condition),'detail':detail})
    print(('PASS ' if condition else 'FAIL ')+name,flush=True)

def main():
    session=boto3.Session(region_name=REGION)
    s3=session.client('s3')
    prefix='etl4/batches/'+BATCH+'/'
    listed=[v for page in s3.get_paginator('list_objects_v2').paginate(Bucket=BUCKET,Prefix=prefix) for v in page.get('Contents',[])]
    candidates=[v for v in listed if v['Key'].endswith('/manifest.json')]
    REPORT['manifest_candidates']=[{k:str(v[k]) for k in ('Key','Size','LastModified')} for v in candidates]
    require(len(candidates)==1,'Expected exactly one manifest; review alternate exports before proceeding')
    key=candidates[0]['Key']; base=key.rsplit('/',1)[0]
    require(candidates[0]['Size']<16*1024*1024,'Manifest is unexpectedly large')
    raw=s3.get_object(Bucket=BUCKET,Key=key)['Body'].read()
    (EXPORT/'manifest.json').write_bytes(raw)
    m=read_json(EXPORT/'manifest.json')
    msha=hashlib.sha256(raw).hexdigest()
    REPORT.update(manifest_key=key,manifest_sha256=msha,manifest_uploaded_at=candidates[0]['LastModified'].isoformat(),datasets=m['datasets'])
    check('manifest path and identity',msha==base.rsplit('/',1)[1] and m['batch_id']==BATCH and digest(m['identity'])==BATCH)
    require(sum(v['byte_size'] for v in m['files'].values())<128*1024*1024,'Structured export exceeds audit download bound')
    for relative,item in m['files'].items():
        path=local_file(EXPORT,relative)
        require(relative.startswith(('tables/','evidence/','schema/')) or relative=='composites.json','Unexpected file type')
        data=s3.get_object(Bucket=BUCKET,Key=base+'/'+relative)['Body'].read()
        require(len(data)==item['byte_size'] and hashlib.sha256(data).hexdigest()==item['sha256'],'File integrity mismatch: '+relative)
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    checked,checked_sha=load_export(EXPORT)
    check('owner Step 38/39 export format and all structured file SHA256',checked_sha==msha,{'files':len(m['files'])})
    validations,composites=local_acceptance_evidence(EXPORT,m)
    second=read_json(EXPORT/'evidence/acceptance_2.json')
    REPORT['acceptance_2_summary']={k:v for k,v in second.items() if k not in ('example_selections','prepared_acceptances')}
    REPORT['composites']=composites
    check('owner Step 40 local acceptance evidence',True,{'revisions':list(validations),'stage_2_status':second['status']})
    check('batch migrations match owner code',m['schema']['migrations']==OWNER_MIGRATIONS,{'batch':m['schema']['migrations'],'owner':OWNER_MIGRATIONS})
    tables={};table_checks=[]
    for name,info in m['tables'].items():
        rows=[]; keys=set();count=0
        with gzip.open(EXPORT/info['path'],'rt',encoding='utf-8') as f:
            for line in f:
                require(len(line)<8*1024*1024,'Unexpected JSON line size')
                row=json.loads(line);count+=1
                require(set(row)==set(info['columns']),'Column mismatch: '+name)
                pk=tuple(row[k] for k in info['primary_key'])
                require(pk not in keys,'Duplicate primary key: '+name);keys.add(pk)
                rows.append(row)
                require(count<2000000,'Unexpected row count')
        require(count==info['rows'],'Row count mismatch: '+name)
        tables[name]=rows
        table_checks.append({'table':name,'rows':count})
    REPORT['table_counts']=table_checks
    REPORT['boreholes']=tables['borehole'];REPORT['sample_axes']=tables['sample_axis']
    REPORT['quality_issue_summary']=dict(Counter((v['severity']+':'+v['code']) for v in tables['quality_issue']))
    check('all table row counts, columns and primary-key uniqueness',True,table_checks)
    check('one named borehole and one dataset',len(tables['borehole'])==1 and tables['borehole'][0]['source_hole_id']=='BSDD023' and len(m['datasets'])==1)
    assets={a['object_key']:a for a in m['assets']}
    expected={('etl4/'+k):{'sha256':a['sha256'],'byte_size':a['byte_size'],'kind':'asset'} for k,a in assets.items()}
    expected.update({base+'/'+p:{'sha256':v['sha256'],'byte_size':v['byte_size'],'kind':v['kind']} for p,v in m['files'].items()})
    expected[key]={'sha256':msha,'byte_size':len(raw),'kind':'manifest'}
    REPORT['object_totals']={'asset_records':len(m['assets']),'unique_asset_objects':len(assets),'delivery_files':len(m['files']),'total_objects':len(expected),'total_bytes':sum(v['byte_size'] for v in expected.values()),'asset_bytes':sum(a['byte_size'] for a in assets.values()),'batch_directory_objects':len(listed)}
    check('manifest-derived unique object scope',len(expected)==len(assets)+len(m['files'])+1,REPORT['object_totals'])
    check('batch directory contains expected delivery files',set([base+'/'+p for p in m['files']]+[key]).issubset(set(v['Key'] for v in listed)))
    REPORT['extra_batch_files']=[v['Key'] for v in listed if v['Key'] not in set([base+'/'+p for p in m['files']]+[key])]
    def head(kv):
        k,wanted=kv
        try:
            h=s3.head_object(Bucket=BUCKET,Key=k,ChecksumMode='ENABLED')
            sha_ok=h.get('ChecksumType')=='FULL_OBJECT' and h.get('ChecksumSHA256')==base64.b64encode(bytes.fromhex(wanted['sha256'])).decode()
            return {'key':k,**wanted,'exists':True,'size_ok':h['ContentLength']==wanted['byte_size'],'sha256_verified_by_s3':sha_ok,'native':{n:h[n] for n in ('ChecksumType','ChecksumSHA256','ChecksumCRC32','ChecksumCRC32C','ChecksumCRC64NVME','ETag','LastModified','VersionId','ServerSideEncryption') if n in h}}
        except Exception as e:
            return {'key':k,**wanted,'exists':False,'error':str(e)}
    with ThreadPoolExecutor(max_workers=6) as pool:
        heads=list(pool.map(head,expected.items()))
    REPORT['objects']=heads
    check('all expected S3 objects exist and sizes match',all(h.get('exists') and h.get('size_ok') for h in heads))
    checksum_groups=Counter(('SHA256_VERIFIED' if h.get('sha256_verified_by_s3') else h.get('native',{}).get('ChecksumType','NO_CHECKSUM')) for h in heads)
    REPORT['checksum_summary']=dict(checksum_groups)
    REPORT['objects_requiring_streamed_sha256']=[{'key':h['key'],'byte_size':h['byte_size'],'sha256':h['sha256'],'kind':h['kind']} for h in heads if not h.get('sha256_verified_by_s3') and h['kind']=='asset']
    print('S3_SUMMARY '+json.dumps(REPORT['object_totals'])+' CHECKSUMS '+json.dumps(REPORT['checksum_summary']),flush=True)
    print('Connecting to Aurora with a READ ONLY transaction',flush=True)
    token=session.client('rds').generate_db_auth_token(DBHostname=HOST,Port=5432,DBUsername='postgres')
    with psycopg.connect(host=HOST,port=5432,dbname='etl4_core',user='postgres',password=token,sslmode='verify-full',sslrootcert=ssl.get_default_verify_paths().cafile,connect_timeout=60,autocommit=True,row_factory=dict_row,options='-c default_transaction_read_only=on -c statement_timeout=60000') as conn:
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            ro=conn.execute('SHOW transaction_read_only').fetchone()
            check('database transaction is read-only',ro['transaction_read_only']=='on')
            active=conn.execute('SELECT release_id::text,switched_at FROM core.active_release WHERE singleton').fetchone()
            members=conn.execute('SELECT rd.dataset_id::text,rd.dataset_revision_id::text,d.borehole_id::text,b.source_hole_id FROM core.active_release a JOIN core.release_dataset rd ON rd.release_id=a.release_id JOIN core.dataset d ON d.id=rd.dataset_id JOIN core.borehole b ON b.id=d.borehole_id ORDER BY rd.dataset_id').fetchall()
            REPORT['cloud_active']={**active,'holes':len({r['borehole_id'] for r in members}),'datasets':len(members)}
            REPORT['cloud_active_members']=members
            applied=conn.execute('SELECT name,sha256 FROM core.schema_migration ORDER BY name').fetchall()
            REPORT['cloud_migrations']=applied
            check('batch migrations equal cloud migrations',applied==m['schema']['migrations'])
            cloud_schema=inspect_columns(conn)
            check('batch schema equals cloud columns/types/keys',cloud_schema==m['schema']['tables'])
            bids=[v['borehole_id'] for v in m['datasets']];dids=[v['dataset_id'] for v in m['datasets']];rids=[v['dataset_revision_id'] for v in m['datasets']]
            holes=conn.execute('SELECT * FROM core.borehole WHERE id=ANY(%s::uuid[]) OR source_hole_id=%s',(bids,'BSDD023')).fetchall()
            datasets=conn.execute('SELECT * FROM core.dataset WHERE id=ANY(%s::uuid[]) OR borehole_id=ANY(%s::uuid[])',(dids,bids)).fetchall()
            revisions=conn.execute('SELECT id,dataset_id,borehole_id,input_digest,source_snapshot_id,pipeline_id FROM core.dataset_revision WHERE id=ANY(%s::uuid[]) OR dataset_id=ANY(%s::uuid[])',(rids,dids)).fetchall()
            REPORT['cloud_existing']={'boreholes':holes,'datasets':datasets,'revisions':revisions}
            check('incoming borehole/dataset/revision are new to cloud',not holes and not datasets and not revisions,REPORT['cloud_existing'])
            runs=conn.execute("SELECT id,status,started_at,finished_at,holes,detail FROM core.ingest_run WHERE detail::text LIKE %s ORDER BY started_at DESC",('%'+BATCH+'%',)).fetchall()
            REPORT['cloud_batch_runs']=runs
            check('no previous cloud import record for this batch',not runs)
            staged=conn.execute("SELECT id,finished_at,detail->>'release_id' release_id FROM core.ingest_run WHERE status='staged' AND detail->>'flow'='etl4-cloud-batch-v1' AND detail ? 'release_id' ORDER BY finished_at DESC,id DESC LIMIT 1").fetchone()
            REPORT['latest_staged']=staged
            extra=[];changed=[]
            if staged and staged['release_id']!=active['release_id']:
                candidate=conn.execute('SELECT dataset_id::text,dataset_revision_id::text FROM core.release_dataset WHERE release_id=%s',(staged['release_id'],)).fetchall()
                active_map={r['dataset_id']:r['dataset_revision_id'] for r in members}
                extra=[v for v in candidate if v['dataset_id'] not in active_map]
                changed=[v for v in candidate if v['dataset_id'] in active_map and v['dataset_revision_id']!=active_map[v['dataset_id']]]
            REPORT['latest_staged_unapproved_delta']={'extra_datasets':extra,'changed_revisions':changed}
            check('latest staged release would not pull in additional changes',not extra and not changed)
            REPORT['expected_counts_if_approved_as_new']={'holes':len({r['borehole_id'] for r in members}|set(bids)),'datasets':len({r['dataset_id'] for r in members}|set(dids))}
    print('DB_SUMMARY '+json.dumps(REPORT['cloud_active'],default=str),flush=True)
    print('EXISTING '+json.dumps(REPORT['cloud_existing'],default=str),flush=True)
    print('STAGED_DELTA '+json.dumps(REPORT['latest_staged_unapproved_delta'],default=str),flush=True)

try:
    main()
except Exception as e:
    REPORT['fatal_error']=str(e)
    traceback.print_exc()
finally:
    REPORT['finished_at']=datetime.now(timezone.utc).isoformat()
    (ROOT/'audit_report.json').write_bytes(encoded(REPORT))
    package=Path.home()/'audit_BSDD023_20261011.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(ROOT).as_posix())
    print('AUDIT_RESULT '+json.dumps({'failed_checks':[c['name'] for c in REPORT['checks'] if not c['passed']],'fatal_error':REPORT.get('fatal_error'),'archive':str(package),'archive_bytes':package.stat().st_size,'archive_sha256':sha(package)}),flush=True)
