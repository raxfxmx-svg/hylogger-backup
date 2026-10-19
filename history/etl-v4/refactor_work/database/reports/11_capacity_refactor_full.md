# Measured local database capacity

Database: 574,975,123 bytes; core tables and indexes: 556,908,544 bytes.
Empty database/PostGIS baseline: 16,174,227 bytes; total import increase: 558,800,896 bytes.

| File category | Logical files | Logical bytes | Bytes deduplicated by SHA256 |
|---|---:|---:|---:|
| canonical_payloads | 5652 | 1,435,799,599 | 1,435,799,599 |
| processing_evidence | 1595 | 4,554,233,761 | 606,305,664 |
| other_original_archive | 1674 | 2,975,040,358 | 2,749,949,202 |
| tray_thumbnails | 945 | 15,974,270 | 15,974,270 |
| original_spectral_arrays | 24 | 2,190,186,144 | 2,190,186,144 |

Registered assets: 11,171,234,132 bytes. Canonical payloads and thumbnails: 1,451,773,869 bytes, excluding the complete source archive.

Database size already includes tables and indexes; do not add per-table totals again. WAL, exported backups, and object files are listed separately. The JSON report retains per-table counts, TOAST, indexes, query plans, and bounded-read measurements.
Current WAL directory size and cumulative temporary query bytes do not capture peak import usage. Initial SHA256 verification reads each entire file; the report lists that overhead separately.
No cloud platform selection, upload, or deployment was performed. Capacity for approximately 2000 boreholes still depends on actual sample, log, and image counts and version-retention policy.
