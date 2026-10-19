"""Build a small CloudShell control bundle without copying the 2.4 GB assets."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--pg-restore', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    backup = json.loads((ROOT / 'manifests/database_backup.json').read_text(encoding='utf-8-sig'))
    dump = ROOT / 'etl4/database' / backup['backup_relative_path']
    if sha(dump) != backup['backup_sha256']:
        raise ValueError('Original dump checksum mismatch')
    payload = ROOT / 'deployment/core_restore.sql.gz'
    proc = subprocess.Popen([args.pg_restore, '--schema=core', '--no-owner', '--no-acl', '--file=-', str(dump)], stdout=subprocess.PIPE)
    digest = hashlib.sha256()
    with payload.open('wb') as dest, gzip.GzipFile(fileobj=dest, mode='wb', mtime=0) as out:
        for block in iter(lambda: proc.stdout.read(1024**2), b''):
            digest.update(block)
            out.write(block)
    if proc.wait():
        raise ValueError('SQL export failed')
    info = dict(source_dump_sha256=backup['backup_sha256'], sql_sha256=digest.hexdigest(),
        gzip_sha256=sha(payload), gzip_bytes=payload.stat().st_size,
        export_options=['--schema=core', '--no-owner', '--no-acl'],
        note='Derivative SQL export only. Original dump, migrations and scientific data are unchanged.')
    (ROOT / 'deployment/restore_payload.json').write_text(json.dumps(info, indent=2)+'\n', encoding='utf-8')
    outpath = Path(args.output)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for pattern in ('deployment/*.py','deployment/*.sql','deployment/*.json','deployment/*.md',
                    'deployment/*.gz','cloud_api/*.py','cloud_api/*.md','manifests/*.json',
                    'examples/*.json','tools/handoff.py','requirements*.txt'):
        paths.extend(ROOT.glob(pattern))
    with zipfile.ZipFile(outpath, 'w', zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(set(paths)):
            archive.write(source, source.relative_to(ROOT).as_posix())
    print(json.dumps({'archive':str(outpath.resolve()), 'bytes':outpath.stat().st_size,
                      'sha256':sha(outpath), 'files':len(set(paths))}))

if __name__ == '__main__':
    main()
