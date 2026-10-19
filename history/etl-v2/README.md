# ETL2: NVCL Downloads and Readable CSVs

This version performs two tasks:

1. Download raw NVCL data with Python.
2. Organise raw data into clearly named CSVs that open directly in Excel.

**This version produces CSVs without SQLite, PostgreSQL, workbooks or a separate field dictionary.**

## Run

```powershell
cd C:\path\to\project\etl2
python -m pip install -r requirements.txt
python run.py 05GJD001 --provider wa --verify
```

List multiple boreholes in `holes.csv`:

```csv
hole_id
05GJD001
another_borehole_id
```

Then run:

```powershell
python run.py --holes-file holes.csv --provider wa --verify
```

Download one borehole at a time by default; use `--workers 2` for two concurrent downloads.

## Run stages separately

Download only:

```powershell
python download.py 05GJD001 --provider wa
```

Generate CSVs only:

```powershell
python etl.py 05GJD001
```

Validate CSVs:

```powershell
python verify.py
```

## Output locations

Outputs in `etl2/data/csv/` use five logical tables:

```text
data/csv/
├── holes.csv
├── measurements/
│   └── 05GJD001.csv
├── core_intervals/
│   └── 05GJD001.csv
├── signals/
│   └── 05GJD001.csv
└── assets/
    └── 05GJD001.csv
```

Partition files by borehole to avoid a single CSV of hundreds of GB. The logical model contains five tables.

### 1. `holes.csv`

One row per borehole records coordinates, depth, drilling information, sample and measurement counts, section count and download status.

### 2. `measurements/<borehole_id>.csv`

One row per sample, with four fixed leading columns:

```text
hole_id, sample_no, depth_from_m, depth_to_m
```

Populated scalar measurements such as `Albedo` and `SNR sTSAV` follow the fixed columns. Merge identical logs, omit all-null columns and use measurement names directly as headers.

### 3. `core_intervals/<borehole_id>.csv`

One row per core section combines tray and section numbers, sample ranges, physical depths, tray depths and thumbnail paths.

### 4. `signals/<borehole_id>.csv`

Spectra and profilometer records share one table:

- One row per signal sample.
- `signal_name` distinguishes Reflectance, Base Refl and other signals.
- `signal_type` distinguishes spectrum and profilometer.
- Use wavelength columns such as `wl_380_nm`.
- Retain status rows for metadata-only and explicitly unavailable signals.

This table is large because it contains complete spectral values.

### 5. `assets/<borehole_id>.csv`

Record tray thumbnails, mosaics, high-resolution images and per-sample imagery. Store paths for available files and mark unsupported WA imagery as `unavailable`.

## Raw download layer

Raw data location:

```text
etl2/data/raw/<borehole_id>/
```

UUID filenames remain in the raw layer for provenance and resumable downloads; final CSV filenames use borehole IDs.

The downloader handles:

- Borehole and dataset metadata
- All scalar logs
- Spectral binaries
- Profilometer data when provided
- Tray thumbnails, mosaics, high-resolution images and imagery when provided

Resume spectra through `.part` files and verify byte counts and SHA-256. Missing upstream endpoints produce warnings.

## Current 05GJD001 outputs

| CSV | Result |
|---|---:|
| `holes.csv` | 1 row |
| `measurements/05GJD001.csv` | 25,938 rows and 106 measurements |
| `core_intervals/05GJD001.csv` | 198 rows |
| `signals/05GJD001.csv` | 51,890 rows, including two complete spectral series |
| `assets/05GJD001.csv` | 36 rows |

WA did not return profilometer, high-resolution tray or per-sample imagery, so these remain `unavailable` in the CSVs.
