"""Run the real FastAPI handlers against Aurora and S3; no public API hosting."""
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'deployment'))
from cloud_runner import TARGET, RELEASE, identity, params, helper, load, save

def main():
    import psycopg
    from fastapi.testclient import TestClient
    from PIL import Image
    from cloud_api.app import Settings, create_app
    identity()
    signed_params = params(user='etl4_reader')
    os.environ['ETL4_READ_DSN'] = psycopg.conninfo.make_conninfo(**signed_params)
    try:
        helper().check_db(None)
    finally:
        os.environ.pop('ETL4_READ_DSN', None)
    signed_params.pop('password')
    dsn = psycopg.conninfo.make_conninfo(**signed_params)
    token = secrets.token_urlsafe(36)
    settings = Settings(dsn, token, TARGET['s3_bucket'], TARGET['region'],
        prefix=TARGET['s3_prefix'], db_auth='iam')
    app = create_app(settings)
    headers = {'Authorization': 'Bearer '+token}
    with TestClient(app) as api:
        if api.get('/health').status_code != 401:
            raise ValueError('Unauthenticated request was accepted')
        def get(url, **kwargs):
            r = api.get(url, headers=headers, **kwargs)
            if r.status_code != 200:
                raise ValueError(f'Cloud API check failed with HTTP {r.status_code}: {url}')
            return r
        get('/health')
        holes = get('/v1/holes').json()['items']
        if len(holes) != 5 or sum(x['sample_count'] for x in holes) != 261892:
            raise ValueError('API hole/sample counts differ')
        cases = []
        for f in load('examples/ACCEPTANCE_FIXTURES.json')['sample_cases']:
            row = get(f"/v1/holes/{f['hole_id']}/samples/{f['sample_no']}").json()
            if abs(row['md_m']-f['md_m']) > 1e-9:
                raise ValueError('API depth fixture differs')
            if sorted(x['image_region_id'] for x in row['images']) != sorted(f['image_region_ids']):
                raise ValueError('API image selection differs')
            cases.append({'hole': f['hole_id'], 'sample_no': f['sample_no'], 'passed': True})
        row = get('/v1/holes/07THD002/samples/15', params={'log_id':'a4a5c7d3-0fe8-53be-97a2-02a5c7771ae8'}).json()
        if row['md_m'] != 62.50175 or row['results'][0]['value']['value_text'] != 'Muscovite':
            raise ValueError('Muscovite fixture differs')
        png = get(row['images'][0]['content_path']).content
        if Image.open(io.BytesIO(png)).size != (399,25):
            raise ValueError('S3 row image dimensions differ')
        (ROOT / 'validation/cloud_sample15.png').write_bytes(png)
        spectra = []
        for dataset in load('examples/DATASET_CATALOG.json')['datasets']:
            for array in dataset['spectral_arrays']:
                result = get(f"/v1/holes/{dataset['hole_id']}/samples/15", params={'log_id':array['log_id']}).json()['results'][0]
                if (result['status'] != 'available' or len(result['spectra']) != array['channel_count']
                        or len(result['wavelength']) != array['channel_count']):
                    raise ValueError('S3 spectral range read differs')
                spectra.append({'hole':dataset['hole_id'], 'log_id':array['log_id'], 'channels':array['channel_count'], 'passed':True})
    report = dict(status='passed', checked_at=datetime.now(timezone.utc).isoformat(), release_id=RELEASE,
        execution='FastAPI TestClient in CloudShell; live Aurora and live S3; no local-file fallback',
        public_api_hosted=False, database_user='etl4_reader', database_auth='iam',
        samples=cases, spectral_arrays=spectra, sample15_mineral='Muscovite', sample15_image_size=[399,25])
    save('cloud_api_acceptance.json',report)
    print('CLOUD_API_ACCEPTANCE_PASSED: five holes, 13 fixtures, real PNG, all eight F32 arrays.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, ValueError) else type(exc).__name__, file=sys.stderr)
        sys.exit(1)
