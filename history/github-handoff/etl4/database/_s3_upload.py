"""Shared S3 object upload for step 39: verify content, use conditional writes, and clean up failed multipart uploads.
Shared S3 upload for step 39: content checks, conditional writes, and cleanup of failed multipart uploads.
"""

import base64
import hashlib
import mimetypes
from pathlib import Path
import zlib


def crc32_text(value):
    return base64.b64encode((value & 0xffffffff).to_bytes(4, 'big')).decode('ascii')


def file_checks(path, expected_sha256, expected_size):
    """Verify source SHA256 and calculate the S3 full-object CRC32 in one file read.
    Check source SHA256 and calculate full-object S3 CRC32 in one read.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size != expected_size:
        raise ValueError('The source file is missing or its size differs from the manifest: ' + path.name)
    digest = hashlib.sha256()
    checksum = 0
    size = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
            checksum = zlib.crc32(block, checksum)
            size += len(block)
    if size != expected_size or digest.hexdigest() != expected_sha256:
        raise ValueError('The source file content differs from the manifest: ' + path.name)
    return crc32_text(checksum)


def error_code(error):
    return str(getattr(error, 'response', {}).get('Error', {}).get('Code', ''))


def check_upload_sdk(client):
    """Reject older SDKs before upload when conditional-write or full-object checksum parameters are missing.
    Reject outdated SDKs missing conditional-write or full-checksum parameters before uploading.
    """
    required = {
        'PutObject': {'ChecksumAlgorithm', 'ChecksumCRC32', 'IfNoneMatch'},
        'HeadObject': {'ChecksumMode'},
        'CreateMultipartUpload': {'ChecksumAlgorithm', 'ChecksumType'},
        'UploadPart': {'ChecksumAlgorithm', 'ChecksumCRC32'},
        'CompleteMultipartUpload': {'ChecksumType', 'ChecksumCRC32', 'MpuObjectSize', 'IfNoneMatch'},
    }
    for operation, fields in required.items():
        available = client.meta.service_model.operation_model(operation).input_shape.members
        if not fields.issubset(available):
            raise ValueError('The installed boto3/botocore lacks full-object checksum APIs; upgrade the AWS upload dependencies')


def remote_object(client, bucket, key, expected_sha256, expected_size, crc32):
    # HEAD API reference: https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/head_object.html
    try:
        head = client.head_object(Bucket=bucket, Key=key, ChecksumMode='ENABLED')
    except Exception as exc:
        if error_code(exc) in ('404', 'NoSuchKey', 'NotFound'):
            return None
        raise
    if head.get('ContentLength') != expected_size:
        raise ValueError('The existing object has a size conflict; it was not overwritten: ' + key)
    recorded_sha = head.get('Metadata', {}).get('source-sha256')
    if recorded_sha and recorded_sha != expected_sha256:
        raise ValueError('The existing object has a content identity conflict; it was not overwritten: ' + key)
    sha_base64 = base64.b64encode(bytes.fromhex(expected_sha256)).decode('ascii')
    if head.get('ChecksumType') != 'FULL_OBJECT':
        raise ValueError('The existing object has no comparable full-object checksum; use a new prefix: ' + key)
    if head.get('ChecksumSHA256'):
        if head['ChecksumSHA256'] != sha_base64:
            raise ValueError('The existing object has a SHA256 conflict; it was not overwritten: ' + key)
        algorithm, checksum = 'SHA256', sha_base64
    elif head.get('ChecksumCRC32') == crc32:
        algorithm, checksum = 'CRC32', crc32
    else:
        raise ValueError('The existing object checksum is missing or does not match; it was not overwritten: ' + key)
    return {'sha256': expected_sha256, 'byte_size': expected_size, 'object_key': key,
            'checksum_algorithm': algorithm, 'checksum_type': 'FULL_OBJECT', 'checksum': checksum,
            'etag': head.get('ETag'), 'version_id': head.get('VersionId')}


class UploadStream:
    """Forward SDK file-read progress to the entry point; determine completion from the server response.
    Report SDK file-read progress through the entry point; server responses determine completion.
    """

    def __init__(self, stream, size, progress):
        self.stream = stream
        self.size = size
        self.progress = progress

    def read(self, count=-1):
        data = self.stream.read(count)
        if self.progress:
            self.progress(self.stream.tell(), self.size)
        return data

    def __getattr__(self, name):
        return getattr(self.stream, name)


def upload_multipart(client, source, bucket, key, size, sha256, crc32, part_size, progress):
    # Multipart SHA256 is not a whole-file digest, so explicitly use CRC32 FULL_OBJECT here.
    # Upload integrity reference: https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html
    created = client.create_multipart_upload(
        Bucket=bucket, Key=key, ChecksumAlgorithm='CRC32', ChecksumType='FULL_OBJECT',
        Metadata={'source-sha256': sha256},
        ContentType=mimetypes.guess_type(source.name)[0] or 'application/octet-stream')
    upload_id = created['UploadId']
    try:
        parts = []
        sent = 0
        with source.open('rb') as stream:
            for number in range(1, 10001):
                block = stream.read(part_size)
                if not block:
                    break
                part_crc = crc32_text(zlib.crc32(block))
                result = client.upload_part(
                    Bucket=bucket, Key=key, UploadId=upload_id, PartNumber=number,
                    Body=block, ContentLength=len(block),
                    ChecksumAlgorithm='CRC32', ChecksumCRC32=part_crc)
                if result.get('ChecksumCRC32') != part_crc:
                    raise ValueError('The S3 part checksum response does not match: ' + key)
                parts.append({'PartNumber': number, 'ETag': result['ETag'], 'ChecksumCRC32': part_crc})
                sent += len(block)
                if progress:
                    progress(sent, size)
            if stream.read(1) or sent != size:
                raise ValueError('The source size changed during upload or the part count exceeded the limit: ' + key)
        client.complete_multipart_upload(
            Bucket=bucket, Key=key, UploadId=upload_id, MultipartUpload={'Parts': parts},
            ChecksumCRC32=crc32, ChecksumType='FULL_OBJECT', MpuObjectSize=size, IfNoneMatch='*')
    except BaseException:
        # Restart incomplete large uploads; reuse completed objects through HEAD on a later run.
        try:
            client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
        except Exception:
            pass
        raise


def upload_object(client, source, bucket, key, expected_sha256, expected_size, *,
                  progress=None, part_size=64 * 1024**2, multipart_threshold=64 * 1024**2):
    """Upload or reuse one object without overwriting existing content or downloading the full file with GET.
    Upload or reuse one object without overwriting existing content or downloading the complete file through GET.
    """
    source = Path(source)
    if part_size < 5 * 1024**2 or part_size > 5 * 1024**3:
        raise ValueError('The S3 part size must be between 5 MiB and 5 GiB')
    if (type(expected_size) is not int or expected_size < 0
            or not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(value not in '0123456789abcdef' for value in expected_sha256)):
        raise ValueError('Invalid file identity format')
    crc32 = file_checks(source, expected_sha256, expected_size)
    existing = remote_object(client, bucket, key, expected_sha256, expected_size, crc32)
    if existing:
        return {**existing, 'reused': True}
    if progress:
        progress(0, expected_size)
    try:
        if expected_size >= multipart_threshold or expected_size > 5 * 1024**3:
            # Allow at most 10000 parts, rounding sizes up to MiB so memory usage depends only on a single part.
            minimum = ((expected_size + 9999) // 10000 + 1024**2 - 1) // 1024**2 * 1024**2
            selected_size = max(part_size, minimum)
            if selected_size > 5 * 1024**3:
                raise ValueError('The file exceeds the size supported by S3 multipart upload')
            upload_multipart(client, source, bucket, key, expected_size, expected_sha256,
                             crc32, selected_size, progress)
        else:
            with source.open('rb') as stream:
                client.put_object(
                    Bucket=bucket, Key=key, Body=UploadStream(stream, expected_size, progress),
                    ContentLength=expected_size, ChecksumAlgorithm='CRC32', ChecksumCRC32=crc32,
                    ContentType=mimetypes.guess_type(source.name)[0] or 'application/octet-stream',
                    Metadata={'source-sha256': expected_sha256}, IfNoneMatch='*')
    except Exception as exc:
        if error_code(exc) not in ('412', 'PreconditionFailed'):
            raise
        # If another process completes the same object after HEAD, verify its content before reuse.
        existing = remote_object(client, bucket, key, expected_sha256, expected_size, crc32)
        if not existing:
            raise ValueError('No complete object was found after a conditional-write conflict: ' + key) from exc
        return {**existing, 'reused': True}
    uploaded = remote_object(client, bucket, key, expected_sha256, expected_size, crc32)
    if not uploaded:
        raise ValueError('No complete object was found after upload: ' + key)
    if progress:
        progress(expected_size, expected_size)
    return {**uploaded, 'reused': False}
