# Cloud Batch Delivery and Cleanup Preview

2026-10-03. Completed S3 upload, PostgreSQL merge, explicit publication and repeat execution for 12 boreholes / 17 datasets. Reused the existing 39 tables and six migrations. The older five-borehole cloud API still required adaptation; these results establish storage/database delivery, not a deployed twelve-borehole website.

Step 40 consumes the public export and complete upload receipt using an explicit TLS-verified cloud DSN. It preserves numeric precision, NULL, UUID, arrays, JSON and SRID-bearing EWKB. Each dataset commits independently; identical records are reused and conflicting records rejected. Existing revisions remain. Publication requires `--finalize`, explicit members and the expected current release.

Step 39 supports SDK and CloudShell-signed uploads, 1-16 workers (default 1), per-worker TLS reuse and atomic main-thread receipts. Transient failures receive at most three attempts; 400/403 are not blindly retried, and 412 triggers HEAD verification. Signed uploads are limited to 5 GiB per file; larger files use SDK multipart. Signatures stay outside public manifests and logs. Fixed the first validation's required axis filename from `4_sample_axis.parquet` to the actual `4_sample_axis.npz`, retaining manifest/hash checks.

Local results: 221 offline tests passed in 31.525 seconds; 67 Python files parsed. All 17 datasets listed NPZ inputs; five first-gate reports and the second gate passed. Reruns reused all 17 versions. PostgreSQL staging loaded 29 tables and passed 510 conflict/parent queries; 17 collar geometries matched at SRID 4326. The read-only staging check rolled back all temporary tables in 15.969 seconds. First gates totalled 22.192 seconds; steps 37 and 38 took 84.186 and 18.115 seconds.

| Export | Recorded value |
|---|---:|
| Complete samples | 732,206 |
| Row images / spectral matrices | 4,738 / 31 |
| Asset identities / unique objects | 11,685 / 10,119 |
| Delivery files | 43; 20,339,471 bytes |
| Referenced unique large files | 7,731,122,300 bytes |

Batch ID: `8039f5a6c2c5711141bb201eaa1fb96636924d23c48faddd66edb782253519cd`. Manifest SHA256: `e8f404230838ba81fdea39b8fd57fcbddc2c285c7413b584d5a54d883ba348f5`. Export root: `etl4/single_final_check_20260930/database/exports/<batch_id>/`.

Actual upload confirmed 10,163 objects / 7,756,184,046 bytes. The final resumed run took 349.625 seconds, excluding earlier attempts. Refreshed CloudShell credentials resolved temporary-signature expiry. A suspended browser transfer was replaced by a same-bucket control-package transfer; its ZIP was 1,245,404 bytes.

| Cloud release | Before | After |
|---|---:|---:|
| Boreholes / datasets | 5 / 5 | 12 / 17 |
| Complete samples | 261,892 | 732,206 |
| Row images / spectra | 1,361 / 8 | 4,738 / 31 |
| Historical revisions | 10 | 27 |
| Applied migrations | 5 | 6 |

The current 3D selection contains 715,759 samples and every current asset has an S3 location. Historical scan_sample rows total 1,255,990. Explicit finalize switched release `fd02659c-dc3d-52ea-a8eb-c032b91e7624` to `292e1573-f868-5494-81a8-0f85bcdbb8ad`. Initial merge took 124.263 seconds. The 1.543-second rerun reused all members and preserved 29 business-table counts, the active release and four total releases. These timings describe different workloads.

Step 41 produced previews only: refactor_work 5,652 files / 1,435,799,599 bytes; new_input_check 872 / 155,185,051; structure_input_20260930 138 / 4,136,379. Total: 6,662 files / 1,595,121,029 bytes (about 1.486 GiB), comprising 4,738 PNGs and 1,924 Parquet files. Zero files were deleted. Raw/evidence, code, environments, databases, backups, reports, manifests and receipts remained protected.

Cleanup reference checks cover registered new-format exports, not all legacy database or unregistered references. Actual cleanup requires review of those references and serial execution while preparation/export is stopped; this version has no shared lock throughout deletion. Windows export ACL access and temporary receipt locks were also corrected without changing data identities.

See [LOCAL_BATCH_RUNBOOK.md](LOCAL_BATCH_RUNBOOK.md), [BATCH_FORMAT.md](BATCH_FORMAT.md) and [cleanup preview](../../working-snapshots/etl4_cloud_batch_20261003/CLEANUP_PREVIEW.md). Detailed receipts and snapshots are in `_codex_work/etl4_cloud_batch_20261003/`.
