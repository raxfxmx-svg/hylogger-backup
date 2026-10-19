# Sydney five-hole deployment

This deployment uses the existing `database-1` Aurora PostgreSQL cluster in
`ap-southeast-2`. The target engine was observed as 17.9 on 2026-09-17. Its writer
is Serverless v2 with 0 to 4 ACUs and a 300-second auto-pause setting. These are
observed settings, not changes made by this package.

The deployment is limited to the five-hole release in `target.json`. It does not
download, process, or publish the approximately 4 TB source collection.

## Current compatibility gate

The supplied dump was created by PostgreSQL 17.4 with PostGIS 3.6.2. AWS lists
PostGIS 3.5.1 for Aurora PostgreSQL 17.9. The original `tools/handoff.py restore`
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

Use an official RDS CA bundle and `sslmode=verify-full`. Generate an IAM database
token immediately before each new connection; do not write tokens to this folder,
print them, or place literal secrets into shell history. A token does not by
itself grant database access. Existing IAM and database permissions must allow
the connection.

The `postgres` database is only the initial administration connection. Restore
business data into the separate `etl4_core` database once compatibility is
verified. Do not replace populated databases or change the existing master
authentication method.

## Files and API acceptance

Keep the S3 bucket private. Upload only the asset manifest allowlist, preserve
the fixed release prefix, verify all object hashes, and register the verified
S3 locations. The bucket remains unset until an actual destination is selected.

Use a separate read-only database login for the API. The original reference API
is local-only; the separate `cloud_api/` implementation is being prepared for
S3-backed validation. Do not treat local-file fallback as a successful cloud test.

Acceptance must include all five holes and 261,892 current samples, all 13
database fixtures, the `07THD002` sample 15 depth/mineral/row-image fixture,
duplicate-depth samples 129 and 130 in `05KCD001`, and all eight spectral arrays.
Record actual outcomes in validation reports. A prepared script is not evidence
that the corresponding AWS operation has run.
