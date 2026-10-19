# Sample Reader Contract

Local database: PostgreSQL/PostGIS at `127.0.0.1:55432 / etl4_core`; media release `fd02659c-dc3d-52ea-a8eb-c032b91e7624`. This describes data access, not deployed HTTP endpoints.

Fix `(release_id, dataset_id, axis_id, sample_no)` for each selection. Validate membership through release_dataset/sample_axis. sample_no is zero-based with unit increments; depth, borehole or tray number alone is not unique.

```sql
SELECT d.source_dataset_id, r.dataset_id, r.dataset_revision_id,
       a.id AS axis_id, a.sample_count
FROM core.release_dataset r
JOIN core.dataset d ON d.id=r.dataset_id
JOIN core.sample_axis a ON a.dataset_revision_id=r.dataset_revision_id
WHERE r.release_id = 'fd02659c-dc3d-52ea-a8eb-c032b91e7624';
```

The synchronous [_media_reader.py](_media_reader.py) uses a caller-provided read-only connection:

```python
read_sample(conn, release_id, dataset_id, axis_id, sample_no,
            log_ids=None, image_log_id=None)
```

Choose scan_log.id from the same revision. Preserve source_log_id/name, interpretation_set_id, variant_code, algorithm_family, output_region, component_rank, metric_key and unit. Same names, s/u and interpretation regions remain distinct. VSWIR covers VNIR/SWIR; missing TIR retains its availability state. An empty log_ids list requests sample/images only; None reads all listed logs. image_log_id resolves multiple image sources explicitly.

| Return field | Meaning |
|---|---|
| release_id / dataset_id / dataset_revision_id / axis_id / sample_no | Complete selection identity |
| md_m | Actual scan_sample.md_m, never image interpolation |
| sample | Original tray/Section, position and SecDist |
| results | Original log values, provenance and explicit null/unavailable states |
| image_status | available, image_unavailable or selection_required |
| images | Explicit candidates; do not silently select the first |
| image_region_id / image_asset_id / image_log_id | Row, crop asset and source log |
| sample_no_from / sample_no_to | Inclusive original row sample bounds |
| object_key | Relative storage key; the API supplies controlled access |
| indicator | method, version, status, p and x_px; null when unavailable |

Indicator label: The indicator position is estimated from the sample number; depth and results come from the selected sample.

Scalar value fields retain source_row, sample_no, depth_m, value_numeric, value_text and value_raw. source_null is not zero and does not remove a sample. Display original weights without converting them to probability. Spectra return wavelength, wavelength_unit, spectra, value_unit, source_row, region_code, array_id and scaling_applied=false. Unknown units remain null. Non-finite channels use JSON null plus nonfinite_channels while F32 preserves the original bits. Return complete channels without depth averaging; unverified older bindings do not produce assumed curves.

For original row [a,b], sample s and width W: `p=(s-a)/(b-a)`, or 0.5 for one sample; `x_px=p*(W-1)`, including x=0 when W=1. This is approximate sample_index_linear v1 in crop pixel-centre coordinates. For 05KCD001 samples 129/130, switch row images before positioning despite equal depth. Scale against actual displayed image content, reject stale asynchronous selections and clear old images/pointers when unavailable. Out-of-range selections fail rather than clamp. Unbound rows have no invented pointer; discontinuous mappings require a separate rule.

metadata_associated / section_interval identifies source/template association. anchor_points, error_px and error_depth_m remain null. Left-to-right is project-confirmed, not pixel-depth calibration.

PostgreSQL stores identities/indexes; Parquet stores results, F32 matrices and PNG rows are assets. Reused Parquet retains old embedded axis metadata; asset.provenance explains source_axis_id/source_revision_id/reused_from_asset_id and current database bindings govern reads. Cloud access requires replica registration and Parquet/F32/PNG adapters. The historical local reader has no S3 client. Real multi-dataset raw packages still require dedicated per-dataset preparation.
