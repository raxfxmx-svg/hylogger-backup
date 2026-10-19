# ETL4 Source Package

This snapshot groups data preparation, local database import and the supplementary tools selected at that stage. Numbered scripts show the execution order; shared modules implement file access, validation, identity, database operations and media reads.

The complete-version workflow is raw precheck (0), single-dataset preparation (1–6, 7 --inputs-only, 20 --files-only, 21–27) or multi-dataset preparation (31–33), first package acceptance (28), schema setup (8), then complete import and second acceptance (37). Earlier two-stage tools are historical utilities. Numbers 15–19 were not present in the original project.

Supplementary `etl4/` trees, where included, merge into the main `etl4/` tree and share its common modules. This source selection does not contain raw data, virtual environments, databases, passwords or every runtime resource. Running it requires migrations 001–006, official spectral-format evidence with its original license, Python dependencies, PostgreSQL/PostGIS and local configuration. Required evidence includes NVCLDataSvcDao.java, SpectralDataVo.java and getspectraldatausage.html. The frontend/API is a separate integration component.

## Files in This Snapshot

| File | Purpose |
|---|---|
| 0_check_raw.py (`etl4/processing/0_check_raw.py`, historical file not included here) | Check raw files and separate single-dataset, multi-dataset, and pending boreholes. |
| 1_inventory.py (`etl4/processing/1_inventory.py`, historical file not included here) | Inventory raw files for the selected boreholes before content validation. |
| 2_validate_payloads.py (`etl4/processing/2_validate_payloads.py`, historical file not included here) | Check file hashes and formats while recording explainable source issues. |
| 3_normalize_metadata.py (`etl4/processing/3_normalize_metadata.py`, historical file not included here) | Normalize metadata and source identifiers while preserving original documents. |
| 4_align_samples.py (`etl4/processing/4_align_samples.py`, historical file not included here) | Map sample indices to depths and check tray and section ranges. |
| 5_build_columnar.py (`etl4/processing/5_build_columnar.py`, historical file not included here) | Write Parquet files and read them back to compare values, nulls, and row counts. |
| 6_verify_prepared_data.py (`etl4/processing/6_verify_prepared_data.py`, historical file not included here) | Check prepared data and depth-based reads without changing data content. |
| 7_preflight_database.py (`etl4/database/7_preflight_database.py`, historical file not included here) | Register the selected input manifest and prepare an isolated local database instance. |
| 8_apply_schema.py (`etl4/database/8_apply_schema.py`, historical file not included here) | Apply migrations in order and grant permissions to the import and reader roles. |
| 20_audit_spectral_sources.py (`etl4/database/20_audit_spectral_sources.py`, historical file not included here) | Select the source release for media processing and check spectra against the file manifest. |
| 21_verify_spectral_bindings.py (`etl4/database/21_verify_spectral_bindings.py`, historical file not included here) | Check spectral order and sample numbers against cached official sample records. |
| 22_prepare_spectral_access.py (`etl4/database/22_prepare_spectral_access.py`, historical file not included here) | Index byte blocks in the original spectra without copying entire arrays. |
| 23_audit_dataset_image_groups.py (`etl4/database/23_audit_dataset_image_groups.py`, historical file not included here) | Build an image manifest by dataset, image log, and tray. |
| 24_detect_image_rows.py (`etl4/database/24_detect_image_rows.py`, historical file not included here) | Propose crop regions from row sections and build contact sheets for review. |
| 25_review_image_row_regions.py (`etl4/database/25_review_image_row_regions.py`, historical file not included here) | Check row boundaries, preserve all core pixels, and record visual review results. |
| 26_bind_image_rows_to_samples.py (`etl4/database/26_bind_image_rows_to_samples.py`, historical file not included here) | Link image rows to actual sample intervals and retain the approximate-position explanation. |
| 27_build_image_row_assets.py (`etl4/database/27_build_image_row_assets.py`, historical file not included here) | Create lossless row images and compare every pixel after reading them back. |
| 28_import_media_revision.py (`etl4/database/28_import_media_revision.py`, historical file not included here) | Use --package-only for sealing and first acceptance in the formal workflow; the older media-import entry remains in this snapshot. |
| 31_audit_multi_dataset_sources.py (`etl4/database/31_audit_multi_dataset_sources.py`, historical file not included here) | Check log membership across multiple datasets using saved source evidence. |
| 32_prepare_multi_dataset_payloads.py (`etl4/database/32_prepare_multi_dataset_payloads.py`, historical file not included here) | Prepare each dataset with an explicitly supplied parsing context. |
| 33_prepare_multi_dataset_media.py (`etl4/database/33_prepare_multi_dataset_media.py`, historical file not included here) | Check spectra across multiple datasets and create separate row image assets. |
| 37_import_final_version.py (`etl4/database/37_import_final_version.py`, historical file not included here) | Import a complete local batch from packages that passed the first acceptance, then run the second acceptance. |
| 38_export_batch.py (`etl4/database/38_export_batch.py`, historical file not included here) | Export complete boreholes after both local acceptances without copying large assets. |
| 39_upload_batch.py (`etl4/database/39_upload_batch.py`, historical file not included here) | Upload the batch exported by step 38, retaining per-object progress without cloud scientific recomputation. |
| 40_merge_cloud_batch.py (`etl4/database/40_merge_cloud_batch.py`, historical file not included here) | Append an independent batch to the cloud database; prepare a cumulative release by default and switch only with explicit finalize. |
| 41_cleanup_batch.py (`etl4/database/41_cleanup_batch.py`, historical file not included here) | Preview local cleanup for uploaded and merged batches; only --apply deletes individual files. |
| etl4/_file_checks.py (`etl4/_file_checks.py`, historical file not included here) | Deduplicate file hashes within one check and count actual file scans. |
| etl4/_settings.py (`etl4/_settings.py`, historical file not included here) | Initialize run settings in numbered entry points; importing this module does not parse arguments. |
| etl4/database/_batch_files.py (`etl4/database/_batch_files.py`, historical file not included here) | Batch file format shared by 38 and 39; checks delivery files without recomputing scientific data. |
| etl4/database/_db_common.py (`etl4/database/_db_common.py`, historical file not included here) | Database connections, identifiers, inserts, and schema checks. |
| etl4/database/_db_files.py (`etl4/database/_db_files.py`, historical file not included here) | JSON encoding, file access, and content digests for database manifests. |
| etl4/database/_final_import.py (`etl4/database/_final_import.py`, historical file not included here) | Prepare final-version inputs, map related IDs, and import individual datasets. |
| etl4/database/_ingest.py (`etl4/database/_ingest.py`, historical file not included here) | Map prepared data into the database while preserving source values and relationships. |
| etl4/database/_media_common.py (`etl4/database/_media_common.py`, historical file not included here) | Read files and calculate coordinates for image and spectral processing steps. |
| etl4/database/_media_import.py (`etl4/database/_media_import.py`, historical file not included here) | Package media evidence and import independent dataset revisions. |
| etl4/database/_media_manifest.py (`etl4/database/_media_manifest.py`, historical file not included here) | Store shared media metadata once and expand it into the dictionaries used by each processing step. |
| etl4/database/_media_reader.py (`etl4/database/_media_reader.py`, historical file not included here) | Read results and media by dataset, sample axis, and sample number. |
| etl4/database/_media_rows.py (`etl4/database/_media_rows.py`, historical file not included here) | Share image row boundary and sample association algorithms across single and multiple datasets. |
| etl4/database/_media_verification.py (`etl4/database/_media_verification.py`, historical file not included here) | Compare base values sample by sample and check media sources and reader results. |
| etl4/database/_multi_common.py (`etl4/database/_multi_common.py`, historical file not included here) | Read the explicit source scope and prepared results for multiple datasets. |
| etl4/database/_multi_db.py (`etl4/database/_multi_db.py`, historical file not included here) | Record the source release and build traceable display segments. |
| etl4/database/_prepared_inputs.py (`etl4/database/_prepared_inputs.py`, historical file not included here) | Read the selected preparation manifest and check its file references. |
| etl4/database/_publication.py (`etl4/database/_publication.py`, historical file not included here) | Prepare the manifest, then record validation and switch the release pointer in a transaction. |
| etl4/database/_run_reports.py (`etl4/database/_run_reports.py`, historical file not included here) | Save run reports and provide shared command execution and entry-point error handling. |
| etl4/database/_schema_docs.py (`etl4/database/_schema_docs.py`, historical file not included here) | Generate field and source descriptions from the database schema. |
| etl4/database/_verification.py (`etl4/database/_verification.py`, historical file not included here) | Compare prepared outputs with the database; API checks are enabled separately. |
| etl4/processing/_etl_common.py (`etl4/processing/_etl_common.py`, historical file not included here) | Provide file I/O, rule versions, and dataset context for processing steps. |
| etl4/processing/columnar_storage.py (`etl4/processing/columnar_storage.py`, historical file not included here) | Write Parquet files and read them back to compare values, nulls, and row counts. |
| etl4/processing/metadata_normalization.py (`etl4/processing/metadata_normalization.py`, historical file not included here) | Normalize metadata and source identifiers while preserving original documents. |
| etl4/processing/payload_validation.py (`etl4/processing/payload_validation.py`, historical file not included here) | Check file hashes and formats while recording explainable source issues. |
| etl4/processing/sample_alignment.py (`etl4/processing/sample_alignment.py`, historical file not included here) | Map sample indices to depths and check tray and section ranges. |
| [etl4/handoff/tools/handoff.py](../etl4_batch_delivery_20261003/code_before/etl4/handoff/tools/handoff.py) | Step 39 dynamically loads its SDK checks and upload helpers; older fixed-release commands are outside this workflow. |
