"""Read-only streaming SHA256 verification for assets without native full SHA256."""
import hashlib
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import boto3

root=Path.home()/'audit_12DHDD0002_20261011'
audit=json.loads((root/'audit_report.json').read_text())
pending=audit['objects_requiring_streamed_sha256']
heads={x['key']:x for x in audit['objects']}
s3=boto3.client('s3',region_name=audit['region'])
result={'started_at':datetime.now(timezone.utc).isoformat(),'method':'S3 GetObject with IfMatch to audited ETag; incremental SHA256; no bulk file stored','batch_id':audit['batch_id'],'manifest_sha256':audit['manifest_sha256']}
def verify(obj):
    key=obj['key'];size=0;h=hashlib.sha256()
    try:
        body=s3.get_object(Bucket=audit['bucket'],Key=key,IfMatch=heads[key]['native']['ETag'])['Body']
        try:
            for chunk in body.iter_chunks(chunk_size=1024*1024):
                size+=len(chunk)
                if size>obj['byte_size']:raise ValueError('Object grew beyond expected byte size')
                h.update(chunk)
        finally:body.close()
        return {'key':key,'bytes_read':size,'sha256':h.hexdigest(),'passed':size==obj['byte_size'] and h.hexdigest()==obj['sha256']}
    except Exception as e:return {'key':key,'passed':False,'error':str(e),'bytes_read':size}
print('STREAM_VERIFY '+str(len(pending))+' objects, '+str(sum(x['byte_size'] for x in pending))+' bytes; no local bulk download',flush=True)
with ThreadPoolExecutor(max_workers=4) as pool:
    rows=[]
    for row in pool.map(verify,pending):
        rows.append(row)
        if len(rows)%40==0:print('HASHED '+str(len(rows))+'/'+str(len(pending)),flush=True)
result.update(objects=rows,finished_at=datetime.now(timezone.utc).isoformat(),all_passed=all(x['passed'] for x in rows),bytes_read=sum(x['bytes_read'] for x in rows))
(root/'stream_sha256_report.json').write_text(json.dumps(result,indent=2)+'\n')
package=Path.home()/'audit_12DHDD0002_20261011_verified.zip'
with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob('*'):
        if p.is_file():z.write(p,p.relative_to(root).as_posix())
print('STREAM_RESULT '+json.dumps({k:v for k,v in result.items() if k!='objects'}),flush=True)
print('ARCHIVE '+json.dumps({'path':str(package),'bytes':package.stat().st_size,'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}),flush=True)
