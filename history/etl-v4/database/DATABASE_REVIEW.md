# Database Relationships and Integrity Improvements

2026-09-08. Checked the five-borehole database and fixed three relationship gaps using migration [004_relational_integrity.sql](migrations/004_relational_integrity.sql): bulk sample checks for interval roles, parent trays, bounds and positions; an `(asset_id, verified_sha256)` foreign key; and `(log_id, asset_id)` links from image_frame/data_chunk to log_asset. Existing scientific records and migrations 001-003 stayed unchanged.

The 30-table model separates boreholes/revisions, datasets, sample axes, intervals, spectra, interpretations, files, provenance and releases. It contained 261,892 samples, 1,610 intervals, 583 logs, 23 interpretation groups, 1,391 assets, 6,777 row groups, 249 thumbnails, 70 source documents, 15 references and 75 issues. Branch, segment and survey extension tables were empty.

Compared 21,288 promoted source values and all 26 business-table digests. Checked 54 foreign keys and 21 relationship/state rules, with no invalid constraints, indexes or disabled triggers. Twelve database cases passed, including invalid inputs and legitimate duplicate depths/multi-dataset overlaps. A fresh five-borehole import matched 24 scientific tables; repeat imports skipped existing records. Backup restoration matched the 26 business tables, full schema and release. Reader roles retained SELECT only.

VSWIR has 531 channels for all five boreholes; TIR has 341 channels where available. The 62 mineral-weight logs remain non-probabilistic. Tray/Section logs use inclusive sample intervals. Profile observed_row_count NULL values do not imply absent profiles; data_chunk totals provide the checked counts. Historical JSON states remain source snapshots; current state comes from log_axis_binding and active_release.

| Storage measurement | Bytes |
|---|---:|
| Database before constraints | 86,330,515 |
| Database after constraints | 86,510,739 |
| Restored database | 81,030,291 |
| Compressed backup | 4,760,893 |

Added structures used 180,224 bytes. Release `20bbb134-501d-54bc-9428-5ee48b6801e4` and object files remained unchanged. The dump excludes external assets.

Use `13_audit_database.py` for read-only production checks plus temporary-database tests, and `14_verify_database_backup.py` for independent restoration. Reports: `13_database_audit_before.json`, `13_database_audit_after.json`, `13_full_import_new_constraints.json`, `14_database_only_restore.json` and `latest_database_backup.json` under `reports/`. These counts belong to this historical five-borehole baseline.
