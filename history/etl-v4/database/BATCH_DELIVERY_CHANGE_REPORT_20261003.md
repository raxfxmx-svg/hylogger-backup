# Independent Batch Export and S3 Upload

2026-10-03. Added step 38 to export complete boreholes from the second local validation, and step 39 to upload only manifest objects. See [LOCAL_BATCH_RUNBOOK.md](LOCAL_BATCH_RUNBOOK.md) and [BATCH_FORMAT.md](BATCH_FORMAT.md).

Exports contain 29 compressed JSONL business tables, classifications for all 39 tables, six unchanged migrations and both validation bindings. They preserve UUIDs, values and relationships. Public manifests contain asset identities, hashes, sizes and object keys; private `local_sources.json` retains local paths. Large assets are referenced rather than copied, and identical content shares storage while retaining separate asset identities.

Read-only snapshot exports stream through server-side cursors. Re-exporting identical business content reuses the package; conflicting content under the same identity is rejected. Step 39 reuses the shared handoff uploader, conditional writes, multipart transfers and atomic partial/complete receipts. It compares local SHA256 and S3 full CRC32/size through HEAD, then uploads the manifest last. Private mappings are excluded.

146 offline tests passed in about 15.48 seconds, including 61 batch tests (16 manifest, 14 export, 31 upload); 65 Python files parsed successfully. Tests covered scope, tampering, repeat runs, conflicts and failed receipt/export writes using temporary files, mock databases and mock S3. No actual database export, S3 upload or twelve-borehole processing ran in this iteration. Cloud merge and local cleanup were still pending.

Evidence: `_codex_work/etl4_batch_delivery_20261003/` contains `code_before`, `changed_files.json`, `offline_validation.json`, `offline_test_output.txt` and `run_offline.py`.
