# Restore and Deployment Operations

For the existing Sydney `database-1 / etl4_core` deployment, use
[TEAMMATE_START.md](../deployment/TEAMMATE_START.md). That database has already been
restored and uses Aurora Express IAM-only authentication with public CA roots.
The generic restore/password examples below are for other, newly provisioned
compatible targets; do not apply them to the existing Sydney database.

## Prerequisites and target settings

Use Python 3.12. Install the root requirements.txt for local operations. For S3 commands additionally install requirements-aws.txt and configure the recipient's AWS identity through its normal credential provider, such as an AWS profile, SSO session or instance role.

The dump was created by PostgreSQL 17.4 with PostGIS 3.6.2. The automated restore requires PostgreSQL 17+ and PostGIS 3.6+ in the public schema. This conservative compatibility check prevents an unreviewed PostGIS downgrade. For RDS choose an available stable engine/extension combination from the [AWS extension version table](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html); verify the target before relying on it. A matching version number alone is not proof of a successful restore.

The receiving operator supplies the database endpoint, empty database name, admin credentials, reader credentials, CA certificate, region and bucket name. None is supplied as a working cloud connection in this package.

## Restore into an empty database

1. Create a new empty UTF-8 database using the database administration tool. A suggested name is etl4_core. Do not use an existing application database. Enable a permitted network route from the restoring computer.
2. Set ETL4_ADMIN_DSN for that database. Do not copy the sender's loopback address for a remote server. For RDS use the real endpoint, official CA certificate and sslmode=verify-full. Local examples may use sslmode=disable only for a local test server without TLS.
3. Run the restore command. It checks the dump hash and refuses a nonempty core schema. It creates PostGIS and an empty core schema, then restores core using --no-owner --no-acl --single-transaction --exit-on-error. Do not pre-create business tables by running migrations 001–005.

PowerShell example; replace every bracketed value before use:

```powershell
$env:ETL4_ADMIN_DSN = 'host=<endpoint> port=5432 dbname=etl4_core user=<admin> password=<password> sslmode=verify-full sslrootcert=<CA-file>'
& .\.venv\Scripts\python.exe tools/handoff.py restore --database etl4_core --pg-restore 'C:\Program Files\PostgreSQL\17\bin\pg_restore.exe'
& .\.venv\Scripts\python.exe tools/handoff.py create-reader --role etl4_reader
```

The reader command prompts for a new password without echoing it. It refuses to change an already existing role; choose a new role name if necessary. Restore skips old role ownership/ACLs and explicitly removes PUBLIC access to core. The new role receives only CONNECT, schema USAGE and table SELECT. Keep administration credentials separate from the API process.

Linux/macOS use `export ETL4_ADMIN_DSN='...'` and `python tools/handoff.py ...`. If pg_restore is on PATH, omit --pg-restore. Database credentials are passed to pg_restore through its environment, not its command-line arguments or package files. In interactive terminals avoid saving real credentials in shared shell history.

If restoration fails, read the error. The data restore is transactional, but extension/schema preparation can remain. Retrying is allowed only if core is empty. The tool never drops an existing database or deletes populated tables.

AWS documentation: [PostgreSQL import](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Procedural.Importing.html), [PostGIS setup](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.PostGIS.html), [RDS TLS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html).

## Read the package immediately after restoration

Configure the reader DSN, then validate:

```powershell
$env:ETL4_READ_DSN = 'host=<endpoint> port=5432 dbname=etl4_core user=etl4_reader password=<reader-password> sslmode=verify-full sslrootcert=<CA-file>'
& .\.venv\Scripts\python.exe tools/handoff.py check-db
& .\.venv\Scripts\python.exe tools/handoff.py sample --hole 07THD002 --sample 15 --log-id a4a5c7d3-0fe8-53be-97a2-02a5c7771ae8 --output validation/sample15.json
```

The sample must have md_m=62.50175 and Muscovite in the selected mineral log. Its row image is 399 by 25 pixels. The returned object_key is relative to this package's etl4/ directory; open that file locally to inspect the crop. It is not an HTTP URL. This command creates its own dict_row connection and never reads the sender's local_config.json.

Without --log-id, the portable command intentionally reads only depth and image metadata. Repeat --log-id to select more logs. The full spectral log IDs are listed in examples/DATASET_CATALOG.json. A 05KCD001 check at samples 129 and 130 must return the same depth but different row images.

check-db verifies the fixed release, 36 tables, current sample count, the 13 depth/image fixtures, validated constraints, and absence of core write/CREATE privileges for the reader. It does not mutate scientific data.

## Upload all current-release objects to S3

Use a private bucket in the selected region. Give the transfer identity permission to inspect, upload and read the chosen object prefix. API runtime identities only need appropriate read permissions. Keep Block Public Access enabled; provide images through the backend or signed URLs.

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-aws.txt
$env:AWS_PROFILE = '<your-profile>'
& .\.venv\Scripts\python.exe tools/handoff.py upload-s3 --bucket <your-bucket> --region <your-region> --prefix data
```

The uploader uses the asset allowlist, not a recursive upload of the whole package. Each local data file is hashed; missing objects are uploaded to data/<original-key>. Existing objects are read and checked without being overwritten. Every remote object is streamed back and checked against the full local SHA256. This adds approximately 2.401 GB of verification reads and may incur normal request/transfer charges. Concurrency defaults to four and can be set with --workers 1 through 8.

A mismatch stops the operation. Objects already uploaded remain and are reusable on retry. Each attempt first writes an in_progress receipt, invalidating any older success receipt; it becomes verified_remote only after all 2,810 files pass. An incomplete receipt cannot be registered. Avoid concurrent uploaders writing the same prefix; use a dedicated prefix for this fixed release.

The receipt is validation/s3_receipt.json. Treat it as an administrator-controlled record. It records bucket, region, exact keys and verified hashes; it does not contain credentials. S3 ETag and user-provided metadata are not substitutes for full-file SHA256 verification. See [S3 integrity guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html).

## Register verified S3 locations

With ETL4_ADMIN_DSN still pointing to the restored database:

```powershell
& .\.venv\Scripts\python.exe tools/handoff.py register-s3 --root-key etl4_s3_primary
```

The tool requires the complete upload receipt, verifies target asset identities, and inserts S3 replicas in one transaction. It does not change scientific rows. There are 3,042 asset-location records for 2,810 physical objects. Re-running after a successful registration skips identical records; conflicting existing statuses cause rollback instead of silently changing them.

validation/s3_mapping.json maps the logical root to the actual bucket/region for the API configuration. Keep the existing local replicas so package-local reading continues to work. The reference reader still selects local files; the API developer must implement S3 reading as described in API_HANDOFF.md, or initially run against the supplied local data directory with a database connection.

## Transfer acceptance

Run verify after copying the folder. Run check-db after restoring with a reader account. Read one scalar sample, one F32 spectrum and one row image. Record S3 upload/registration completion only after the corresponding commands succeed. Validation reports may be regenerated and are excluded from the immutable package inventory.

Do not send this folder's newly created .venv, shell history or personal configuration onward. Source-machine runtime files were excluded when the package was prepared. The sender has not created AWS resources or tested the recipient's AWS account; local test evidence is recorded separately in validation/PREPARATION_TESTS.json.
