# Measured local database capacity

Database: 86,330,515 bytes; core tables and indexes: 68,911,104 bytes.
Empty database/PostGIS baseline: 16,174,227 bytes; total import increase: 70,156,288 bytes.

| File category | Logical files | Logical bytes | Bytes deduplicated by SHA256 |
|---|---:|---:|---:|
| canonical_payloads | 507 | 488,295,090 | 488,295,090 |
| processing_evidence | 50 | 9,808,782 | 9,808,782 |
| other_original_archive | 577 | 1,021,583,500 | 949,736,736 |
| tray_thumbnails | 249 | 4,889,146 | 4,889,146 |
| original_spectral_arrays | 8 | 819,799,776 | 819,799,776 |

Registered assets: 2,344,376,294 bytes. Canonical payloads and thumbnails: 493,184,236 bytes, excluding the complete source archive.

Database size already includes tables and indexes; do not add per-table totals again. WAL, exported backups, and object files are listed separately. The JSON report retains per-table counts, TOAST, indexes, query plans, and bounded-read measurements.
Current WAL directory size and cumulative temporary query bytes do not capture peak import usage. Initial SHA256 verification reads each entire file; the report lists that overhead separately.
No cloud platform selection, upload, or deployment was performed. Capacity for approximately 2000 boreholes still depends on actual sample, log, and image counts and version-retention policy.
