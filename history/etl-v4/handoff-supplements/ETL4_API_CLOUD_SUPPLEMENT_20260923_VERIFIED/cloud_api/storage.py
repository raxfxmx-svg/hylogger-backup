"""Verified S3 reads. No local-file fallback and no whole-file F32 reads."""
from collections import OrderedDict
import hashlib
import re
from threading import RLock


class APIError(Exception):
    def __init__(self, code, status=503):
        self.code, self.status = code, status
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise APIError(code)


class S3Store:
    def __init__(self, client, bucket, root_key, prefix, *, cache_bytes=128 * 1024**2,
                 object_limit=64 * 1024**2, block_limit=16 * 1024**2):
        self.client, self.bucket, self.root_key = client, bucket, root_key
        self.prefix = prefix.strip('/') + '/'
        require(bool(prefix.strip('/')), 's3_prefix_required')
        self.cache_bytes, self.object_limit, self.block_limit = cache_bytes, object_limit, block_limit
        self._cache, self._bytes, self._lock = OrderedDict(), 0, RLock()

    def asset(self, conn, asset_id):
        rows = conn.execute('''SELECT a.*,l.object_key FROM core.asset a
          JOIN core.asset_location l ON l.asset_id=a.id AND l.verified_sha256=a.sha256
          WHERE a.id=%s AND l.backend='s3' AND l.access_status='verified_remote'
          AND l.root_key=%s ORDER BY l.object_key''', (asset_id, self.root_key)).fetchall()
        if not rows:
            return None
        require(len(rows) == 1, 'ambiguous_s3_location')
        row = rows[0]
        key = row['object_key']
        require(key.startswith(self.prefix) and not any(p in ('.', '..', '') for p in key.split('/'))
                and '\\' not in key and ':' not in key, 's3_key_outside_configured_prefix')
        require(bool(re.fullmatch('[0-9a-f]{64}', row['sha256'])), 'invalid_asset_identity')
        return row

    def _read(self, asset, offset=None, length=None, checksum=None):
        ranged = offset is not None
        expected = length if ranged else asset['byte_size']
        digest = checksum if ranged else asset['sha256']
        require(isinstance(expected, int) and 0 < expected <= (self.block_limit if ranged else self.object_limit),
                'asset_exceeds_read_limit')
        if ranged:
            require(offset >= 0 and offset + expected <= asset['byte_size'], 'invalid_byte_range')
        key = (asset['object_key'], asset['sha256'], offset, expected, digest)
        # Hold the lock while fetching to prevent many identical simultaneous downloads.
        # This intentionally small pilot prioritizes bounded memory over throughput.
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            options = {'Bucket': self.bucket, 'Key': asset['object_key']}
            if ranged:
                options['Range'] = f'bytes={offset}-{offset + expected - 1}'
            response = self.client.get_object(**options)
            with response['Body'] as body:
                require(response.get('ContentLength') == expected, 'remote_size_mismatch')
                if ranged:
                    require(response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 206
                            and response.get('ContentRange') == f'bytes {offset}-{offset + expected - 1}/{asset["byte_size"]}',
                            'remote_range_mismatch')
                data = body.read(expected + 1)
                require(len(data) == expected and hashlib.sha256(data).hexdigest() == digest,
                        'remote_checksum_mismatch')
            if len(data) <= self.cache_bytes:
                while self._bytes + len(data) > self.cache_bytes and self._cache:
                    _, old = self._cache.popitem(last=False)
                    self._bytes -= len(old)
                self._cache[key] = data
                self._bytes += len(data)
            return data

    def full(self, asset):
        # F32 matrices must only be read through verified spectral blocks.
        require(not asset['object_key'].lower().endswith('.f32'), 'full_spectral_read_forbidden')
        return self._read(asset)

    def block(self, asset, block):
        return self._read(asset, block['byte_offset'], block['byte_length'], block['sha256'])
