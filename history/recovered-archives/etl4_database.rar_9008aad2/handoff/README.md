# ETL4 Complete Read Only Handoff

Prepared on 2026-09-13 for the API developer and deployment operator.

This folder contains the database backup, all external files required by the selected five-hole release, reference source code, SQL examples, validation fixtures and portable operation tools. Copy this entire folder to the receiving computer. No files outside this folder are required for the selected release, apart from installed software and the recipient's own database/cloud credentials.

The dataset is fixed and read only after deployment. Do not run ETL steps or rebuild image crops. A database administrator performs the initial restore and storage-location registration; the API and normal users receive read access only.

## Package contents

| Path | Contents |
|---|---|
| etl4/ | 2,810 data files in their original relative layout, totaling 2,400,546,756 bytes |
| etl4/database/backups/ | Verified PostgreSQL custom-format dump and its original manifest |
| etl4/database/migrations/ | Original migrations 001–005; included for reference, not to run before restoring the dump |
| etl4/database/ | Original Python reader modules and existing local API source |
| tools/handoff.py | File verification, empty-database restore, reader setup, sample reading and S3 transfer tools |
| docs/ | English operation guide, API contract and database dictionary |
| examples/ | Six SQL queries, real sample JSON, five-hole ID catalog and 13 acceptance fixtures |
| manifests/ | Original asset manifest, backup pointer and schema catalog |
| config.env.example | Recipient-specific configuration placeholders; never auto-loaded and contains no working credentials |
| PACKAGE_FILES.json | Package file inventory and SHA256 digests |
| validation/ | Verification results; receiving-side operations write their own results here |

Source JSON, CSV, Parquet, binary arrays and evidence files are preserved byte for byte. Original source-language strings in these data files are intentional. All newly prepared handoff documentation and operation instructions are in English. No local_config.json, passwords, AWS keys, database runtime directory or virtual environment is included.

## Start here

Run commands from the folder containing this README. A path containing spaces or non-ASCII characters is supported; alternatively rename the outer folder to ETL4_HANDOFF after copying it. Keep its internal layout unchanged.

Install Python 3.12 and PostgreSQL client tools 17 or later. The target server must have compatible PostGIS support. Python libraries are installed from the internet; offline environments need their own wheel mirror. PostgreSQL server software and AWS resources are not bundled.

PowerShell:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe tools/handoff.py verify
```

Linux or macOS:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python tools/handoff.py verify
```

The verifier checks the copied data, backup, migrations and package inventory. If it fails, stop and recopy the named file before restoring.

Next follow [the operation guide](docs/OPERATIONS.md): create an empty database, restore it, create a reader, configure ETL4_READ_DSN, and run the sample command. To use AWS, also upload and verify S3 objects and register their locations.

For API development read [the API handoff](docs/API_HANDOFF.md), then [the database model](docs/DATA_MODEL.md). Field definitions and constraints are in [the schema dictionary](docs/SCHEMA_DICTIONARY.md).

## Fixed release

```text
fd02659c-dc3d-52ea-a8eb-c032b91e7624
```

| Hole | Samples | Available full spectra |
|---|---:|---|
| 05KCD001 | 22,356 | VSWIR and TIR |
| 07THD002 | 116,424 | VSWIR and TIR |
| 07THD003 | 54,432 | VSWIR and TIR |
| 09ATD015 | 46,030 | VSWIR |
| 09ATD019 | 22,650 | VSWIR |

There are 36 core tables, 261,892 current samples, 249 tray JPGs, 1,361 row PNGs and 8 full spectral arrays. Three additional PNGs are evidence images. The dump also retains historical revisions: its total scan_sample row count is 523,784. Applications must select the fixed release rather than query all historical samples.

This package covers the selected release. It does not promise files for arbitrary historical releases, the three excluded reference holes, an offline software installer, or a new ETL run. The supplied existing HTTP API still requires cloud/media integration; the portable sample command can already read the restored database with this package's local files.

## Preparation checks

The package was restored into an isolated local PostgreSQL 17.4/PostGIS 3.6.2 test server. Reader privileges, all six SQL examples, the 13 sample fixtures, a real mineral result and image, and all eight spectral arrays passed. The test server was stopped afterward. S3 transfer safety paths were tested with a local mock; no AWS account or cloud restore was exercised. See validation/PREPARATION_TESTS.json for the exact scope.
