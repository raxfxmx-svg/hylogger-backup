# ETL3: Publishable Data from Immutable Raw Packages

ETL3 reads existing data without downloading:

```text
data/raw/<hole_id>/
```

and creates versioned `processed` packages with checksums and provenance.

Stages are separated into modules:

```text
metadata_etl.py   Borehole and dataset source metadata
assets_etl.py     Images, mosaics and availability
scalars_etl.py    Common sample axis, scalars, trays and sections
core_images_etl.py Tray thumbnail crops and section-depth-image mappings
spectra_etl.py    Independent spectral matrices, wavelengths and profilometer status
release_etl.py    Staging, quality reports and immutable releases
common.py         Shared hashing, path and Parquet utilities
etl.py            Command entry point and orchestration
```

Copied 05GJD001 from `etl2/data/raw/05GJD001` and verified SHA-256 for all 175 files with zero differences. ETL3 uses its own implementation and reads raw inputs.

## Core rules

- Keep raw packages immutable.
- Identify samples by `(dataset_id, sample_index)`, never by depth alone.
- Store aligned scalars in one columnar table per borehole, avoiding expansion of approximately 106 measurements into 2.75 million rows.
- Store each spectral series as an independent two-dimensional `float32` matrix.
- PostgreSQL will register matrix series, shapes, wavelengths, status, storage and hashes without expanding every wavelength value into rows.
- Keep not-downloaded, unavailable, metadata-only and complete-data states distinct.
- Name source and derived fields separately; do not invent units or meanings absent from the source.

## Installation and execution

```powershell
cd C:\path\to\project\etl3
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python etl.py 05GJD001
.\.venv\Scripts\python verify.py
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Specify another directory or release ID:

```powershell
python etl.py 05GJD001 --raw-root data/raw --processed-root data/processed
```

Default release IDs combine the ETL schema version and raw-content fingerprint. Existing release IDs cannot be overwritten.

## Output structure

```text
data/processed/
├── current.json
└── releases/
    └── <release_id>/
        ├── release_manifest.json
        ├── quality_report.json
        ├── catalog/
        │   ├── holes.parquet
        │   ├── datasets.parquet
        │   ├── scalar_series.parquet
        │   ├── spectral_series.parquet
        │   ├── spectral_axes.parquet
        │   ├── assets.parquet
        │   └── availability.parquet
        └── holes/05GJD001/
            ├── sample_axis.parquet
            ├── scalars/
            │   ├── values.parquet
            │   └── series_catalog.json
            ├── core/
            │   ├── trays.parquet
            │   ├── sections.parquet
            │   ├── section_images.parquet
            │   └── section_images.json
            ├── spectra/
            │   ├── axes/<axis_id>.json
            │   ├── series/<log_id>/values.f32
            │   ├── series/<log_id>/manifest.json
            │   └── series_catalog.json
            ├── assets/
            │   ├── files/...
            │   ├── core_strips/tray_XXXX_sec_N.jpg
            │   └── catalog.json
            └── source_metadata.json
```

## Expected sample results

- Common sample axis: 25,938 rows.
- 33 trays.
- 198 sections, six per tray.
- Two complete spectra with shapes `(25938, 531)` and `(25938, 341)`.
- Store both complete spectra independently without `signals.csv`.
- Retain the source `metadata_only` status for 13 other spectral series.
- Profilometer remains `unavailable`.
- 33 tray thumbnails and 198 derived section images.
- Section images retain the original 400-pixel thumbnail width and are marked
  `thumbnail_derived`; high-resolution tray and per-sample images remain `unavailable`.

## Section images

`core/section_images.parquet` is the canonical mapping; `section_images.json` contains identical data
for direct backend or frontend access. Each row corresponds to one row in `sections.parquet`.
It includes tray and row numbers, sample-index ranges, full-precision depths, image asset IDs,
package-relative paths, crop coordinates, file sizes and SHA-256 hashes.

The source provides only 400×130 tray thumbnails. Split each tray using the standard six equal-height rows,
cropping inward at vertical boundaries to exclude dividers. Preserve horizontal size and label these as thumbnail-derived
rather than high-resolution originals. Record depth direction as `left_to_right`. With access to high-resolution tray images,
a later release can replace these with high-resolution crops while retaining logical sections and mapping fields.

## Scalar tables

`scalars/values.parquet` contains only logs strictly aligned with the common sample axis. Stable source log IDs name physical columns. Identical values share one column, while `scalar_series.parquet` retains every source log and its column mapping.

Logs that cannot align with the common axis are written to `scalars/irregular/` and marked `irregular`.

## Spectra

Complete spectra use headerless, row-major `.f32` files:

```text
Byte offset for sample i = i × band_count × 4
```

Each matrix has a manifest recording `shape`, `dtype`, byte order, wavelengths, row mapping, size and SHA-256. Reading requires both files.

## Validation scope

The ETL and validator check:

- Source-manifest file existence, sizes and SHA-256 hashes;
- Row-by-row scalar alignment to the common sample axis;
- Duplicate depths preserve unique `sample_index` values;
- Tray and section ranges map to sample indices without overlap;
- Spectral byte counts match `sample_count × band_count × 4`;
- Wavelength counts match `band_count`;
- Finite and non-finite spectral value counts;
- Image sizes, hashes, formats and pixel dimensions;
- One image for each of 198 sections, with matching depth and sample intervals;
- Section images retain source thumbnail width and traceable source/derived assets;
- Release file sizes and SHA-256 hashes;
- Storage keys relative to the release package;
- No combined `signals.csv` in the release package.

Quality statistics describe technical checks, not mineral quantities or geological conclusions.
