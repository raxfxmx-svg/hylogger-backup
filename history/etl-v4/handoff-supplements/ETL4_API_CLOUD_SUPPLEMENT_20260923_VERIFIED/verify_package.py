"""Verify this supplement offline without importing runtime dependencies."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'PACKAGE_FILES.json').read_text(encoding='utf-8'))
for row in manifest['files']:
    path = (root / row['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise SystemExit('Missing or invalid path: ' + row['path'])
    content = path.read_bytes()
    if len(content) != row['bytes'] or hashlib.sha256(content).hexdigest() != row['sha256']:
        raise SystemExit('Checksum mismatch: ' + row['path'])
print('PACKAGE_CHECK_PASSED:', len(manifest['files']), 'files; AWS was not contacted.')
