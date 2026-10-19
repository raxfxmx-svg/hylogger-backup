"""Collect non-secret live deployment evidence after successful acceptance."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloud_runner import ROOT, TARGET, RELEASE, client, connect, identity, load, save


def main():
    identity()
    acceptance = load('validation/cloud_api_acceptance.json')
    receipt = load('validation/s3_receipt.json')
    if acceptance['status'] != 'passed' or receipt['status'] != 'verified_remote':
        raise ValueError('Live acceptance and complete S3 verification are required')
    with connect(user='etl4_reader') as c:
        locations = c.execute("SELECT count(*) AS locations,count(DISTINCT object_key) AS objects FROM core.asset_location WHERE backend='s3' AND root_key='etl4_s3_primary' AND access_status='verified_remote'").fetchone()
        if locations != {'locations': 3042, 'objects': 2810}:
            raise ValueError('Registered S3 location count differs')
        database_bytes = c.execute('SELECT pg_database_size(current_database()) AS bytes').fetchone()['bytes']
    cluster = client('rds').describe_db_clusters(DBClusterIdentifier=TARGET['cluster_identifier'])['DBClusters'][0]
    s3 = client('s3')
    public_access = s3.get_public_access_block(Bucket=TARGET['s3_bucket'])['PublicAccessBlockConfiguration']
    if not all(public_access.values()):
        raise ValueError('Expected private bucket protection is missing')
    sources = ['cloud_api/app.py', 'cloud_api/reader.py', 'cloud_api/storage.py',
               'deployment/cloud_runner.py', 'deployment/smoke_cloud.py', 'deployment/run_api.py']
    hashes = {name: hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() for name in sources}
    packages = {name: importlib.metadata.version(name) for name in
                ('psycopg', 'numpy', 'pyarrow', 'fastapi', 'uvicorn', 'Pillow', 'httpx', 'boto3', 'botocore', 'certifi')}
    save('deployment_summary.json', dict(status='passed', checked_at=datetime.now(timezone.utc).isoformat(),
        release_id=RELEASE, account=TARGET['aws_account_id'], region=TARGET['region'],
        cluster=cluster['DBClusterIdentifier'], cluster_resource_id=cluster['DbClusterResourceId'],
        database=TARGET['database'], database_bytes=database_bytes, reader='etl4_reader',
        s3_bucket=TARGET['s3_bucket'], s3_prefix=TARGET['s3_prefix'], **locations,
        s3_bytes=sum(row['byte_size'] for row in receipt['objects']), public_access_block=public_access,
        api_acceptance=acceptance['status'], public_api_hosted=False,
        runtime_sources_utf8_lf_sha256=hashes, runtime_packages=packages))
    names = ['aurora_restore_verification.json', 'reader_setup.json', 'database_verification.json',
             's3_receipt.json', 's3_mapping.json', 'cloud_api_acceptance.json',
             'cloud_sample15.png', 'deployment_summary.json']
    dest = Path.home()/'ETL4_DEPLOYMENT_EVIDENCE.zip'
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(ROOT/'validation'/name, 'validation/'+name)
    print(json.dumps(dict(archive=str(dest), bytes=dest.stat().st_size,
        sha256=hashlib.sha256(dest.read_bytes()).hexdigest(), files=len(names), **locations)))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, ValueError) else type(exc).__name__, file=sys.stderr)
        sys.exit(1)
