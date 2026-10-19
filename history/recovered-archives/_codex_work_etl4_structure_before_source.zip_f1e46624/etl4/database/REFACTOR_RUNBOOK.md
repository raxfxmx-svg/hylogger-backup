# Refactored Pipeline Workflow

I separated preparation, import and acceptance, made inputs and source releases explicit, and allowed replay from sealed packages. Data rules determine revision identity; run times, environment details and verification code remain recorded separately. Existing migrations and business constraints are retained.

This runbook records the earlier base-then-media workflow. Run its stages in order in an independent workspace/database. Reference evidence is cached; use `--fetch-reference` only when it is missing. Review crop-boundary contact sheets before recording review. Multi-dataset ordering requires explicit decisions, and branch geometry is not inferred from dataset names.

Packages retain manifests and media evidence while referencing persistent raw/prepared assets. Imports and verification must use the same recorded source release. Same-input replay reuses revisions. Publication writes the release-specific asset manifest before switching the pointer, and checks the expected previous release. A failed dataset remains unpublished; completed work can resume from the same package.

Database acceptance does not require HTTP; `--check-api` enables the separate HTTP checks. Capacity measurements, fault injection, history comparisons and restore tests remain independent tools. Some examples create/write temporary test databases; they are not ordinary read-only checks. New inputs use actual sample ranges rather than the original five-hole counts, preserve repeated depths and source nulls, and retain full dataset ownership.

## Historical Commands and Examples

Use the paths, input packages and configuration for this snapshot. Run each stage only after its prerequisites pass. Upload, publication and cleanup commands are separate actions.

### Example 1

```powershell
$python = '.\etl4\database\.venv\Scripts\python.exe'
$env:ETL4_WORK_DIR = Join-Path (Get-Location) 'etl4\refactor_work'
$env:ETL4_DBNAME = 'etl4_refactor_check'
```

### Example 2

```powershell
& $python etl4/processing/1_inventory.py
& $python etl4/processing/2_validate_payloads.py
& $python etl4/processing/3_normalize_metadata.py
& $python etl4/processing/4_align_samples.py
& $python etl4/processing/5_build_columnar.py
& $python etl4/processing/6_verify_prepared_data.py
& $python etl4/database/7_preflight_database.py
& $python etl4/database/8_apply_schema.py
& $python etl4/database/9_import_prepared_data.py
& $python etl4/database/10_verify_database.py
```

### Example 3

```powershell
& $python etl4/database/20_audit_spectral_sources.py --source-release <BASE_RELEASE_ID>
& $python etl4/database/21_verify_spectral_bindings.py
& $python etl4/database/22_prepare_spectral_access.py
& $python etl4/database/23_audit_dataset_image_groups.py
& $python etl4/database/24_detect_image_rows.py
& $python etl4/database/25_review_image_row_regions.py
# Check the contact sheets before recording review; changed sheets require another check.
& $python etl4/database/25_review_image_row_regions.py --record-reviewed
& $python etl4/database/26_bind_image_rows_to_samples.py
& $python etl4/database/27_build_image_row_assets.py
& $python etl4/database/28_import_media_revision.py
& $python etl4/database/29_verify_media_grain.py
```

### Example 4

```powershell
& $python etl4/database/31_audit_multi_dataset_sources.py
& $python etl4/database/32_prepare_multi_dataset_payloads.py
& $python etl4/database/33_prepare_multi_dataset_media.py
# Run after checking the contact sheets:
& $python etl4/database/33_prepare_multi_dataset_media.py --record-reviewed
& $python etl4/database/34_import_multi_dataset_database.py --source-release <FIVE_HOLE_MEDIA_RELEASE_ID>
& $python etl4/database/35_verify_multi_dataset_database.py
```

### Example 5

```powershell
& $python etl4/database/28_import_media_revision.py --package <PACKAGE_DIRECTORY>
& $python etl4/database/29_verify_media_grain.py --package <PACKAGE_DIRECTORY> --release <MEDIA_RELEASE_ID> --no-activate
& $python etl4/database/34_import_multi_dataset_database.py --package <MULTI_DATASET_PACKAGE_DIRECTORY> --source-release <RECORDED_SOURCE_RELEASE_ID>
& $python etl4/database/35_verify_multi_dataset_database.py --package <MULTI_DATASET_PACKAGE_DIRECTORY> --release <COMPOSITE_RELEASE_ID>
```

### Example 6

```powershell
& $python -m unittest discover -s etl4/processing/tests
& $python -m unittest discover -s etl4/database/tests -p test_refactor.py
& $python -m unittest discover -s etl4/database/tests -p test_database_contracts.py
& $python etl4/database/tests/check_replays.py
& $python etl4/database/tests/measure_file_checks.py
& $python etl4/database/36_backup_multi_dataset_database.py --check-failures
```
