"""Run the real FastAPI handlers against Aurora and S3; no public API hosting."""
from datetime import datetime, timezone
import io
import math
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'deployment'))
from cloud_runner import TARGET, RELEASE, identity, params, helper, load, save


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close_number(actual, expected, *, relative=1e-7, absolute=1e-9):
    return (isinstance(actual, (int, float)) and not isinstance(actual, bool)
            and isinstance(expected, (int, float)) and not isinstance(expected, bool)
            and math.isfinite(actual) and math.isfinite(expected)
            and math.isclose(actual, expected, rel_tol=relative, abs_tol=absolute))


def check_spectrum(actual, expected, channels):
    require(set(expected) <= set(actual), 'Spectral result fields differ from baseline')
    vectors = {'spectra', 'wavelength', 'nonfinite_channels'}
    for key in set(expected) - vectors:
        require(actual[key] == expected[key], 'Spectral metadata differs: ' + key)
    require(actual['status'] == 'available', 'Spectral result is unavailable')
    for key in ('spectra', 'wavelength'):
        require(len(actual[key]) == len(expected[key]) == channels,
                'Spectral channel count differs: ' + key)
    for result in (actual, expected):
        require(all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < channels
                    for i in result['nonfinite_channels']), 'Invalid nonfinite channel indexes')
    require(set(actual['nonfinite_channels']) == set(expected['nonfinite_channels']),
            'Spectral nonfinite channels differ')
    nonfinite = set(expected['nonfinite_channels'])
    for key in ('wavelength', 'spectra'):
        for index, (value, reference) in enumerate(zip(actual[key], expected[key])):
            if key == 'spectra' and index in nonfinite:
                # JSON null and nonfinite float representations carry the same unavailable value.
                require(all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)
                            and not math.isfinite(v)) for v in (value, reference)),
                        'Spectral nonfinite value differs at channel ' + str(index))
            else:
                require(close_number(value, reference), f'Spectral {key} differs at channel {index}')


def check_images(row, fixture, get, image_module):
    images = row['images']
    require(row['image_status'] == 'available' and images, 'Fixture row image is unavailable')
    require(sorted(x['image_region_id'] for x in images) == sorted(fixture['image_region_ids']),
            'API image selection differs')
    require(sorted([x['sample_no_from'], x['sample_no_to']] for x in images)
            == sorted(fixture['row_intervals']), 'API row intervals differ')
    for item in images:
        require(item['status'] == 'available' and bool(item['content_path']),
                'Fixture image content is unavailable')
        require(item['content_path'] == f"/v1/images/{item['image_asset_id']}/content",
                'Unexpected authenticated image content path')
        first, last, width = item['sample_no_from'], item['sample_no_to'], item['width_px']
        require(first <= fixture['sample_no'] <= last and width >= 1, 'Invalid fixture image extent')
        indicator = item['indicator']
        require(isinstance(indicator, dict) and indicator.get('method') == 'sample_index_linear'
                and indicator.get('version') == 1 and indicator.get('status') == 'approximate',
                'Fixture sample indicator is unavailable or changed')
        position = (fixture['sample_no'] - first) / (last - first) if last > first else .5
        require(close_number(indicator.get('p'), position, relative=1e-9)
                and close_number(indicator.get('x_px'), position * (width - 1), relative=1e-9),
                'Fixture sample indicator position differs')
        response = get(item['content_path'])
        require(response.headers.get('content-type', '').split(';')[0] == 'image/png',
                'Fixture image response is not PNG')
        with image_module.open(io.BytesIO(response.content)) as png:
            require(png.format == 'PNG' and png.size == (width, item['height_px']),
                    'Fixture PNG dimensions differ')
            png.load()
    return len(images)


def main():
    import psycopg
    from fastapi.testclient import TestClient
    from PIL import Image
    from cloud_api.app import Settings, create_app
    fixtures = load('examples/ACCEPTANCE_FIXTURES.json')
    catalog = load('examples/DATASET_CATALOG.json')
    baseline = load('examples/cloud_spectra_baseline.json')
    require(fixtures['release_id'] == catalog['release_id'] == baseline['release_id'] == RELEASE,
            'Acceptance fixture release differs')
    require(len(fixtures['sample_cases']) == 13, 'Expected 13 sample fixtures')
    arrays = [(dataset, array) for dataset in catalog['datasets'] for array in dataset['spectral_arrays']]
    expected_arrays = {case['result']['array_id']: case for case in baseline['cases']}
    require(len(arrays) == len(baseline['cases']) == len(expected_arrays) == 8
            and set(expected_arrays) == {array['array_id'] for _, array in arrays},
            'Expected baseline for all eight spectral arrays')
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
        for f in fixtures['sample_cases']:
            row = get(f"/v1/holes/{f['hole_id']}/samples/{f['sample_no']}").json()
            require(row['release_id'] == RELEASE and all(row[key] == f[key]
                    for key in ('hole_id', 'dataset_revision_id', 'axis_id', 'sample_no')),
                    'API sample identity differs')
            require(close_number(row['md_m'], f['md_m'], relative=0), 'API depth fixture differs')
            image_count = check_images(row, f, get, Image)
            cases.append({'hole': f['hole_id'], 'sample_no': f['sample_no'], 'passed': True,
                          'png_images_verified': image_count, 'row_intervals_and_indicators_verified': True})
        row = get('/v1/holes/07THD002/samples/15', params={'log_id':'a4a5c7d3-0fe8-53be-97a2-02a5c7771ae8'}).json()
        if row['md_m'] != 62.50175 or row['results'][0]['value']['value_text'] != 'Muscovite':
            raise ValueError('Muscovite fixture differs')
        png = get(row['images'][0]['content_path']).content
        with Image.open(io.BytesIO(png)) as sample_image:
            require(sample_image.format == 'PNG' and sample_image.size == (399,25),
                    'S3 row image dimensions differ')
            sample_image.load()
        (ROOT / 'validation/cloud_sample15.png').write_bytes(png)
        spectra = []
        for dataset, array in arrays:
            case = expected_arrays[array['array_id']]
            require(case['hole_id'] == dataset['hole_id'] and case['sample_no'] == 15
                    and case['result']['log_id'] == array['log_id'], 'Spectral baseline identity differs')
            payload = get(f"/v1/holes/{dataset['hole_id']}/samples/15", params={'log_id':array['log_id']}).json()
            require(payload['release_id'] == RELEASE and payload['sample_no'] == case['sample_no']
                    and all(payload[key] == case[key] for key in ('dataset_id', 'dataset_revision_id', 'axis_id'))
                    and close_number(payload['md_m'], case['md_m'], relative=0),
                    'Spectral sample identity differs')
            require(len(payload['results']) == 1, 'Expected exactly one selected spectral result')
            check_spectrum(payload['results'][0], case['result'], array['channel_count'])
            spectra.append({'hole':dataset['hole_id'], 'log_id':array['log_id'], 'array_id':array['array_id'],
                            'channels':array['channel_count'], 'scientific_values_match_baseline':True, 'passed':True})
    report = dict(status='passed', checked_at=datetime.now(timezone.utc).isoformat(), release_id=RELEASE,
        execution='FastAPI TestClient in CloudShell; live Aurora and live S3; no local-file fallback',
        public_api_hosted=False, database_user='etl4_reader', database_auth='iam',
        samples=cases, spectral_arrays=spectra, sample15_mineral='Muscovite', sample15_image_size=[399,25],
        spectral_numeric_tolerance={'relative':1e-7, 'absolute':1e-9},
        spectral_baseline='examples/cloud_spectra_baseline.json')
    save('cloud_api_acceptance.json',report)
    print('CLOUD_API_ACCEPTANCE_PASSED: five holes, 13 fixtures with PNGs and indicators, all eight F32 arrays match scientific baselines.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, ValueError) else type(exc).__name__, file=sys.stderr)
        sys.exit(1)
