# Cloud Batch Processing

Merge this group's `etl4/` files into the main `etl4/` tree to use its shared modules. Configure dependencies, source assets, AWS authorization and the cloud database locally.

- `38_export_batch.py`: export a complete, twice-validated local batch without copying large assets.
- `39_upload_batch.py`: verify and upload manifest-listed S3 objects, with per-object progress receipts.
- `40_merge_cloud_batch.py`: merge datasets into the cloud database; `--finalize` explicitly selects the active release.
- `41_cleanup_batch.py`: preview local cleanup; deletion requires `--apply` and matching completed delivery receipts.
- `_batch_files.py`: package and receipt checks.
- `_s3_upload.py`: object integrity and transfer helpers, where included in this snapshot.

This grouping is source organization, not evidence that a new batch has already been uploaded or merged. The corresponding run receipts record actual historical operations.

This earlier snapshot uses the upload helper available in its main handoff tree; follow its existing imports when assembling the package.
