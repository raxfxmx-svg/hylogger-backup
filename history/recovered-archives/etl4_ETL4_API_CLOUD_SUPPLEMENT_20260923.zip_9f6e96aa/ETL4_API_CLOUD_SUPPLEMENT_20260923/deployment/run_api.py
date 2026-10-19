"""Start the private pilot against target.json without embedding credentials."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import ssl
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check live DB, scalar and PNG, then exit')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    import boto3
    import certifi
    import psycopg
    from cloud_api.app import Settings, create_app

    target = json.loads((ROOT / 'deployment/target.json').read_text(encoding='utf-8'))
    identity = boto3.client('sts', region_name=target['region']).get_caller_identity()
    if identity['Account'] != target['aws_account_id']:
        raise ValueError('AWS account does not match deployment/target.json')
    ca = os.environ.get('ETL4_CA_FILE') or ssl.get_default_verify_paths().cafile or certifi.where()
    if not Path(ca).is_file():
        raise ValueError('A trusted public CA bundle is required')
    dsn = psycopg.conninfo.make_conninfo(host=target['host'], port=target['port'],
        dbname=target['database'], user='etl4_reader', sslmode='verify-full', sslrootcert=ca)
    token = secrets.token_urlsafe(36) if args.check else os.environ.get('ETL4_API_TOKEN')
    if not token:
        token = getpass.getpass('Private API bearer token (at least 32 characters; hidden): ')
    if len(token) < 32:
        raise ValueError('The API bearer token must contain at least 32 characters')
    settings = Settings(dsn, token, target['s3_bucket'], target['region'],
        prefix=target['s3_prefix'], db_auth='iam')
    app = create_app(settings)
    if args.check:
        from fastapi.testclient import TestClient
        from PIL import Image
        import io
        with TestClient(app) as api:
            headers = {'Authorization': 'Bearer ' + token}
            def get(path, **kwargs):
                response = api.get(path, headers=headers, **kwargs)
                if response.status_code != 200:
                    raise ValueError(f'Live check failed with HTTP {response.status_code}; check AWS session, IAM grants and S3 registration')
                return response
            get('/health')
            row = get('/v1/holes/07THD002/samples/15', params={
                'log_id': 'a4a5c7d3-0fe8-53be-97a2-02a5c7771ae8'}).json()
            if row['md_m'] != 62.50175 or row['results'][0]['value']['value_text'] != 'Muscovite':
                raise ValueError('Live scalar fixture differs')
            if not row['images'] or row['images'][0]['status'] != 'available':
                raise ValueError('Live image is unavailable')
            image = get(row['images'][0]['content_path'])
            with Image.open(io.BytesIO(image.content)) as png:
                if png.size != (399, 25):
                    raise ValueError('Live PNG fixture differs')
                png.load()
        print('LIVE_CHECK_PASSED: reader IAM/TLS, Aurora sample15, S3 scalar and PNG.')
        return
    import uvicorn
    print(f'Private pilot: http://127.0.0.1:{args.port}; every request needs the entered bearer token.')
    uvicorn.run(app, host='127.0.0.1', port=args.port, workers=1,
                limit_concurrency=8, access_log=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, ValueError) else
              f'{type(exc).__name__}: check your AWS session and deployment/TEAMMATE_START.md; credentials were not printed.',
              file=sys.stderr)
        sys.exit(1)
