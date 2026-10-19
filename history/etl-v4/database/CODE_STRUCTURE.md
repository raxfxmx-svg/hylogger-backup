# ETL4 Code Guide

Start with each numbered script's main() to follow the processing order, then read its ordinary business functions. This guide describes the code in this historical snapshot.

Metric display names use English and the preparation rule is v3; sealed earlier inputs retain their recorded rules. See [CODE_LANGUAGE_UPDATE_20261003.md](CODE_LANGUAGE_UPDATE_20261003.md).

## Modules

| File | Purpose |
|---|---|
| `processing/2_validate_payloads.py` | File-validation entry point |
| `processing/payload_validation.py` | Validate scalar, image, spectral and profile files |
| `processing/3_normalize_metadata.py` | Metadata-normalisation entry point |
| `processing/metadata_normalization.py` | Normalise boreholes, datasets, logs and source relationships |
| `processing/4_align_samples.py` | Sample-alignment entry point |
| `processing/sample_alignment.py` | Map sample numbers, depths, trays and Sections |
| `processing/5_build_columnar.py` | Columnar-output entry point |
| `processing/columnar_storage.py` | Write Parquet and verify readback |
| `database/32_prepare_multi_dataset_payloads.py` | Prepare each selected dataset through shared processing functions |
| `database/34_import_multi_dataset_database.py` | Import complete samples/media and create a pending release |
| `database/37_import_final_version.py` | Import complete revisions and record the second local validation |
| `database/38_export_batch.py` | Export validated batch records and asset manifests read-only |
| `database/39_upload_batch.py` | Upload or reuse manifest objects and save per-file receipts |
| `database/40_merge_cloud_batch.py` | Merge datasets, accumulate candidates and explicitly finalise publication |
| `database/41_cleanup_batch.py` | Preview eligible files and delete only with explicit execution |
| `_settings.py` | Runtime directories, database settings and derived paths |
| `_db_common.py` | Database connections, identities, writes and migration checks |
| `_db_files.py` | JSON, file I/O and content digests |
| `_run_reports.py` | Run records, reports, commands and error reporting |
| `_batch_files.py` | Shared batch format, table classes, content/path/receipt checks |
| `_s3_upload.py` | SDK checks, remote verification, conditional uploads and multipart cleanup |
| `_verification.py` | Validate dataset metadata, samples and assets |
| `_media_import.py` | Prepared packages, first validation, media identities and record writes |
| `_prepared_inputs.py` | Read prepared manifests and check referenced files |
| `_final_import.py` | Read complete inputs, map relationship IDs and import datasets |
| `_media_manifest.py` | Compact shared dataset/frame metadata; read old and new manifests |
| `_media_rows.py` | Shared row detection and sample association |
| `_media_reader.py` | Batch selected-log indexes and asset queries for sample/media reads |

## Preparation and import

Step 32 checks sources, selects a dataset, checks reuse, saves source documents, validates, normalises, aligns samples, writes columnar data and saves results. Normalisation receives selected dataset metadata separately from complete source evidence, recording missing reasons and selection once. It calls ordinary processing modules directly.

The historical step 34 separates import_complete_datasets(), add_complete_segment(), import_dataset_media(), combine_release_members(), import_release() and save_import_result(). Its transaction covers samples, media, pending publication and display selections; failures roll back writes, record failure outside the transaction and release the lock. Later validation activates the release.

Batch selection starts at processing/0_check_raw.py, which separates single-dataset, multi-dataset and pending inputs. Step 1 records scope, steps 2-6 reuse it, and database steps use the step-7 manifest. Image direction follows the confirmed left-to-right source rule; crop layouts are checked separately.

The current route has two local gates: step 28 seals inputs and validates the prepared package; step 37 imports complete base/media revisions and performs the second validation. Use [LOCAL_BATCH_RUNBOOK.md](LOCAL_BATCH_RUNBOOK.md).

Step 28 performs preparation only, with or without --package-only, and does not connect to a database. Step 37 owns imports. Legacy media/verification functions remain isolated in _legacy_media_import.py and _legacy_verification.py and are absent from the current upload collection.

In this snapshot, 37_import_final_version.py owns the complete import/transaction/publication sequence through import_checked_batch() and run_final_import(). The latter records running/passed/failed second-gate state.

release_plan() selects members, verify_final_dataset() records revision validation, and publish_final_batch() commits publication. _final_import.py retains input reading, relationship-ID mapping and dataset insertion.

## Batch delivery

Step 38 reads validation, fixes scope, streams table exports and writes the manifest. Step 39 uploads or reuses objects and saves receipts, using _s3_upload.py. _batch_files.py supplies shared format and atomic-file utilities.

CloudShell --sign-urls creates a private signing file; local --signed-urls consumes it with private path mappings. These modes are exclusive. Workers range from 1 to 16 (default 1); receipts are centralised and the manifest uploads last. Each worker reuses its own TLS connection. Transient failures receive at most three attempts; 400/403 return directly and 412 triggers HEAD. Logs/receipts omit private URLs and raw service messages.

Step 40 checks package/receipt/target structure, stages rows, commits each dataset and creates an accumulated candidate. Reuse identical records, reject conflicts and retain history. --finalize selects final members and atomically switches the expected active release. The target comes only from ETL4_CLOUD_DSN or an explicitly named ETL4_CLOUD_ variable. Existing local validation evidence is reused without a third full scientific recomputation.

Step 41 checks both complete receipts and registered-batch references, then writes cleanup_report.json. --apply rechecks and deletes individual listed files only. Explicit work/raw/export roots protect code, evidence, databases, backups and unfinished-batch references. Do not infer that an entire directory is disposable.

collect_cleanup_files() gathers by purpose, inspect_cleanup_files() deduplicates and classifies candidates/retained files/blockers, and cleanup_batch() keeps receipt checks, preview and explicit execution in order.

## Configuration and checks

StepParser parses full arguments once before configure(args). Imports do not parse CLI arguments; default directories resolve at call time. One process runs one selected configuration. load_or_record_source_release() makes source selection explicit. Reader signatures, processing rules and migrations remain stable.

Callers import utilities directly from their owning modules; _db_common.py no longer maintains compatibility re-export lists.

Media reruns return early after checking existing revisions/axes. Crop generation decodes each original once while retaining output order and PNG checks. Compact manifests share metadata; row algorithms are reused by steps 25/26/33. Readers filter selected logs before batching indexes and locations.

```powershell
$python = '.\etl4\database\.venv\Scripts\python.exe'
& $python -m unittest discover -s etl4/processing/tests
& $python -m unittest discover -s etl4/database/tests -p test_refactor.py
& $python -m unittest discover -s etl4/database/tests -p test_code_structure.py
& $python -m unittest discover -s etl4/database/tests -p test_database_contracts.py
& $python -m unittest discover -s etl4/database/tests -p 'test_batch_*.py'
```

Tests cover configuration timing, directory isolation, first-write metadata, rollback and duplicate publication members. Database integration tests require an actual test instance; offline batch tests use temporary files and substitute connections. Test success is separate from actual cloud delivery.

tests/check_batch_flow.py previews by default; --execute creates two temporary databases on local port 55433, runs export/merge SQL with in-memory S3 and verifies interrupted batches, recovery, reruns and missing earlier sources. Synthetic data checks software flow rather than NVCL scientific content.

Related documents: [CODE_LANGUAGE_UPDATE_20261003.md](CODE_LANGUAGE_UPDATE_20261003.md), [LOCAL_BATCH_RUNBOOK.md](LOCAL_BATCH_RUNBOOK.md), [CLOUD_BATCH_CHANGE_REPORT_20261003.md](CLOUD_BATCH_CHANGE_REPORT_20261003.md), [ETL_STRUCTURE_BATCH_REPORT_20261003.md](ETL_STRUCTURE_BATCH_REPORT_20261003.md), [STRUCTURE_CHANGE_REPORT.md](STRUCTURE_CHANGE_REPORT.md), [REFACTOR_RUNBOOK.md](REFACTOR_RUNBOOK.md), [MEDIA_STRUCTURE_REPORT_20260930.md](MEDIA_STRUCTURE_REPORT_20260930.md), [PUBLIC_MODULE_SIMPLIFICATION_20261003.md](PUBLIC_MODULE_SIMPLIFICATION_20261003.md).
