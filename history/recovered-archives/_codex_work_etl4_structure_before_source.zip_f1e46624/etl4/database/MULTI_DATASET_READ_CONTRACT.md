# Multi-Dataset Reader Contract

Applies to release `177d1720-d327-534c-90da-5e3f517d8807`. HTTP integration belongs to the backend; sample values, spectra and images follow [MEDIA_READ_CONTRACT.md](MEDIA_READ_CONTRACT.md). Fix the release for a session and select samples by `(release_id, dataset_id, axis_id, sample_no)`.

```sql
SELECT release_id FROM core.active_release WHERE singleton;
```

## Complete 2D datasets

```sql
SELECT f.*
FROM core.v_borehole_dataset_full f
JOIN core.borehole b ON b.id=f.borehole_id
WHERE f.release_id=%(release_id)s AND b.source_hole_id=%(hole_id)s
ORDER BY f.sequence_no;
```

Use full depth_min_m/depth_max_m, sample_count, source name, axis_id and sequence. Share one pixels-per-metre scale and shallowest source-depth origin; each column offset is depth_min_m-common_min_m. Do not stretch every dataset to equal height. The sample slider spans 0..sample_count-1 and reads real md_m. overview_selection_status describes 3D selection only; full 2D details remain available for replaced segments.

## Confirmed 3D succession

```sql
SELECT s.*
FROM core.v_borehole_composite_samples s
JOIN core.borehole b ON b.id=s.borehole_id
WHERE s.release_id=%(release_id)s AND b.source_hole_id=%(hole_id)s
ORDER BY s.sequence_no,s.sample_no;
```

The view returns selected real samples with original dataset/revision/axis/sample_no. Keep these identities even when the UI adds a sequential browse index; paginate large results in the API. Read composition boundaries from selection_from_md_m/selection_to_md_m/upper_inclusive. The switch belongs to the successor; sample_no_from/to instead describe inclusive actual selected samples.

Preserve equal-depth samples and null results; do not substitute values across datasets. Display compositions do not provide missing survey angles.

```python
from _multi_reader import read_borehole_layout
from _media_reader import read_sample

layout = read_borehole_layout(conn, release_id, "15EIS001")
d = layout["datasets_2d_full"][1]  # Explicitly select the wedge column.
sample = read_sample(conn, release_id, d["dataset_id"], d["axis_id"],
                     sample_no=0, log_ids=[])
```

read_borehole_layout returns datasets_2d_full, parts_3d_selected, shared depth extent and offsets. Select logs from the same revision. A 3D click passes the returned dataset/axis/sample_no to read_sample; a 2D column change selects that column's axis/logs even when depths and tray labels coincide.

Use the full original image-row bounds for `p=(s-a)/(b-a)` and `x=p*(W-1)`; single samples are centred. Never substitute 3D-clipped bounds or crop away pixels outside the selected display interval. Depth/results remain the original sample values. Complete wavelength/spectra arrays, VSWIR/TIR and interpretation VNIR/SWIR/TIR s/u groups stay separate. S3 adapters are an integration responsibility.
