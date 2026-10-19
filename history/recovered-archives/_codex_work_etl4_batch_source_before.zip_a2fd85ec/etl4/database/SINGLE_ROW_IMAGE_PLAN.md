# Single-Row Images and Dataset Isolation

This plan, created on 2026-09-08 and updated on 2026-09-09, defined single-row image browsing linked to actual samples. The subsequent five-hole implementation and measurements are recorded in [MEDIA_DELIVERY.md](MEDIA_DELIVERY.md). The plan itself did not deploy cloud resources or implement the frontend.

I kept each original tray image and separated visible regions (`image_region`), sample associations (`image_sample_mapping`) and derived files (`image_region_asset`). Rows are identified within their source frame and dataset revision. Equal tray names, row numbers or depths never merge different datasets. Crop coordinates use native decoded pixels with half-open rectangles; sample intervals are inclusive.

The five-hole source contained 249 trays and 1,361 Sections: 05KCD001 had 30/171, 07THD002 77/462, 07THD003 36/216, 09ATD015 72/343 and 09ATD019 34/169. Trays varied between four, five and six Sections. Validated Section references and sample ranges guided reviewed layout templates; row count was not fixed. The earlier demo's 1,361 JPEG crops occupied 7,250,341 bytes and served only as a comparison, not as validation of the new lossless output.

Crop preparation keeps row pixels, gaps, fragments and labels, records source hash and recipe, and compares lossless PNG pixels with the specified original region. Borders and exceptions require layout review. Source depth direction was confirmed left to right; this does not establish pixel-depth calibration. Cross-dataset, out-of-bounds and incorrect source links must be rejected.

Selection uses `(release_id, dataset_id, axis_id, sample_no)`. Depth and results come from the selected real sample. The row indicator uses `sample_index_linear`, version 1, status `approximate`: for sample s in inclusive range [a,b], `p=(s-a)/(b-a)`; a single sample uses 0.5; native x is `p*(W-1)`. Error fields remain NULL without measured calibration. Repeated depths remain separate samples, missing images clear the indicator, and absent sample bindings cannot be replaced with fabricated positions.

Steps 20–22 verify spectral sources and access; 23–27 group images, detect/review regions, bind rows and generate assets; 28–29 import and validate the media revision in the original plan. Full spectra and raw images remain stored externally. The initial single-dataset parser did not yet establish real multi-dataset processing; future support required dataset-specific identity, preparation, alignment and import rather than simply removing the rejection.
