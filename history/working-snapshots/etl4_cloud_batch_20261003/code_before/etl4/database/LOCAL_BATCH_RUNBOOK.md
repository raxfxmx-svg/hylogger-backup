# Local Batch Workflow

I separated file preparation from database import so each batch fits local storage and retains two explicit acceptance records. Single-dataset inputs use 1–6, 7 `--inputs-only`, 20 `--files-only` and 21–27; multi-dataset inputs use 31–33. Step 28 seals and checks each preparation package. Step 8 applies the existing schema, and step 37 imports complete dataset revisions and performs the second acceptance before publishing the batch.

Set raw/work roots, database name and connection configuration explicitly. Raw and work roots must not overlap. Root keys locate files without changing dataset identity. Keep the same roots for preparation, acceptance and export. Step 0 only checks manifests, existence and size: exit 0 is clear, 1 reports empty categories, and 2 reports alerts or incomplete checks. Select the actual batch rather than processing the entire raw directory automatically.

Source depth increases left to right. Review the generated crop-boundary contact sheets before recording review. `--fetch-reference` retrieves missing official spectral evidence; cached evidence can be reused. Multi-dataset display order requires confirmed `decisions.orders`. Each package needs its first acceptance; step 37 checks that evidence against actual inputs before database access. It verifies samples, depths, log ownership, crop pixels and spectral layout. Failed datasets roll back; completed datasets remain resumable. Same inputs and rules reuse business versions. HTTP is not required.

The batch JSON explicitly lists sealed packages, preparation workspaces and display decisions. Incremental imports explicitly record their source release. Failure updates the latest acceptance state; an older successful report is not evidence for a failed run. If database commit succeeds but report writing fails, fix the file problem and rerun the same batch.

Step 38 exports the second acceptance scope as 29 business tables, 39 schema definitions, migrations and evidence. Large assets stay in place; private `local_sources.json` maps them for upload. Step 39 verifies local SHA256 and remote full-object checksums, writes resumable receipts, and uploads the manifest last. Keep the source files until delivery and retention requirements are resolved.

Cloud merge and cleanup were not part of the implemented entry points shown in this snapshot. Follow its recorded commands and results rather than assuming later cloud features were already present.

## Historical Commands and Examples

Use the paths, input packages and configuration for this snapshot. Run each stage only after its prerequisites pass. Upload, publication and cleanup commands are separate actions.

### Example 1

```powershell
$python = '.\etl4\database\.venv\Scripts\python.exe'
$env:ETL4_RAW_DIR = 'D:\100demo\data\raw'
$env:ETL4_WORK_DIR = 'D:\etl4_work\batch_001'
$env:ETL4_DBNAME = 'etl4_local_batch_001'
# Reuse the existing local instance configuration.
$env:ETL4_DB_CONFIG = (Resolve-Path 'etl4/refactor_work/database/runtime/local_config.json').Path
$work = $env:ETL4_WORK_DIR
```

### Example 2

```powershell
& $python etl4/processing/0_check_raw.py
```

### Example 3

```powershell
& $python etl4/processing/1_inventory.py --holes 09ATRCD025 12BRDDH003
& $python etl4/processing/2_validate_payloads.py
& $python etl4/processing/3_normalize_metadata.py
& $python etl4/processing/4_align_samples.py
& $python etl4/processing/5_build_columnar.py
& $python etl4/processing/6_verify_prepared_data.py
& $python etl4/database/7_preflight_database.py --inputs-only
& $python etl4/database/20_audit_spectral_sources.py --files-only
& $python etl4/database/21_verify_spectral_bindings.py --fetch-reference
& $python etl4/database/22_prepare_spectral_access.py
& $python etl4/database/23_audit_dataset_image_groups.py
& $python etl4/database/24_detect_image_rows.py
& $python etl4/database/25_review_image_row_regions.py
# Record review only after checking the generated crop-boundary contact sheets:
& $python etl4/database/25_review_image_row_regions.py --record-reviewed
& $python etl4/database/26_bind_image_rows_to_samples.py
& $python etl4/database/27_build_image_row_assets.py
& $python etl4/database/28_import_media_revision.py --package-only
$singlePackage = (Get-Content "$work/database/reports/28_media_package.json" -Raw | ConvertFrom-Json).package_object_key
```

### Example 4

```powershell
& $python etl4/database/31_audit_multi_dataset_sources.py --holes 12CADD001 --fetch-reference
& $python etl4/database/32_prepare_multi_dataset_payloads.py
& $python etl4/database/33_prepare_multi_dataset_media.py --fetch-reference
# After checking the multi-dataset crop-boundary contact sheets:
& $python etl4/database/33_prepare_multi_dataset_media.py --record-reviewed
& $python etl4/database/28_import_media_revision.py --package-only `
  --media-work-dir "$work/database/multi_work/media" `
  --evidence-dir "$work/database/multi_work/evidence"
$multiPackage = (Get-Content "$work/database/reports/28_media_package.json" -Raw | ConvertFrom-Json).package_object_key
```

### Example 5

```powershell
$batch = @{ packages = @(@{ directory = $singlePackage; prepared_work_dir = $work }) }
# For a mixed batch, add $multiPackage and the confirmed display decisions:
# $batch.packages += @{ directory = $multiPackage; prepared_work_dir = $work }
# $batch.decisions = Get-Content 'confirmed_batch_decisions.json' -Raw | ConvertFrom-Json
$batch | ConvertTo-Json -Depth 10 | Set-Content "$work/batch.json" -Encoding utf8
& $python etl4/database/8_apply_schema.py
& $python etl4/database/37_import_final_version.py --batch "$work/batch.json"
```

### Example 6

```powershell
& $python etl4/database/38_export_batch.py `
  --acceptance "$work/database/reports/local_acceptance_2.json" `
  --output-dir "$work/database/exports"
if ($LASTEXITCODE -ne 0) { throw 'Batch export failed' }
```

### Example 7

```powershell
& $python -m pip install --upgrade -r etl4/handoff/requirements-aws.txt
# Use normal AWS SDK credential configuration, such as AWS_PROFILE; keep keys outside the batch package.
$exportDir = 'FULL_EXPORT_DIRECTORY_FROM_STEP_38'
& $python etl4/database/39_upload_batch.py --export-dir $exportDir `
  --bucket 'YOUR_BUCKET' --region 'YOUR_AWS_REGION' --prefix 'etl4'
if ($LASTEXITCODE -ne 0) { throw 'Upload incomplete; fix the error and rerun the same command' }
```
