# NVCL Borehole Data ETL

This Python ETL has three stages:

1. **Extract**: download NVCL borehole metadata, scalar logs, spectral binaries, tray thumbnails and available imagery.
2. **Transform**: align logs by sample and depth, deduplicate identical sources, preserve field provenance, and join trays and sections to physical depth.
3. **Load**: write six readable CSV/SQLite tables and a workbook for quick browsing.

Keep UUID source files in `raw/` for provenance. Record unavailable upstream data as `unavailable`.

## Quick start

```bash
cd etl
python -m pip install -r requirements.txt
python run.py 05GJD001 --provider wa
```

Run the two stages separately:

```bash
python download.py 05GJD001 --provider wa
python load.py 05GJD001
```

- `download.py` downloads and resumes transfers.
- `load.py` joins, names and deduplicates data, then writes CSV and SQLite.
- `run.py` runs both steps and reports table row counts.
- `--out <directory>` sets the data root; default: `etl/data`.
- `--cache <directory>` sets the HTTP cache; default: `<out>/.cache`.

## Outputs: six business tables

Outputs are in `data/readable/<borehole_id>/` and SQLite in `data/<borehole_id>.sqlite`. CSV uses UTF-8 BOM for Excel.

| File / SQLite table | Row meaning | Purpose |
|---|---|---|
| `01_hole_summary.csv` / `hole_summary` | One borehole | Coordinates, depth range, data volume, download status and ETL summary |
| `02_measurements.csv` / `measurements` | One sample | `sample_no + depth_m` followed by populated scalar measurements |
| `03_measurement_dictionary.csv` / `measurement_dictionary` | One readable field | Field name, original log name, type, source UUID, file and deduplication notes |
| `04_core_layout.csv` / `core_layout` | One core section | Tray, section, sample range, physical depth range and thumbnail path |
| `05_spectrum_reflectance.csv` / `spectrum_reflectance` | One sample | Reflectance from 380-2500 nm, one column per wavelength |
| `06_spectrum_base_refl.csv` / `spectrum_base_refl` | One sample | Base reflectance from 6000-14500 nm, one column per wavelength |

`05GJD001_readable.xlsx` provides an overview, complete field dictionary and core layout, plus representative scalar and spectral samples. Full tables remain in CSV and SQLite to keep the workbook responsive.

## Joining rules

### 1. Combine scalar logs into `measurements`

- Align the common axis of 25,938 samples by `sample_no`.
- Preserve `depth_from_m` and `depth_to_m`, expanding the remaining logs into readable columns.
- Normalise source log names into field names, including lowercase and underscores.
- Preserve different logs with the same name using suffixes such as `final_mask_1` and `final_mask_2`.
- Store identical logs once and retain every source UUID in the field dictionary.
- All-null logs appear in the dictionary as `all_null_omitted` without empty main-table columns.

### 2. Join trays and sections into `core_layout`

- Source `Tray` and `Section` bounds are sample numbers, not physical depths.
- Join by sample number, then derive `depth_from_m` and `depth_to_m`.
- Each section includes its tray number, tray interval and thumbnail path for visual traceability.

### 3. Expand spectra into analysis tables

- Decode `.f32` as little-endian `float32`.
- One row per sample and one column per wavelength, such as `wl_380_nm`.
- Preserve sample numbers and depths for joins to `measurements` on `sample_no`.

## Directory structure

```text
etl/
├── download.py
├── load.py
├── run.py
├── requirements.txt
└── data/
    ├── .cache/                         HTTP cache
    ├── raw/<borehole_id>/              Source provenance, including UUID files
    │   ├── scalars/*.csv
    │   ├── spectral/*.f32
    │   ├── images/
    │   ├── mosaics/
    │   └── *_manifest.json
    ├── readable/<borehole_id>/         Readable outputs
    │   ├── 01_hole_summary.csv
    │   ├── 02_measurements.csv
    │   ├── 03_measurement_dictionary.csv
    │   ├── 04_core_layout.csv
    │   ├── 05_spectrum_reflectance.csv
    │   ├── 06_spectrum_base_refl.csv
    │   └── <borehole_id>_readable.xlsx
    └── <borehole_id>.sqlite            The same six business tables
```

## Integrity and reruns

- Download spectra in fixed sample blocks; `.part` files resume at complete sample boundaries.
- Verify expected byte counts and SHA-256; incomplete downloads cannot be marked successful.
- Automatically check scalar CSVs, JPEGs, manifests, spectral dimensions, output row counts and database schemas.
- Stage CSV and SQLite outputs in temporary locations and replace final outputs only after complete success.
- `download-report.txt` distinguishes missing upstream endpoints (warnings) from corrupt data (failures).

## Current 05GJD001 results

- 25,938 samples and 106 populated scalar fields.
- Merged 13 identical scalar sources; omitted 8 all-null sources from the main table while retaining them in the dictionary.
- Linked 198 core sections to 33 trays and physical depths.
- Two complete spectral tables: 531 reflectance columns and 341 base-reflectance columns.
- WA profilometer, high-resolution tray and per-sample imagery endpoints returned 404 and are marked `unavailable`.
