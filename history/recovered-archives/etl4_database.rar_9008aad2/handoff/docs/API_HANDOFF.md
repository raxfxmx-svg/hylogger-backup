# API Developer Handoff

## Scope and first action

Implement read-only access to the fixed release fd02659c-dc3d-52ea-a8eb-c032b91e7624. Start with the portable sample command in OPERATIONS.md. The original Python reference reader and actual files are included; online ETL, editing scientific values and new-version publishing are outside this handoff.

The existing source files are reference implementations, not a finished cloud API. In particular, the old API does not expose the new row-crop and sample-spectrum reader. The full package makes database restoration and local-file sample reading operational; HTTP/S3 integration remains the API developer's work.

## Identity contract

Validate (release_id, dataset_id, axis_id, sample_no) together. release_dataset selects dataset_revision_id. Internal dataset_id and log_id are UUIDs distinct from upstream source_dataset_id and source_log_id. The old URL /v1/datasets/{revision_id}/... expects a revision UUID, not the stable dataset UUID.

sample_no is zero based. Its pair with axis_id is the sample identity. md_m is measured depth in metres and may repeat. tray_sample_no and section_sample_no are one based. Do not use hole name, depth or tray label as a replacement for this identity.

examples/DATASET_CATALOG.json contains actual IDs for all five holes and all eight spectral arrays. examples/READONLY_QUERIES.sql contains independent queries for catalog, sample, logs, dense Parquet chunks, image candidates and spectral blocks. Their default selection is 05KCD001 sample 129; the sample JSON example instead uses 07THD002 sample 15.

## Reference reader

Files are etl4/database/_media_reader.py, _media_common.py and _db_common.py. They import NumPy, PyArrow, Psycopg and Pillow. Maintain their directory relation: _db_common.py resolves the data root as its parent directory's parent, namely this package's etl4/ directory.

```python
read_sample(conn, release_id, dataset_id, axis_id, sample_no,
            log_ids=None, image_log_id=None)
```

Provide your own psycopg connection with dict_row and reader credentials, as tools/handoff.py does. This bypasses the original connection() helper, which reads local_config.json before considering a DSN override. Importing the modules does not run numbered ETL steps.

Use explicit log_ids for the page's selected results. [] means depth/images only. None attempts all scalar/profile/spectral logs, including ones not readable as dense samples; do not use that as the default for scrolling. IDs are deduplicated and results are sorted by kind/name/ID, not request order. image_log_id optionally chooses the image source, and must belong to the selected revision.

## Dense scalar and profile results

scan_log describes the result, its unit, interpretation set, component rank and availability. log_axis_binding identifies the actual axis. For a verified dense log, data_chunk selects the Parquet row group containing the sample. Slice sample_no minus source_row_from within that group and confirm the returned sample_no.

Preserve value_numeric, value_text, value_raw, units and source-null semantics. A source_null is not numeric zero and must not remove the sample. Keep mineral names, original weights and the s/u variant separate; weights are not calibrated probabilities or grade estimates.

Interval logs are not dense rows: source_row is their interval record number and sample_no may be null. Do not force a non-dense binding to verified. Read tray/Section structure from core_interval; use sample-range overlap for other interval logs. The old /values API has a dedicated interval branch.

Some current revisions reuse Parquet with original axis/revision metadata. Resolve this using current database bindings and asset.provenance.source_axis_id/source_revision_id/reused_from_asset_id. Do not reject legitimate reused files simply because their old header ID differs from the current revision.

Profiles return status available_uncalibrated_profile and a value with sample_no and values. They are not spectra with a confirmed wavelength or physical geometry axis.

## Full spectra

For a verified spectral_array, map the selected sample through spectral_sample_map. Find the unique spectral_block whose half-open source-row interval includes that row. Read its byte_offset/byte_length and verify block SHA256.

```text
source_row = map.source_row_from + sample_no - map.sample_no_from
HTTP Range = bytes=block.byte_offset-(block.byte_offset + block.byte_length - 1)
offset_in_block = (source_row - block.source_row_from) * array.sample_stride_bytes
```

Decode channel_count values using the recorded dtype, currently <f4, with verified sample-major layout. Read wavelengths from spectral_stream rather than generating them from an assumed range. The current VSWIR arrays have 531 channels; TIR arrays have 341. The two 09ATD holes have no downloaded TIR array; do not fabricate one or substitute VSWIR.

A successful spectral result has wavelength, spectra, wavelength_unit, value_unit, source_row, region_code, array_id, nonfinite_channels and scaling_applied=false at result level. It does not have the scalar value object. Nonfinite channels are JSON null with their zero-based indices in nonfinite_channels. Unknown value_unit remains null.

## Images and sample marker

Read the sample's Section. Select image_sample_mapping using the same axis, same Section and a closed sample range containing sample_no. image_region identifies the row in its source image_frame; image_region_asset identifies the derived PNG. asset and asset_location then identify bytes and a storage replica. A frame ID, region ID and image asset ID are different identifiers.

Preserve multiple candidates and return selection_required; never silently choose the first same-depth image. Validate reviewed region and supported mapping status, and check file availability. An available image may still have indicator=null.

For the supported sample_index_linear version 1 marker:

```text
p = (sample_no - sample_no_from) / (sample_no_to - sample_no_from)
# For a single-sample range, p = 0.5.
x_px = p * (width_px - 1)
```

The status is approximate, not a calibrated pixel-to-depth mapping. Return actual md_m independently. Missing images must clear the old image and marker without suppressing otherwise available depth/results. Frontend scaling uses the actual displayed image rectangle, not surrounding padding.

## Existing HTTP source versus required integration

The existing etl4/database/api/app.py contains borehole/dataset/log/sample catalogs, wavelength metadata, intervals, local scalar/profile/interval values and tray-image endpoints. It has no new sample-media route. Its spectral values branch still returns sample_wavelength_order_unconfirmed even though the newer reference reader can read verified spectra.

The original release() helper accepts arbitrary existing releases and otherwise follows active_release. For this static deployment, make all endpoints select the fixed release and reject other release parameters. Do not accidentally expose historical rows simply because the dump includes them.

Suggested new GET routes, to be implemented by the API developer:

| Route | Responsibility |
|---|---|
| /v1/datasets/{revision_id}/samples/{sample_no} | Require axis_id, validate fixed-release membership, derive stable dataset_id server-side, select requested log_ids and optional image_log_id |
| /v1/image-assets/{asset_id}/content | Validate fixed-release image membership and JPG/PNG representation, then return bytes or a short-lived signed URL |

The old /v1/images/{frame_id}/content serves tray images. Do not pass a row PNG asset_id to that route. Keep bounded catalog/sample pagination: existing samples/values default to 1,000 and limit to 5,000. Match asynchronously returned data to the complete request identity so late responses do not replace the currently selected sample.

## Response and error rules

Return release_id, dataset_id, dataset_revision_id, axis_id, sample_no, md_m, sample_count, sample, results, image_status, images and indicator_label. A result carries log identity, unit, interpretation/variant/component metadata and status. Match results by log_id rather than array order.

| Status | Meaning |
|---|---|
| available | Content can be read |
| source_null | Original scalar value is null |
| metadata_only | Metadata exists without a downloaded payload |
| available_uncalibrated_profile | Profile values exist; physical calibration is unknown |
| axis_binding_unavailable | The requested dense-axis binding is unavailable |
| spectral_mapping_unavailable | No unique verified spectral mapping |
| sample_result_unavailable | No unique readable dense row group |
| asset_unavailable / image_unavailable | File or image unavailable |
| selection_required | Multiple image candidates require explicit selection |

Serialize nested UUIDs with the framework's JSON encoder. Do not emit NaN/Infinity. The reference Python function raises exceptions and does not define HTTP errors: implement 422 for invalid parameters, 404 for missing/out-of-release identities, and an explicit storage/server error such as 503 for unavailable or corrupt storage. Metadata-only and source-null are normal data states, generally HTTP 200.

examples/SAMPLE_REFERENCE.json preserves the original local response including its original UI label. The portable command renders that label in English. Scientific values, identities and image selection must match; the label language and cloud URL representation may differ.

## Cloud file adaptation

Use verified_remote S3 locations and the logical-root mapping produced by the transfer tools. object_key is already the complete bucket key: do not add data/ twice. Preserve stable asset identity rather than storing expiring URLs in the database. Keep uploaded files unchanged after validation, using appropriate write restrictions or an explicit version ID when versioning is employed.

The supplied reference reader deliberately remains a local-files reader. It can operate with this complete package and a remote RDS connection. For S3-only runtime, replace local_asset and file access with a store abstraction. Read F32 by verified blocks, Parquet by row-group-capable access or a bounded cache, and images individually. Avoid fetching all data into RAM or hashing a whole remote Parquet for every row-group cache miss. The original local cache does perform full-file hashes on misses and should not be copied blindly to S3.

## Acceptance examples

07THD002 sample 15: depth 62.50175 m; Min1 sTSAS log a4a5c7d3-0fe8-53be-97a2-02a5c7771ae8 gives Muscovite. Its image is 399 by 25 pixels, row range [0,251], p=0.05976095617529881 and x_px=23.784860557768926.

05KCD001 samples 129 and 130 both have depth 60.37269 m but use different row images. The first is at the right endpoint of [0,129]; the second is at the left endpoint of [130,259]. They must remain separate samples.

Run all 13 supplied depth/image fixtures, inspect at least one real spectrum from each of the eight arrays, and test nulls, missing storage, invalid axes and multiple image candidates. /health alone is not data-read acceptance. The deployment operator supplies RDS/S3 access and verified locations; the API developer owns query/file/HTTP integration; the frontend owns display and stale-response handling.
