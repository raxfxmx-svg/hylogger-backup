"""Build the small, standalone cloud API supplement from the verified handoff."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'handoff'
NAME = 'ETL4_API_CLOUD_SUPPLEMENT_20260923_VERIFIED'
DEST = HERE / NAME
ARCHIVE = HERE / (NAME + '.zip')
if DEST.exists() or ARCHIVE.exists():
    raise SystemExit('Output already exists; review it before building another version.')
DEST.mkdir()

copied = [
    'deployment/run_api.py',
    'deployment/requirements-cloud.txt',
    'deployment/target.json',
    'deployment/runtime_policy.template.json',
    'deployment/TEAMMEMBERA_SIGN_IN.md',
    'cloud_api/__init__.py',
    'cloud_api/app.py',
    'cloud_api/reader.py',
    'cloud_api/storage.py',
    'docs/DATA_MODEL.md',
    'docs/SCHEMA_DICTIONARY.md',
    'examples/DATASET_CATALOG.json',
    'validation/cloud_api_acceptance.json',
    'validation/deployment_summary.json',
    'validation/aws_access_review_20260923.json',
]
for relative in copied:
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE / relative, target)

def write(relative, content):
    target = DEST / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.strip() + '\n', encoding='utf-8')

write('README.md', r'''
# ETL4 cloud API supplement

Prepared on 2026-09-23 for Contributor 3 and the API team.

The local `database.rar` dated 2026-09-13 does not contain `deployment/` or
`cloud_api/`. Those files were added during the later AWS deployment. This ZIP
provides the missing runtime and English instructions. It can run independently
of that older archive against the existing five-hole AWS deployment.

## Start here

1. Extract the entire ZIP into a new folder. Keep `deployment/` and `cloud_api/`
   next to this README. Do not move only `run_api.py` into the old database folder.
2. Read [the connection guide](deployment/TEAMMATE_START.md).
3. Use your existing TeamMemberA IAM login. The AWS console review on 2026-09-23
   confirmed that the user, console access and required policies are configured.
   This ZIP contains no credentials; it does not replace your personal login.
4. Install the requirements and run `deployment/run_api.py --check` as documented.
5. Start the local API and use [the route guide](cloud_api/README.md).

The cloud database and objects were previously deployed and validated. Do not
restore the old database dump, run migrations, upload data again or rebuild crops.
This ZIP has no images, spectra, database dump, virtual environment or credentials.
The API fetches the needed data from Aurora and private S3 at runtime.

## Files

| Path | Purpose |
| --- | --- |
| `deployment/run_api.py` | Launch the API or check the real Aurora/S3 connection |
| `deployment/requirements-cloud.txt` | Python runtime dependencies |
| `deployment/target.json` | Existing non-secret AWS target configuration |
| `deployment/TEAMMATE_START.md` | Setup, verification and startup instructions |
| `deployment/TEAMMEMBERA_SIGN_IN.md` | Verified account status and personal CLI profile instructions |
| `deployment/runtime_policy.template.json` | Required scoped data permissions; administrator reference |
| `cloud_api/` | Complete cloud API runtime and route documentation |
| `docs/` | Database relationships and schema dictionary |
| `examples/DATASET_CATALOG.json` | Hole and log identifiers, including spectral logs |
| `validation/` | Historical cloud acceptance and the September 23 console review; not a live test using your identity |
| `PACKAGE_FILES.json` | File sizes and SHA256 digests |
| `verify_package.py` | Offline integrity check; needs only Python's standard library |

To add this supplement to the shared repository, keep both runtime directories
at the same repository level and retain the matching instructions/configuration.
If the repository already has either directory, compare changes before merging.
The existing reference database code is not required by this cloud runtime.

The API binds to `127.0.0.1:8000`. This ZIP does not create a hosted API URL or
cloud resources. Persistent hosting remains a separate deployment step.
''')

write('deployment/TEAMMATE_START.md', r'''
# Connect the standalone API supplement

Run commands from the extracted folder containing the top-level README.
Use Python 3.12 or 3.13. The existing Aurora database and S3 objects are already
populated; no database restore, migration or ETL operation is needed.

## AWS access

The target is project account `000000000000`, region `ap-southeast-2`, database
`etl4_core`, using the existing `etl4_reader` PostgreSQL role. Configuration is
in `target.json`. The fixed release is
`fd02659c-dc3d-52ea-a8eb-c032b91e7624`: five holes and 261,892 current samples.

Your own AWS identity must be authorized to connect as `etl4_reader` and read
the fixed S3 release prefix. See `runtime_policy.template.json`. A local copy of
that policy does not grant access. Browser login alone is not an SDK login.

TeamMemberA: read [AWS CLI setup](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html) first. The recorded plan uses
an IAM user with CLI temporary credentials, not an SSO account. A console review
on 2026-09-23 confirmed that your account and required policies are configured;
your console last sign-in was 2026-09-22 15:17 (UTC+08:00).
Use your existing sign-in details and perform your own live check.
Do not use an administrator's credentials or register a personal root account.

## Install and check (PowerShell)

After completing the two AWS profile setup steps in TEAMMEMBERA_SIGN_IN.md:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r deployment/requirements-cloud.txt
& .\.venv\Scripts\python.exe verify_package.py
$env:AWS_PROFILE = 'etl4-teammembera'
aws login --profile etl4-teammembera-signin
aws sts get-caller-identity --profile etl4-teammembera
& .\.venv\Scripts\python.exe deployment/run_api.py --check
```

Expected identity: account `000000000000`, user `teammembera.Contributor3`.
An approved alternative identity can use its own profile instead.

The live check prints `LIVE_CHECK_PASSED` only after checking IAM/TLS database
access, sample 15, its Muscovite scalar and the corresponding private S3 PNG.
It does not write to the database or S3. It requires internet access and completed
AWS permissions. Aurora can take time to resume after inactivity; allow more than
60 seconds for a first request. A successful STS call alone is not a data check.

The launcher uses public certificate authorities for the Aurora Express gateway,
with `sslmode=verify-full`. It generates a fresh IAM database token per connection;
there is no PostgreSQL password to place in `target.json`.

## Start the local API

```powershell
& .\.venv\Scripts\python.exe deployment/run_api.py
```

Enter your own private API bearer token of at least 32 characters at the hidden
prompt. This is separate from the AWS console password and AWS session tokens.
Use `Authorization: Bearer <your-api-token>` for all requests, including images
and health. The service listens on `http://127.0.0.1:8000` on your computer.
The token can also be supplied through your existing secret handling as
`ETL4_API_TOKEN`; never commit it or put it in shared configuration files.

Read [the route guide](../cloud_api/README.md) for examples and limitations.
No public API address, HTTPS hosting, account-wide permissions, or CloudShell
access is included. The API team can adapt the code for its chosen hosting setup.

## Troubleshooting

- `ModuleNotFoundError`: install requirements in the same virtual environment used
  to run the launcher; keep both `deployment/` and `cloud_api/` in this folder.
- An unknown `aws login` command: install AWS CLI v2 version 2.32.0 or newer.
- Expired credentials: sign in again using the sign-in profile above.
- Wrong account: choose the project IAM identity in the browser and sign in again.
- AWS/SQL AccessDenied or failed live check: ask the administrator to confirm the
  identity policy and reader role. Do not repair this by restoring the database.
- S3 console or bucket-list AccessDenied: listing is outside the intended read
  permissions; use the supplied live check to test an actual permitted object.

Historical evidence under `validation/` records the operator's earlier successful
cloud checks. It is not evidence that the recipient's new credentials work today.
''')

original_api_doc = (SOURCE / 'cloud_api/README.md').read_text(encoding='utf-8-sig')
routes_and_boundaries = original_api_doc.split('## API routes\n', 1)[1].split('## Offline verification\n', 1)[0]
write('cloud_api/README.md', '''
# Five-hole cloud API route guide

Start with [the connection guide](../deployment/TEAMMATE_START.md) and use
`deployment/run_api.py`. Install only `deployment/requirements-cloud.txt` for this
standalone supplement. No files from the old database archive are needed at runtime.

Every route requires `Authorization: Bearer <your-api-token>`. There are no public
or presigned S3 image links. Swagger/OpenAPI HTTP pages and CORS are not enabled.
The bearer-token scheme and single local worker serve the pilot; persistent HTTPS
hosting and production application authentication are separate deployment work.

In the example below, set `ETL4_API_TOKEN` in your HTTP-client terminal through
your private secret handling to the same token entered in the server terminal.
If writing the PNG output, run from this package's top-level folder.

## API routes
''' + routes_and_boundaries)

write('MESSAGE_TO_TEAMMEMBERA.txt', '''
Hi TeamMemberA, the database archive I sent was the September 13 version. The cloud
deployment files were added later, so they were missing from that archive.

This supplement includes run_api.py, requirements-cloud.txt, target.json, the
complete cloud_api runtime and English setup instructions. Please extract the
whole ZIP and start with README.md. You can run it separately from the old
database archive; there is no need to download or restore the data again.

Your AWS IAM user and required read-only policies were checked in the console on
September 23 and are configured. Use your existing login, then run the documented
--check command to verify Aurora and S3 from your computer before starting the API.
''')

write('verify_package.py', '''
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
''')

write('.gitignore', '''
.venv/
__pycache__/
*.pyc
.env
''')

source_inventory = {row['path']: row for row in json.loads(
    (SOURCE / 'PACKAGE_FILES.json').read_text(encoding='utf-8-sig'))['files']}
for relative in copied:
    actual = (DEST / relative).read_bytes()
    assert actual == (SOURCE / relative).read_bytes(), relative
    if relative in source_inventory:
        assert hashlib.sha256(actual).hexdigest() == source_inventory[relative]['sha256'], relative
for path in DEST.rglob('*.py'):
    ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))

files = []
for path in sorted(DEST.rglob('*')):
    if path.is_file():
        content = path.read_bytes()
        files.append({'path': path.relative_to(DEST).as_posix(), 'bytes': len(content),
                      'sha256': hashlib.sha256(content).hexdigest()})
write('PACKAGE_FILES.json', json.dumps({
    'package': NAME,
    'prepared_on': '2026-09-23',
    'scope': 'Standalone runtime supplement for the existing five-hole AWS deployment',
    'copied_unchanged_from_handoff': copied,
    'cloud_retested_during_packaging': False,
    'files': files,
}, ensure_ascii=False, indent=2))

with zipfile.ZipFile(ARCHIVE, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for path in sorted(DEST.rglob('*')):
        if path.is_file():
            z.write(path, (Path(NAME) / path.relative_to(DEST)).as_posix())

with tempfile.TemporaryDirectory(prefix='etl4_supplement_check_') as tmp:
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None, 'ZIP integrity failure'
        z.extractall(tmp)
        zip_count = len(z.infolist())
    extracted = Path(tmp) / NAME
    for args in [
        ['verify_package.py'],
        ['deployment/run_api.py', '--help'],
        ['-c', 'from cloud_api.app import Settings, create_app; from cloud_api.reader import HOLES; from cloud_api.storage import S3Store; assert len(HOLES) == 5; print("RUNTIME_IMPORTS_PASSED: no AWS calls")'],
    ]:
        subprocess.run([sys.executable, '-B', *args], cwd=extracted, check=True)

checksum = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
(HERE / (NAME + '.zip.sha256')).write_text(checksum + '  ' + ARCHIVE.name + '\n', encoding='ascii')
print(json.dumps({'archive': str(ARCHIVE), 'bytes': ARCHIVE.stat().st_size,
                  'zip_files': zip_count, 'sha256': checksum,
                  'copied_unchanged_files': len(copied), 'validation': 'passed',
                  'new_cloud_test': False}, ensure_ascii=False))
