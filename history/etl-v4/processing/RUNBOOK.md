# Preparation Workflow and Results

The original 2026-09-07 run processed five boreholes: 05KCD001, 07THD002, 07THD003, 09ATD015 and 09ATD019. Steps 1–6 completed with `passed_with_known_limitations` and zero source-file integrity errors. The processing version prefix was `5dc45c0ef2a195bc`.

| Output | Recorded result |
|---|---|
| Raw files | 834; 1,846,272,422 bytes |
| Sample axes | 261,892 samples |
| Scalar logs | 497; 25,955,670 records |
| Parquet files | 507; 488,295,090 bytes |
| Associated thumbnails | 249 |
| Physical spectral arrays | 8; integrity checked, layout not yet confirmed in this phase |
| Metadata-only spectral records | 53 |
| Profilometer files | 5 |
| Retained repeated-depth samples | 28,103 |

Range queries matched independent source CSV reads and retained every repeated-depth sample. Replaying 05KCD001 produced identical SHA256 values for all 145 files under the same inputs, code and environment. Twelve boundary/regression tests covered null versus zero, categories, inclusive intervals, depth tolerance, large-batch sample identity and interrupted writes. This phase prepared files; it did not itself deploy the database or cloud service.

Run inventory, payload validation, metadata normalization, sample alignment, Parquet construction and verification in order. Stop on any nonzero exit. `latest_processing.json` may point to an incomplete run; only `latest_verified.json` identifies accepted output. Code/dependency changes in this original version required preparation from step 1. Later workflows are described separately in database/LOCAL_BATCH_RUNBOOK.md where present.

Scalar Parquet preserves source_row, sample_no, depth_m, inclusive sample ranges, value_numeric, value_text and value_raw. Raw text retains null tokens, empty strings, leading zeros and original numeric spelling. Files use 4,096-row groups and Zstandard compression in this snapshot. Float64 columns do not claim arbitrary decimal precision. Source arrays and thumbnails are retained; HTML mosaics are archived without execution.

Validation compares typed values, null masks and source order after Parquet readback. Image/sample depths use a 0.00001 m tolerance, without claiming pixel-level calibration. A Windows Arrow fill_null failure was caught by readback checks; independent value hashing and regression tests preserve nulls rather than replacing them with zero.

## Historical Commands and Examples

Use the paths, input packages and configuration for this snapshot. Run each stage only after its prerequisites pass. Upload, publication and cleanup commands are separate actions.

### Example 1

```powershell
Set-Location 'C:\path\to\project\etl4\processing'
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Example 2

```powershell
& .\.venv\Scripts\python.exe -X utf8 .\1_inventory.py --holes 05KCD001
& .\.venv\Scripts\python.exe -X utf8 .\2_validate_payloads.py --holes 05KCD001
& .\.venv\Scripts\python.exe -X utf8 .\3_normalize_metadata.py --holes 05KCD001
& .\.venv\Scripts\python.exe -X utf8 .\4_align_samples.py --holes 05KCD001
& .\.venv\Scripts\python.exe -X utf8 .\5_build_columnar.py --holes 05KCD001
& .\.venv\Scripts\python.exe -X utf8 .\6_verify_prepared_data.py --holes 05KCD001
```

### Example 3

```powershell
$pythonExe = '.\.venv\Scripts\python.exe'
$steps = @(
    '1_inventory.py',
    '2_validate_payloads.py',
    '3_normalize_metadata.py',
    '4_align_samples.py',
    '5_build_columnar.py',
    '6_verify_prepared_data.py'
)
foreach ($stepFile in $steps) {
    & $pythonExe -X utf8 $stepFile
    if ($LASTEXITCODE -ne 0) { throw "Processing stopped: $stepFile" }
}
```

### Example 4

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

### Example 5

```text
processing/outputs/
  <hole>/
    latest_processing.json
    <source_snapshot_prefix>/<pipeline_prefix>/
      1_inventory.json / .md
      2_integrity.json / .md
      2_profile_min_<source_log_id>.json
      3_normalized_metadata.json
      3_metadata_report.json / .md
      4_sample_axis.npz
      4_core_intervals.json
      4_image_frames.json
      4_axis_bindings.json
      4_alignment_report.json / .md
      5_canonical/
        scalars/<source_log_id>.parquet
        profiles/<source_log_id>.parquet
        sample_axis.parquet
      5_storage_report.json / .md
  verification/<pipeline_prefix>/6_all_five.json / .md
  latest_verified.json
  failures/
```
