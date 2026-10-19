"""Five-hole CloudShell deployment. Credentials stay in the AWS SDK provider."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TARGET = json.loads((ROOT / 'deployment/target.json').read_text(encoding='utf-8'))
RELEASE = TARGET['release_id']

def save(name, value):
    p = ROOT / 'validation' / name
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(value, indent=2, default=str) + '\n', encoding='utf-8')

def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8-sig'))

def sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()

def client(service):
    import boto3
    from botocore.config import Config
    return boto3.client(service, region_name=TARGET['region'],
        config=Config(signature_version='s3v4' if service == 's3' else 'v4',
                      connect_timeout=10, read_timeout=60, retries={'max_attempts': 4}))

def identity():
    account = client('sts').get_caller_identity()['Account']
    if account != TARGET['aws_account_id']:
        raise ValueError('Unexpected AWS account')

def params(database=None, user=None):
    user = user or TARGET['admin_user']
    ca = os.environ.get('ETL4_CA_FILE') or ssl.get_default_verify_paths().cafile
    if not ca or not Path(ca).is_file():
        raise ValueError('A trusted public CA bundle is required')
    return dict(host=TARGET['host'], port=TARGET['port'],
        dbname=database or TARGET['database'], user=user, sslmode='verify-full',
        sslrootcert=ca, connect_timeout=30,
        password=client('rds').generate_db_auth_token(DBHostname=TARGET['host'],
            Port=TARGET['port'], DBUsername=user))

def connect(database=None, user=None):
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(**params(database, user), autocommit=True, row_factory=dict_row)

def helper():
    spec = importlib.util.spec_from_file_location('handoff_ops', ROOT / 'tools/handoff.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def objects():
    manifest, unique = helper().assets()
    if manifest['release_id'] != RELEASE:
        raise ValueError('Wrong release')
    return unique

def restore():
    import psycopg
    from psycopg import sql
    info = load('deployment/restore_payload.json')
    payload = ROOT / 'deployment/core_restore.sql.gz'
    if sha_file(payload) != info['gzip_sha256']:
        raise ValueError('Restore payload checksum mismatch')
    backup = load('manifests/database_backup.json')
    if info['source_dump_sha256'] != backup['backup_sha256']:
        raise ValueError('Restore payload and selected dump do not match')
    with connect('postgres') as c:
        if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s', (TARGET['database'],)).fetchone():
            c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(TARGET['database'])))
    with connect() as c:
        version = int(c.execute('SHOW server_version_num').fetchone()['server_version_num'])
        if version != 170009:
            raise ValueError('This compatibility trial is scoped to PostgreSQL 17.9')
        if c.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='core' LIMIT 1").fetchone():
            raise ValueError('The target core schema is populated; refusing to overwrite')
        versions = {r['version'] for r in c.execute("SELECT version FROM pg_available_extension_versions WHERE name='postgis'")}
        if '3.5.6' not in versions:
            raise ValueError('The inspected PostGIS 3.5.6 target is not available')
        c.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public VERSION '3.5.6'")
        ext = c.execute("SELECT extversion,extnamespace::regnamespace::text AS schema FROM pg_extension WHERE extname='postgis'").fetchone()
        if ext != {'extversion': '3.5.6', 'schema': 'public'}:
            raise ValueError('Unexpected installed PostGIS version/schema')
        c.execute('CREATE SCHEMA IF NOT EXISTS core')
    p = params()
    env = os.environ.copy()
    env['PGPASSWORD'] = p.pop('password')
    dsn = psycopg.conninfo.make_conninfo(**p)
    log = ROOT / 'validation/restore_psql.log'
    log.parent.mkdir(exist_ok=True)
    with log.open('wb') as out:
        proc = subprocess.Popen(['psql', '-X', '-w', '-v', 'ON_ERROR_STOP=1',
            '--single-transaction', '--dbname', dsn, '--file', '-'],
            env=env, stdin=subprocess.PIPE, stdout=out, stderr=out)
        try:
            with gzip.open(payload, 'rb') as source:
                for block in iter(lambda: source.read(1024**2), b''):
                    proc.stdin.write(block)
        except BrokenPipeError:
            pass
        finally:
            proc.stdin.close()
        if proc.wait():
            raise ValueError('Transactional restore failed; inspect validation/restore_psql.log')
    with connect() as c:
        c.execute('REVOKE ALL ON SCHEMA core FROM PUBLIC')
        c.execute('REVOKE ALL ON ALL TABLES IN SCHEMA core FROM PUBLIC')
        c.execute('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA core FROM PUBLIC')
        c.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
    validate()

def validate():
    results = []
    with connect() as c:
        cursor = c.cursor()
        cursor.execute((ROOT / 'deployment/post_restore_spatial_checks.sql').read_text(encoding='utf-8'), prepare=False)
        while True:
            if cursor.description:
                rows = cursor.fetchall()
                results.append(rows)
                for row in rows:
                    for key, value in row.items():
                        if (key.endswith('_passed') or key.startswith('expected_pg_')) and value is not True:
                            raise ValueError('Spatial compatibility check failed: ' + key)
            if not cursor.nextset():
                break
        ext = c.execute("SELECT extversion FROM pg_extension WHERE extname='postgis'").fetchone()
        if ext is None or ext['extversion'] != '3.5.6':
            raise ValueError('Expected installed extension was not found')
        count = c.execute("SELECT count(*) AS n FROM pg_tables WHERE schemaname='core'").fetchone()['n']
        samples = c.execute('''SELECT sum(a.sample_count) AS n FROM core.sample_axis a JOIN
            core.release_dataset d ON d.dataset_revision_id=a.dataset_revision_id WHERE d.release_id=%s''', (RELEASE,)).fetchone()['n']
        if count != 36 or samples != 261892:
            raise ValueError('Restored baseline counts differ')
        for f in load('examples/ACCEPTANCE_FIXTURES.json')['sample_cases']:
            row = c.execute('SELECT md_m FROM core.scan_sample WHERE axis_id=%s AND sample_no=%s', (f['axis_id'], f['sample_no'])).fetchone()
            if not row or abs(row['md_m'] - f['md_m']) > 1e-9:
                raise ValueError('Sample fixture mismatch')
    save('aurora_restore_verification.json', dict(status='passed', release_id=RELEASE,
        postgres='17.9', postgis='3.5.6', tables=count, current_samples=samples,
        checked_at=datetime.now(timezone.utc).isoformat(), spatial_results=results))
    print('Aurora compatibility restore verified: 36 tables; 261892 current samples.')

def sign_uploads():
    s3 = client('s3')
    bucket = TARGET['s3_bucket']
    if s3.get_bucket_location(Bucket=bucket).get('LocationConstraint') != TARGET['region']:
        raise ValueError('Bucket region mismatch')
    if not all(s3.get_public_access_block(Bucket=bucket)['PublicAccessBlockConfiguration'].values()):
        raise ValueError('Bucket public access protection differs from preflight')
    signed = []
    for row in objects().values():
        key = TARGET['s3_prefix'] + '/' + row['source_key']
        checksum = base64.b64encode(bytes.fromhex(row['sha256'])).decode()
        mime = mimetypes.guess_type(key)[0] or 'application/octet-stream'
        url = s3.generate_presigned_url('put_object', Params=dict(Bucket=bucket, Key=key,
            ChecksumSHA256=checksum, ContentType=mime, IfNoneMatch='*'), ExpiresIn=10800)
        signed.append({**row, 'url': url, 'content_type': mime, 'checksum_base64': checksum})
    dest = Path.home() / 'etl4-upload-urls.json'
    dest.write_text(json.dumps(dict(release_id=RELEASE, bucket=bucket,
        region=TARGET['region'], prefix=TARGET['s3_prefix'], objects=signed)), encoding='utf-8')
    dest.chmod(0o600)
    print('Scoped upload URLs prepared for', len(signed), 'objects; download ~/etl4-upload-urls.json. Do not share it.')

def verify_s3():
    s3 = client('s3')
    save('s3_receipt.json', dict(status='in_progress', release_id=RELEASE))
    def verify(row):
        key = TARGET['s3_prefix'] + '/' + row['source_key']
        obj = s3.get_object(Bucket=TARGET['s3_bucket'], Key=key)
        if obj['ContentLength'] != row['byte_size']:
            raise ValueError('Object size mismatch: ' + row['source_key'])
        h = hashlib.sha256()
        with obj['Body'] as stream:
            for part in iter(lambda: stream.read(1024**2), b''):
                h.update(part)
        if h.hexdigest() != row['sha256']:
            raise ValueError('Object checksum mismatch: ' + row['source_key'])
        return {**row, 'object_key': key, 'remote_sha256': h.hexdigest(), 'version_id': obj.get('VersionId')}
    with ThreadPoolExecutor(max_workers=4) as pool:
        done = list(pool.map(verify, objects().values()))
    save('s3_receipt.json', dict(status='verified_remote', release_id=RELEASE,
        bucket=TARGET['s3_bucket'], region=TARGET['region'], prefix=TARGET['s3_prefix'],
        manifest_sha256=sha_file(ROOT / 'manifests/deployment_assets.json'), objects=done,
        verified_at=datetime.now(timezone.utc).isoformat()))
    print('Verified all', len(done), 'S3 objects by full SHA256.')

def register_s3():
    import psycopg
    os.environ['ETL4_ADMIN_DSN'] = psycopg.conninfo.make_conninfo(**params())
    try:
        helper().register(argparse.Namespace(root_key='etl4_s3_primary'))
    finally:
        os.environ.pop('ETL4_ADMIN_DSN', None)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['restore', 'validate', 'sign-uploads', 'verify-s3', 'register-s3'])
    args = parser.parse_args()
    identity()
    {'restore': restore, 'validate': validate, 'sign-uploads': sign_uploads,
     'verify-s3': verify_s3, 'register-s3': register_s3}[args.action]()

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never print provider exceptions or connection strings.
        print(str(exc) if isinstance(exc, ValueError) else type(exc).__name__, file=sys.stderr)
        sys.exit(1)
