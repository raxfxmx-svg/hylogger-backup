# ETL Structure and Batch Validation

2026-10-03. Moved the complete dataset transaction, validation and publication sequence into `37_import_final_version.py`, with ordinary helpers for release members, dataset validation and batch publication. `_final_import.py` retains input reading, ID mapping and dataset insertion; three business functions remained AST-equivalent and the rule stayed `single-final-v1`. Step 41 now separates collection, deduplication and candidate checks. SQL, views, arguments and package formats stayed unchanged.

224 offline tests passed in 31.594 seconds with zero failures/errors/skips and zero database/network attempts. Tests covered upload reuse, multipart cancellation, manifest ordering, refreshed signatures, transient errors, connection failures and receipt-write failures. All 63 processing/database Python files parsed; hashes for 29 migrations/cloud_api/deployment files remained unchanged.

A separate PostgreSQL test on port 55433 used two temporary databases, six migrations, two synthetic boreholes, three datasets, nine samples and three assets; the final display selected seven samples. Export/merge/publication passed, including unavailable prior-batch sources, incomplete-hole rejection, dataset rollback/recovery, partial-receipt cleanup refusal and incorrect-finalize rollback. Replays preserved all 39 table digests and added no S3 PUT. Runtime: 4.625 seconds; mocked S3 calls: 83 PUT, 207 HEAD, 0 GET. Both test databases were removed.

A real 14CADD003 prepared package was imported into a new test database, then replayed with old and new entry points. All runs passed: one dataset, 1,584 samples, 12 row images and two spectra. Both reruns returned `already_present`, preserving 35 business-table digests, identities, members and active release; only run/validation records updated.

| Run | SHA256 scans | Bytes read | Seconds |
|---|---:|---:|---:|
| New initial import | 324 | 19,960,627 | 2.082 |
| Old rerun | 324 | 19,967,453 | 1.257 |
| New rerun | 324 | 19,960,627 | 1.237 |

Both reruns had 790 within-check cache hits. These small-case measurements do not establish general speedups. Dataset revision remained `984f74b7-3ba5-5d14-bf9d-9f8f783d1506`; test release `f7bcf5b1-504c-5026-b4c6-a9741aae73ac` was local only. An initial test-report path error stopped before database creation and was fixed in the test helper.

Evidence is under `_codex_work/etl4_structure_batch_20261003/`, including offline_suite.json, batch_flow/flow20261003/report.json, local_37_old_new_validation.json and code_integrity_review.json. Existing business databases, source data and delivery assets were unchanged. No actual cleanup, AWS write or API deployment ran. See [runbook](LOCAL_BATCH_RUNBOOK.md) and [code structure](CODE_STRUCTURE.md).
