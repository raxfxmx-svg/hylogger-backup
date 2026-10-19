# Read-Only AWS Delivery Plan

2026-09-12. Planned a fixed five-borehole, read-only deployment using RDS PostgreSQL and S3, preserving the existing 36-table model. New indicators, online imports and additional version/publication machinery were deferred. No business code, database or cloud resource was changed in this iteration.

Verified all 2,810 unique files: 2,400,546,756 bytes with matching sizes/SHA256. The 10,240,368-byte dump matched its pointer and companion manifest; migrations 001-005 matched. Offline pg_restore parsing confirmed 36 tables and 261,892 current samples. Local database connection timed out, so changes since the backup were not ruled out.

Current media: 249 tray JPGs, 1,361 official row PNGs and eight spectra. Object breakdown: 1,610 tray/row images about 35.74 MB; 507 Parquet about 488.30 MB; eight F32 about 819.80 MB; 502 CSV/JSONL about 1,020.67 MB; 183 other metadata/evidence files about 36.05 MB. Total PNG count 1,364 includes three evidence images.

1. Fix release `fd02659c-dc3d-52ea-a8eb-c032b91e7624` and pair the latest backup with its asset manifest. The old latest_verified_database pointer refers to the pre-media release.
2. Upload only manifest files as `data/<original_relative_key>` to private S3. Exclude runtime, pgdata, local configuration, environments, old outputs and reference boreholes.
3. Prepare a compatible empty RDS database with public.postgis and core, then restore using `--schema=core --no-owner --no-acl --single-transaction --exit-on-error`. Verify target extension compatibility and TLS with the official CA.
4. Register 3,042 asset locations for 2,810 unique objects. Mark verified_remote only after remote checks. Grant everyday accounts CONNECT, schema USAGE and SELECT without business-write/owner privileges.

Application integration remains separate: `_db_common.py` reads local configuration before its environment DSN, `_media_reader.py` reads local objects only, and the old HTTP API does not expose the completed sample spectra. Adapters must read S3 Parquet/F32/images and work without the original computer.

Validate 261,892 current samples, 1,361 row images and eight arrays; the historical table's 523,784 rows include both revisions. Compare object keys, sizes and full hashes, test read-only permissions and inspect real sample/file reads. A healthy endpoint alone does not validate media. See [manual upload guide](../AWS_MANUAL_UPLOAD_GUIDE.md), asset_audit.json and backup_audit.json. This historical plan does not establish a tested RDS version combination or completed remote deployment.
