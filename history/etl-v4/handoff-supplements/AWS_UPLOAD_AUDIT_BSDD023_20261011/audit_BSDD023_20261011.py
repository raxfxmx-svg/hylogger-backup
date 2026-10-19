import base64, gzip, hashlib, io, json, re, ssl, sys, traceback, zipfile
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import boto3
import psycopg
from psycopg.rows import dict_row

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False, default=str) + "\n").encode("utf-8")
def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def safe_child(root, relative):
    root=Path(root).resolve()
    path=(root/relative).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("Unsafe relative path")
    return path


FORMAT = "etl4-batch-v1"

DATA_TABLES = (
    "borehole", "borehole_revision", "dataset", "dataset_revision", "sample_axis",
    "core_interval", "scan_sample", "spectral_stream", "interpretation_set",
    "interpretation_input", "metric_definition", "scan_log", "log_axis_binding",
    "asset", "log_asset", "data_chunk", "image_frame", "source_document",
    "source_reference", "quality_issue", "borehole_branch", "dataset_segment",
    "survey_station", "spectral_array", "spectral_sample_map", "spectral_block",
    "image_region", "image_sample_mapping", "image_region_asset",
)

EVIDENCE_TABLES = ("revision_validation", "asset_location")

RELEASE_TABLES = ("data_release", "release_dataset", "active_release",
                  "borehole_composite", "borehole_composite_part", "dataset_succession")

ADMIN_TABLES = ("schema_migration", "ingest_run")

KNOWN_TABLES = set(DATA_TABLES + EVIDENCE_TABLES + RELEASE_TABLES + ADMIN_TABLES)

def require(condition, message):
    if not condition:
        raise ValueError(message)

def checksum(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

def object_key(sha256):
    require(checksum(sha256), 'The asset is missing a valid SHA256')
    return f"objects/sha256/{sha256[:2]}/{sha256}"

def file_info(path, kind):
    return {"sha256": sha(path), "byte_size": Path(path).stat().st_size, "kind": kind}

def read_json(path):
    # Reject duplicate keys so separate stages cannot interpret the same manifest differently.
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"The batch JSON contains a duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs)

def check_file_info(value):
    require(isinstance(value, dict) and checksum(value.get("sha256")), 'Invalid delivery file digest')
    require(type(value.get("byte_size")) is int and value["byte_size"] >= 0, 'Invalid delivery file size')

def local_file(directory, relative):
    require(isinstance(relative, str) and "\\" not in relative and ":" not in relative,
            'Delivery files must use relative paths with forward slashes')
    return safe_child(directory, relative)

def load_export(directory):
    """Validate received export files without reading the original images or spectra referenced by the manifest.
    Validate incoming export boundaries without reading referenced original images or spectra.
    """
    directory = Path(directory).resolve()
    path = directory / "manifest.json"
    manifest = read_json(path)
    require(manifest.get("format") == FORMAT, 'Unsupported batch format')
    require(isinstance(manifest.get("identity"), dict)
            and manifest.get("batch_id") == digest(manifest["identity"]), 'The batch ID does not match its identity')
    identity = manifest["identity"]
    require(identity.get("format") == FORMAT, 'The batch identity format does not match')
    files = manifest.get("files")
    require(isinstance(files, dict) and files, 'The batch contains no structured files')
    for relative, value in files.items():
        require(relative.startswith(("tables/", "evidence/", "schema/")) or relative == "composites.json",
                'The manifest contains non-delivery files or private run files')
        source = local_file(directory, relative)
        check_file_info(value)
        require(source.is_file() and source.stat().st_size == value["byte_size"]
                and sha(source) == value["sha256"], f"The delivery file is missing or its content changed: {relative}")
    schema = manifest.get("schema")
    require(isinstance(schema, dict) and isinstance(schema.get("tables"), dict)
            and set(schema["tables"]) == KNOWN_TABLES, 'The batch database schema has an incomplete table scope')
    migrations = schema.get("migrations")
    require(isinstance(migrations, list), 'The batch is missing its migration manifest')
    migration_hashes = {}
    for migration in migrations:
        name = migration.get("name")
        require(isinstance(name, str) and name not in migration_hashes
                and checksum(migration.get("sha256")), 'A migration name is duplicated or its digest is invalid')
        migration_hashes[name] = migration["sha256"]
        relative = "schema/" + name
        require(relative in files and files[relative]["sha256"] == migration["sha256"],
                'The migration file digest does not match the schema manifest')
    require(migration_hashes == identity.get("schema_migrations"), 'The migration manifest does not match the batch identity')
    require(isinstance(manifest.get("tables"), dict)
            and set(manifest["tables"]) == set(DATA_TABLES), 'The batch has an incomplete data table scope')
    for name, table in manifest["tables"].items():
        require(re.fullmatch(r"[a-z][a-z0-9_]*", name) is not None, 'Invalid data table name')
        relative = table.get("path")
        require(relative == f"tables/{name}.jsonl.gz" and relative in files, 'The data table file is not in the delivery manifest')
        require(all(table.get(key) == files[relative][key] for key in ("sha256", "byte_size")),
                'The data table digest does not match the file manifest')
    require({path for path in files if path.startswith("tables/")}
            == {table["path"] for table in manifest["tables"].values()}, 'The delivery files contain unlisted data tables')
    datasets = manifest.get("datasets")
    require(isinstance(datasets, list) and datasets, 'The batch contains no datasets')
    revisions = {item["dataset_revision_id"] for item in datasets}
    require(len(revisions) == len(datasets)
            and len({item["dataset_id"] for item in datasets}) == len(datasets), 'The batch contains duplicate datasets')
    dataset_identities = []
    for item in datasets:
        require(checksum(item.get("input_digest")), 'Invalid dataset input identity')
        dataset_identities.append({key: item[key] for key in ("dataset_id", "dataset_revision_id", "input_digest")})
    require(sorted(dataset_identities, key=lambda item: item["dataset_id"])
            == identity.get("datasets"), 'The dataset manifest does not match the batch identity')
    ids, objects = set(), {}
    assets = manifest.get("assets")
    require(isinstance(assets, list), 'The batch is missing its asset manifest')
    for asset in assets:
        check_file_info(asset)
        require(asset.get("asset_id") and asset["asset_id"] not in ids, 'An asset ID is missing or duplicated')
        require(asset.get("dataset_revision_id") in revisions, 'The asset belongs to a revision outside this batch')
        require(asset.get("object_key") == object_key(asset["sha256"]), 'The asset object key does not match its content identity')
        ids.add(asset["asset_id"])
        content = (asset["sha256"], asset["byte_size"])
        require(objects.setdefault(asset["object_key"], content) == content, 'The same object key has conflicting content')
    return manifest, sha(path)

def inspect_columns(conn):
    tables = {row["table_name"] for row in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='core' AND table_type='BASE TABLE'"
    ).fetchall()}
    require(tables == KNOWN_TABLES, 'The cloud table scope does not match the batch format')
    rows = conn.execute("""SELECT c.relname table_name,a.attname column_name,
        format_type(a.atttypid,a.atttypmod) data_type,NOT a.attnotnull nullable
        FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='core' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum""").fetchall()
    keys = conn.execute("""SELECT c.relname table_name,array_agg(a.attname ORDER BY k.ordinality) primary_key
        FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN LATERAL unnest(p.conkey) WITH ORDINALITY k(attnum,ordinality)
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
        WHERE n.nspname='core' AND p.contype='p' GROUP BY c.relname""").fetchall()
    result = {name: {"columns": [], "primary_key": []} for name in tables}
    for row in rows:
        result[row["table_name"]]["columns"].append({key: row[key] for key in ("column_name", "data_type", "nullable")})
    for row in keys:
        result[row["table_name"]]["primary_key"] = list(row["primary_key"])
    return result

def local_acceptance_evidence(directory, manifest):
    second = read_json(directory / "evidence/acceptance_2.json")
    wanted = {item["dataset_id"]: {"dataset_revision_id": item["dataset_revision_id"], "input_digest": item["input_digest"]}
              for item in manifest["datasets"]}
    require(second.get("stage") == 2 and second.get("status") == "passed"
            and second.get("dataset_contents") == wanted and second.get("content_sha256") == digest(wanted),
            "The second local acceptance does not correspond to this batch's data")
    covered = set()
    require(second.get("prepared_acceptances"), 'The referenced first local acceptance is missing')
    for item in second["prepared_acceptances"]:
        path = item["report_path"]
        require(path in manifest["files"] and path.startswith("evidence/"), 'The first-stage report is not listed in the delivery manifest')
        report = read_json(directory / path)
        content = report.get("content", {})
        require(report.get("stage") == 1 and report.get("status") == "passed"
                and content.get("package_sha256") == item["package_sha256"]
                and report.get("content_sha256") == item["content_sha256"] == digest(content), 'The first local acceptance does not match')
        ids = set(content.get("datasets", {}))
        require(not covered.intersection(ids), 'The first-stage reports contain duplicate datasets')
        covered.update(ids)
    require(covered == set(wanted), 'The first acceptance covers different datasets')
    rows = read_json(directory / "evidence/revision_validation.json")["rows"]
    validations = {item["dataset_revision_id"]: item for item in rows}
    require(len(rows) == len(validations) and set(validations) == {item["dataset_revision_id"] for item in wanted.values()},
            'The local revision acceptance evidence covers a different scope')
    for item in wanted.values():
        value = validations[item["dataset_revision_id"]]
        require(value["input_digest"] == item["input_digest"] and value["result"].get("status") == "passed",
                'The local revision acceptance has not passed')
    composites = read_json(directory / "composites.json")
    require(digest(composites["definition"]) == manifest["identity"]["composite_definition_sha256"],
            "The display definition does not match this batch's identity")
    return validations, composites

OWNER_MIGRATIONS = [{'name': '001_initial.sql', 'sha256': '35ce6669acacd1e738f6d550f16c1a7631fc937d10f8fc61f063212d23071082'}, {'name': '002_nullable_metric_semantics.sql', 'sha256': '7cad9bd7fd5430dc773c1acee605b89c5465f33d246f15eb63e7e1e0553496db'}, {'name': '003_metric_source_identity.sql', 'sha256': 'de3c9a0df5c59f7de888851528f14a2c9870f5f3ee61f14884c986050f885310'}, {'name': '004_relational_integrity.sql', 'sha256': 'e0860f1a793ad022a642b3ca6261d0d69280e6687bed80d94d5b06f0b97a5cc9'}, {'name': '005_sample_media.sql', 'sha256': '5bea0cd4bd5cb454b1acec09544020f440460f16e69ee2ae8a0a254ffbbfa680'}, {'name': '006_multi_dataset_composites.sql', 'sha256': '8f8447e5805a409f2fdb5e5f1c5ca578ff208b8a1cf62d45a1280ce3c147e6a6'}]

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
