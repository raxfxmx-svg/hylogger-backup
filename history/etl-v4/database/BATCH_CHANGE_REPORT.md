# Batch Entry-Point Changes

2026-09-29. Added consistent borehole-list handling and resumable dataset imports. Step 0 distinguishes missing manifests, partial downloads, empty source categories and unknown dataset counts. It publishes a usable selection only after writing its report. Steps 1-6, 9, 10, 31 and 32 accept mutually exclusive `--holes-file` and `--holes` options; later steps reuse the selected scope.

Step 7 registers validated digests by borehole/rule version; step 9 rereads received files. Images follow the confirmed left-to-right convention while retaining source, bounds and pixel checks. API/media tests select real row-group and image boundaries. Step 28 commits each dataset, then creates the pending batch release; step 34 retains its transaction and explicit display decisions.

68 checks passed: processing 12, input/direction 7, versions/failures 17, structure 8, batch checks 7 and database integration 17. Two-borehole reruns preserved all 35 business-table digests and the active release, adding no business revision. Step 7 scans fell from 493 to 11 and bytes from 274,866,791 to 1,026,202; observed times were 0.711 and 0.016 seconds.

The source contained 101 boreholes / 106 datasets. Prechecks selected 95 single-dataset and 3 multi-dataset boreholes: 98 boreholes / 103 datasets, approximately 49.43 GiB. Full processing was subsequently cancelled: the single-dataset route stopped at step 2 and the multi-dataset route reached step 33, without full import/publication/restoration.

Removed 88 newly copied raw directories and `etl4/batch_check`, approximately 45.51 GiB; free C: space rose about 45.56 GiB to 88.15 GiB. Original D: sources, ten existing borehole directories, existing work and databases remained. `05GJD001` lacked source profiles; `19AFRD2003` and `19AFRD2004` had missing manifests/partial downloads. Existing SQL constraint gaps remain documented in [NEW_INPUT_CHECK_REPORT.md](NEW_INPUT_CHECK_REPORT.md).

Snapshots, selections, rerun results and cleanup records are under `_codex_work/etl4_batch/`.
