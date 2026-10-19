# Historical AWS Storage Plan

2026-09-08 plan, superseded for the first launch by [AWS_FIRST_LAUNCH_PLAN.md](AWS_FIRST_LAUNCH_PLAN.md) on 2026-09-10. The 30-table scope, capacities and proposed steps 15-19 below belong to this earlier plan. No AWS resources, uploads or database changes were performed here.

Store PostgreSQL/PostGIS in RDS and files/backups in private S3. The five-borehole baseline had about 86.51 MB of database storage, 493.18 MB of Parquet/thumbnails, about 1.851 GB of other originals/evidence and a 4.76 MB dump. All 1,391 assets total 2,344,376,294 bytes; dumps are additional. Preserve VSWIR/TIR, s/u, weights, nulls and provenance. Three reference boreholes and new high-resolution downloads were excluded.

The proposed trial used a small supported db.t4g.micro/db.t3.micro instance, Single-AZ, gp3 starting at 20 GiB, same-region backend/S3, S3 Standard with versioning/SSE-S3 and seven-day RDS backups. These were historical options requiring account, region, cost and compatibility checks, not resources already created.

Source versions were PostgreSQL 17.4 / PostGIS 3.6.2. The consulted AWS table listed PostGIS 3.5.x for PostgreSQL 17 and 3.6.3 for PostgreSQL 18.4/18.3R2, making a stable PostgreSQL 18 target a candidate pending a trial restore. Use compatible major-version tools; retain the local verified backup. See [extension versions](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-extensions.html).

```text
payload/sha256/<first_two_chars>/<sha256>.parquet
payload/sha256/<first_two_chars>/<sha256>.jpg
archive/sha256/<first_two_chars>/<sha256>.<extension>
backups/<date>/<release_id>/database.dump
manifests/<batch_id>/asset_manifest.json
manifests/<batch_id>/upload_receipt.json
```

Keep asset identities/provenance in the database. Add backend=s3 locations with a configured root_key, relative object_key, original SHA256 and verified_remote only after verification. Receipts include target, VersionId, checksum type, size and time; credentials and expiring URLs stay outside the database. Cloud readers must not select unavailable local paths.

Planned sequence: freeze backup/manifest and budget; verify target extensions/permissions; provision restricted resources; upload one borehole then the remaining four; restore into an empty compatible database; register S3 replicas and compare data; independently restore a new cloud backup before handoff. The largest first-batch file was 247,284,576 bytes, suitable for a full-SHA256 single PUT. Different-content objects must not be overwritten.

Restore core using --no-owner/--no-acl and backup ordering without precreating all business tables or disabling constraints. Validate 30 tables, 261,892 samples, 583 logs, 54 foreign keys, 21 relationship checks and coverage for 1,391 assets. Use portable serialisation for cross-server value comparisons; raw textual hashes may differ with version/timezone. Expected location changes are checked separately.

Proposed, unimplemented scripts: 15_plan_aws_transfer.py, 16_prepare_aws_storage.py, 17_upload_s3_assets.py, 18_restore_rds_database.py and 19_verify_aws_delivery.py. Existing local steps 7-14 include cluster/runtime assumptions and cannot become cloud commands by replacing only the DSN.

Private access, least-privilege roles, TLS verify-full and retained version/backup manifests protect delivery. The backend owner implements S3 and Parquet access. Full-object checks differ from multipart composite checks, ETags and user-supplied metadata.

Budget includes instance hours, provisioned storage, backups, S3 requests/capacity/transfer and optional networking/credential services. Historical free-plan eligibility, credits and pause rules require account/current-documentation checks; this plan promises no free service or precise monthly fee. Measure later batches rather than multiplying five-borehole capacity by 400.
