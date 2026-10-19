# Data Preparation

I designed a traceable preparation pipeline for HyLogger source metadata, scalar logs, spectra, profilometer arrays and tray images. It preserves source values and records unresolved relationships rather than guessing missing scientific meaning.

The initial scope was 05KCD001, 07THD002, 07THD003, 09ATD015 and 09ATD019. The three multi-dataset reference boreholes were outside that initial processing scope. This document describes the preparation design; actual execution results are recorded in RUNBOOK.md and the step 6 reports.

- `1_inventory.py`: discover files and lock source identities and hashes.
- `2_validate_payloads.py`: stream file checks, counts, numeric layouts and image decoding.
- `3_normalize_metadata.py`: normalize boreholes, datasets, logs, spectral streams and interpretation groups while retaining original JSON/XML.
- `4_align_samples.py`: establish real sample axes, inclusive tray/Section intervals and evidence-backed bindings.
- `5_build_columnar.py`: produce Parquet and row-group indexes, then compare decoded output with source values.
- `6_verify_prepared_data.py`: validate outputs and representative range queries before updating the verified pointer.
- Shared modules and `tests/`: path safety, atomic IO, identity, input contracts and regressions.

Sample identity is the axis position, not depth. Repeated depths, source nulls, leading-zero tray labels, duplicate log names and original masks remain distinct. `Wt` is a model component weight, not a calibrated probability. Unknown units, source references, survey angles and array semantics remain explicitly unknown. No smoothing, clipping, interpolation, automatic renormalization or cross-dataset joining is introduced.

The design separates PostgreSQL metadata/relationships from external large arrays and images. Image association, spectral layout and sample binding have independent availability states. Matching counts alone do not prove a spectral layout or binding. Source Section IDs and validated sample ranges guide image associations; pixel-depth calibration is separate.

The initial observations included 497 scalar logs, eight physical F32 arrays, 53 metadata-only spectral records, five profilometer files and 249 thumbnails. Some profilometer headers declared zero channels while actual arrays contained 128; both values were retained with an issue record. Missing high-resolution images followed the thumbnail policy rather than being treated as a failed download.

Use [RUNBOOK.md](RUNBOOK.md) for commands and recorded results. Raw packages remain unchanged, and failed preparation does not replace a previously verified version.
