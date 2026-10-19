# One Complete Version per Dataset

I added step 37 to import base records, images and spectra into one complete dataset revision. This removed the duplicate base/media storage of the earlier two-stage workflow while preserving historical versions when inputs or processing rules change. Each dataset commits independently; a failed dataset rolls back, completed datasets can resume, and the release switches only after the batch succeeds.

The 2026-09-30 evaluation used isolated `etl4_single_final_*` or `etl4_test_*` databases. Step 37 was an independent experimental entry point in this snapshot and had not yet replaced the default import workflow.

The initial eleven-hole comparison retained 16 datasets, 730,622 source samples, 4,726 row images, 29 spectral matrices and 714,175 selected 3D samples. Stored revisions fell from 32 to 16 and stored sample rows from 1,461,244 to 730,622. All source values, crop pixels, mappings and 3D selections matched. Adding 14CADD003 later produced 12 holes, 17 complete dataset revisions and 732,206 samples; see [the append results](FINAL_APPEND_14CADD003_REPORT.md).

An eleven-hole replay added no business records: 10,106 file-hash scans, about 7.97 GB read and 56.85 seconds. In a separate two-hole measurement, first import changed from 6.16 to 4.49 seconds, replay from 3.69 to 3.22 seconds, and stored samples from 65,928 to 32,964. Both workflows made 777 hash scans. These are local measurements.

Fault tests covered interrupted COPY, validation failure, manifest-write failure, resume, rule upgrades, conflicting output for the same identity, invalid crop provenance, cross-dataset logs, spectral dimensions and sample bounds. The 17,838,135-byte backup restored with matching tables, views, release pointer and counts. After compaction, database size was 218,918,035 bytes, reclaiming 88,875,008 bytes. External object files remain separate from the dump.

Prepare single datasets with 1–6, 7 `--inputs-only`, 20 `--files-only` and 21–27; prepare multi-dataset inputs with 31–33. Step 28 seals inputs and performs first acceptance. A batch JSON lists package directories, prepared work directories and confirmed multi-dataset ordering. Step 37 imports and checks the actual database content without requiring HTTP. Input identity uses preparation, media and final-mapping rules, not comments, timestamps or verification-code hashes.

Keep raw files, prepared files and sealed packages referenced by the manifest. Same-input replay reuses business records. Incremental batches explicitly name their source release; ordering is never inferred from directory names or depth alone.

Implementation: `37_import_final_version.py`, `_final_import.py`, `_media_verification.py`; isolated checks: `tests/check_final_flow.py` and `tests/measure_final_flow.py`. Detailed evidence is in `database/reports/final_reference_comparison.json`, `final_flow_failure_checks.json`, `final_flow_measurement.json` and `final_evaluation.json` under the recorded validation workspace.

## Historical Commands and Examples

Use the paths, input packages and configuration for this snapshot. Run each stage only after its prerequisites pass. Upload, publication and cleanup commands are separate actions.

### Example 1

```powershell
$python = '.\etl4\database\.venv\Scripts\python.exe'
& $python etl4/database/7_preflight_database.py --inputs-only --work-dir etl4/batch_final
& $python etl4/database/20_audit_spectral_sources.py --files-only --work-dir etl4/batch_final
# After completing steps 21–27:
& $python etl4/database/28_import_media_revision.py --package-only --work-dir etl4/batch_final
```

### Example 2

```json
{
  "packages": [
    {
      "directory": "batch_final/database/media_releases/PACKAGE_DIGEST",
      "prepared_work_dir": "batch_final"
    }
  ],
  "decisions": {"orders": {}}
}
```

### Example 3

```powershell
& $python etl4/database/37_import_final_version.py `
  --work-dir etl4/single_final_check_20260930 `
  --dbname etl4_test_single_final_20260930 `
  --batch etl4/single_final_check_20260930/batch.json
```
