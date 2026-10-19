# Initial Local Database Delivery

2026-09-08. Built the five-borehole PostgreSQL 17.4 / PostGIS 3.6.2 database at `127.0.0.1:55432`, database `etl4_core`. The initial release was `20bbb134-501d-54bc-9428-5ee48b6801e4`. Later media work is documented in [MEDIA_DELIVERY.md](MEDIA_DELIVERY.md); this file preserves the first delivery baseline.

The 30 tables contain 261,892 samples, 583 logs (497 scalar), 6,777 Parquet row-group indexes, 1,610 tray/section intervals and 249 thumbnail links. Registered assets: 834 raw files, 507 Parquet files and 50 evidence files, totalling 1,391. Source/normalised metadata, s/u, VSWIR/TIR, original weights, NULLs and known issues were retained.

Seventeen integration tests passed, covering repeat imports, COPY rollback, concurrency, cross-dataset/axis constraints, reader permissions, historical releases and failed-validation publication. All samples, metadata, hashes and row-group indexes were checked; representative HTTP reads matched CSV, profile and image bytes. Independent backup restoration passed. Migration 004 later added relationship checks; see [DATABASE_REVIEW.md](DATABASE_REVIEW.md).

| Database storage | Bytes |
|---|---:|
| Running database | 86,330,515 |
| Included core tables/indexes | 68,911,104 |
| Empty database/PostGIS baseline | 16,174,227 |
| Restored database | 79,916,179 |
| Compressed dump | 4,755,097 |

| External objects | Files | Bytes |
|---|---:|---:|
| Parquet | 507 | 488,295,090 |
| Tray thumbnails | 249 | 4,889,146 |
| Raw spectral F32 | 8 | 819,799,776 |
| Other raw archives | 577 | 1,021,583,500 |
| Evidence | 50 | 9,808,782 |

Total registered assets: 2,344,376,294 bytes; theoretical SHA256-deduplicated size: 2,272,529,530 bytes. Parquet plus thumbnails: 493,184,236 bytes. No object deduplication or upload was performed. Dumps exclude external objects.

Representative 0.5 m queries read one Parquet row group; wider requests paginate at 5000 rows and read two groups in the measurement. Initial SHA256 checks read full files; later cached checks permit partial reads. Operating-system caches were not cleared. At 0.1-second sampling, WAL directory peak was 117,440,512 bytes and WAL growth 85,398,744 bytes; observed temporary-file peak was zero.

scan_sample plus indexes occupied 60,030,976 bytes, about 229.2 bytes/sample. Sensitivity estimates for 10/50/100 million samples are 2.29/11.46/22.92 GB for that component only. These are not forecasts for 2000 boreholes and exclude other tables, files, history, backups and working space.

See [README](README.md), [schema dictionary](schema_dictionary.md), [source mapping](source_to_table_mapping.md), [architecture](architecture.md) and [API contract](api_contract.md). Detailed results are in reports/11_capacity_after_restore.json, deployment_asset_manifest.json, latest_verified_database.json, tests_latest.txt, 12_restore.json and delivery_manifest.json. The local reader used a read-only role and localhost port 58000. No cloud deployment occurred in this iteration.
