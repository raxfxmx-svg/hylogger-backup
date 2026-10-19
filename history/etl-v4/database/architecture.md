# Data Relationships and Read Paths

```mermaid
erDiagram
  borehole ||--o{ borehole_revision : history
  borehole ||--o{ dataset : contains
  dataset ||--o{ dataset_revision : versions
  borehole_revision ||--o{ dataset_revision : describes
  dataset_revision ||--o{ sample_axis : has
  sample_axis ||--o{ scan_sample : positions
  sample_axis ||--o{ core_interval : intervals
  core_interval ||--o{ core_interval : parent
  dataset_revision ||--o{ spectral_stream : wavelengths
  dataset_revision ||--o{ interpretation_set : results
  interpretation_set ||--o{ scan_log : outputs
  spectral_stream ||--o{ scan_log : spectra
  scan_log ||--|| log_axis_binding : binding_status
  sample_axis o|--o{ log_axis_binding : verified_axis
  scan_log ||--o{ log_asset : files
  asset ||--o{ log_asset : association
  asset ||--o{ asset_location : copies
  asset ||--o{ data_chunk : row_groups
  core_interval ||--o{ image_frame : thumbnail
  asset ||--o{ image_frame : image_bytes
  image_frame ||--o{ image_region : visible_rows
  image_region ||--o{ image_sample_mapping : sample_ranges
  core_interval ||--o{ image_sample_mapping : source_section
  sample_axis ||--o{ image_sample_mapping : actual_samples
  image_region ||--o{ image_region_asset : derived_files
  asset ||--o{ image_region_asset : lossless_png
  scan_log ||--o{ spectral_array : binary_arrays
  spectral_stream ||--o{ spectral_array : channels
  asset ||--o{ spectral_array : original_f32
  spectral_array ||--o{ spectral_sample_map : sample_binding
  sample_axis ||--o{ spectral_sample_map : source_index
  spectral_array ||--o{ spectral_block : byte_ranges
  dataset_revision ||--o{ quality_issue : limitations
  data_release ||--o{ release_dataset : manifest
  dataset_revision ||--o{ release_dataset : selected_version
  data_release ||--o| active_release : current
  data_release ||--o{ borehole_composite : display_versions
  borehole ||--o{ borehole_composite : overview
  borehole_composite ||--o{ borehole_composite_part : ordered_selection
  dataset_revision ||--o{ borehole_composite_part : source_dataset
  sample_axis ||--o{ borehole_composite_part : actual_samples
  dataset_revision ||--o{ dataset_succession : predecessor_or_successor
  dataset_succession o|--o{ borehole_composite_part : confirmed_order
```

`interpretation_input` links results and spectral streams only with supporting evidence. `source_document`, `source_reference` and ingest records preserve that evidence. Branches and surveys are not fabricated; `dataset_segment` stores complete source sample ranges for the added datasets.

On 2026-09-24, the database contained 39 tables, 8 boreholes and 13 datasets. `v_borehole_composite_samples` selects confirmed 3D continuation samples; `v_borehole_dataset_full` exposes complete 2D ranges and independent axes. Images, spectra and results retain their source axes. See the [multi-dataset read contract](MULTI_DATASET_READ_CONTRACT.md).

Media reads follow release/dataset/axis/sample_no → original scan_sample depth → bound log values or spectra → Section image_region → row PNG and sample_index_linear indicator. See [MEDIA_READ_CONTRACT.md](MEDIA_READ_CONTRACT.md). The diagram below describes the original HTTP interface; media HTTP endpoints were not implemented in this snapshot.

```mermaid
flowchart LR
  A[Request with release and log IDs] --> B[FastAPI read-only connection]
  B --> C[PostgreSQL queries logs, axes and row-group bounds]
  C --> D[Asset IDs and storage locations]
  D --> E[Local Parquet or thumbnails]
  E --> F[Verify files and read required row groups]
  F --> G[Return original values, units, s/u, availability and pagination cursor]
```

Configuration resolves the local `root_key=etl4`; the database stores relative object keys. Storage adapters and replica locations can change without changing business or asset identities.

A sample is identified by its position within an axis; depths may repeat. Each release selects one immutable revision per dataset. Subsequent frontend pages must carry the previous response's `release_id` to avoid mixing versions when the default release changes.
