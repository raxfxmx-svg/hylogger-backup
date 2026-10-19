# Database Schema Dictionary

Generated from the supplied schema catalog. Table/column names, types, nullability, defaults, constraints and indexes are retained. Source JSON may contain original-language evidence; that is data, not translated schema documentation.

Tables: 36. Schema checksum: `e8840cb822ad3006064c93c8fb8e69bfbd7afe46697234e6d1f77eb4972fb367`.

`borehole_revision.coordinate_basis` describes the source/basis of the collar coordinates. `image_region.coordinate_basis` describes image pixel coordinates; these are different meanings.

## active_release

Current release pointer; applications in this handoff also enforce the fixed release ID.

| Column | Type | Nullable | Default |
|---|---|---|---|
| singleton | boolean | NO | true |
| release_id | uuid | NO | None |
| switched_at | timestamp with time zone | NO | now() |

Constraints:

- `active_release_pkey`: `PRIMARY KEY (singleton)`
- `active_release_release_id_fkey`: `FOREIGN KEY (release_id) REFERENCES data_release(id)`
- `active_release_singleton_check`: `CHECK (singleton)`

Indexes:

- `CREATE UNIQUE INDEX active_release_pkey ON core.active_release USING btree (singleton)`

## asset

Content identity, source provenance, byte size and SHA256 of an external file.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| asset_kind | text | NO | None |
| representation | text | NO | None |
| logical_path | text | NO | None |
| sha256 | text | NO | None |
| byte_size | bigint | NO | None |
| media_type | text | NO | None |
| payload_status | text | NO | 'present'::text |
| semantic_status | text | NO | None |
| provenance | jsonb | NO | None |

Constraints:

- `asset_byte_size_check`: `CHECK ((byte_size >= 0))`
- `asset_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `asset_dataset_revision_id_representation_logical_path_key`: `UNIQUE (dataset_revision_id, representation, logical_path)`
- `asset_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `asset_id_sha256_key`: `UNIQUE (id, sha256)`
- `asset_pkey`: `PRIMARY KEY (id)`
- `asset_representation_check`: `CHECK ((representation = ANY (ARRAY['raw'::text, 'canonical'::text, 'evidence'::text])))`
- `asset_sha256_check`: `CHECK ((sha256 ~ '^[a-f0-9]{64}$'::text))`

Indexes:

- `CREATE UNIQUE INDEX asset_dataset_revision_id_representation_logical_path_key ON core.asset USING btree (dataset_revision_id, representation, logical_path)`
- `CREATE UNIQUE INDEX asset_id_dataset_revision_id_key ON core.asset USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX asset_id_sha256_key ON core.asset USING btree (id, sha256)`
- `CREATE UNIQUE INDEX asset_pkey ON core.asset USING btree (id)`

## asset_location

Physical file replicas; logical storage root and relative object key.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| asset_id | uuid | NO | None |
| backend | text | NO | None |
| root_key | text | NO | None |
| object_key | text | NO | None |
| access_status | text | NO | None |
| verified_sha256 | text | NO | None |

Constraints:

- `asset_location_asset_id_backend_root_key_object_key_key`: `UNIQUE (asset_id, backend, root_key, object_key)`
- `asset_location_asset_id_fkey`: `FOREIGN KEY (asset_id) REFERENCES asset(id)`
- `asset_location_content_identity_fkey`: `FOREIGN KEY (asset_id, verified_sha256) REFERENCES asset(id, sha256)`
- `asset_location_object_key_check`: `CHECK ((object_key !~ '(^[/\\]|(^|[/\\])\.\.([/\\]|$)|:)'::text))`
- `asset_location_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX asset_location_asset_id_backend_root_key_object_key_key ON core.asset_location USING btree (asset_id, backend, root_key, object_key)`
- `CREATE UNIQUE INDEX asset_location_pkey ON core.asset_location USING btree (id)`

## borehole

Stable borehole identity and upstream identifier.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| provider_code | text | NO | None |
| source_hole_id | text | NO | None |
| source_identifier | text | YES | None |

Constraints:

- `borehole_pkey`: `PRIMARY KEY (id)`
- `borehole_provider_code_source_hole_id_key`: `UNIQUE (provider_code, source_hole_id)`

Indexes:

- `CREATE UNIQUE INDEX borehole_pkey ON core.borehole USING btree (id)`
- `CREATE UNIQUE INDEX borehole_provider_code_source_hole_id_key ON core.borehole USING btree (provider_code, source_hole_id)`

## borehole_branch

Optional branch identity; empty for this baseline.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| borehole_id | uuid | NO | None |
| parent_branch_id | uuid | YES | None |
| source_branch_id | text | YES | None |
| branch_depth_m | double precision | YES | None |
| evidence | jsonb | NO | None |

Constraints:

- `borehole_branch_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `borehole_branch_check`: `CHECK (((parent_branch_id IS NULL) OR (parent_branch_id <> id)))`
- `borehole_branch_id_borehole_id_key`: `UNIQUE (id, borehole_id)`
- `borehole_branch_parent_branch_id_borehole_id_fkey`: `FOREIGN KEY (parent_branch_id, borehole_id) REFERENCES borehole_branch(id, borehole_id)`
- `borehole_branch_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX borehole_branch_id_borehole_id_key ON core.borehole_branch USING btree (id, borehole_id)`
- `CREATE UNIQUE INDEX borehole_branch_pkey ON core.borehole_branch USING btree (id)`

## borehole_revision

Source metadata snapshot and the reported 2D collar point.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| borehole_id | uuid | NO | None |
| source_name | text | NO | None |
| provider_code | text | YES | None |
| custodian_name | text | YES | None |
| driller_name | text | YES | None |
| operator_name | text | YES | None |
| project_name | text | YES | None |
| drilling_method | text | YES | None |
| reported_length_m | double precision | YES | None |
| drill_start_date | date | YES | None |
| drill_end_date | date | YES | None |
| actual_drill_date_precision | text | NO | None |
| collar_geom | geometry(Point,4326) | YES | None |
| coordinate_basis | text | YES | None |
| horizontal_crs | text | YES | None |
| vertical_crs | text | YES | None |
| elevation_m | double precision | YES | None |
| azimuth_deg | double precision | YES | None |
| inclination_deg | double precision | YES | None |
| inclination_convention | text | YES | None |
| orientation_missing_reason | text | YES | None |
| orientation_missing_reason_source | text | YES | None |
| trajectory_status | text | NO | None |
| normalized_metadata | jsonb | NO | None |

Constraints:

- `borehole_revision_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `borehole_revision_id_borehole_id_key`: `UNIQUE (id, borehole_id)`
- `borehole_revision_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE INDEX borehole_collar_gist ON core.borehole_revision USING gist (collar_geom)`
- `CREATE UNIQUE INDEX borehole_revision_id_borehole_id_key ON core.borehole_revision USING btree (id, borehole_id)`
- `CREATE UNIQUE INDEX borehole_revision_pkey ON core.borehole_revision USING btree (id)`

## core_interval

Tray or Section with a closed sample interval and parent relation.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| axis_id | uuid | NO | None |
| interval_kind | text | NO | None |
| ordinal | integer | NO | None |
| source_label | text | NO | None |
| parent_interval_id | uuid | YES | None |
| sample_no_from | bigint | NO | None |
| sample_no_to | bigint | NO | None |
| observed_depth_min_m | double precision | YES | None |
| observed_depth_max_m | double precision | YES | None |
| source_log_id | text | NO | None |
| source_data_row | bigint | NO | None |
| source_interval_convention | text | NO | None |

Constraints:

- `core_interval_axis_id_fkey`: `FOREIGN KEY (axis_id) REFERENCES sample_axis(id)`
- `core_interval_axis_id_interval_kind_ordinal_key`: `UNIQUE (axis_id, interval_kind, ordinal)`
- `core_interval_axis_id_sample_no_from_fkey`: `FOREIGN KEY (axis_id, sample_no_from) REFERENCES scan_sample(axis_id, sample_no) DEFERRABLE INITIALLY DEFERRED`
- `core_interval_axis_id_sample_no_to_fkey`: `FOREIGN KEY (axis_id, sample_no_to) REFERENCES scan_sample(axis_id, sample_no) DEFERRABLE INITIALLY DEFERRED`
- `core_interval_check`: `CHECK ((sample_no_from <= sample_no_to))`
- `core_interval_check1`: `CHECK ((((interval_kind = 'tray'::text) AND (parent_interval_id IS NULL)) OR ((interval_kind = 'section'::text) AND (parent_interval_id IS NOT NULL))))`
- `core_interval_id_axis_id_key`: `UNIQUE (id, axis_id)`
- `core_interval_interval_kind_check`: `CHECK ((interval_kind = ANY (ARRAY['tray'::text, 'section'::text])))`
- `core_interval_ordinal_check`: `CHECK ((ordinal >= 0))`
- `core_interval_parent_interval_id_axis_id_fkey`: `FOREIGN KEY (parent_interval_id, axis_id) REFERENCES core_interval(id, axis_id)`
- `core_interval_pkey`: `PRIMARY KEY (id)`
- `core_interval_sample_no_from_check`: `CHECK ((sample_no_from >= 0))`
- `core_interval_source_interval_convention_check`: `CHECK ((source_interval_convention = 'closed'::text))`

Indexes:

- `CREATE UNIQUE INDEX core_interval_axis_id_interval_kind_ordinal_key ON core.core_interval USING btree (axis_id, interval_kind, ordinal)`
- `CREATE UNIQUE INDEX core_interval_id_axis_id_key ON core.core_interval USING btree (id, axis_id)`
- `CREATE UNIQUE INDEX core_interval_pkey ON core.core_interval USING btree (id)`

## data_chunk

Parquet row-group index with a half-open source-row range.

| Column | Type | Nullable | Default |
|---|---|---|---|
| asset_id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| axis_id | uuid | NO | None |
| log_id | uuid | YES | None |
| row_group | integer | NO | None |
| source_row_from | bigint | NO | None |
| source_row_to_exclusive | bigint | NO | None |
| row_count | integer | NO | None |
| coordinate_kind | text | NO | None |
| coordinate_min | double precision | NO | None |
| coordinate_max | double precision | NO | None |
| logical_sha256 | text | NO | None |

Constraints:

- `data_chunk_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `data_chunk_axis_id_dataset_revision_id_fkey`: `FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES sample_axis(id, dataset_revision_id)`
- `data_chunk_check`: `CHECK (((source_row_to_exclusive - source_row_from) = row_count))`
- `data_chunk_check1`: `CHECK ((coordinate_min <= coordinate_max))`
- `data_chunk_log_asset_fkey`: `FOREIGN KEY (log_id, asset_id) REFERENCES log_asset(log_id, asset_id)`
- `data_chunk_log_id_dataset_revision_id_fkey`: `FOREIGN KEY (log_id, dataset_revision_id) REFERENCES scan_log(id, dataset_revision_id)`
- `data_chunk_pkey`: `PRIMARY KEY (asset_id, row_group)`
- `data_chunk_row_count_check`: `CHECK ((row_count > 0))`
- `data_chunk_row_group_check`: `CHECK ((row_group >= 0))`
- `data_chunk_source_row_from_check`: `CHECK ((source_row_from >= 0))`

Indexes:

- `CREATE INDEX chunk_range_idx ON core.data_chunk USING btree (log_id, coordinate_min, coordinate_max)`
- `CREATE UNIQUE INDEX data_chunk_pkey ON core.data_chunk USING btree (asset_id, row_group)`

## data_release

Release content manifest and its checksum.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| manifest_sha256 | text | NO | None |
| created_at | timestamp with time zone | NO | now() |
| release_kind | text | NO | 'local_verified'::text |
| manifest | jsonb | NO | None |

Constraints:

- `data_release_manifest_sha256_key`: `UNIQUE (manifest_sha256)`
- `data_release_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX data_release_manifest_sha256_key ON core.data_release USING btree (manifest_sha256)`
- `CREATE UNIQUE INDEX data_release_pkey ON core.data_release USING btree (id)`

## dataset

Stable scan dataset identity within a borehole.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| borehole_id | uuid | NO | None |
| source_dataset_id | text | NO | None |

Constraints:

- `dataset_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `dataset_borehole_id_source_dataset_id_key`: `UNIQUE (borehole_id, source_dataset_id)`
- `dataset_id_borehole_id_key`: `UNIQUE (id, borehole_id)`
- `dataset_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX dataset_borehole_id_source_dataset_id_key ON core.dataset USING btree (borehole_id, source_dataset_id)`
- `CREATE UNIQUE INDEX dataset_id_borehole_id_key ON core.dataset USING btree (id, borehole_id)`
- `CREATE UNIQUE INDEX dataset_pkey ON core.dataset USING btree (id)`

## dataset_revision

Prepared version of a dataset and its input/processing identity.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_id | uuid | NO | None |
| borehole_id | uuid | NO | None |
| borehole_revision_id | uuid | NO | None |
| source_dataset_name | text | YES | None |
| source_borehole_uri | text | YES | None |
| source_project_name | text | YES | None |
| instrument_name | text | YES | None |
| owner_name | text | YES | None |
| source_snapshot_id | text | NO | None |
| pipeline_id | text | NO | None |
| input_digest | text | NO | None |
| mapping_version | integer | NO | None |
| source_created_at | timestamp with time zone | YES | None |
| source_modified_at | timestamp with time zone | YES | None |
| source_download_started_at | timestamp with time zone | YES | None |
| source_download_finished_at | timestamp with time zone | YES | None |
| normalized_metadata | jsonb | NO | None |

Constraints:

- `dataset_revision_borehole_revision_id_borehole_id_fkey`: `FOREIGN KEY (borehole_revision_id, borehole_id) REFERENCES borehole_revision(id, borehole_id)`
- `dataset_revision_dataset_id_borehole_id_fkey`: `FOREIGN KEY (dataset_id, borehole_id) REFERENCES dataset(id, borehole_id)`
- `dataset_revision_dataset_id_source_snapshot_id_pipeline_id__key`: `UNIQUE (dataset_id, source_snapshot_id, pipeline_id, mapping_version)`
- `dataset_revision_id_borehole_id_key`: `UNIQUE (id, borehole_id)`
- `dataset_revision_id_dataset_id_key`: `UNIQUE (id, dataset_id)`
- `dataset_revision_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX dataset_revision_dataset_id_source_snapshot_id_pipeline_id__key ON core.dataset_revision USING btree (dataset_id, source_snapshot_id, pipeline_id, mapping_version)`
- `CREATE UNIQUE INDEX dataset_revision_id_borehole_id_key ON core.dataset_revision USING btree (id, borehole_id)`
- `CREATE UNIQUE INDEX dataset_revision_id_dataset_id_key ON core.dataset_revision USING btree (id, dataset_id)`
- `CREATE UNIQUE INDEX dataset_revision_pkey ON core.dataset_revision USING btree (id)`

## dataset_segment

Optional scan segment; empty for this baseline.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| borehole_id | uuid | NO | None |
| branch_id | uuid | YES | None |
| axis_id | uuid | NO | None |
| sample_no_from | bigint | NO | None |
| sample_no_to | bigint | NO | None |
| sequence_no | integer | YES | None |
| evidence | jsonb | NO | None |

Constraints:

- `dataset_segment_axis_id_dataset_revision_id_fkey`: `FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES sample_axis(id, dataset_revision_id)`
- `dataset_segment_axis_id_sample_no_from_fkey`: `FOREIGN KEY (axis_id, sample_no_from) REFERENCES scan_sample(axis_id, sample_no)`
- `dataset_segment_axis_id_sample_no_to_fkey`: `FOREIGN KEY (axis_id, sample_no_to) REFERENCES scan_sample(axis_id, sample_no)`
- `dataset_segment_branch_id_borehole_id_fkey`: `FOREIGN KEY (branch_id, borehole_id) REFERENCES borehole_branch(id, borehole_id)`
- `dataset_segment_check`: `CHECK ((sample_no_from <= sample_no_to))`
- `dataset_segment_dataset_revision_id_borehole_id_fkey`: `FOREIGN KEY (dataset_revision_id, borehole_id) REFERENCES dataset_revision(id, borehole_id)`
- `dataset_segment_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX dataset_segment_pkey ON core.dataset_segment USING btree (id)`

## image_frame

Original tray image with its dataset, log, axis and interval.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| axis_id | uuid | NO | None |
| core_interval_id | uuid | NO | None |
| log_id | uuid | NO | None |
| asset_id | uuid | NO | None |
| image_kind | text | NO | None |
| image_ordinal | integer | NO | None |
| source_tray_label | text | NO | None |
| width_px | integer | NO | None |
| height_px | integer | NO | None |
| depth_from_m | double precision | NO | None |
| depth_to_m | double precision | NO | None |
| depth_from_difference_m | double precision | NO | None |
| depth_to_difference_m | double precision | NO | None |
| depth_comparison_tolerance_m | double precision | NO | None |
| association_basis | text | NO | None |
| pixel_depth_mapping | jsonb | YES | None |

Constraints:

- `image_frame_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `image_frame_axis_id_dataset_revision_id_fkey`: `FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES sample_axis(id, dataset_revision_id)`
- `image_frame_check`: `CHECK ((depth_from_m <= depth_to_m))`
- `image_frame_core_interval_id_axis_id_fkey`: `FOREIGN KEY (core_interval_id, axis_id) REFERENCES core_interval(id, axis_id)`
- `image_frame_height_px_check`: `CHECK ((height_px > 0))`
- `image_frame_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `image_frame_log_asset_fkey`: `FOREIGN KEY (log_id, asset_id) REFERENCES log_asset(log_id, asset_id)`
- `image_frame_log_id_dataset_revision_id_fkey`: `FOREIGN KEY (log_id, dataset_revision_id) REFERENCES scan_log(id, dataset_revision_id)`
- `image_frame_log_id_image_ordinal_key`: `UNIQUE (log_id, image_ordinal)`
- `image_frame_pkey`: `PRIMARY KEY (id)`
- `image_frame_width_px_check`: `CHECK ((width_px > 0))`

Indexes:

- `CREATE UNIQUE INDEX image_frame_id_dataset_revision_id_key ON core.image_frame USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX image_frame_log_id_image_ordinal_key ON core.image_frame USING btree (log_id, image_ordinal)`
- `CREATE UNIQUE INDEX image_frame_pkey ON core.image_frame USING btree (id)`

## image_region

Reviewed row region within an image frame.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| image_frame_id | uuid | NO | None |
| region_kind | text | NO | None |
| region_ordinal | integer | NO | None |
| x_px | integer | NO | None |
| y_px | integer | NO | None |
| width_px | integer | NO | None |
| height_px | integer | NO | None |
| valid_area | jsonb | YES | None |
| coordinate_basis | text | NO | None |
| region_status | text | NO | None |
| detection_method | text | NO | None |
| review_basis | text | NO | None |
| evidence_asset_id | uuid | NO | None |

Constraints:

- `image_region_evidence_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (evidence_asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `image_region_height_px_check`: `CHECK ((height_px > 0))`
- `image_region_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `image_region_image_frame_id_dataset_revision_id_fkey`: `FOREIGN KEY (image_frame_id, dataset_revision_id) REFERENCES image_frame(id, dataset_revision_id)`
- `image_region_image_frame_id_region_ordinal_key`: `UNIQUE (image_frame_id, region_ordinal)`
- `image_region_pkey`: `PRIMARY KEY (id)`
- `image_region_region_kind_check`: `CHECK ((region_kind = 'core_row'::text))`
- `image_region_region_ordinal_check`: `CHECK ((region_ordinal >= 0))`
- `image_region_region_status_check`: `CHECK ((region_status = ANY (ARRAY['candidate'::text, 'reviewed'::text, 'unavailable'::text])))`
- `image_region_width_px_check`: `CHECK ((width_px > 0))`
- `image_region_x_px_check`: `CHECK ((x_px >= 0))`
- `image_region_y_px_check`: `CHECK ((y_px >= 0))`

Indexes:

- `CREATE UNIQUE INDEX image_region_id_dataset_revision_id_key ON core.image_region USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX image_region_image_frame_id_region_ordinal_key ON core.image_region USING btree (image_frame_id, region_ordinal)`
- `CREATE UNIQUE INDEX image_region_pkey ON core.image_region USING btree (id)`

## image_region_asset

Derived row PNG and crop transformation information.

| Column | Type | Nullable | Default |
|---|---|---|---|
| region_id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| asset_id | uuid | NO | None |
| log_id | uuid | NO | None |
| representation_kind | text | NO | None |
| width_px | integer | NO | None |
| height_px | integer | NO | None |
| transform | jsonb | NO | None |
| recipe_version | integer | NO | None |

Constraints:

- `image_region_asset_height_px_check`: `CHECK ((height_px > 0))`
- `image_region_asset_log_id_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (log_id, asset_id, dataset_revision_id) REFERENCES log_asset(log_id, asset_id, dataset_revision_id)`
- `image_region_asset_pkey`: `PRIMARY KEY (region_id, asset_id)`
- `image_region_asset_recipe_version_check`: `CHECK ((recipe_version > 0))`
- `image_region_asset_region_id_dataset_revision_id_fkey`: `FOREIGN KEY (region_id, dataset_revision_id) REFERENCES image_region(id, dataset_revision_id)`
- `image_region_asset_width_px_check`: `CHECK ((width_px > 0))`

Indexes:

- `CREATE UNIQUE INDEX image_region_asset_pkey ON core.image_region_asset USING btree (region_id, asset_id)`

## image_sample_mapping

Row-to-sample range and approximate indicator contract.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| image_region_id | uuid | NO | None |
| axis_id | uuid | NO | None |
| section_interval_id | uuid | NO | None |
| sample_no_from | bigint | NO | None |
| sample_no_to | bigint | NO | None |
| anchor_points | jsonb | YES | None |
| source_depth_direction | text | NO | None |
| direction_status | text | NO | None |
| direction_basis | text | NO | None |
| direction_evidence_asset_id | uuid | NO | None |
| mapping_level | text | NO | None |
| mapping_status | text | NO | None |
| mapping_method | text | NO | None |
| indicator_method | text | NO | None |
| indicator_version | integer | NO | None |
| indicator_status | text | NO | None |
| indicator_parameters | jsonb | NO | None |
| error_px | double precision | YES | None |
| error_depth_m | double precision | YES | None |
| evidence_asset_id | uuid | NO | None |

Constraints:

- `image_sample_mapping_axis_id_dataset_revision_id_fkey`: `FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES sample_axis(id, dataset_revision_id)`
- `image_sample_mapping_axis_id_sample_no_from_fkey`: `FOREIGN KEY (axis_id, sample_no_from) REFERENCES scan_sample(axis_id, sample_no)`
- `image_sample_mapping_axis_id_sample_no_to_fkey`: `FOREIGN KEY (axis_id, sample_no_to) REFERENCES scan_sample(axis_id, sample_no)`
- `image_sample_mapping_check`: `CHECK ((sample_no_from <= sample_no_to))`
- `image_sample_mapping_check1`: `CHECK (((indicator_method <> 'sample_index_linear'::text) OR ((indicator_version = 1) AND (indicator_status = 'approximate'::text) AND (source_depth_direction = 'left_to_right'::text) AND (indicator_parameters = '{"range_basis": "row_sample_interval", "endpoint_rule": "first_last_pixel_center", "coordinate_space": "row_crop_pixels", "single_sample_rule": "center"}'::jsonb) AND (error_px IS NULL) AND (error_depth_m IS NULL))))`
- `image_sample_mapping_direction_evidence_asset_id_dataset_r_fkey`: `FOREIGN KEY (direction_evidence_asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `image_sample_mapping_error_depth_m_check`: `CHECK (((error_depth_m IS NULL) OR ((error_depth_m >= (0)::double precision) AND (error_depth_m < 'Infinity'::double precision))))`
- `image_sample_mapping_error_px_check`: `CHECK (((error_px IS NULL) OR ((error_px >= (0)::double precision) AND (error_px < 'Infinity'::double precision))))`
- `image_sample_mapping_evidence_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (evidence_asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `image_sample_mapping_image_region_id_axis_id_sample_no_from_key`: `UNIQUE (image_region_id, axis_id, sample_no_from)`
- `image_sample_mapping_image_region_id_dataset_revision_id_fkey`: `FOREIGN KEY (image_region_id, dataset_revision_id) REFERENCES image_region(id, dataset_revision_id)`
- `image_sample_mapping_indicator_status_check`: `CHECK ((indicator_status = ANY (ARRAY['approximate'::text, 'unavailable'::text, 'calibrated'::text])))`
- `image_sample_mapping_pkey`: `PRIMARY KEY (id)`
- `image_sample_mapping_section_interval_id_axis_id_fkey`: `FOREIGN KEY (section_interval_id, axis_id) REFERENCES core_interval(id, axis_id)`

Indexes:

- `CREATE INDEX image_mapping_sample_idx ON core.image_sample_mapping USING btree (axis_id, section_interval_id, sample_no_from, sample_no_to)`
- `CREATE UNIQUE INDEX image_sample_mapping_image_region_id_axis_id_sample_no_from_key ON core.image_sample_mapping USING btree (image_region_id, axis_id, sample_no_from)`
- `CREATE UNIQUE INDEX image_sample_mapping_pkey ON core.image_sample_mapping USING btree (id)`

## ingest_run

Historical import audit, not an online ingestion interface.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| started_at | timestamp with time zone | NO | now() |
| finished_at | timestamp with time zone | YES | None |
| input_digest | text | NO | None |
| code_sha256 | text | NO | None |
| schema_sha256 | text | NO | None |
| holes | jsonb | NO | None |
| status | text | NO | None |
| detail | jsonb | NO | '{}'::jsonb |

Constraints:

- `ingest_run_pkey`: `PRIMARY KEY (id)`
- `ingest_run_status_check`: `CHECK ((status = ANY (ARRAY['running'::text, 'staged'::text, 'failed'::text])))`

Indexes:

- `CREATE UNIQUE INDEX ingest_run_pkey ON core.ingest_run USING btree (id)`

## interpretation_input

Evidence-backed links to input spectra; empty for this baseline.

| Column | Type | Nullable | Default |
|---|---|---|---|
| interpretation_set_id | uuid | NO | None |
| spectral_stream_id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| evidence | jsonb | NO | None |

Constraints:

- `interpretation_input_interpretation_set_id_dataset_revisio_fkey`: `FOREIGN KEY (interpretation_set_id, dataset_revision_id) REFERENCES interpretation_set(id, dataset_revision_id)`
- `interpretation_input_pkey`: `PRIMARY KEY (interpretation_set_id, spectral_stream_id)`
- `interpretation_input_spectral_stream_id_dataset_revision_i_fkey`: `FOREIGN KEY (spectral_stream_id, dataset_revision_id) REFERENCES spectral_stream(id, dataset_revision_id)`

Indexes:

- `CREATE UNIQUE INDEX interpretation_input_pkey ON core.interpretation_input USING btree (interpretation_set_id, spectral_stream_id)`

## interpretation_set

Source interpretation group, algorithm family, output region and s/u variant.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| source_set_code | text | NO | None |
| algorithm_family | text | YES | None |
| output_region | text | YES | None |
| variant_code | text | YES | None |
| algorithm_version | text | YES | None |
| actual_mineral_library | text | YES | None |
| parameters | jsonb | YES | None |
| grouping_basis | text | NO | None |
| input_association_status | text | NO | None |

Constraints:

- `interpretation_set_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `interpretation_set_dataset_revision_id_source_set_code_key`: `UNIQUE (dataset_revision_id, source_set_code)`
- `interpretation_set_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `interpretation_set_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX interpretation_set_dataset_revision_id_source_set_code_key ON core.interpretation_set USING btree (dataset_revision_id, source_set_code)`
- `CREATE UNIQUE INDEX interpretation_set_id_dataset_revision_id_key ON core.interpretation_set USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX interpretation_set_pkey ON core.interpretation_set USING btree (id)`

## log_asset

Association between a log and its file assets.

| Column | Type | Nullable | Default |
|---|---|---|---|
| log_id | uuid | NO | None |
| asset_id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| role | text | NO | None |

Constraints:

- `log_asset_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `log_asset_log_id_asset_id_dataset_revision_id_key`: `UNIQUE (log_id, asset_id, dataset_revision_id)`
- `log_asset_log_id_dataset_revision_id_fkey`: `FOREIGN KEY (log_id, dataset_revision_id) REFERENCES scan_log(id, dataset_revision_id)`
- `log_asset_pkey`: `PRIMARY KEY (log_id, asset_id)`

Indexes:

- `CREATE UNIQUE INDEX log_asset_log_id_asset_id_dataset_revision_id_key ON core.log_asset USING btree (log_id, asset_id, dataset_revision_id)`
- `CREATE UNIQUE INDEX log_asset_pkey ON core.log_asset USING btree (log_id, asset_id)`

## log_axis_binding

Relationship between a result log and a sample axis.

| Column | Type | Nullable | Default |
|---|---|---|---|
| log_id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| axis_id | uuid | YES | None |
| status | text | NO | None |
| basis | text | NO | None |

Constraints:

- `log_axis_binding_axis_id_dataset_revision_id_fkey`: `FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES sample_axis(id, dataset_revision_id)`
- `log_axis_binding_check`: `CHECK (((status <> 'verified'::text) OR (axis_id IS NOT NULL)))`
- `log_axis_binding_log_id_dataset_revision_id_fkey`: `FOREIGN KEY (log_id, dataset_revision_id) REFERENCES scan_log(id, dataset_revision_id)`
- `log_axis_binding_pkey`: `PRIMARY KEY (log_id)`

Indexes:

- `CREATE UNIQUE INDEX log_axis_binding_pkey ON core.log_axis_binding USING btree (log_id)`

## metric_definition

Metric name, type, units and semantic status.

| Column | Type | Nullable | Default |
|---|---|---|---|
| dataset_revision_id | uuid | NO | None |
| metric_key | text | NO | None |
| display_name | text | NO | None |
| value_type | text | YES | None |
| unit | text | YES | None |
| definition_status | text | NO | None |
| is_probability | boolean | YES | None |
| source_log_id | text | YES | None |

Constraints:

- `metric_definition_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `metric_definition_pkey`: `PRIMARY KEY (dataset_revision_id, metric_key)`

Indexes:

- `CREATE UNIQUE INDEX metric_definition_pkey ON core.metric_definition USING btree (dataset_revision_id, metric_key)`

## quality_issue

Recorded source/processing limitations, severity, evidence and impact.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| processing_step | integer | NO | None |
| code | text | NO | None |
| severity | text | NO | None |
| scope | text | NO | None |
| detail | text | NO | None |
| evidence | jsonb | YES | None |
| impact | text | NO | None |

Constraints:

- `quality_issue_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `quality_issue_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX quality_issue_pkey ON core.quality_issue USING btree (id)`

## release_dataset

Dataset revision selected by a release.

| Column | Type | Nullable | Default |
|---|---|---|---|
| release_id | uuid | NO | None |
| dataset_id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |

Constraints:

- `release_dataset_dataset_revision_id_dataset_id_fkey`: `FOREIGN KEY (dataset_revision_id, dataset_id) REFERENCES dataset_revision(id, dataset_id)`
- `release_dataset_pkey`: `PRIMARY KEY (release_id, dataset_id)`
- `release_dataset_release_id_fkey`: `FOREIGN KEY (release_id) REFERENCES data_release(id)`

Indexes:

- `CREATE UNIQUE INDEX release_dataset_pkey ON core.release_dataset USING btree (release_id, dataset_id)`

## revision_validation

Recorded validation result for a prepared revision.

| Column | Type | Nullable | Default |
|---|---|---|---|
| dataset_revision_id | uuid | NO | None |
| validated_at | timestamp with time zone | NO | now() |
| input_digest | text | NO | None |
| verification_code_sha256 | text | NO | None |
| result | jsonb | NO | None |

Constraints:

- `revision_validation_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `revision_validation_pkey`: `PRIMARY KEY (dataset_revision_id)`

Indexes:

- `CREATE UNIQUE INDEX revision_validation_pkey ON core.revision_validation USING btree (dataset_revision_id)`

## sample_axis

Verified ordered sample coordinate system for a dataset revision.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| sample_count | bigint | NO | None |
| depth_min_m | double precision | NO | None |
| depth_max_m | double precision | NO | None |
| coordinate_kind | text | NO | 'measured_depth_m'::text |
| alignment_evidence | jsonb | NO | None |

Constraints:

- `sample_axis_check`: `CHECK ((depth_min_m <= depth_max_m))`
- `sample_axis_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `sample_axis_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `sample_axis_pkey`: `PRIMARY KEY (id)`
- `sample_axis_sample_count_check`: `CHECK ((sample_count > 0))`

Indexes:

- `CREATE UNIQUE INDEX sample_axis_id_dataset_revision_id_key ON core.sample_axis USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX sample_axis_pkey ON core.sample_axis USING btree (id)`

## scan_log

Result or media log metadata, metric, interpretation group and availability.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| source_log_id | text | NO | None |
| source_log_name | text | NO | None |
| log_kind | text | NO | None |
| source_log_type | text | YES | None |
| source_algorithm_id | text | YES | None |
| source_mask_log_id | text | YES | None |
| source_is_public | boolean | YES | None |
| source_created_at | timestamp with time zone | YES | None |
| source_modified_at | timestamp with time zone | YES | None |
| source_status | text | YES | None |
| metric_key | text | YES | None |
| metric_code | text | YES | None |
| component_rank | integer | YES | None |
| interpretation_set_id | uuid | YES | None |
| spectral_stream_id | uuid | YES | None |
| coordinate_kind | text | YES | None |
| observed_row_count | bigint | YES | None |
| observed_value_kind | text | YES | None |
| unit | text | YES | None |
| origin | text | YES | None |
| availability_status | text | NO | None |
| omission_reason | text | YES | None |
| definition_status | text | NO | None |
| array_layout_status | text | YES | None |
| per_sample_publication_allowed | boolean | NO | false |
| declared_channel_count | integer | YES | None |
| observed_channel_count | integer | YES | None |
| physical_geometry_status | text | YES | None |
| null_tokens | jsonb | YES | None |
| source_metadata_file | text | NO | None |
| normalized_metadata | jsonb | NO | None |

Constraints:

- `scan_log_component_rank_check`: `CHECK (((component_rank IS NULL) OR (component_rank > 0)))`
- `scan_log_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `scan_log_dataset_revision_id_log_kind_source_log_id_key`: `UNIQUE (dataset_revision_id, log_kind, source_log_id)`
- `scan_log_dataset_revision_id_metric_key_fkey`: `FOREIGN KEY (dataset_revision_id, metric_key) REFERENCES metric_definition(dataset_revision_id, metric_key)`
- `scan_log_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `scan_log_interpretation_set_id_dataset_revision_id_fkey`: `FOREIGN KEY (interpretation_set_id, dataset_revision_id) REFERENCES interpretation_set(id, dataset_revision_id)`
- `scan_log_pkey`: `PRIMARY KEY (id)`
- `scan_log_spectral_stream_id_dataset_revision_id_fkey`: `FOREIGN KEY (spectral_stream_id, dataset_revision_id) REFERENCES spectral_stream(id, dataset_revision_id)`

Indexes:

- `CREATE UNIQUE INDEX scan_log_dataset_revision_id_log_kind_source_log_id_key ON core.scan_log USING btree (dataset_revision_id, log_kind, source_log_id)`
- `CREATE INDEX scan_log_filter_idx ON core.scan_log USING btree (dataset_revision_id, log_kind, interpretation_set_id, metric_key)`
- `CREATE UNIQUE INDEX scan_log_id_dataset_revision_id_key ON core.scan_log USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX scan_log_pkey ON core.scan_log USING btree (id)`

## scan_sample

Real sample number, measured depth and tray/Section membership.

| Column | Type | Nullable | Default |
|---|---|---|---|
| axis_id | uuid | NO | None |
| sample_no | bigint | NO | None |
| md_m | double precision | NO | None |
| tray_interval_id | uuid | NO | None |
| section_interval_id | uuid | NO | None |
| tray_sample_no | bigint | NO | None |
| section_sample_no | bigint | NO | None |
| section_distance_mm | double precision | YES | None |

Constraints:

- `scan_sample_axis_id_fkey`: `FOREIGN KEY (axis_id) REFERENCES sample_axis(id)`
- `scan_sample_md_m_check`: `CHECK (((md_m > '-Infinity'::double precision) AND (md_m < 'Infinity'::double precision)))`
- `scan_sample_pkey`: `PRIMARY KEY (axis_id, sample_no)`
- `scan_sample_sample_no_check`: `CHECK ((sample_no >= 0))`
- `scan_sample_section_interval_id_axis_id_fkey`: `FOREIGN KEY (section_interval_id, axis_id) REFERENCES core_interval(id, axis_id)`
- `scan_sample_section_sample_no_check`: `CHECK ((section_sample_no > 0))`
- `scan_sample_tray_interval_id_axis_id_fkey`: `FOREIGN KEY (tray_interval_id, axis_id) REFERENCES core_interval(id, axis_id)`
- `scan_sample_tray_sample_no_check`: `CHECK ((tray_sample_no > 0))`

Indexes:

- `CREATE INDEX sample_depth_idx ON core.scan_sample USING btree (axis_id, md_m, sample_no)`
- `CREATE UNIQUE INDEX scan_sample_pkey ON core.scan_sample USING btree (axis_id, sample_no)`

## schema_migration

Applied migration names, timestamps and original checksums.

| Column | Type | Nullable | Default |
|---|---|---|---|
| name | text | NO | None |
| sha256 | text | NO | None |
| applied_at | timestamp with time zone | NO | now() |

Constraints:

- `schema_migration_pkey`: `PRIMARY KEY (name)`

Indexes:

- `CREATE UNIQUE INDEX schema_migration_pkey ON core.schema_migration USING btree (name)`

## source_document

Preserved original source document content and asset reference.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| asset_id | uuid | NO | None |
| document_name | text | NO | None |
| content_json | jsonb | YES | None |
| content_text | text | YES | None |

Constraints:

- `source_document_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `source_document_check`: `CHECK (((content_json IS NOT NULL) OR (content_text IS NOT NULL)))`
- `source_document_dataset_revision_id_document_name_key`: `UNIQUE (dataset_revision_id, document_name)`
- `source_document_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX source_document_dataset_revision_id_document_name_key ON core.source_document USING btree (dataset_revision_id, document_name)`
- `CREATE UNIQUE INDEX source_document_pkey ON core.source_document USING btree (id)`

## source_reference

Source references and their resolution evidence.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| role | text | NO | None |
| source_target_id | text | NO | None |
| target_log_id | uuid | YES | None |
| status | text | NO | None |
| evidence | jsonb | NO | None |

Constraints:

- `source_reference_check`: `CHECK (((status <> 'resolved'::text) OR (target_log_id IS NOT NULL)))`
- `source_reference_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `source_reference_pkey`: `PRIMARY KEY (id)`
- `source_reference_target_log_id_dataset_revision_id_fkey`: `FOREIGN KEY (target_log_id, dataset_revision_id) REFERENCES scan_log(id, dataset_revision_id)`

Indexes:

- `CREATE UNIQUE INDEX source_reference_pkey ON core.source_reference USING btree (id)`

## spectral_array

F32 array layout, strides, counts, provenance and verified order.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| log_id | uuid | NO | None |
| asset_id | uuid | NO | None |
| spectral_stream_id | uuid | NO | None |
| sample_count | bigint | NO | None |
| channel_count | integer | NO | None |
| dtype_code | text | NO | None |
| matrix_order | text | NO | None |
| data_offset_bytes | bigint | NO | None |
| sample_stride_bytes | bigint | NO | None |
| channel_stride_bytes | integer | NO | None |
| layout_status | text | NO | None |
| value_unit | text | YES | None |
| scaling_applied | boolean | NO | None |
| evidence_asset_id | uuid | NO | None |
| evidence | jsonb | NO | None |

Constraints:

- `spectral_array_channel_count_check`: `CHECK ((channel_count > 0))`
- `spectral_array_channel_stride_bytes_check`: `CHECK ((channel_stride_bytes = 4))`
- `spectral_array_check`: `CHECK ((sample_stride_bytes = ((channel_count)::bigint * 4)))`
- `spectral_array_data_offset_bytes_check`: `CHECK ((data_offset_bytes >= 0))`
- `spectral_array_dtype_code_check`: `CHECK ((dtype_code = '<f4'::text))`
- `spectral_array_evidence_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (evidence_asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `spectral_array_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `spectral_array_layout_status_check`: `CHECK ((layout_status = ANY (ARRAY['verified_sample_major'::text, 'unconfirmed'::text])))`
- `spectral_array_log_id_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (log_id, asset_id, dataset_revision_id) REFERENCES log_asset(log_id, asset_id, dataset_revision_id)`
- `spectral_array_log_id_asset_id_key`: `UNIQUE (log_id, asset_id)`
- `spectral_array_matrix_order_check`: `CHECK ((matrix_order = 'C'::text))`
- `spectral_array_pkey`: `PRIMARY KEY (id)`
- `spectral_array_sample_count_check`: `CHECK ((sample_count > 0))`
- `spectral_array_scaling_applied_check`: `CHECK ((NOT scaling_applied))`
- `spectral_array_spectral_stream_id_dataset_revision_id_fkey`: `FOREIGN KEY (spectral_stream_id, dataset_revision_id) REFERENCES spectral_stream(id, dataset_revision_id)`

Indexes:

- `CREATE UNIQUE INDEX spectral_array_id_dataset_revision_id_key ON core.spectral_array USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX spectral_array_log_id_asset_id_key ON core.spectral_array USING btree (log_id, asset_id)`
- `CREATE UNIQUE INDEX spectral_array_pkey ON core.spectral_array USING btree (id)`

## spectral_block

Verified byte block for ranged spectrum reading.

| Column | Type | Nullable | Default |
|---|---|---|---|
| spectral_array_id | uuid | NO | None |
| block_no | integer | NO | None |
| source_row_from | bigint | NO | None |
| source_row_to_exclusive | bigint | NO | None |
| byte_offset | bigint | NO | None |
| byte_length | bigint | NO | None |
| sha256 | text | NO | None |

Constraints:

- `spectral_block_block_no_check`: `CHECK ((block_no >= 0))`
- `spectral_block_byte_length_check`: `CHECK ((byte_length > 0))`
- `spectral_block_byte_offset_check`: `CHECK ((byte_offset >= 0))`
- `spectral_block_check`: `CHECK ((source_row_to_exclusive > source_row_from))`
- `spectral_block_pkey`: `PRIMARY KEY (spectral_array_id, block_no)`
- `spectral_block_sha256_check`: `CHECK ((sha256 ~ '^[a-f0-9]{64}$'::text))`
- `spectral_block_source_row_from_check`: `CHECK ((source_row_from >= 0))`
- `spectral_block_spectral_array_id_fkey`: `FOREIGN KEY (spectral_array_id) REFERENCES spectral_array(id)`
- `spectral_block_spectral_array_id_source_row_from_key`: `UNIQUE (spectral_array_id, source_row_from)`

Indexes:

- `CREATE UNIQUE INDEX spectral_block_pkey ON core.spectral_block USING btree (spectral_array_id, block_no)`
- `CREATE UNIQUE INDEX spectral_block_spectral_array_id_source_row_from_key ON core.spectral_block USING btree (spectral_array_id, source_row_from)`

## spectral_sample_map

Mapping between source matrix rows and real sample numbers.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| spectral_array_id | uuid | NO | None |
| axis_id | uuid | NO | None |
| source_row_from | bigint | NO | None |
| source_row_to | bigint | NO | None |
| sample_no_from | bigint | NO | None |
| sample_no_to | bigint | NO | None |
| mapping_kind | text | NO | None |
| binding_status | text | NO | None |
| evidence_asset_id | uuid | NO | None |
| basis | text | NO | None |

Constraints:

- `spectral_sample_map_axis_id_dataset_revision_id_fkey`: `FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES sample_axis(id, dataset_revision_id)`
- `spectral_sample_map_axis_id_sample_no_from_fkey`: `FOREIGN KEY (axis_id, sample_no_from) REFERENCES scan_sample(axis_id, sample_no)`
- `spectral_sample_map_axis_id_sample_no_to_fkey`: `FOREIGN KEY (axis_id, sample_no_to) REFERENCES scan_sample(axis_id, sample_no)`
- `spectral_sample_map_binding_status_check`: `CHECK ((binding_status = 'verified'::text))`
- `spectral_sample_map_check`: `CHECK ((source_row_from <= source_row_to))`
- `spectral_sample_map_check1`: `CHECK ((sample_no_from <= sample_no_to))`
- `spectral_sample_map_check2`: `CHECK (((source_row_to - source_row_from) = (sample_no_to - sample_no_from)))`
- `spectral_sample_map_evidence_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (evidence_asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `spectral_sample_map_mapping_kind_check`: `CHECK ((mapping_kind = 'identity_range'::text))`
- `spectral_sample_map_pkey`: `PRIMARY KEY (id)`
- `spectral_sample_map_source_row_from_check`: `CHECK ((source_row_from >= 0))`
- `spectral_sample_map_spectral_array_id_dataset_revision_id_fkey`: `FOREIGN KEY (spectral_array_id, dataset_revision_id) REFERENCES spectral_array(id, dataset_revision_id)`
- `spectral_sample_map_spectral_array_id_source_row_from_key`: `UNIQUE (spectral_array_id, source_row_from)`

Indexes:

- `CREATE UNIQUE INDEX spectral_sample_map_pkey ON core.spectral_sample_map USING btree (id)`
- `CREATE UNIQUE INDEX spectral_sample_map_spectral_array_id_source_row_from_key ON core.spectral_sample_map USING btree (spectral_array_id, source_row_from)`

## spectral_stream

Physical spectral region, wavelength unit and full wavelength vector.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| dataset_revision_id | uuid | NO | None |
| region_code | text | NO | None |
| wavelength_unit | text | NO | None |
| wavelength_count | integer | NO | None |
| wavelengths | double precision[] | NO | None |
| classification_basis | text | NO | None |

Constraints:

- `spectral_stream_check`: `CHECK ((cardinality(wavelengths) = wavelength_count))`
- `spectral_stream_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `spectral_stream_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `spectral_stream_pkey`: `PRIMARY KEY (id)`
- `spectral_stream_wavelength_count_check`: `CHECK ((wavelength_count > 0))`

Indexes:

- `CREATE UNIQUE INDEX spectral_stream_id_dataset_revision_id_key ON core.spectral_stream USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX spectral_stream_pkey ON core.spectral_stream USING btree (id)`

## survey_station

Optional survey measurements; empty for this baseline.

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NO | None |
| borehole_id | uuid | NO | None |
| branch_id | uuid | YES | None |
| survey_version | text | NO | None |
| md_m | double precision | NO | None |
| azimuth_deg | double precision | NO | None |
| inclination_deg | double precision | NO | None |
| angle_convention | text | NO | None |
| evidence | jsonb | NO | None |

Constraints:

- `survey_station_azimuth_deg_check`: `CHECK (((azimuth_deg >= (0)::double precision) AND (azimuth_deg < (360)::double precision)))`
- `survey_station_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `survey_station_branch_id_borehole_id_fkey`: `FOREIGN KEY (branch_id, borehole_id) REFERENCES borehole_branch(id, borehole_id)`
- `survey_station_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX survey_station_pkey ON core.survey_station USING btree (id)`

