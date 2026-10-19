# Source field to database mapping

Step 7 registers the selected inputs; steps 31-33 prepare multiple datasets, and step 37 imports and validates complete revisions. Original XML remains intact in the source datasets.json document.

| Database table | Input source | Mapping and semantics |
|---|---|---|
| `schema_migration` | Migration SHA256; step 8 | Database schema change history |
| `borehole` | Step 3 borehole | Stable borehole identity; source IDs are unique within provider_code |
| `borehole_revision` | Step 3 borehole; metadata_revision_id → id | Borehole metadata snapshot; organization names retain their source roles |
| `dataset` | Step 3 dataset | A borehole may contain multiple datasets; this does not establish branches |
| `dataset_revision` | Step 3 dataset + dataset_revision; Step 9 input_digest | Scan and processing revision; changing organization and instrument attributes belong to the revision |
| `sample_axis` | Step 4 alignment_report | Validated common sample axis and alignment evidence |
| `scan_sample` | Step 5 sample_axis.parquet + Step 4 core_intervals | Sample position within an axis; sample_no starts at 0 and repeated depths are valid |
| `core_interval` | Step 4 core_intervals.json | Tray and section intervals with inclusive sample bounds; source_label retains leading zeros |
| `spectral_stream` | Step 3 spectral_streams | Physical VSWIR/TIR wavelength axes, separate from interpretation regions |
| `interpretation_set` | Step 3 interpretation_sets | Algorithm family, VNIR/SWIR/TIR region, and s/u result variant; no inferred upstream processing batch |
| `interpretation_input` | Step 3 interpretation_inputs; empty in this batch | Only evidence-backed input relationships; similar regions do not establish a relationship |
| `metric_definition` | Step 3 metric_definitions | Metric semantics; unknown or inapplicable probability attributes may be NULL, and Wt is not a probability |
| `scan_log` | Step 3/32 logs; matching fields map directly and extra source attributes remain in normalized_metadata | All source logs, including duplicate names and metadata-only records, belong to their own dataset revision |
| `log_axis_binding` | Step 4 axis_bindings takes precedence; step 9 explicitly registers unbound states | Step 3 pending_step_4 is not treated as the final binding state |
| `asset` | Step 5 assets/raw_assets; processing evidence locked by step 7 | File identity, bytes, and hash; semantic state is independent of file existence |
| `asset_location` | Step 9 local root key and relative path | An asset may have multiple stored copies; credentials are never stored in the database |
| `log_asset` | Step 3 payload_paths + Step 5 source_log_id | Links logs to source and canonical files; metadata_only logs may have no record |
| `data_chunk` | Step 5/32 assets[].row_groups / logical_group_sha256 | Parquet row-group bounds and integrity indexes |
| `image_frame` | Step 4 image_frames; source_log_id/source_path map to internal foreign keys | Thumbnails and trays retain both depth sets and their differences; no pixel-level calibration |
| `source_document` | Step 3 raw_metadata + original text files | 13 original JSON documents per borehole and text files; original XML remains inside the source datasets.json document |
| `source_reference` | Step 3 source_references | Exact source ID resolution; unresolved references remain queryable |
| `quality_issue` | Step 2–5 issues | Source issues, evidence, and affected scope |
| `ingest_run` | Step 9/28/34 | Run records; repeated runs reuse existing business entities |
| `revision_validation` | Step 10/29/35 | Revision validation results and validator code hash; validation may be repeated |
| `data_release` | Step 10/28/34 dataset_revision set | Release manifest; local publication follows validation, and cloud activation uses an explicit final member selection |
| `release_dataset` | data_release.manifest from each stage | Each release selects exactly one revision for each dataset |
| `active_release` | Step 10/29/35 switch after successful validation | Single current-release reference; historical releases remain readable, and database validation has no API dependency |
| `borehole_branch` | Future evidence-backed branch records; currently empty | Parent-child branches are not inferred from the number of datasets |
| `dataset_segment` | Step 34; complete sample intervals of independent datasets | Keep complete segments for each dataset; composite_part separately defines 3D display selections |
| `survey_station` | Future survey records; currently empty | Survey revision, measured depth, and angle conventions; no fabricated trajectory |
| `spectral_array` | Step 20–22; imported by step 28 | Validated original F32 matrices, channels, and byte strides; complete values remain in the source file |
| `spectral_sample_map` | Step 21 official sampleNo JSON comparison; imported by step 28 | Inclusive mapping between source spectral rows and real database samples; no depth interpolation |
| `spectral_block` | Step 22; imported by step 28 | Contiguous source F32 byte ranges and block hashes for bounded reads |
| `image_region` | Step 23–25; imported by step 28 | Visible row region in a dataset tray image; variable row count and native pixel coordinates |
| `image_sample_mapping` | Step 26; imported by step 28 | Source Section and actual sample interval; sample_index_linear v1 indicators are approximate |
| `image_region_asset` | Step 27; imported by step 28 | Row region, lossless PNG, source log, and crop recipe; pixels match the source image |
| `dataset_succession` | multi_dataset_decisions.json; Step 34 | User-confirmed display succession, actual sample switch depth, and evidence; no inferred branch trajectory |
| `borehole_composite` | Step 34; created per release and borehole | 3D composite definition; no automatic gap filling or fallback to old paths, while 2D retains each complete dataset |
| `borehole_composite_part` | Step 34; confirmed order and actual sample depths of each dataset | 3D selection windows and inclusive source sample intervals; sequence_no also defines the 2D order |

Field transformations to note:

- `borehole.metadata_revision_id` -> `borehole_revision.id`; stable borehole identity is separate from attribute history.
- Attributes such as `dataset.instrument_name/owner_name/source_dataset_name` belong to `dataset_revision`, preserving the complete revision object.
- Step 3 `axis_id=null` and `axis_binding_status=pending_step_4` remain in normalized evidence; API and canonical relationships use step 4 `log_axis_binding`.
- Sample Parquet `tray_index/section_index` map to interval foreign keys using step 4 ordinals on the same axis; ordinals are not tray labels.
- Image `source_log_id/source_path` resolve to `log_id/asset_id`; source fields in logs and assets retain the original values.
- Parquet row-group `source_row_to_exclusive` is exclusive; tray and section `sample_no_to` is inclusive.
- `is_probability` may be NULL for text or undefined metrics; Wt stores false. Numeric payloads remain in Parquet without renormalization or clipping.
- Each original `raw_metadata` document has one `source_document`; asset tables retain the original path, byte count, and SHA256.
- In addition to source and canonical files, locked processing reports and alignment evidence are registered as evidence assets; failed development outputs are not automatically published.
- `interpretation_input`, `borehole_branch`, and `survey_station` do not invent data to fill foreign keys. dataset_segment stores complete source segments; composite_part only describes display selections.
- 2D obtains complete dataset ranges through v_borehole_dataset_full and reads samples/images by independent axis_id; 3D uses v_borehole_composite_samples.
- Multi-dataset image depth comparisons allow original decimal endpoints to reconstruct identical IEEE float32 bits; actual differences are retained without uniform rounding or source rewriting.
