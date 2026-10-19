# ETL4 Refactoring Results

Refactored 31 numbered scripts and 13 shared modules using explicit imports and ordinary functions. Added `_settings.py` for runtime configuration, `_file_checks.py` for within-check hash reuse and run records, and `_publication.py` for publication ordering. Used separate `etl4/refactor_work` and `etl4_refactor_check`, retaining old databases, outputs and backups. Six migration hashes, 39 tables, two views and reader interfaces stayed unchanged.

Data identities now depend on explicit rules, source content, dataset evidence and parameters. Source-code bytes, timestamps and interpreter versions are run metadata. Per-dataset metadata/payload projections avoid changes caused by unrelated members. Sealed packages preserve their rules and small source documents; large files remain referenced. Same identity with different content is rejected.

Publication checks nonempty members, manifest agreement, matching validation and file contents. It writes the release-specific asset manifest before switching the active pointer transactionally. Full validation reports remain historical; latest pointers may update. HTTP checks in steps 10-12 require `--check-api`. See [VALIDATION_POLICY.md](VALIDATION_POLICY.md).

Full old/new comparisons matched eight boreholes, thirteen datasets, 654,778 samples, 4,160 row images, 24 spectra and 638,331 display samples. Compared 1,492 Parquet files / 74,965,515 rows, 2,643 source files, all crop pixels, spectral blocks and display selections by source identity. New release: `707bbb9e-6e0a-50f9-9638-96cb13a6daf3`.

05KCD001 preparation replay preserved 145 files in 94.831 seconds. Replays with media_work/multi_work temporarily unavailable reused sealed packages, adding zero business records and retaining 26 revisions / three releases. Recorded seconds for steps 9/28/29/34/35: 3.082 / 9.675 / 23.031 / 40.873 / 62.753. Tests passed: 12 preparation, 17 refactor, 17 integration, 19 media and five display-selection cases.

Within-check path deduplication reduced SHA256 scans 9,890→8,652 and bytes 11,171,234,132→7,229,984,809, with 1,238 cache hits. Time was 18.018→18.375 seconds, so no speedup was demonstrated. Cache results are not reused across runs.

Step 36 independently restored and compared 35 business tables, schema, views and release. Backup size: 28,124,073 bytes; SHA256 `20668d5efc5cc2872402fae557ff96e3ca4166a232109467a4578fa5c8d54e6a`. External files are still required. Static checks passed for 47 source files and 31 CLI entry points. Reports are under refactor_work/database/reports and `_codex_work/etl4_refactor/`; see [REFACTOR_RUNBOOK.md](REFACTOR_RUNBOOK.md).
