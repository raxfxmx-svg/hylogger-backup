# ETL4 Code Guide

Start with each numbered script's main() to follow the processing order, then read its ordinary business functions. This guide describes the code in this historical snapshot.

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
| `_settings.py` | Runtime directories, database settings and derived paths |
| `_db_common.py` | Database connections, identities, writes and migration checks |
| `_db_files.py` | JSON, file I/O and content digests |
| `_run_reports.py` | Run records, reports, commands and error reporting |
| `_prepared_inputs.py` | Read prepared manifests and check referenced files |
| `_media_manifest.py` | Compact shared dataset/frame metadata; read old and new manifests |
| `_media_rows.py` | Shared row detection and sample association |
| `_media_reader.py` | Batch selected-log indexes and asset queries for sample/media reads |

## Preparation and import

Step 32 checks sources, selects a dataset, checks reuse, saves source documents, validates, normalises, aligns samples, writes columnar data and saves results. Normalisation receives selected dataset metadata separately from complete source evidence, recording missing reasons and selection once. It calls ordinary processing modules directly.

The historical step 34 separates import_complete_datasets(), add_complete_segment(), import_dataset_media(), combine_release_members(), import_release() and save_import_result(). Its transaction covers samples, media, pending publication and display selections; failures roll back writes, record failure outside the transaction and release the lock. Later validation activates the release.

Batch selection starts at processing/0_check_raw.py, which separates single-dataset, multi-dataset and pending inputs. Step 1 records scope, steps 2-6 reuse it, and database steps use the step-7 manifest. Image direction follows the confirmed left-to-right source rule; crop layouts are checked separately.

The current route has two local gates: step 28 seals inputs and validates the prepared package; step 37 imports complete base/media revisions and performs the second validation. Use [LOCAL_BATCH_RUNBOOK.md](LOCAL_BATCH_RUNBOOK.md).

The retained step-28 import_batch() path commits datasets individually and creates the pending release after completion; historical step 34 retains a single transaction.

In this snapshot, _final_import.py owns the complete import/transaction/publication sequence through import_checked_batch() and run_final_import(). The latter records running/passed/failed second-gate state.

## Configuration and checks

StepParser parses full arguments once before configure(args). Imports do not parse CLI arguments; default directories resolve at call time. One process runs one selected configuration. load_or_record_source_release() makes source selection explicit. Reader signatures, processing rules and migrations remain stable.

_db_common.py retains compatibility exports for older tools; current numbered scripts import from the owning modules.

Media reruns return early after checking existing revisions/axes. Crop generation decodes each original once while retaining output order and PNG checks. Compact manifests share metadata; row algorithms are reused by steps 25/26/33. Readers filter selected logs before batching indexes and locations.

```powershell
$python = '.\etl4\database\.venv\Scripts\python.exe'
& $python -m unittest discover -s etl4/processing/tests
& $python -m unittest discover -s etl4/database/tests -p test_refactor.py
& $python -m unittest discover -s etl4/database/tests -p test_code_structure.py
& $python -m unittest discover -s etl4/database/tests -p test_database_contracts.py
```

Tests cover configuration timing, directory isolation, first-write metadata, rollback and duplicate publication members. Database integration tests require an actual test instance; offline batch tests use temporary files and substitute connections. Test success is separate from actual cloud delivery.

Related documents: [LOCAL_BATCH_RUNBOOK.md](LOCAL_BATCH_RUNBOOK.md), [STRUCTURE_CHANGE_REPORT.md](../../../../etl4_local_batch_20261003/code_before/etl4/database/STRUCTURE_CHANGE_REPORT.md), [REFACTOR_RUNBOOK.md](../../../../etl4_local_batch_20261003/code_before/etl4/database/REFACTOR_RUNBOOK.md), [MEDIA_STRUCTURE_REPORT_20260930.md](../../../../etl4_local_batch_20261003/code_before/etl4/database/MEDIA_STRUCTURE_REPORT_20260930.md).
