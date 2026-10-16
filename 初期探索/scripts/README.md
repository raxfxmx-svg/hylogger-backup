# Data Processing Scripts

AI-generated tools for preparing HyLogger and NVCL data.

| File | Purpose |
| --- | --- |
| `ingest_hole.py` | Runs the complete pipeline for a local TSG dataset. |
| `parse_vnir.py` | Extracts VNIR-SWIR scalars and wavelengths. |
| `parse_tir.py` | Extracts TIR scalars and wavelengths. |
| `make_strips.py` | Creates depth-aligned core strip images from tray photos. |
| `build_intervals.py` | Groups samples into mineral intervals. |
| `load_db.py` | Builds the per-hole database and updates the borehole index. |
| `tsg_core.py` | Shared parsing, image processing, interval, and database functions. |
| `ingest_nvcl.py` | Runs the NVCL download and database import pipeline. |
| `nvcl_download.py` | Downloads NVCL metadata, scalar logs, and tray thumbnails. |
| `nvcl_etl.py` | Imports downloaded NVCL data into SQLite tables. |

Generated files are stored under `data/`. Rebuilding a local TSG database clears its review annotations.
