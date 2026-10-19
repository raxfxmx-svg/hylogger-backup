"""Upload the fixed manifest using short-lived, object-scoped URLs. No AWS keys."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import ssl
import sys
import time
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('handoff_upload', ROOT / 'tools/handoff.py')
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)

def run(path, workers):
    signed = json.loads(Path(path).read_text(encoding='utf-8'))
    target = json.loads((ROOT / 'deployment/target.json').read_text(encoding='utf-8'))
    _, unique = ops.assets()
    if (signed['release_id'] != ops.RELEASE or signed['bucket'] != target['s3_bucket']
            or signed['region'] != target['region'] or signed['prefix'] != target['s3_prefix']
            or len(signed['objects']) != len(unique)
            or {r['source_key'] for r in signed['objects']} != set(unique)):
        raise ValueError('Scoped upload file does not match this deployment')
    def upload(row):
        expected = unique[row['source_key']]
        if any(row[k] != expected[k] for k in ('byte_size', 'sha256')):
            raise ValueError('Signed object identity mismatch')
        source = ops.safe(ROOT / 'etl4', row['source_key'])
        if source.stat().st_size != row['byte_size'] or ops.sha(source) != row['sha256']:
            raise ValueError('Source file failed verification: ' + row['source_key'])
        url = urlsplit(row['url'])
        allowed = {f"{target['s3_bucket']}.s3.{target['region']}.amazonaws.com",
                   f"{target['s3_bucket']}.s3.amazonaws.com"}
        if (url.scheme != 'https' or url.hostname not in allowed or url.port not in (None,443)
                or url.username or url.fragment
                or unquote(url.path) != '/' + target['s3_prefix'] + '/' + row['source_key']):
            raise ValueError('Unexpected upload destination')
        for attempt in range(3):
            conn = http.client.HTTPSConnection(url.hostname, timeout=120, context=ssl.create_default_context())
            try:
                conn.putrequest('PUT', url.path + '?' + url.query)
                conn.putheader('Content-Length', str(row['byte_size']))
                conn.putheader('Content-Type', row['content_type'])
                conn.putheader('x-amz-checksum-sha256', row['checksum_base64'])
                conn.putheader('If-None-Match', '*')
                conn.endheaders()
                with source.open('rb') as f:
                    for block in iter(lambda: f.read(1024**2), b''):
                        conn.send(block)
                response = conn.getresponse()
                response.read()
                if response.status in (200, 412):
                    return {'source_key': row['source_key'], 'http_status': response.status}
                if response.status not in (429, 500, 502, 503, 504):
                    raise ValueError(f'Upload rejected (HTTP {response.status}); refresh scoped URLs if expired')
            except (OSError, http.client.HTTPException):
                if attempt == 2:
                    raise ValueError('Network upload failed for: ' + row['source_key']) from None
            finally:
                conn.close()
            time.sleep(attempt + 1)
        raise ValueError('Upload retries exhausted for: ' + row['source_key'])
    ops.save('scoped_upload_progress.json', {'status': 'in_progress'})
    done = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(upload, signed['objects']):
            done.append(result)
            if len(done) % 100 == 0:
                print(f'Transferred {len(done)}/{len(unique)} objects', flush=True)
    ops.save('scoped_upload_progress.json', {'status': 'awaiting_remote_verification', 'objects': done})
    print('Transfer complete. Run cloud_runner.py verify-s3 before registration.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('scoped_urls', help='Private URL file downloaded from CloudShell; never commit/share it')
    parser.add_argument('--workers', type=int, default=4, choices=range(1,9))
    args = parser.parse_args()
    try:
        run(args.scoped_urls, args.workers)
    except Exception as exc:
        print(str(exc) if isinstance(exc, ValueError) else type(exc).__name__, file=sys.stderr)
        sys.exit(1)
