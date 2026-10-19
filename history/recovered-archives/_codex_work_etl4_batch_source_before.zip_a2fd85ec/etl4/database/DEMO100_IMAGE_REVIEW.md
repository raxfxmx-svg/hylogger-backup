# Single-Row Image Prototype Findings

2026-09-08. Read the D:/100demo implementation and existing five-borehole image outputs without running its pipeline or changing its files/database. Adopted its organisation of preserved tray originals, separate row images and source/sample mappings. The project owner subsequently confirmed left-to-right depth direction.

The prototype groups source Sections by tray, sorts their row order, uses the Section count as row count, applies EXIF orientation and RGB conversion, then crops equal-height slots with 9% vertical inset. It preserves image width and writes JPEG quality=90, subsampling=0, plus matching Parquet/JSON mappings. This supports varying row counts but does not independently detect visible rows.

```text
pitch = h / n
inset = max(1, round(pitch * 0.09))
top = round(i * pitch) + inset
bottom = round((i + 1) * pitch) - inset
crop = (0, top, image_width, bottom)
```

For 05KCD001, a 400×136 tray with five Sections produces first-row bounds `(0, 2, 400, 25)`, image size 400×23, samples 0-129 and depths 59.5-60.37269 m. Depth derives from source samples, not pixel measurement.

| Borehole | Row images | JPEG bytes |
|---|---:|---:|
| 05KCD001 | 171 | 991,241 |
| 07THD002 | 462 | 2,408,622 |
| 07THD003 | 216 | 1,191,225 |
| 09ATD015 | 343 | 1,797,116 |
| 09ATD019 | 169 | 862,137 |
| Total | 1,361 | 7,250,341 |

All 249 originals matched ETL4 hashes and all 1,361 crop coordinates matched the formula. Three representative outputs were viewed (400×23, 399×20 and 400×28); this was not visual inspection of every crop. JPEG re-encoding is lossy, so the project requires lossless reference crops or explicitly labelled previews.

The plan uses source Section/sample relationships with representative geometry checks, full automated checks and separate exception review. Preserve EXIF coordinate transforms, crop bounds, source identities, unavailable states and `section_interval`/`thumbnail_derived` labels. Do not treat equal-height templates as pixel calibration or remove dark rock based on brightness alone.

The downloader groups image logs by dataset, but the processor rejects multiple datasets. Tray-only grouping, filenames and asset IDs can collide across datasets; future handling needs dataset/log context and composite relationships. Three reference boreholes remained design/synthetic scope at this date. Spectral layout/sample-axis binding still required independent step-21 evidence. No prototype code or crops were copied into production during this review.
