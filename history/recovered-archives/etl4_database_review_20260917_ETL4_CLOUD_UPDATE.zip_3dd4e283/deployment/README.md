# Sydney five-hole deployment

This deployment uses the existing `database-1` Aurora PostgreSQL cluster in
`ap-southeast-2`. The target engine was observed as 17.9 on 2026-09-17. Its writer
is Serverless v2 with 0 to 4 ACUs and a 300-second auto-pause setting. These are
observed settings, not changes made by this package.

The deployment is limited to the five-hole release in `target.json`. It does not
download, process, or publish the approximately 4 TB source collection.

## Current compatibility gate

The supplied dump was created by PostgreSQL 17.4 with PostGIS 3.6.2. The actual
Aurora 17.9.3 server offers PostGIS 3.5.6, as verified by a read-only SQL query on
2026-09-17. Actual server discovery takes precedence over extension-table examples.
The original `tools/handoff.py restore`
therefore refuses this target because it conservatively requires PostGIS 3.6+.
This is an untested version combination, not proof of data incompatibility.

Do not run the old restore command merely to inspect the target: it creates the
extension before checking its version. Run the read-only `preflight.sql` first.
Any compatibility trial must use a new, empty database and preserve the dump,
original migrations, scientific data, and original package release identity.

## Connection and credentials

`target.json` contains non-secret endpoint metadata. Use the actual AWS account
and region shown there. Browser login does not configure local AWS CLI access.
AWS CloudShell can use the current console identity without creating access keys.

This is an **Aurora Express** cluster with an internet access gateway and IAM-only
authentication. Its gateway certificate uses AWS public roots. Use the trusted
operating-system public CA bundle and `sslmode=verify-full`; the ordinary regional
RDS CA bundle does not validate this gateway. TLS 1.3 and IAM login were verified.
See the [Aurora Express guide](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/CHAP_GettingStartedAurora.AuroraPostgreSQL.ExpressConfig.html).
Generate an IAM database
token immediately before each new connection; do not write tokens to this folder,
print them, or place literal secrets into shell history. A token does not by
itself grant database access. Existing IAM and database permissions must allow
the connection. Password-only reader accounts cannot connect through this gateway.

The `postgres` database is only the initial administration connection. Restore
business data into the separate `etl4_core` database once compatibility is
verified. Do not replace populated databases or change the existing master
authentication method.

## Files and API acceptance

Keep the S3 bucket private. Upload only the asset manifest allowlist, preserve
the fixed release prefix, verify all object hashes, and register the verified
S3 locations. The existing bucket is recorded in `target.json`; all four Block
Public Access settings were verified as enabled. Existing unrelated objects are
outside the deployment prefix and are not modified.

Use a separate read-only database login for the API. The original reference API
is local-only; the separate `cloud_api/` implementation provides S3-backed reads
and passed nine local tests. Actual cloud acceptance is a separate step. Do not
treat local-file fallback as a successful cloud test.

## Control bundle and transfer

`build_control.py` uses the installed PostgreSQL 17 `pg_restore` to export the
unchanged verified custom dump as compressed SQL. `restore_payload.json` records
both its source dump hash and derivative payload hashes. This permits CloudShell's
existing `psql` to import PostgreSQL 17 SQL into PostgreSQL 17 without treating its
older `pg_restore` as compatible with the newer dump format. Only `core` is
exported; target PostGIS is installed separately.

`cloud_runner.py restore` creates the separate database if missing, refuses a
populated `core` schema, requires the inspected PostgreSQL 17.9/PostGIS 3.5.6
combination, and imports in one transaction. It then executes exact EWKB, source
coordinate, spatial-query and sample-baseline checks. It does not weaken the
original generic restore tool's version gate.

The raw 2.4 GB asset collection is not included in the CloudShell control ZIP.
`cloud_runner.py sign-uploads` generates short-lived URLs restricted to the exact
manifest object keys, checksums and non-overwrite uploads. Download the private
`~/etl4-upload-urls.json` from CloudShell and use it with `upload_scoped.py` on the
computer that already holds this package. Do not copy that URL file into the
handoff folder, logs, source control or messages. It contains temporary upload
capabilities, not general AWS access keys.

After transfer, run `cloud_runner.py verify-s3` in CloudShell. It reads every
remote object and compares the full SHA256 before writing the receipt accepted
by `cloud_runner.py register-s3`. A transfer-only report is never an acceptance
report. Existing keys are not overwritten; mismatched content is an error.

Acceptance must include all five holes and 261,892 current samples, all 13
database fixtures, the `07THD002` sample 15 depth/mineral/row-image fixture,
duplicate-depth samples 129 and 130 in `05KCD001`, and all eight spectral arrays.
Record actual outcomes in validation reports. A prepared script is not evidence
that the corresponding AWS operation has run.
