# HyLogger Ingestion

The local TSG pipeline prepares borehole metadata, spectra, mineral intervals and core strips for `server/` and `web/`. `scripts/tsg_core.py` contains shared logic; thin command-line scripts expose each stage.

```bash
python scripts/ingest_hole.py <raw_dir> <hole_id> [--out-root data]
```

The raw directory is read-only. Required VNIR files are `<hole_id>_tsg.{tsg,ini,cal,bip}`. TIR uses `<hole_id>_tsg_tir.{tsg,ini,cal,bip}` and must be fully present or entirely absent. Missing photos produce warnings; mosaic files are excluded. Dimensions and counts come from the source files rather than fixed dataset sizes.

Outputs include `index.sqlite`, `holes/<hole_id>/hole.sqlite`, `fixture/` scalar/wavelength CSVs and reports, and `strips/` images plus geometry metadata. The local database contains samples, intervals, trays, photos and annotations. Stages discover files, parse VNIR/TIR, create strips, build intervals, load the hole database and update the index. Failed checks stop processing and retain intermediate results for diagnosis.

Local TSG replay rebuilds hole.sqlite, including annotations. Back up manual-review records before rerunning ingestion or changing WT1_MIN/ERROR_MAX/NIL_MAX. Use a separate --out-root for regression runs. Spectrum byte checks expect two float32 planes with size `2 * samples * bands * 4`. VNIR wavelength ramps are checked against calibration metadata; TIR uses its wavelength specification. Ambiguous mineral/class columns fail explicitly.

The NVCL workflow downloads online data and loads additional source-preserving tables:

```bash
python scripts/ingest_nvcl.py <nvcl_id> [--provider wa] [--out-root data]
python scripts/nvcl_download.py <nvcl_id> [--provider wa] [--out-root data] [--cache data/.nvcl_cache]
python scripts/nvcl_etl.py <hole_id> [--out-root data]
```

Downloads are stored under `raw/<nvcl_id>/`: borehole metadata, datasets, scalar/image/spectral/profilometer log inventories, scalar CSVs, tray images and depth mappings. Reports check file formats and database counts. The NVCL loader adds its source tables and index location/operator fields while retaining the original five TSG tables. Existing nonempty downloads are reused in this early implementation; later ETL snapshots add stronger manifest/content checks.

Missing optional data remains unavailable. Photo-less trays retain NULL file references; unavailable TIR does not become fabricated spectra. Source log identity and original metadata remain traceable through the stored tables and reports.
