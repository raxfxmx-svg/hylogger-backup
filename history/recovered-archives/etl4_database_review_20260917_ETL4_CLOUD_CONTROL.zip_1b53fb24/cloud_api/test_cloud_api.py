"""Offline tests: fake S3/DB, real sample-15 Parquet and PNG, synthetic F32."""
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from .app import Settings, create_app, database
from .reader import INDICATOR, RELEASE, result
from .storage import APIError, S3Store

PACKAGE = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


class Cursor:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class FakeS3:
    def __init__(self, objects): self.objects, self.calls = objects, []
    def get_object(self, **request):
        self.calls.append(request)
        data = self.objects[request['Key']]
        response = {'ResponseMetadata': {'HTTPStatusCode': 200}}
        if 'Range' in request:
            start, end = map(int, request['Range'].removeprefix('bytes=').split('-'))
            response = {'ContentRange': f'bytes {start}-{end}/{len(data)}',
                        'ResponseMetadata': {'HTTPStatusCode': 206}}
            data = data[start:end + 1]
        return {**response, 'ContentLength': len(data), 'Body': io.BytesIO(data)}


class FixtureDB:
    def __init__(self):
        self.reference = load(PACKAGE / 'examples/SAMPLE_REFERENCE.json')
        manifest = load(PACKAGE / 'manifests/deployment_assets.json')
        self.catalog = load(PACKAGE / 'examples/DATASET_CATALOG.json')['datasets']
        ref = self.reference
        image_id = ref['images'][0]['image_asset_id']
        source_id = ref['results'][0]['source_log_id']
        locations = [row for row in manifest['locations'] if row['asset_id'] == image_id
                     or row['object_key'].endswith('/' + source_id + '.parquet')]
        wanted = {row['asset_id']: row for row in locations}
        self.assets, self.objects = {}, {}
        for asset in manifest['assets']:
            if asset['id'] in wanted:
                key = wanted[asset['id']]['object_key']
                self.assets[asset['id']] = {**asset, 'object_key': 'data/' + key}
                self.objects['data/' + key] = (PACKAGE / 'etl4' / key).read_bytes()
        self.scalar_id = next(a['id'] for a in self.assets.values() if a['id'] != image_id)
        scalar = dict(ref['results'][0])
        scalar.update(id=scalar.pop('log_id'), availability_status='payload_present',
                      binding_status='verified', axis_id=ref['axis_id'])
        self.scalar = scalar
        self.spectral = {**scalar, 'id': '1936b71e-f3bc-56d8-ae0e-d284edf0a86b', 'log_kind': 'spectral'}
        # Deliberately synthetic F32 data; no scientific claim is made for these values.
        floats = [float(i) / 10 for i in range(32 * 531)]
        floats[15 * 531 + 7] = float('nan')
        data = struct.pack('<' + 'f' * len(floats), *floats)
        self.spectral_asset = {'id': 'synthetic-spectral-asset', 'object_key': 'data/fixture.f32',
            'byte_size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        self.assets[self.spectral_asset['id']] = self.spectral_asset
        self.objects['data/fixture.f32'] = data
        start, end = 8, 24
        block_data = data[start * 531 * 4:end * 531 * 4]
        self.block = {'source_row_from': start, 'source_row_to_exclusive': end, 'byte_offset': start * 531 * 4,
            'byte_length': len(block_data), 'sha256': hashlib.sha256(block_data).hexdigest()}
        self.queries = []

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        text = ' '.join(sql.split())
        ref = self.reference
        if 'FROM core.asset a JOIN core.asset_location' in text:
            assert "l.backend='s3'" in text and "l.access_status='verified_remote'" in text
            assert 'l.verified_sha256=a.sha256' in text and params[1] == 'etl4_s3_primary'
            rows = [self.assets[params[0]]] if params[0] in self.assets else []
        elif 'SELECT rd.dataset_id' in text:
            rows = [{k: row[k] for k in ('dataset_id', 'dataset_revision_id', 'axis_id', 'sample_count')}
                    for row in self.catalog if row['hole_id'] == params[1]]
        elif 'FROM core.scan_sample' in text:
            rows = [ref['sample']] if str(params[0]) == ref['axis_id'] and params[1] == 15 else []
        elif 'SELECT l.*,b.status' in text:
            rows = [self.scalar, self.spectral]
        elif 'FROM core.image_sample_mapping' in text:
            image = ref['images'][0]
            rows = [{**image, 'asset_id': image['image_asset_id'], 'log_id': image['image_log_id'],
                'source_asset_id': image['source_image_asset_id'], 'region_status': 'reviewed',
                'indicator_method': 'sample_index_linear', 'indicator_version': 1,
                'indicator_status': 'approximate', 'indicator_parameters': INDICATOR}]
        elif 'FROM core.data_chunk' in text:
            rows = [{'asset_id': self.scalar_id, 'source_row_from': 0, 'source_row_to_exclusive': 4096,
                     'row_group': 0, 'sha256': self.assets[self.scalar_id]['sha256']}]
        elif 'FROM core.spectral_array' in text:
            rows = [{'id': 'synthetic-array', 'source_row_from': 0, 'sample_no_from': 0, 'sample_no_to': 31,
                'asset_id': self.spectral_asset['id'], 'sample_stride_bytes': 531 * 4, 'channel_count': 531,
                'dtype_code': '<f4', 'spectral_stream_id': 'synthetic-stream', 'value_unit': None}]
        elif 'FROM core.spectral_block' in text:
            rows = [self.block]
        elif 'FROM core.spectral_stream' in text:
            rows = [{'wavelengths': list(range(531)), 'wavelength_unit': 'nm', 'region_code': 'VSWIR'}]
        elif 'FROM core.image_region_asset ra' in text:
            assert params[1] == RELEASE
            rows = [{'ok': 1}] if params[0] == ref['images'][0]['image_asset_id'] else []
        elif 'SELECT count(*) AS n FROM core.release_dataset' in text:
            rows = [{'n': 5}]
        else:
            raise AssertionError('Unhandled fixture query')
        return Cursor(rows)

    @contextmanager
    def connect(self):
        yield self


class CloudAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = FixtureDB()

    def setUp(self):
        self.s3 = FakeS3(dict(self.fixture.objects))
        self.store = S3Store(self.s3, 'private-test-bucket', 'etl4_s3_primary', 'data')
        self.settings = Settings('unused-test-dsn', 'x' * 40, 'private-test-bucket', 'ap-southeast-2')
        app = create_app(self.settings, connector=self.fixture.connect, store=self.store)
        self.client = TestClient(app)
        self.headers = {'Authorization': 'Bearer ' + self.settings.token}

    def test_auth_required_for_data_and_images(self):
        for route in ['/health', '/v1/holes', '/v1/images/2a4b5519-b410-543f-a671-54ef1ae03f32/content']:
            self.assertEqual(self.client.get(route).status_code, 401)
        self.assertEqual(self.client.get('/health', headers={'Authorization': 'Bearer wrong'}).status_code, 401)

    def test_fixed_holes_and_health(self):
        data = self.client.get('/v1/holes', headers=self.headers).json()
        self.assertEqual(len(data['items']), 5)
        self.assertEqual(sum(row['sample_count'] for row in data['items']), 261892)
        health = self.client.get('/health', headers=self.headers).json()
        self.assertFalse(health['media_verified_by_health'])

    def test_sample15_real_scalar_image_fixture(self):
        ref = self.fixture.reference
        response = self.client.get('/v1/holes/07THD002/samples/15', headers=self.headers,
                                   params={'log_id': ref['results'][0]['log_id']})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['md_m'], ref['md_m'])
        self.assertEqual(data['results'][0], ref['results'][0])
        self.assertEqual(data['images'][0]['indicator'], ref['images'][0]['indicator'])
        self.assertNotIn('object_key', data['images'][0])
        image = self.client.get(data['images'][0]['content_path'], headers=self.headers)
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers['content-type'], 'image/png')
        self.assertEqual(hashlib.sha256(image.content).hexdigest(), self.fixture.assets[ref['images'][0]['image_asset_id']]['sha256'])
        self.assertEqual(len(self.s3.calls), 2)  # PNG reused from verified bounded cache.

    def test_spectrum_uses_verified_range_and_preserves_nonfinite(self):
        response = self.client.get('/v1/holes/07THD002/samples/15', headers=self.headers,
                                   params={'log_id': self.fixture.spectral['id']})
        self.assertEqual(response.status_code, 200, response.text)
        spectrum = response.json()['results'][0]
        self.assertEqual(len(spectrum['spectra']), 531)
        self.assertEqual(spectrum['nonfinite_channels'], [7])
        self.assertIsNone(spectrum['spectra'][7])
        self.assertFalse(spectrum['scaling_applied'])
        calls = [c for c in self.s3.calls if c['Key'].endswith('.f32')]
        self.assertEqual(len(calls), 1)
        b = self.fixture.block
        self.assertEqual(calls[0]['Range'], f'bytes={b["byte_offset"]}-{b["byte_offset"] + b["byte_length"] - 1}')
        with self.assertRaises(APIError):
            self.store.full(self.fixture.spectral_asset)

    def test_corrupt_image_is_rejected(self):
        asset = self.fixture.assets[self.fixture.reference['images'][0]['image_asset_id']]
        data = bytearray(self.s3.objects[asset['object_key']]); data[-1] ^= 1
        self.s3.objects[asset['object_key']] = bytes(data)
        response = self.client.get('/v1/holes/07THD002/samples/15', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error'], 'remote_checksum_mismatch')

    def test_wrong_range_and_s3_failure_are_rejected_without_detail(self):
        original = self.s3.get_object
        def broken(**kwargs):
            response = original(**kwargs)
            response['ContentRange'] = 'bytes 0-1/2'
            return response
        self.s3.get_object = broken
        with self.assertRaises(APIError) as caught:
            self.store.block(self.fixture.spectral_asset, self.fixture.block)
        self.assertEqual(caught.exception.code, 'remote_range_mismatch')
        self.s3.get_object = lambda **kwargs: (_ for _ in ()).throw(RuntimeError('SECRET DSN password=DO-NOT-EXPOSE C:/private'))
        response = self.client.get('/v1/holes/07THD002/samples/15', headers=self.headers)
        self.assertEqual(response.json(), {'error': 'backend_unavailable'})

    def test_selection_scope_and_empty_log_default(self):
        url = '/v1/holes/07THD002/samples/15'
        self.assertEqual(self.client.get(url, headers=self.headers).json()['results'], [])
        response = self.client.get(url, headers=self.headers, params={'log_id': '00000000-0000-0000-0000-000000000000'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get('/v1/holes/12CADD001/samples/15', headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get('/v1/holes/07THD002/samples/-1', headers=self.headers).status_code, 422)

    def test_reader_with_write_privilege_refused(self):
        class AdminConn:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, params=()):
                if 'FROM pg_roles' in sql:
                    return Cursor([{'rolsuper': False, 'rolcreatedb': False, 'rolcreaterole': False,
                                    'rolreplication': False, 'rolbypassrls': False}])
                if 'FROM pg_tables' in sql: return Cursor([{'writeable': 1}])
                if 'has_schema_privilege' in sql: return Cursor([{'allowed': False}])
                return Cursor([])
        settings = Settings('host=localhost dbname=test user=test', 'x' * 40, 'bucket', 'ap-southeast-2')
        with patch('cloud_api.app.psycopg.connect', return_value=AdminConn()):
            with self.assertRaises(APIError) as caught:
                with database(settings): pass
        self.assertEqual(caught.exception.code, 'reader_has_write_privileges')

    def test_cache_is_bounded_and_avoids_refetch(self):
        objects = {'data/a': b'abcd', 'data/b': b'efgh'}
        s3 = FakeS3(objects)
        store = S3Store(s3, 'bucket', 'etl4_s3_primary', 'data', cache_bytes=4)
        def asset(key): return {'object_key': key, 'sha256': hashlib.sha256(objects[key]).hexdigest(), 'byte_size': 4}
        store.full(asset('data/a')); store.full(asset('data/a'))
        self.assertEqual(len(s3.calls), 1)
        store.full(asset('data/b'))
        self.assertEqual(store._bytes, 4)
        store.full(asset('data/a'))
        self.assertEqual(len(s3.calls), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
