# Database Review and Recovery Tools

This historical grouping preserves review and restore tools with their shared dependencies. Merge its `etl4/` tree into the main tree before use. Preparing this source grouping did not run database or cloud operations.

- `13_audit_database.py`: relationships and schema checks, plus older preparation-ID source checks. Its main routine is not automatically compatible with step 37's remapped final versions.
- `14_verify_database_backup.py`: current-release backup and independent restore checks. It reuses structural checks from 13, not its older source-check main routine.
- `30_audit_media_database.py`: media review and fault cases in a restored copy; retains old asset-root and 28/34 report assumptions.
- `36_backup_multi_dataset_database.py`: restore comparison based on 35_verification.json; optional failures also depend on 34_import.json and the three original multi-dataset holes. Step 37 does not generate those old reports.
- `29_verify_media_grain.py`, `35_verify_multi_dataset_database.py`, `_trial_support.py`, `_media_tests.py`, `_multi_reader.py`: dependencies for the selected tools.

These older assumptions require adaptation before using the group as a generic new-batch review tool. Keep backups and referenced external assets together; do not fabricate missing old reports.
