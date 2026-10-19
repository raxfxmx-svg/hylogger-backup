# One Complete Version per Dataset

I added step 37 to import base records, images and spectra into one complete dataset revision. This removed the duplicate base/media storage of the earlier two-stage workflow while preserving historical versions when inputs or processing rules change. Each dataset commits independently; a failed dataset rolls back, completed datasets can resume, and the release switches only after the batch succeeds.

The initial 2026-09-30 evaluation used an isolated test database. On 2026-10-03, step 37 became the new batch entry point after step 28's first local acceptance; see [the batch runbook](LOCAL_BATCH_RUNBOOK.md). Earlier test commands below describe their original snapshot.

The initial eleven-hole comparison retained 16 datasets, 730,622 source samples, 4,726 row images, 29 spectral matrices and 714,175 selected 3D samples. Stored revisions fell from 32 to 16 and stored sample rows from 1,461,244 to 730,622. All source values, crop pixels, mappings and 3D selections matched. Adding 14CADD003 later produced 12 holes, 17 complete dataset revisions and 732,206 samples; see [the append results](FINAL_APPEND_14CADD003_REPORT.md).

An eleven-hole replay added no business records: 10,106 file-hash scans, about 7.97 GB read and 56.85 seconds. In a separate two-hole measurement, first import changed from 6.16 to 4.49 seconds, replay from 3.69 to 3.22 seconds, and stored samples from 65,928 to 32,964. Both workflows made 777 hash scans. These are local measurements.

Fault tests covered interrupted COPY, validation failure, manifest-write failure, resume, rule upgrades, conflicting output for the same identity, invalid crop provenance, cross-dataset logs, spectral dimensions and sample bounds. The 17,838,135-byte backup restored with matching tables, views, release pointer and counts. After compaction, database size was 218,918,035 bytes, reclaiming 88,875,008 bytes. External object files remain separate from the dump.

Prepare single datasets with 1–6, 7 `--inputs-only`, 20 `--files-only` and 21–27; prepare multi-dataset inputs with 31–33. Step 28 seals inputs and performs first acceptance. A batch JSON lists package directories, prepared work directories and confirmed multi-dataset ordering. Step 37 imports and checks the actual database content without requiring HTTP. Input identity uses preparation, media and final-mapping rules, not comments, timestamps or verification-code hashes.

Keep raw files, prepared files and sealed packages referenced by the manifest. Same-input replay reuses business records. Incremental batches explicitly name their source release; ordering is never inferred from directory names or depth alone.

Implementation: `37_import_final_version.py`, `_final_import.py`, `_media_verification.py`; isolated checks: `tests/check_final_flow.py` and `tests/measure_final_flow.py`. Detailed evidence is in `database/reports/final_reference_comparison.json`, `final_flow_failure_checks.json`, `final_flow_measurement.json` and `final_evaluation.json` under the recorded validation workspace.
