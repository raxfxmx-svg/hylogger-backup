# ETL4 Read-Only API Handoff

Historical handoff date: 2026-09-12. Integrate prepared data through RDS PostgreSQL/PostGIS and S3 without rerunning ETL or adding online writes. Start with READONLY_QUERIES.sql, compare SAMPLE_REFERENCE.json, then implement S3 and HTTP access.

## Five-borehole baseline

Fixed release: `fd02659c-dc3d-52ea-a8eb-c032b91e7624`.

| Borehole | Samples | Internal sample_no | Complete spectra |
|---|---:|---|---|
| 05KCD001 | 22,356 | 0-22,355 | VSWIR 531; TIR 341 |
| 07THD002 | 116,424 | 0-116,423 | VSWIR 531; TIR 341 |
| 07THD003 | 54,432 | 0-54,431 | VSWIR 531; TIR 341 |
| 09ATD015 | 46,030 | 0-46,029 | VSWIR 531 |
| 09ATD019 | 22,650 | 0-22,649 | VSWIR 531 |
| Total | 261,892 | Separate axes | Eight matrices |

The 36-table database contains 523,784 historical sample rows, including old revisions. Current media: 249 tray JPGs and 1,361 row PNGs. Dump size is about 10.24 MB; 2,810 external files total about 2.401 GB, including about 39.81 MB of JPG/PNG. The dump excludes external values/files.

Local preparation and historical validation were complete. This review checked every file size/hash and parsed the backup offline. A local connection timed out, so the running database was not revalidated. RDS restoration, S3 verification, permissions and website integration were not completed by this handoff.

## Package contents

- READONLY_QUERIES.sql: independent queries, defaulting to 05KCD001 samples 129/130.
- DATASET_CATALOG.json: dataset/revision/axis/array/log identities extracted from the selected backup.
- SAMPLE_REFERENCE.json: complete local reference for 07THD002 sample 15.
- ACCEPTANCE_FIXTURES.json: thirteen first/last/boundary sample checks.
- reference_code/: local reader/API snapshots and tested Python 3.12 dependencies.
- reference_docs/: schema, contracts and source mappings.

Dumps, large objects and credentials are delivered separately. Deployment supplies region, endpoint/port, database, tested PostgreSQL/PostGIS versions, reader account, official CA, bucket, root-key mapping, prefix and API address. Proposed names are etl4_core, etl4_s3_primary and data/. Use verify-full and reader-only SQL/S3 permissions; migration administration is separate.

## Identity and reads

Select `(release_id, dataset_id, axis_id, sample_no)`; release membership selects dataset_revision_id. Internal UUIDs differ from source IDs. sample_no is zero-based and depth may repeat. tray_sample_no/section_sample_no are one-based. Asset IDs differ from frames, regions and URLs.

For scalars/profiles, choose revision-local scan_log IDs, check bindings, locate data_chunk row groups and verify the returned sample. Preserve value_numeric/text/raw, units, source state, s/u, region and component rank. Interval logs require interval-overlap queries, not dense-row formulas. Reused Parquet may retain older embedded axis IDs; use current database bindings and asset.provenance. Original weights are not probabilities or grades.

For spectra, map sample_no to source_row, select its spectral_block and read/verify that byte range. Read dtype, stride and channel_count from records rather than hardcoding 531/341.

```text
source_row = map.source_row_from + sample_no - map.sample_no_from
S3 Range = bytes=byte_offset-(byte_offset + byte_length - 1)
sample_byte_offset = (source_row - block.source_row_from) * sample_stride_bytes
```

Return complete wavelength/spectra arrays with units, source_row, array_id, region_code and scaling_applied=false. Unknown units remain null; non-finite channels use JSON null plus nonfinite_channels. Do not substitute VSWIR for missing TIR.

For images, follow section_interval_id and same-axis Section mappings to image_region/image_region_asset. Return identities, dimensions, sample bounds and controlled access. Multiple candidates require image_log_id selection. For sample s in original row [a,b], use `p=(s-a)/(b-a)` (0.5 when a=b), `x_px=p*(W-1)`, labelled approximate sample_index_linear v1. Real depth is scan_sample.md_m. Missing images clear prior images/pointers; resize against actual image content.

## Integration work

```python
read_sample(conn, release_id, dataset_id, axis_id, sample_no,
            log_ids=None, image_log_id=None)
```

Provide a psycopg dict_row read-only connection. The snapshot depends on numpy, pyarrow, psycopg and Pillow; install dependencies on the target. Its local_asset() needs S3 adaptation. Empty log_ids requests sample/images; None enumerates all logs. Match results by log_id, not request order.

Existing API routes in reference_docs/api_contract.md cover catalogue, logs, samples, intervals, scalar/profile values and tray images. They do not expose the new media reader. For this historical fixed-release deployment, enforce the selected release across every route, including images. Suggested additions are `/v1/datasets/{revision_id}/samples/{sample_no}` with required axis_id and optional log_ids/image_log_id, and `/v1/image-assets/{asset_id}/content` with release/type checks. Keep all business routes read-only.

Preserve pagination (default 1,000, maximum 5,000), selection identity and stale-response rejection. Scalar results use value; spectra use wavelength/spectra fields. Preserve available, source_null, metadata_only, available_uncalibrated_profile, axis_binding_unavailable, spectral_mapping_unavailable, sample_result_unavailable, asset_unavailable, image_unavailable and selection_required states. Map invalid input to 422, absent/out-of-release identities to 404, and storage/hash failures to 503; ordinary source-null states usually remain 200. Encode UUIDs and prohibit JSON NaN/Infinity.

Read actual S3 keys from verified locations and deployment root mappings. Prefer verified_remote; any manually checked scope must be explicit. Use bounded Parquet caches, verified F32 block reads and individual image reads/signatures. The local Parquet cache performs initial full-file hashing; do not multiply remote transfers by copying that behaviour blindly. Migration verification establishes full object identity; ETag is not SHA256.

## Reference samples

07THD002 sample 15: dataset `d3c51d8a-3c91-553b-89dd-cee9e926979d`, revision `ca3660de-f678-5256-89f5-40d17832e4eb`, axis `b9ba28cd-0216-5314-83df-f6247b0f56b6`, log `a4a5c7d3-0fe8-53be-97a2-02a5c7771ae8`. Expect depth 62.50175 m and Min1 sTSAS=Muscovite. Image: 399×25, samples [0,251], p≈0.0597609562, x_px≈23.78486056.

05KCD001 samples 129/130 both have depth 60.37269 m but use rows [0,129] and [130,259]. Images/pointers must switch without merging samples.

Validate the thirteen fixtures, at least one sample per spectral array, null/missing/ambiguous cases and complete RDS/S3 reads without the original computer. Data/deployment owners supply paired assets and locations; backend owners implement reads/HTTP/errors; frontend owners preserve selection and approximate-pointer semantics. Missing survey angles, calibration, units and TIR remain unknown.
