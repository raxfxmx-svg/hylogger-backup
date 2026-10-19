"""Portable operations for the fixed ETL4 release. No source-machine configuration."""
from __future__ import annotations
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'etl4'
RELEASE = 'fd02659c-dc3d-52ea-a8eb-c032b91e7624'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe(root, key):
    p = (root / key).resolve()
    if not p.is_relative_to(root.resolve()) or p == root.resolve():
        raise ValueError('Path escapes the package root')
    return p


def assets():
    m = read(ROOT / 'manifests/deployment_assets.json')
    if m['release_id'] != RELEASE:
        raise ValueError('Unexpected release in asset manifest')
    by_id = {a['id']: a for a in m['assets']}
    unique = {}
    for loc in m['locations']:
        if loc['backend'] != 'local' or loc['root_key'] != 'etl4':
            raise ValueError('Unexpected source location')
        a = by_id[loc['asset_id']]
        key = loc['object_key']
        item = {'source_key': key, 'sha256': a['sha256'], 'byte_size': a['byte_size']}
        if key in unique and unique[key] != item:
            raise ValueError('Conflicting source object identity')
        safe(DATA, key)
        unique[key] = item
    return m, unique


def save(name, obj):
    dest = ROOT / 'validation' / name
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')


def verify(args):
    _, unique = assets()
    for i, row in enumerate(unique.values(), 1):
        p = safe(DATA, row['source_key'])
        if not p.is_file() or p.stat().st_size != row['byte_size'] or sha(p) != row['sha256']:
            raise ValueError('Data verification failed: ' + row['source_key'])
        if i % 500 == 0:
            print(f'Verified {i}/{len(unique)} data files', flush=True)
    pointer = read(ROOT / 'manifests/database_backup.json')
    dump = safe(DATA / 'database', pointer['backup_relative_path'])
    if sha(dump) != pointer['backup_sha256']:
        raise ValueError('Database backup checksum mismatch')
    bm = read(dump.with_suffix('.manifest.json'))
    if sha(ROOT / 'manifests/deployment_assets.json') != bm['asset_manifest_sha256']:
        raise ValueError('Backup and asset manifest do not match')
    for name, digest in bm['migrations'].items():
        if sha(DATA / 'database/migrations' / name) != digest:
            raise ValueError('Migration checksum mismatch')
    inventory = ROOT / 'PACKAGE_FILES.json'
    if inventory.exists():
        for item in read(inventory)['files']:
            f = safe(ROOT, item['path'])
            if not f.is_file() or f.stat().st_size != item['bytes'] or sha(f) != item['sha256']:
                raise ValueError('Package file verification failed: ' + item['path'])
    result = {'status': 'passed', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'release_id': RELEASE, 'data_files': len(unique),
              'data_bytes': sum(x['byte_size'] for x in unique.values()),
              'backup_bytes': dump.stat().st_size, 'package_inventory_checked': inventory.exists()}
    save('file_verification.json', result)
    print(json.dumps(result))


def connect(admin=False):
    import psycopg
    from psycopg.rows import dict_row
    key = 'ETL4_ADMIN_DSN' if admin else 'ETL4_READ_DSN'
    if not os.environ.get(key):
        raise ValueError(f'Set {key} in your environment; do not edit source files')
    c = psycopg.connect(os.environ[key], row_factory=dict_row, autocommit=True, connect_timeout=10)
    c.execute("SET search_path TO core, public")
    c.execute("SET statement_timeout TO '120s'")
    if not admin:
        c.execute('SET default_transaction_read_only TO on')
    return c


def restore(args):
    import psycopg
    pointer = read(ROOT / 'manifests/database_backup.json')
    dump = safe(DATA / 'database', pointer['backup_relative_path'])
    if sha(dump) != pointer['backup_sha256']:
        raise ValueError('Backup checksum mismatch')
    executable = shutil.which(args.pg_restore) or args.pg_restore
    with connect(True) as c:
        name = c.execute('SELECT current_database() AS name').fetchone()['name']
        if name != args.database:
            raise ValueError('The explicit database name does not match ETL4_ADMIN_DSN')
        if c.execute("SELECT count(*) AS n FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='core'").fetchone()['n']:
            raise ValueError('Target core schema is not empty; restore into a new empty database')
        if int(c.execute('SHOW server_version_num').fetchone()['server_version_num']) < 170000:
            raise ValueError('Use PostgreSQL 17 or later and a compatible PostGIS version')
        c.execute('CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public')
        ext = c.execute("SELECT extversion,nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE extname='postgis'").fetchone()
        if ext['nspname'] != 'public' or tuple(map(int, ext['extversion'].split('.')[:2])) < (3, 6):
            raise ValueError('This restore workflow requires PostGIS 3.6+ in public; see the runbook')
        c.execute('CREATE SCHEMA IF NOT EXISTS core')
    env = os.environ.copy()
    # pg_restore needs an explicit --dbname to restore rather than print SQL.
    # Keep connection passwords in the process environment, never in argv.
    params = psycopg.conninfo.conninfo_to_dict(os.environ['ETL4_ADMIN_DSN'])
    if 'password' in params:
        env['PGPASSWORD'] = params.pop('password')
    if 'sslpassword' in params:
        env['PGSSLPASSWORD'] = params.pop('sslpassword')
    target_dsn = psycopg.conninfo.make_conninfo(**params)
    proc = subprocess.run([executable, '--schema=core', '--no-owner', '--no-acl',
                           '--single-transaction', '--exit-on-error', '--dbname', target_dsn, str(dump)],
                          env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if proc.returncode:
        password = psycopg.conninfo.conninfo_to_dict(os.environ['ETL4_ADMIN_DSN']).get('password', '')
        detail = proc.stderr.replace(password, '[redacted]') if password else proc.stderr
        raise RuntimeError('pg_restore failed: ' + detail[-3000:])
    with connect(True) as c:
        c.execute('REVOKE ALL ON SCHEMA core FROM PUBLIC')
        c.execute('REVOKE ALL ON ALL TABLES IN SCHEMA core FROM PUBLIC')
        c.execute('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA core FROM PUBLIC')
        c.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
    print('Restore completed. Next create a separate reader and run check-db.')


def create_reader(args):
    from psycopg import sql
    password = os.environ.get('ETL4_READER_PASSWORD') or getpass.getpass('New reader password: ')
    if not password:
        raise ValueError('An empty password is not accepted')
    with connect(True) as c, c.transaction():
        if c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (args.role,)).fetchone():
            raise ValueError('Role already exists; use a new reader name instead of modifying an existing account')
        role = sql.Identifier(args.role)
        db = c.execute('SELECT current_database() AS n').fetchone()['n']
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION').format(role, sql.Literal(password)))
        c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(db), role))
        c.execute(sql.SQL('GRANT USAGE ON SCHEMA core,public TO {}').format(role))
        c.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA core TO {}').format(role))
        c.execute(sql.SQL('ALTER ROLE {} SET default_transaction_read_only=on').format(role))
        c.execute(sql.SQL('ALTER ROLE {} SET search_path=core,public').format(role))
    print('Read-only role created. Set ETL4_READ_DSN separately; credentials were not written to the package.')


def context(c, hole):
    row = c.execute('''SELECT rd.dataset_id,rd.dataset_revision_id,a.id AS axis_id,a.sample_count
      FROM core.release_dataset rd JOIN core.dataset d ON d.id=rd.dataset_id
      JOIN core.borehole b ON b.id=d.borehole_id
      JOIN core.sample_axis a ON a.dataset_revision_id=rd.dataset_revision_id
      WHERE rd.release_id=%s AND b.source_hole_id=%s''', (RELEASE, hole)).fetchall()
    if len(row) != 1:
        raise ValueError('Expected exactly one dataset/axis for this fixed-release hole')
    return row[0]


def check_db(args):
    fixtures = read(ROOT / 'examples/ACCEPTANCE_FIXTURES.json')
    with connect() as c:
        current = str(c.execute('SELECT release_id FROM core.active_release WHERE singleton').fetchone()['release_id'])
        if current != RELEASE:
            raise ValueError('Unexpected active release')
        tables = c.execute("SELECT count(*) AS n FROM pg_tables WHERE schemaname='core'").fetchone()['n']
        samples = c.execute('''SELECT count(*) AS n FROM core.scan_sample s JOIN core.sample_axis a ON a.id=s.axis_id
          JOIN core.release_dataset r ON r.dataset_revision_id=a.dataset_revision_id WHERE r.release_id=%s''', (RELEASE,)).fetchone()['n']
        if tables != 36 or samples != 261892:
            raise ValueError('Database baseline counts differ')
        for f in fixtures['sample_cases']:
            s = c.execute('SELECT md_m FROM core.scan_sample WHERE axis_id=%s AND sample_no=%s', (f['axis_id'], f['sample_no'])).fetchone()
            if not s or abs(s['md_m'] - f['md_m']) > 1e-9:
                raise ValueError('Sample depth differs from fixture')
            regions = c.execute('''SELECT m.image_region_id FROM core.image_sample_mapping m
              JOIN core.scan_sample s ON s.axis_id=m.axis_id AND s.section_interval_id=m.section_interval_id
              WHERE s.axis_id=%s AND s.sample_no=%s AND s.sample_no BETWEEN m.sample_no_from AND m.sample_no_to''', (f['axis_id'], f['sample_no'])).fetchall()
            if sorted(str(r['image_region_id']) for r in regions) != sorted(f['image_region_ids']):
                raise ValueError('Image mapping differs from fixture')
        invalid = c.execute("SELECT count(*) AS n FROM pg_constraint WHERE connamespace='core'::regnamespace AND NOT convalidated").fetchone()['n']
        writeable = c.execute("SELECT tablename FROM pg_tables WHERE schemaname='core' AND (has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'INSERT') OR has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'UPDATE') OR has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'DELETE') OR has_table_privilege(current_user,format('%I.%I',schemaname,tablename),'TRUNCATE'))").fetchall()
        if invalid or writeable:
            raise ValueError('Unvalidated constraints or a reader with write privileges')
        if c.execute("SELECT has_schema_privilege(current_user,'core','CREATE') AS allowed").fetchone()['allowed']:
            raise ValueError('Reader can create objects in core')
    result = {'status': 'passed', 'release_id': RELEASE, 'tables': tables, 'current_samples': samples,
              'sample_fixtures': len(fixtures['sample_cases']), 'reader_write_privileges': False}
    save('database_verification.json', result)
    print(json.dumps(result))


def sample(args):
    sys.path.insert(0, str(DATA / 'database'))
    from _media_reader import read_sample
    from _db_common import serial
    with connect() as c:
        ctx = context(c, args.hole)
        result = read_sample(c, RELEASE, str(ctx['dataset_id']), str(ctx['axis_id']), args.sample,
                             log_ids=args.log_id or [], image_log_id=args.image_log_id)
    # This is a presentation string, not a scientific value or source document.
    result['indicator_label'] = 'The marker estimates position by sample index; depth and results belong to the selected sample.'
    encoded = json.dumps(result, ensure_ascii=False, indent=2, default=serial, allow_nan=False)
    if args.output:
        Path(args.output).write_text(encoded + '\n', encoding='utf-8')
        print('Sample written to ' + args.output)
    else:
        print(encoded)


def upload(args):
    import boto3
    from botocore.exceptions import ClientError
    _, unique = assets()
    prefix = args.prefix.strip('/')
    client = boto3.client('s3', region_name=args.region)
    save('s3_receipt.json', {'status': 'in_progress', 'release_id': RELEASE,
                           'bucket': args.bucket, 'region': args.region, 'prefix': prefix})
    def process(row):
        local = safe(DATA, row['source_key'])
        if local.stat().st_size != row['byte_size'] or sha(local) != row['sha256']:
            raise ValueError('Source data checksum mismatch')
        key = (prefix + '/' if prefix else '') + row['source_key']
        exists = False
        try:
            client.head_object(Bucket=args.bucket, Key=key)
            exists = True
        except ClientError as e:
            if e.response['Error']['Code'] not in ('404', 'NoSuchKey', 'NotFound'):
                raise
        if not exists:
            import mimetypes
            client.upload_file(str(local), args.bucket, key,
                ExtraArgs={'ContentType': mimetypes.guess_type(local.name)[0] or 'application/octet-stream',
                           'Metadata': {'source-sha256': row['sha256']}})
        # Always stream the remote bytes, including pre-existing objects. Never trust ETag as SHA256.
        response = client.get_object(Bucket=args.bucket, Key=key)
        h = hashlib.sha256(); size = 0
        with response['Body'] as body:
            for part in iter(lambda: body.read(1024 * 1024), b''):
                h.update(part); size += len(part)
        if size != row['byte_size'] or h.hexdigest() != row['sha256']:
            raise ValueError('Remote checksum mismatch; existing objects were not overwritten: ' + key)
        return {**row, 'object_key': key, 'remote_sha256': h.hexdigest(), 'version_id': response.get('VersionId')}
    done = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for item in pool.map(process, unique.values()):
            done.append(item)
            if len(done) % 100 == 0:
                print(f'Uploaded/verified {len(done)}/{len(unique)}', flush=True)
    receipt = {'status': 'verified_remote', 'release_id': RELEASE, 'bucket': args.bucket,
               'region': args.region, 'prefix': prefix, 'manifest_sha256': sha(ROOT / 'manifests/deployment_assets.json'),
               'verified_at': datetime.now(timezone.utc).isoformat(), 'objects': done}
    save('s3_receipt.json', receipt)
    print(f'{len(done)} remote objects verified; receipt saved to validation/s3_receipt.json')


def register(args):
    import uuid
    receipt = read(ROOT / 'validation/s3_receipt.json')
    m, unique = assets()
    if receipt.get('status') != 'verified_remote':
        raise ValueError('The most recent S3 upload did not finish verification')
    by_key = {r['source_key']: r for r in receipt['objects']}
    if (receipt['status'] != 'verified_remote' or receipt['release_id'] != RELEASE or
        receipt['manifest_sha256'] != sha(ROOT / 'manifests/deployment_assets.json') or set(by_key) != set(unique)):
        raise ValueError('Upload receipt does not cover this package')
    with connect(True) as c, c.transaction():
        for loc in m['locations']:
            row = by_key[loc['object_key']]
            expected = unique[loc['object_key']]
            if row['remote_sha256'] != expected['sha256'] or row['byte_size'] != expected['byte_size']:
                raise ValueError('Invalid verification receipt entry')
            stored = c.execute('SELECT sha256,byte_size FROM core.asset WHERE id=%s', (loc['asset_id'],)).fetchone()
            if not stored or stored['sha256'] != expected['sha256'] or stored['byte_size'] != expected['byte_size']:
                raise ValueError('Target asset differs from package')
            c.execute('''INSERT INTO core.asset_location(id,asset_id,backend,root_key,object_key,access_status,verified_sha256)
              VALUES (%s,%s,'s3',%s,%s,'verified_remote',%s)
              ON CONFLICT(asset_id,backend,root_key,object_key) DO NOTHING''',
              (uuid.uuid4(), loc['asset_id'], args.root_key, row['object_key'], expected['sha256']))
            existing = c.execute("SELECT access_status,verified_sha256 FROM core.asset_location WHERE asset_id=%s AND backend='s3' AND root_key=%s AND object_key=%s", (loc['asset_id'], args.root_key, row['object_key'])).fetchone()
            if existing['access_status'] != 'verified_remote' or existing['verified_sha256'] != expected['sha256']:
                raise ValueError('Conflicting existing S3 location; review it before retrying')
    save('s3_mapping.json', {'root_key': args.root_key, 'bucket': receipt['bucket'], 'region': receipt['region'], 'release_id': RELEASE})
    print('Verified S3 locations registered. Keep the deployment mapping with the API configuration.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('verify').set_defaults(fn=verify)
    r = sub.add_parser('restore'); r.add_argument('--database', required=True)
    r.add_argument('--pg-restore', default='pg_restore'); r.set_defaults(fn=restore)
    r = sub.add_parser('create-reader'); r.add_argument('--role', default='etl4_reader'); r.set_defaults(fn=create_reader)
    sub.add_parser('check-db').set_defaults(fn=check_db)
    r = sub.add_parser('sample'); r.add_argument('--hole', default='07THD002'); r.add_argument('--sample', type=int, default=15)
    r.add_argument('--log-id', action='append'); r.add_argument('--image-log-id'); r.add_argument('--output'); r.set_defaults(fn=sample)
    r = sub.add_parser('upload-s3'); r.add_argument('--bucket', required=True); r.add_argument('--region', required=True)
    r.add_argument('--prefix', default='data'); r.add_argument('--workers', type=int, choices=range(1,9), default=4); r.set_defaults(fn=upload)
    r = sub.add_parser('register-s3'); r.add_argument('--root-key', default='etl4_s3_primary'); r.set_defaults(fn=register)
    args = p.parse_args()
    try:
        args.fn(args)
    except Exception as e:
        # Do not serialize connection strings or provider credential errors to the console.
        if isinstance(e, ValueError):
            print('STOP: ' + str(e), file=sys.stderr)
        elif isinstance(e, RuntimeError) and str(e).startswith('pg_restore failed:'):
            print(str(e), file=sys.stderr)
        elif getattr(e, 'sqlstate', None) and getattr(e, 'diag', None):
            print(f'STOP: SQLSTATE {e.sqlstate}: {e.diag.message_primary}', file=sys.stderr)
        else:
            print(f'STOP: {type(e).__name__}. Check connectivity, permissions and prerequisites; no credentials were printed.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
