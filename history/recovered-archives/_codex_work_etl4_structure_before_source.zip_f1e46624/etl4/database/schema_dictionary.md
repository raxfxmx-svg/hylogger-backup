# Complete database field dictionary

Generated from the PostgreSQL catalog; schema digest `c54652c8be1cf82d7f90f1bcca7ac196661c9d444311f5c3ed51a24f3c78ad66`. Types, nullability, defaults, and constraints come from the created database.
SQL NULL means missing, unconfirmed, or inapplicable; state and evidence columns record the reason. Common fields use explicit types, and original/normalized objects are retained in full.

**schema_migration**

Database schema change history.Source: Migration SHA256; step 8.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `name` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `sha256` | `text` | NO | — / status or identifier | SHA256 of file or document bytes, not an identification confidence score. | `None` |
| `applied_at` | `timestamp with time zone` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `now()` |

Constraints:

- `schema_migration_pkey`: `PRIMARY KEY (name)`

Indexes:

- `CREATE UNIQUE INDEX schema_migration_pkey ON core.schema_migration USING btree (name)`

Write validation and immutability triggers:

No user-defined triggers; the constraints and role permissions above still apply.

**borehole**

Stable borehole identity; source IDs are unique within provider_code.Source: Step 3 borehole.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `provider_code` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_hole_id` | `text` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_identifier` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `borehole_pkey`: `PRIMARY KEY (id)`
- `borehole_provider_code_source_hole_id_key`: `UNIQUE (provider_code, source_hole_id)`

Indexes:

- `CREATE UNIQUE INDEX borehole_pkey ON core.borehole USING btree (id)`
- `CREATE UNIQUE INDEX borehole_provider_code_source_hole_id_key ON core.borehole USING btree (provider_code, source_hole_id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.borehole FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**borehole_revision**

Borehole metadata snapshot; organization names retain their source roles.Source: Step 3 borehole; metadata_revision_id → id.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `borehole_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_name` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `provider_code` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `custodian_name` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `driller_name` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `operator_name` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `project_name` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `drilling_method` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `reported_length_m` | `double precision` | YES | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `drill_start_date` | `date` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `drill_end_date` | `date` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `actual_drill_date_precision` | `text` | NO | — / status or identifier | Confirmed precision of the actual date; a supplied date alone does not confirm day-level precision. | `None` |
| `collar_geom` | `geometry(Point,4326)` | YES | — / status or identifier | Two-dimensional EPSG:4326 Point from confirmed longitude and latitude; not a borehole trajectory. | `None` |
| `coordinate_basis` | `text` | YES | — / status or identifier | Native decoded pixels, top-left origin, xy coordinates, and a crop rectangle with exclusive upper bounds. | `None` |
| `horizontal_crs` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `vertical_crs` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `elevation_m` | `double precision` | YES | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `azimuth_deg` | `double precision` | YES | degree; inclination conventions recorded separately | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `inclination_deg` | `double precision` | YES | degree; inclination conventions recorded separately | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `inclination_convention` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `orientation_missing_reason` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `orientation_missing_reason_source` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `trajectory_status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `normalized_metadata` | `jsonb` | NO | — / status or identifier | Complete normalized JSONB object, including source attributes without dedicated columns. Original documents remain in source_document and source files. | `None` |

Constraints:

- `borehole_revision_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `borehole_revision_id_borehole_id_key`: `UNIQUE (id, borehole_id)`
- `borehole_revision_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE INDEX borehole_collar_gist ON core.borehole_revision USING gist (collar_geom)`
- `CREATE UNIQUE INDEX borehole_revision_id_borehole_id_key ON core.borehole_revision USING btree (id, borehole_id)`
- `CREATE UNIQUE INDEX borehole_revision_pkey ON core.borehole_revision USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.borehole_revision FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**dataset**

A borehole may contain multiple datasets; this does not establish branches.Source: Step 3 dataset.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `borehole_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_dataset_id` | `text` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |

Constraints:

- `dataset_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `dataset_borehole_id_source_dataset_id_key`: `UNIQUE (borehole_id, source_dataset_id)`
- `dataset_id_borehole_id_key`: `UNIQUE (id, borehole_id)`
- `dataset_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX dataset_borehole_id_source_dataset_id_key ON core.dataset USING btree (borehole_id, source_dataset_id)`
- `CREATE UNIQUE INDEX dataset_id_borehole_id_key ON core.dataset USING btree (id, borehole_id)`
- `CREATE UNIQUE INDEX dataset_pkey ON core.dataset USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.dataset FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**dataset_revision**

Scan and processing revision; changing organization and instrument attributes belong to the revision.Source: Step 3 dataset + dataset_revision; Step 9 input_digest.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `borehole_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `borehole_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_dataset_name` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_borehole_uri` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_project_name` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `instrument_name` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `owner_name` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_snapshot_id` | `text` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `pipeline_id` | `text` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `input_digest` | `text` | NO | — / status or identifier | Meaning depends on the table: dataset_revision hashes prepared data, sample bindings, and media; revision_validation binds the same digest; ingest_run identifies the batch. Different content for the same data revision is rejected. | `None` |
| `mapping_version` | `integer` | NO | — / status or identifier | Database mapping version: 1 for the initial import and 2 for the media extension; earlier snapshots are retained. | `None` |
| `source_created_at` | `timestamp with time zone` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_modified_at` | `timestamp with time zone` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_download_started_at` | `timestamp with time zone` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_download_finished_at` | `timestamp with time zone` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `normalized_metadata` | `jsonb` | NO | — / status or identifier | Complete normalized JSONB object, including source attributes without dedicated columns. Original documents remain in source_document and source files. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.dataset_revision FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**sample_axis**

Validated common sample axis and alignment evidence.Source: Step 4 alignment_report.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `sample_count` | `bigint` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `depth_min_m` | `double precision` | NO | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `depth_max_m` | `double precision` | NO | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `coordinate_kind` | `text` | NO | — / status or identifier | Distinguishes depth in meters, sample indexes, and interval indexes; identical numeric names must not mix units. | `'measured_depth_m'::text` |
| `alignment_evidence` | `jsonb` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `sample_axis_check`: `CHECK ((depth_min_m <= depth_max_m))`
- `sample_axis_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `sample_axis_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `sample_axis_pkey`: `PRIMARY KEY (id)`
- `sample_axis_sample_count_check`: `CHECK ((sample_count > 0))`

Indexes:

- `CREATE UNIQUE INDEX sample_axis_id_dataset_revision_id_key ON core.sample_axis USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX sample_axis_pkey ON core.sample_axis USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.sample_axis FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**scan_sample**

Sample position within an axis; sample_no starts at 0 and repeated depths are valid.Source: Step 5 sample_axis.parquet + Step 4 core_intervals.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `axis_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `sample_no` | `bigint` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `md_m` | `double precision` | NO | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `tray_interval_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `section_interval_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `tray_sample_no` | `bigint` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `section_sample_no` | `bigint` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `section_distance_mm` | `double precision` | YES | mm | Matching field from the table's listed source; see the table description and source mapping. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.scan_sample FOR EACH ROW EXECUTE FUNCTION reject_mutation()`
- `validate_sample_relations`: `CREATE TRIGGER validate_sample_relations AFTER INSERT ON core.scan_sample REFERENCING NEW TABLE AS inserted_samples FOR EACH STATEMENT EXECUTE FUNCTION check_inserted_samples()`

**core_interval**

Tray and section intervals with inclusive sample bounds; source_label retains leading zeros.Source: Step 4 core_intervals.json.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `axis_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `interval_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `ordinal` | `integer` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_label` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `parent_interval_id` | `uuid` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `sample_no_from` | `bigint` | NO | — / status or identifier | Zero-based inclusive start of the real sample interval; samples at repeated depths remain distinct. | `None` |
| `sample_no_to` | `bigint` | NO | — / status or identifier | Inclusive final real sample in the interval. | `None` |
| `observed_depth_min_m` | `double precision` | YES | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `observed_depth_max_m` | `double precision` | YES | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_log_id` | `text` | NO | — / status or identifier | Original log identifier, preserved as text rather than forced into a PostgreSQL UUID. | `None` |
| `source_data_row` | `bigint` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_interval_convention` | `text` | NO | — / status or identifier | Currently closed: both sample_no_from and sample_no_to are included. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.core_interval FOR EACH ROW EXECUTE FUNCTION reject_mutation()`
- `validate_interval_relations`: `CREATE TRIGGER validate_interval_relations AFTER INSERT ON core.core_interval REFERENCING NEW TABLE AS inserted_intervals FOR EACH STATEMENT EXECUTE FUNCTION check_inserted_intervals()`

**spectral_stream**

Physical VSWIR/TIR wavelength axes, separate from interpretation regions.Source: Step 3 spectral_streams.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `region_code` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `wavelength_unit` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `wavelength_count` | `integer` | NO | see wavelength_unit / channel count | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `wavelengths` | `double precision[]` | NO | see wavelength_unit / channel count | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `classification_basis` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `spectral_stream_check`: `CHECK ((cardinality(wavelengths) = wavelength_count))`
- `spectral_stream_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `spectral_stream_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `spectral_stream_pkey`: `PRIMARY KEY (id)`
- `spectral_stream_wavelength_count_check`: `CHECK ((wavelength_count > 0))`

Indexes:

- `CREATE UNIQUE INDEX spectral_stream_id_dataset_revision_id_key ON core.spectral_stream USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX spectral_stream_pkey ON core.spectral_stream USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.spectral_stream FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**interpretation_set**

Algorithm family, VNIR/SWIR/TIR region, and s/u result variant; no inferred upstream processing batch.Source: Step 3 interpretation_sets.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_set_code` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `algorithm_family` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `output_region` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `variant_code` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `algorithm_version` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `actual_mineral_library` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `parameters` | `jsonb` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `grouping_basis` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `input_association_status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `interpretation_set_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `interpretation_set_dataset_revision_id_source_set_code_key`: `UNIQUE (dataset_revision_id, source_set_code)`
- `interpretation_set_id_dataset_revision_id_key`: `UNIQUE (id, dataset_revision_id)`
- `interpretation_set_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX interpretation_set_dataset_revision_id_source_set_code_key ON core.interpretation_set USING btree (dataset_revision_id, source_set_code)`
- `CREATE UNIQUE INDEX interpretation_set_id_dataset_revision_id_key ON core.interpretation_set USING btree (id, dataset_revision_id)`
- `CREATE UNIQUE INDEX interpretation_set_pkey ON core.interpretation_set USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.interpretation_set FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**interpretation_input**

Only evidence-backed input relationships; similar regions do not establish a relationship.Source: Step 3 interpretation_inputs; empty in this batch.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `interpretation_set_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `spectral_stream_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `evidence` | `jsonb` | NO | — / status or identifier | Original or normalized processing evidence; does not infer missing facts. | `None` |

Constraints:

- `interpretation_input_interpretation_set_id_dataset_revisio_fkey`: `FOREIGN KEY (interpretation_set_id, dataset_revision_id) REFERENCES interpretation_set(id, dataset_revision_id)`
- `interpretation_input_pkey`: `PRIMARY KEY (interpretation_set_id, spectral_stream_id)`
- `interpretation_input_spectral_stream_id_dataset_revision_i_fkey`: `FOREIGN KEY (spectral_stream_id, dataset_revision_id) REFERENCES spectral_stream(id, dataset_revision_id)`

Indexes:

- `CREATE UNIQUE INDEX interpretation_input_pkey ON core.interpretation_input USING btree (interpretation_set_id, spectral_stream_id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.interpretation_input FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**metric_definition**

Metric semantics; unknown or inapplicable probability attributes may be NULL, and Wt is not a probability.Source: Step 3 metric_definitions.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `metric_key` | `text` | NO | — / status or identifier | Metric key within a revision; known metrics use their semantics, while auxiliary metrics use source_log:<source ID>. | `None` |
| `display_name` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `value_type` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `unit` | `text` | YES | metric unit; NULL when absent | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `definition_status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `is_probability` | `boolean` | YES | — / status or identifier | true/false/NULL; NULL means unknown or inapplicable and must not be treated as 0. | `None` |
| `source_log_id` | `text` | YES | — / status or identifier | Original log identifier, preserved as text rather than forced into a PostgreSQL UUID. | `None` |

Constraints:

- `metric_definition_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `metric_definition_pkey`: `PRIMARY KEY (dataset_revision_id, metric_key)`

Indexes:

- `CREATE UNIQUE INDEX metric_definition_pkey ON core.metric_definition USING btree (dataset_revision_id, metric_key)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.metric_definition FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**scan_log**

All source logs, including duplicate names and metadata-only records, belong to their own dataset revision.Source: Step 3/32 logs; matching fields map directly and extra source attributes remain in normalized_metadata.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_log_id` | `text` | NO | — / status or identifier | Original log identifier, preserved as text rather than forced into a PostgreSQL UUID. | `None` |
| `source_log_name` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `log_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_log_type` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_algorithm_id` | `text` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_mask_log_id` | `text` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_is_public` | `boolean` | YES | — / status or identifier | Upstream public flag, independent of s/u, identification quality, or this site's authorization. | `None` |
| `source_created_at` | `timestamp with time zone` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_modified_at` | `timestamp with time zone` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_status` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `metric_key` | `text` | YES | — / status or identifier | Metric key within a revision; known metrics use their semantics, while auxiliary metrics use source_log:<source ID>. | `None` |
| `metric_code` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `component_rank` | `integer` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `interpretation_set_id` | `uuid` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `spectral_stream_id` | `uuid` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `coordinate_kind` | `text` | YES | — / status or identifier | Distinguishes depth in meters, sample indexes, and interval indexes; identical numeric names must not mix units. | `None` |
| `observed_row_count` | `bigint` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `observed_value_kind` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `unit` | `text` | YES | metric unit; NULL when absent | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `origin` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `availability_status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `omission_reason` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `definition_status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `array_layout_status` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `per_sample_publication_allowed` | `boolean` | NO | — / status or identifier | Whether per-sample spectral access is validated. Validated physical F32 data uses true; metadata-only logs remain false. | `false` |
| `declared_channel_count` | `integer` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `observed_channel_count` | `integer` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `physical_geometry_status` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `null_tokens` | `jsonb` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_metadata_file` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `normalized_metadata` | `jsonb` | NO | — / status or identifier | Complete normalized JSONB object, including source attributes without dedicated columns. Original documents remain in source_document and source files. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.scan_log FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**log_axis_binding**

Step 3 pending_step_4 is not treated as the final binding state.Source: Step 4 axis_bindings takes precedence; step 9 explicitly registers unbound states.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `log_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `axis_id` | `uuid` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `basis` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `log_axis_binding_axis_id_dataset_revision_id_fkey`: `FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES sample_axis(id, dataset_revision_id)`
- `log_axis_binding_check`: `CHECK (((status <> 'verified'::text) OR (axis_id IS NOT NULL)))`
- `log_axis_binding_log_id_dataset_revision_id_fkey`: `FOREIGN KEY (log_id, dataset_revision_id) REFERENCES scan_log(id, dataset_revision_id)`
- `log_axis_binding_pkey`: `PRIMARY KEY (log_id)`

Indexes:

- `CREATE UNIQUE INDEX log_axis_binding_pkey ON core.log_axis_binding USING btree (log_id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.log_axis_binding FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**asset**

File identity, bytes, and hash; semantic state is independent of file existence.Source: Step 5 assets/raw_assets; processing evidence locked by step 7.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `asset_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `representation` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `logical_path` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `sha256` | `text` | NO | — / status or identifier | SHA256 of file or document bytes, not an identification confidence score. | `None` |
| `byte_size` | `bigint` | NO | byte | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `media_type` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `payload_status` | `text` | NO | — / status or identifier | Whether a physical file exists; metadata-only logs do not create fictitious file records. | `'present'::text` |
| `semantic_status` | `text` | NO | — / status or identifier | Semantic/calibration state, separate from payload_status and access_status. | `None` |
| `provenance` | `jsonb` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.asset FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**asset_location**

An asset may have multiple stored copies; credentials are never stored in the database.Source: Step 9 local root key and relative path.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `asset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `backend` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `root_key` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `object_key` | `text` | NO | — / status or identifier | Path/object key relative to root_key; no absolute paths, parent traversal, or signed URLs. | `None` |
| `access_status` | `text` | NO | — / status or identifier | Whether a copy is accessible: verified_local locally, or verified_remote from cloud upload receipts. | `None` |
| `verified_sha256` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `asset_location_asset_id_backend_root_key_object_key_key`: `UNIQUE (asset_id, backend, root_key, object_key)`
- `asset_location_asset_id_fkey`: `FOREIGN KEY (asset_id) REFERENCES asset(id)`
- `asset_location_content_identity_fkey`: `FOREIGN KEY (asset_id, verified_sha256) REFERENCES asset(id, sha256)`
- `asset_location_object_key_check`: `CHECK ((object_key !~ '(^[/\\]|(^|[/\\])\.\.([/\\]|$)|:)'::text))`
- `asset_location_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX asset_location_asset_id_backend_root_key_object_key_key ON core.asset_location USING btree (asset_id, backend, root_key, object_key)`
- `CREATE UNIQUE INDEX asset_location_pkey ON core.asset_location USING btree (id)`

Write validation and immutability triggers:

No user-defined triggers; the constraints and role permissions above still apply.

**log_asset**

Links logs to source and canonical files; metadata_only logs may have no record.Source: Step 3 payload_paths + Step 5 source_log_id.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `log_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `asset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `role` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `log_asset_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `log_asset_log_id_asset_id_dataset_revision_id_key`: `UNIQUE (log_id, asset_id, dataset_revision_id)`
- `log_asset_log_id_dataset_revision_id_fkey`: `FOREIGN KEY (log_id, dataset_revision_id) REFERENCES scan_log(id, dataset_revision_id)`
- `log_asset_pkey`: `PRIMARY KEY (log_id, asset_id)`

Indexes:

- `CREATE UNIQUE INDEX log_asset_log_id_asset_id_dataset_revision_id_key ON core.log_asset USING btree (log_id, asset_id, dataset_revision_id)`
- `CREATE UNIQUE INDEX log_asset_pkey ON core.log_asset USING btree (log_id, asset_id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.log_asset FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**data_chunk**

Parquet row-group bounds and integrity indexes.Source: Step 5/32 assets[].row_groups / logical_group_sha256.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `asset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `axis_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `log_id` | `uuid` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `row_group` | `integer` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_row_from` | `bigint` | NO | — / status or identifier | Zero-based row within the source payload; complete F32 rows match sample_no in this batch and are still read through validated mappings. | `None` |
| `source_row_to_exclusive` | `bigint` | NO | — / status or identifier | Exclusive upper source-row bound, unlike inclusive tray/section sample_no_to. | `None` |
| `row_count` | `integer` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `coordinate_kind` | `text` | NO | — / status or identifier | Distinguishes depth in meters, sample indexes, and interval indexes; identical numeric names must not mix units. | `None` |
| `coordinate_min` | `double precision` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `coordinate_max` | `double precision` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `logical_sha256` | `text` | NO | — / status or identifier | Step 5 row-group digest of values, nulls, and source row order. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.data_chunk FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**image_frame**

Thumbnails and trays retain both depth sets and their differences; no pixel-level calibration.Source: Step 4 image_frames; source_log_id/source_path map to internal foreign keys.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `axis_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `core_interval_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `log_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `asset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `image_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `image_ordinal` | `integer` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_tray_label` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `width_px` | `integer` | NO | pixel | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `height_px` | `integer` | NO | pixel | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `depth_from_m` | `double precision` | NO | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `depth_to_m` | `double precision` | NO | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `depth_from_difference_m` | `double precision` | NO | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `depth_to_difference_m` | `double precision` | NO | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `depth_comparison_tolerance_m` | `double precision` | NO | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `association_basis` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `pixel_depth_mapping` | `jsonb` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.image_frame FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**source_document**

13 original JSON documents per borehole and text files; original XML remains inside the source datasets.json document.Source: Step 3 raw_metadata + original text files.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `asset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `document_name` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `content_json` | `jsonb` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `content_text` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `source_document_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES asset(id, dataset_revision_id)`
- `source_document_check`: `CHECK (((content_json IS NOT NULL) OR (content_text IS NOT NULL)))`
- `source_document_dataset_revision_id_document_name_key`: `UNIQUE (dataset_revision_id, document_name)`
- `source_document_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX source_document_dataset_revision_id_document_name_key ON core.source_document USING btree (dataset_revision_id, document_name)`
- `CREATE UNIQUE INDEX source_document_pkey ON core.source_document USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.source_document FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**source_reference**

Exact source ID resolution; unresolved references remain queryable.Source: Step 3 source_references.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `role` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_target_id` | `text` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `target_log_id` | `uuid` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `evidence` | `jsonb` | NO | — / status or identifier | Original or normalized processing evidence; does not infer missing facts. | `None` |

Constraints:

- `source_reference_check`: `CHECK (((status <> 'resolved'::text) OR (target_log_id IS NOT NULL)))`
- `source_reference_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `source_reference_pkey`: `PRIMARY KEY (id)`
- `source_reference_target_log_id_dataset_revision_id_fkey`: `FOREIGN KEY (target_log_id, dataset_revision_id) REFERENCES scan_log(id, dataset_revision_id)`

Indexes:

- `CREATE UNIQUE INDEX source_reference_pkey ON core.source_reference USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.source_reference FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**quality_issue**

Source issues, evidence, and affected scope.Source: Step 2–5 issues.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `processing_step` | `integer` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `code` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `severity` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `scope` | `text` | NO | — / status or identifier | Fields, source logs, or boreholes affected by an issue. | `None` |
| `detail` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `evidence` | `jsonb` | YES | — / status or identifier | Original or normalized processing evidence; does not infer missing facts. | `None` |
| `impact` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `quality_issue_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `quality_issue_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX quality_issue_pkey ON core.quality_issue USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.quality_issue FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**ingest_run**

Run records; repeated runs reuse existing business entities.Source: Step 9/28/34.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `started_at` | `timestamp with time zone` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `now()` |
| `finished_at` | `timestamp with time zone` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `input_digest` | `text` | NO | — / status or identifier | Meaning depends on the table: dataset_revision hashes prepared data, sample bindings, and media; revision_validation binds the same digest; ingest_run identifies the batch. Different content for the same data revision is rejected. | `None` |
| `code_sha256` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `schema_sha256` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `holes` | `jsonb` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `detail` | `jsonb` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `'{}'::jsonb` |

Constraints:

- `ingest_run_pkey`: `PRIMARY KEY (id)`
- `ingest_run_status_check`: `CHECK ((status = ANY (ARRAY['running'::text, 'staged'::text, 'failed'::text])))`

Indexes:

- `CREATE UNIQUE INDEX ingest_run_pkey ON core.ingest_run USING btree (id)`

Write validation and immutability triggers:

No user-defined triggers; the constraints and role permissions above still apply.

**revision_validation**

Revision validation results and validator code hash; validation may be repeated.Source: Step 10/29/35.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `validated_at` | `timestamp with time zone` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `now()` |
| `input_digest` | `text` | NO | — / status or identifier | Meaning depends on the table: dataset_revision hashes prepared data, sample bindings, and media; revision_validation binds the same digest; ingest_run identifies the batch. Different content for the same data revision is rejected. | `None` |
| `verification_code_sha256` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `result` | `jsonb` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `revision_validation_dataset_revision_id_fkey`: `FOREIGN KEY (dataset_revision_id) REFERENCES dataset_revision(id)`
- `revision_validation_pkey`: `PRIMARY KEY (dataset_revision_id)`

Indexes:

- `CREATE UNIQUE INDEX revision_validation_pkey ON core.revision_validation USING btree (dataset_revision_id)`

Write validation and immutability triggers:

No user-defined triggers; the constraints and role permissions above still apply.

**data_release**

Release manifest; local publication follows validation, and cloud activation uses an explicit final member selection.Source: Step 10/28/34 dataset_revision set.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `manifest_sha256` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `created_at` | `timestamp with time zone` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `now()` |
| `release_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `'local_verified'::text` |
| `manifest` | `jsonb` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `data_release_manifest_sha256_key`: `UNIQUE (manifest_sha256)`
- `data_release_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX data_release_manifest_sha256_key ON core.data_release USING btree (manifest_sha256)`
- `CREATE UNIQUE INDEX data_release_pkey ON core.data_release USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.data_release FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**release_dataset**

Each release selects exactly one revision for each dataset.Source: data_release.manifest from each stage.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `release_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `dataset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |

Constraints:

- `release_dataset_dataset_revision_id_dataset_id_fkey`: `FOREIGN KEY (dataset_revision_id, dataset_id) REFERENCES dataset_revision(id, dataset_id)`
- `release_dataset_exact_revision_key`: `UNIQUE (release_id, dataset_id, dataset_revision_id)`
- `release_dataset_pkey`: `PRIMARY KEY (release_id, dataset_id)`
- `release_dataset_release_id_fkey`: `FOREIGN KEY (release_id) REFERENCES data_release(id)`

Indexes:

- `CREATE UNIQUE INDEX release_dataset_exact_revision_key ON core.release_dataset USING btree (release_id, dataset_id, dataset_revision_id)`
- `CREATE UNIQUE INDEX release_dataset_pkey ON core.release_dataset USING btree (release_id, dataset_id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.release_dataset FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**active_release**

Single current-release reference; historical releases remain readable, and database validation has no API dependency.Source: Step 10/29/35 switch after successful validation.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `singleton` | `boolean` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `true` |
| `release_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `switched_at` | `timestamp with time zone` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `now()` |

Constraints:

- `active_release_pkey`: `PRIMARY KEY (singleton)`
- `active_release_release_id_fkey`: `FOREIGN KEY (release_id) REFERENCES data_release(id)`
- `active_release_singleton_check`: `CHECK (singleton)`

Indexes:

- `CREATE UNIQUE INDEX active_release_pkey ON core.active_release USING btree (singleton)`

Write validation and immutability triggers:

No user-defined triggers; the constraints and role permissions above still apply.

**borehole_branch**

Parent-child branches are not inferred from the number of datasets.Source: Future evidence-backed branch records; currently empty.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `borehole_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `parent_branch_id` | `uuid` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_branch_id` | `text` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `branch_depth_m` | `double precision` | YES | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `evidence` | `jsonb` | NO | — / status or identifier | Original or normalized processing evidence; does not infer missing facts. | `None` |

Constraints:

- `borehole_branch_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `borehole_branch_check`: `CHECK (((parent_branch_id IS NULL) OR (parent_branch_id <> id)))`
- `borehole_branch_id_borehole_id_key`: `UNIQUE (id, borehole_id)`
- `borehole_branch_parent_branch_id_borehole_id_fkey`: `FOREIGN KEY (parent_branch_id, borehole_id) REFERENCES borehole_branch(id, borehole_id)`
- `borehole_branch_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX borehole_branch_id_borehole_id_key ON core.borehole_branch USING btree (id, borehole_id)`
- `CREATE UNIQUE INDEX borehole_branch_pkey ON core.borehole_branch USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.borehole_branch FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**dataset_segment**

Keep complete segments for each dataset; composite_part separately defines 3D display selections.Source: Step 34; complete sample intervals of independent datasets.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `borehole_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `branch_id` | `uuid` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `axis_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `sample_no_from` | `bigint` | NO | — / status or identifier | Zero-based inclusive start of the real sample interval; samples at repeated depths remain distinct. | `None` |
| `sample_no_to` | `bigint` | NO | — / status or identifier | Inclusive final real sample in the interval. | `None` |
| `sequence_no` | `integer` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `evidence` | `jsonb` | NO | — / status or identifier | Original or normalized processing evidence; does not infer missing facts. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.dataset_segment FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**survey_station**

Survey revision, measured depth, and angle conventions; no fabricated trajectory.Source: Future survey records; currently empty.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `borehole_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `branch_id` | `uuid` | YES | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `survey_version` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `md_m` | `double precision` | NO | m | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `azimuth_deg` | `double precision` | NO | degree; inclination conventions recorded separately | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `inclination_deg` | `double precision` | NO | degree; inclination conventions recorded separately | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `angle_convention` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `evidence` | `jsonb` | NO | — / status or identifier | Original or normalized processing evidence; does not infer missing facts. | `None` |

Constraints:

- `survey_station_azimuth_deg_check`: `CHECK (((azimuth_deg >= (0)::double precision) AND (azimuth_deg < (360)::double precision)))`
- `survey_station_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `survey_station_branch_id_borehole_id_fkey`: `FOREIGN KEY (branch_id, borehole_id) REFERENCES borehole_branch(id, borehole_id)`
- `survey_station_pkey`: `PRIMARY KEY (id)`

Indexes:

- `CREATE UNIQUE INDEX survey_station_pkey ON core.survey_station USING btree (id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.survey_station FOR EACH ROW EXECUTE FUNCTION reject_mutation()`

**spectral_array**

Validated original F32 matrices, channels, and byte strides; complete values remain in the source file.Source: Step 20–22; imported by step 28.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `log_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `asset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `spectral_stream_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `sample_count` | `bigint` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `channel_count` | `integer` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `dtype_code` | `text` | NO | — / status or identifier | Currently <f4: IEEE float32, little-endian. | `None` |
| `matrix_order` | `text` | NO | — / status or identifier | Currently C order, with consecutive wavelength channels for each sample. | `None` |
| `data_offset_bytes` | `bigint` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `sample_stride_bytes` | `bigint` | NO | — / status or identifier | Byte stride between sample starts; channel_count*4 in this batch. | `None` |
| `channel_stride_bytes` | `integer` | NO | — / status or identifier | Byte stride between wavelength channels; 4 in this batch. | `None` |
| `layout_status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `value_unit` | `text` | YES | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `scaling_applied` | `boolean` | NO | — / status or identifier | false in this run; reads preserve source values without normalization or percentage conversion. | `None` |
| `evidence_asset_id` | `uuid` | NO | — / status or identifier | Evidence asset registered within the same dataset revision. | `None` |
| `evidence` | `jsonb` | NO | — / status or identifier | Original or normalized processing evidence; does not infer missing facts. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.spectral_array FOR EACH ROW EXECUTE FUNCTION reject_mutation()`
- `validate_media`: `CREATE TRIGGER validate_media BEFORE INSERT ON core.spectral_array FOR EACH ROW EXECUTE FUNCTION check_media_insert()`

**spectral_sample_map**

Inclusive mapping between source spectral rows and real database samples; no depth interpolation.Source: Step 21 official sampleNo JSON comparison; imported by step 28.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `spectral_array_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `axis_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `source_row_from` | `bigint` | NO | — / status or identifier | Zero-based row within the source payload; complete F32 rows match sample_no in this batch and are still read through validated mappings. | `None` |
| `source_row_to` | `bigint` | NO | — / status or identifier | Inclusive final source spectral row, unlike source_row_to_exclusive. | `None` |
| `sample_no_from` | `bigint` | NO | — / status or identifier | Zero-based inclusive start of the real sample interval; samples at repeated depths remain distinct. | `None` |
| `sample_no_to` | `bigint` | NO | — / status or identifier | Inclusive final real sample in the interval. | `None` |
| `mapping_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `binding_status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `evidence_asset_id` | `uuid` | NO | — / status or identifier | Evidence asset registered within the same dataset revision. | `None` |
| `basis` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.spectral_sample_map FOR EACH ROW EXECUTE FUNCTION reject_mutation()`
- `validate_media`: `CREATE TRIGGER validate_media BEFORE INSERT ON core.spectral_sample_map FOR EACH ROW EXECUTE FUNCTION check_media_insert()`

**spectral_block**

Contiguous source F32 byte ranges and block hashes for bounded reads.Source: Step 22; imported by step 28.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `spectral_array_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `block_no` | `integer` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `source_row_from` | `bigint` | NO | — / status or identifier | Zero-based row within the source payload; complete F32 rows match sample_no in this batch and are still read through validated mappings. | `None` |
| `source_row_to_exclusive` | `bigint` | NO | — / status or identifier | Exclusive upper source-row bound, unlike inclusive tray/section sample_no_to. | `None` |
| `byte_offset` | `bigint` | NO | — / status or identifier | Zero-based starting byte offset of a block in the original F32 file. | `None` |
| `byte_length` | `bigint` | NO | — / status or identifier | Complete contiguous block length in bytes, verifiable with its own SHA256. | `None` |
| `sha256` | `text` | NO | — / status or identifier | SHA256 of file or document bytes, not an identification confidence score. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.spectral_block FOR EACH ROW EXECUTE FUNCTION reject_mutation()`
- `validate_media`: `CREATE TRIGGER validate_media BEFORE INSERT ON core.spectral_block FOR EACH ROW EXECUTE FUNCTION check_media_insert()`

**image_region**

Visible row region in a dataset tray image; variable row count and native pixel coordinates.Source: Step 23–25; imported by step 28.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `image_frame_id` | `uuid` | NO | — / status or identifier | Identity of a tray image within a particular dataset revision and image log. | `None` |
| `region_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `region_ordinal` | `integer` | NO | — / status or identifier | Zero-based top-to-bottom row order within one image; not globally unique or fixed in count. | `None` |
| `x_px` | `integer` | NO | pixel | Horizontal crop origin from the top-left; the rectangle has exclusive upper bounds. | `None` |
| `y_px` | `integer` | NO | pixel | Vertical crop origin from the top-left; the rectangle has exclusive upper bounds. | `None` |
| `width_px` | `integer` | NO | pixel | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `height_px` | `integer` | NO | pixel | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `valid_area` | `jsonb` | YES | — / status or identifier | Reserved for future nonrectangular valid regions; NULL for current rectangular regions. | `None` |
| `coordinate_basis` | `text` | NO | — / status or identifier | Native decoded pixels, top-left origin, xy coordinates, and a crop rectangle with exclusive upper bounds. | `None` |
| `region_status` | `text` | NO | — / status or identifier | Whether the crop region passed checks; separate from sample binding and file accessibility. | `None` |
| `detection_method` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `review_basis` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `evidence_asset_id` | `uuid` | NO | — / status or identifier | Evidence asset registered within the same dataset revision. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.image_region FOR EACH ROW EXECUTE FUNCTION reject_mutation()`
- `validate_media`: `CREATE TRIGGER validate_media BEFORE INSERT ON core.image_region FOR EACH ROW EXECUTE FUNCTION check_media_insert()`

**image_sample_mapping**

Source Section and actual sample interval; sample_index_linear v1 indicators are approximate.Source: Step 26; imported by step 28.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `image_region_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `axis_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `section_interval_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `sample_no_from` | `bigint` | NO | — / status or identifier | Zero-based inclusive start of the real sample interval; samples at repeated depths remain distinct. | `None` |
| `sample_no_to` | `bigint` | NO | — / status or identifier | Inclusive final real sample in the interval. | `None` |
| `anchor_points` | `jsonb` | YES | — / status or identifier | Reserved for measured pixel-to-sample/depth anchors; remains NULL without measurements. | `None` |
| `source_depth_direction` | `text` | NO | — / status or identifier | left_to_right: the project's NVCL source convention increases depth from left to right within each row. | `None` |
| `direction_status` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `direction_basis` | `text` | NO | — / status or identifier | Recorded direction evidence; current inputs use the project-confirmed NVCL row order, while existing packages retain their original confirmation. | `None` |
| `direction_evidence_asset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `mapping_level` | `text` | NO | — / status or identifier | Currently section_interval for images; must not be described as pixel-level calibration. | `None` |
| `mapping_status` | `text` | NO | — / status or identifier | Currently metadata_associated, using source Section order and layout checks. | `None` |
| `mapping_method` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `indicator_method` | `text` | NO | — / status or identifier | Currently sample_index_linear: p=(s-a)/(b-a) within a row, or p=0.5 for one sample. | `None` |
| `indicator_version` | `integer` | NO | — / status or identifier | Current algorithm version 1: x=p*(W-1), with W the native selected row-image width. | `None` |
| `indicator_status` | `text` | NO | — / status or identifier | Currently approximate; unmeasured errors must not be recorded as 0 or calibrated. | `None` |
| `indicator_parameters` | `jsonb` | NO | — / status or identifier | Versioned interval, endpoint pixel-center, single-sample centering, and crop-coordinate conventions. | `None` |
| `error_px` | `double precision` | YES | pixel | Measured pixel error; NULL because no calibration was performed. | `None` |
| `error_depth_m` | `double precision` | YES | m | Measured depth error; NULL because no calibration was performed. | `None` |
| `evidence_asset_id` | `uuid` | NO | — / status or identifier | Evidence asset registered within the same dataset revision. | `None` |

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

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.image_sample_mapping FOR EACH ROW EXECUTE FUNCTION reject_mutation()`
- `validate_media`: `CREATE TRIGGER validate_media BEFORE INSERT ON core.image_sample_mapping FOR EACH ROW EXECUTE FUNCTION check_media_insert()`

**image_region_asset**

Row region, lossless PNG, source log, and crop recipe; pixels match the source image.Source: Step 27; imported by step 28.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `region_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `asset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `log_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `representation_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `width_px` | `integer` | NO | pixel | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `height_px` | `integer` | NO | pixel | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `transform` | `jsonb` | NO | — / status or identifier | Crop rectangle with exclusive upper bounds, source hash, direction/rotation, and pixel-equality validation. | `None` |
| `recipe_version` | `integer` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |

Constraints:

- `image_region_asset_height_px_check`: `CHECK ((height_px > 0))`
- `image_region_asset_log_id_asset_id_dataset_revision_id_fkey`: `FOREIGN KEY (log_id, asset_id, dataset_revision_id) REFERENCES log_asset(log_id, asset_id, dataset_revision_id)`
- `image_region_asset_pkey`: `PRIMARY KEY (region_id, asset_id)`
- `image_region_asset_recipe_version_check`: `CHECK ((recipe_version > 0))`
- `image_region_asset_region_id_dataset_revision_id_fkey`: `FOREIGN KEY (region_id, dataset_revision_id) REFERENCES image_region(id, dataset_revision_id)`
- `image_region_asset_width_px_check`: `CHECK ((width_px > 0))`

Indexes:

- `CREATE UNIQUE INDEX image_region_asset_pkey ON core.image_region_asset USING btree (region_id, asset_id)`

Write validation and immutability triggers:

- `immutable_record`: `CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.image_region_asset FOR EACH ROW EXECUTE FUNCTION reject_mutation()`
- `validate_media`: `CREATE TRIGGER validate_media BEFORE INSERT ON core.image_region_asset FOR EACH ROW EXECUTE FUNCTION check_media_insert()`

**dataset_succession**

User-confirmed display succession, actual sample switch depth, and evidence; no inferred branch trajectory.Source: multi_dataset_decisions.json; Step 34.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `borehole_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `predecessor_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `successor_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `relation_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `switch_md_m` | `double precision` | NO | m | Depth of the first actual sample in the later segment, used as the display switch; not an inferred physical wedge depth. | `None` |
| `switch_basis` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `confirmation_basis` | `jsonb` | NO | — / status or identifier | Project-owner confirmation of succession order, switch rules, and original wording; separate from measured branch survey records. | `None` |

Constraints:

- `dataset_succession_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `dataset_succession_check`: `CHECK ((predecessor_revision_id <> successor_revision_id))`
- `dataset_succession_pkey`: `PRIMARY KEY (id)`
- `dataset_succession_predecessor_revision_id_borehole_id_fkey`: `FOREIGN KEY (predecessor_revision_id, borehole_id) REFERENCES dataset_revision(id, borehole_id)`
- `dataset_succession_predecessor_revision_id_successor_revisi_key`: `UNIQUE (predecessor_revision_id, successor_revision_id)`
- `dataset_succession_relation_kind_check`: `CHECK ((relation_kind = 'confirmed_display_successor'::text))`
- `dataset_succession_successor_revision_id_borehole_id_fkey`: `FOREIGN KEY (successor_revision_id, borehole_id) REFERENCES dataset_revision(id, borehole_id)`
- `dataset_succession_switch_basis_check`: `CHECK ((switch_basis = 'successor_first_actual_sample_md_m'::text))`
- `dataset_succession_switch_md_m_check`: `CHECK (((switch_md_m >= (0)::double precision) AND (switch_md_m < 'Infinity'::double precision)))`

Indexes:

- `CREATE UNIQUE INDEX dataset_succession_pkey ON core.dataset_succession USING btree (id)`
- `CREATE UNIQUE INDEX dataset_succession_predecessor_revision_id_successor_revisi_key ON core.dataset_succession USING btree (predecessor_revision_id, successor_revision_id)`

Write validation and immutability triggers:

No user-defined triggers; the constraints and role permissions above still apply.

**borehole_composite**

3D composite definition; no automatic gap filling or fallback to old paths, while 2D retains each complete dataset.Source: Step 34; created per release and borehole.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `id` | `uuid` | NO | — / status or identifier | Stable internal UUID; run audits use separate UUIDs. Never substitute a source name. | `None` |
| `release_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `borehole_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `composition_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `boundary_rule` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `missing_policy` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `trajectory_kind` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `definition_sha256` | `text` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `evidence` | `jsonb` | NO | — / status or identifier | Original or normalized processing evidence; does not infer missing facts. | `None` |

Constraints:

- `borehole_composite_borehole_id_fkey`: `FOREIGN KEY (borehole_id) REFERENCES borehole(id)`
- `borehole_composite_boundary_rule_check`: `CHECK ((boundary_rule = 'successor_first_actual_sample_md_m'::text))`
- `borehole_composite_composition_kind_check`: `CHECK ((composition_kind = ANY (ARRAY['single_dataset'::text, 'confirmed_successor_chain'::text])))`
- `borehole_composite_definition_sha256_check`: `CHECK ((definition_sha256 ~ '^[a-f0-9]{64}$'::text))`
- `borehole_composite_id_release_id_borehole_id_key`: `UNIQUE (id, release_id, borehole_id)`
- `borehole_composite_missing_policy_check`: `CHECK ((missing_policy = 'preserve_no_fallback'::text))`
- `borehole_composite_pkey`: `PRIMARY KEY (id)`
- `borehole_composite_release_id_borehole_id_key`: `UNIQUE (release_id, borehole_id)`
- `borehole_composite_release_id_fkey`: `FOREIGN KEY (release_id) REFERENCES data_release(id)`
- `borehole_composite_trajectory_kind_check`: `CHECK ((trajectory_kind = 'display_composite_not_surveyed_path'::text))`

Indexes:

- `CREATE UNIQUE INDEX borehole_composite_id_release_id_borehole_id_key ON core.borehole_composite USING btree (id, release_id, borehole_id)`
- `CREATE UNIQUE INDEX borehole_composite_pkey ON core.borehole_composite USING btree (id)`
- `CREATE UNIQUE INDEX borehole_composite_release_id_borehole_id_key ON core.borehole_composite USING btree (release_id, borehole_id)`

Write validation and immutability triggers:

No user-defined triggers; the constraints and role permissions above still apply.

**borehole_composite_part**

3D selection windows and inclusive source sample intervals; sequence_no also defines the 2D order.Source: Step 34; confirmed order and actual sample depths of each dataset.

| Field | PostgreSQL type | Nullable | Unit | Meaning/source | Default |
|---|---|---|---|---|---|
| `composite_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `release_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `borehole_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `sequence_no` | `integer` | NO | — / status or identifier | Matching field from the table's listed source; see the table description and source mapping. | `None` |
| `dataset_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `dataset_revision_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `axis_id` | `uuid` | NO | — / status or identifier | Foreign key or ownership identifier; see the constraints below. | `None` |
| `predecessor_relation_id` | `uuid` | YES | — / status or identifier | Confirmed succession evidence for the selected later segment; NULL for the first segment. | `None` |
| `selection_from_md_m` | `double precision` | NO | m | Inclusive start of a 3D selection window in meters; does not change source depths. | `None` |
| `selection_to_md_m` | `double precision` | NO | m | End of a 3D selection window in meters; upper_inclusive controls endpoint inclusion. | `None` |
| `upper_inclusive` | `boolean` | NO | — / status or identifier | Endpoint inclusion: the preceding segment excludes the start of its successor; a complete segment may include its final sample. | `None` |
| `sample_no_from` | `bigint` | YES | — / status or identifier | Zero-based inclusive start of the real sample interval; samples at repeated depths remain distinct. | `None` |
| `sample_no_to` | `bigint` | YES | — / status or identifier | Inclusive final real sample in the interval. | `None` |
| `selection_status` | `text` | NO | — / status or identifier | selected means samples are selected; fully_superseded retains the dataset but selects no samples in this composite. | `None` |

Constraints:

- `borehole_composite_part_axis_id_dataset_revision_id_fkey`: `FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES sample_axis(id, dataset_revision_id)`
- `borehole_composite_part_axis_id_sample_no_from_fkey`: `FOREIGN KEY (axis_id, sample_no_from) REFERENCES scan_sample(axis_id, sample_no)`
- `borehole_composite_part_axis_id_sample_no_to_fkey`: `FOREIGN KEY (axis_id, sample_no_to) REFERENCES scan_sample(axis_id, sample_no)`
- `borehole_composite_part_check`: `CHECK ((selection_to_md_m >= selection_from_md_m))`
- `borehole_composite_part_check1`: `CHECK ((((selection_status = 'selected'::text) AND (sample_no_from IS NOT NULL) AND (sample_no_to IS NOT NULL) AND (sample_no_from >= 0) AND (sample_no_from <= sample_no_to)) OR ((selection_status = 'fully_superseded'::text) AND (sample_no_from IS NULL) AND (sample_no_to IS NULL))))`
- `borehole_composite_part_check2`: `CHECK ((((sequence_no = 0) AND (predecessor_relation_id IS NULL)) OR ((sequence_no > 0) AND (predecessor_relation_id IS NOT NULL))))`
- `borehole_composite_part_composite_id_dataset_id_key`: `UNIQUE (composite_id, dataset_id)`
- `borehole_composite_part_composite_id_release_id_borehole_i_fkey`: `FOREIGN KEY (composite_id, release_id, borehole_id) REFERENCES borehole_composite(id, release_id, borehole_id)`
- `borehole_composite_part_dataset_revision_id_borehole_id_fkey`: `FOREIGN KEY (dataset_revision_id, borehole_id) REFERENCES dataset_revision(id, borehole_id)`
- `borehole_composite_part_pkey`: `PRIMARY KEY (composite_id, sequence_no)`
- `borehole_composite_part_predecessor_relation_id_fkey`: `FOREIGN KEY (predecessor_relation_id) REFERENCES dataset_succession(id)`
- `borehole_composite_part_release_id_dataset_id_dataset_revi_fkey`: `FOREIGN KEY (release_id, dataset_id, dataset_revision_id) REFERENCES release_dataset(release_id, dataset_id, dataset_revision_id)`
- `borehole_composite_part_selection_from_md_m_check`: `CHECK (((selection_from_md_m >= (0)::double precision) AND (selection_from_md_m < 'Infinity'::double precision)))`
- `borehole_composite_part_selection_status_check`: `CHECK ((selection_status = ANY (ARRAY['selected'::text, 'fully_superseded'::text])))`
- `borehole_composite_part_selection_to_md_m_check`: `CHECK (((selection_to_md_m >= (0)::double precision) AND (selection_to_md_m < 'Infinity'::double precision)))`
- `borehole_composite_part_sequence_no_check`: `CHECK ((sequence_no >= 0))`

Indexes:

- `CREATE UNIQUE INDEX borehole_composite_part_composite_id_dataset_id_key ON core.borehole_composite_part USING btree (composite_id, dataset_id)`
- `CREATE UNIQUE INDEX borehole_composite_part_pkey ON core.borehole_composite_part USING btree (composite_id, sequence_no)`
- `CREATE INDEX composite_part_axis_idx ON core.borehole_composite_part USING btree (axis_id, sample_no_from, sample_no_to)`

Write validation and immutability triggers:

- `composite_part_source_check`: `CREATE TRIGGER composite_part_source_check BEFORE INSERT OR UPDATE ON core.borehole_composite_part FOR EACH ROW EXECUTE FUNCTION check_composite_part()`

**Read views**

Views neither copy nor remove source records. 3D reads composite_samples; 2D retrieves complete axes through dataset_full.

**v_borehole_composite_samples**

| Field | PostgreSQL type |
|---|---|
| `composite_id` | `uuid` |
| `release_id` | `uuid` |
| `borehole_id` | `uuid` |
| `sequence_no` | `integer` |
| `dataset_id` | `uuid` |
| `dataset_revision_id` | `uuid` |
| `axis_id` | `uuid` |
| `sample_no` | `bigint` |
| `md_m` | `double precision` |
| `tray_interval_id` | `uuid` |
| `section_interval_id` | `uuid` |

```sql
 SELECT p.composite_id,
    p.release_id,
    p.borehole_id,
    p.sequence_no,
    p.dataset_id,
    p.dataset_revision_id,
    s.axis_id,
    s.sample_no,
    s.md_m,
    s.tray_interval_id,
    s.section_interval_id
   FROM (borehole_composite_part p
     JOIN scan_sample s ON (((s.axis_id = p.axis_id) AND ((s.sample_no >= p.sample_no_from) AND (s.sample_no <= p.sample_no_to)))))
  WHERE (p.selection_status = 'selected'::text);
```

**v_borehole_dataset_full**

| Field | PostgreSQL type |
|---|---|
| `composite_id` | `uuid` |
| `release_id` | `uuid` |
| `borehole_id` | `uuid` |
| `sequence_no` | `integer` |
| `dataset_id` | `uuid` |
| `dataset_revision_id` | `uuid` |
| `axis_id` | `uuid` |
| `source_dataset_id` | `text` |
| `source_dataset_name` | `text` |
| `sample_count` | `bigint` |
| `depth_min_m` | `double precision` |
| `depth_max_m` | `double precision` |
| `overview_selection_status` | `text` |

```sql
 SELECT p.composite_id,
    p.release_id,
    p.borehole_id,
    p.sequence_no,
    p.dataset_id,
    p.dataset_revision_id,
    p.axis_id,
    d.source_dataset_id,
    r.source_dataset_name,
    a.sample_count,
    a.depth_min_m,
    a.depth_max_m,
    p.selection_status AS overview_selection_status
   FROM (((borehole_composite_part p
     JOIN dataset d ON ((d.id = p.dataset_id)))
     JOIN dataset_revision r ON ((r.id = p.dataset_revision_id)))
     JOIN sample_axis a ON ((a.id = p.axis_id)));
```

**Trigger function definitions**

These definitions come from the database and include bulk sample/interval checks and immutability rules for existing records.

```sql
CREATE OR REPLACE FUNCTION core.check_composite_part()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'core'
AS $function$
DECLARE lo bigint; hi bigint; n bigint; r core.dataset_succession; previous_rev uuid;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(NEW.composite_id::text,9));
 SELECT min(sample_no),max(sample_no),count(*) INTO lo,hi,n FROM core.scan_sample
 WHERE axis_id=NEW.axis_id AND md_m>=NEW.selection_from_md_m
 AND (md_m<NEW.selection_to_md_m OR (NEW.upper_inclusive AND md_m=NEW.selection_to_md_m));
 IF lo IS DISTINCT FROM NEW.sample_no_from OR hi IS DISTINCT FROM NEW.sample_no_to OR
    (n>0 AND (NEW.selection_status<>'selected' OR n<>hi-lo+1)) OR
    (n=0 AND NEW.selection_status<>'fully_superseded') THEN
  RAISE EXCEPTION 'Composite selection does not exactly match its source sample window';
 END IF;
 IF NEW.predecessor_relation_id IS NOT NULL THEN
  SELECT * INTO STRICT r FROM core.dataset_succession WHERE id=NEW.predecessor_relation_id;
  SELECT dataset_revision_id INTO previous_rev FROM core.borehole_composite_part
    WHERE composite_id=NEW.composite_id AND sequence_no=NEW.sequence_no-1;
  IF r.borehole_id<>NEW.borehole_id OR r.successor_revision_id<>NEW.dataset_revision_id OR
     previous_rev IS DISTINCT FROM r.predecessor_revision_id OR r.switch_md_m<>NEW.selection_from_md_m THEN
    RAISE EXCEPTION 'Composite successor relation differs from ordered source datasets';
  END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM core.borehole_composite_part p
  WHERE p.composite_id=NEW.composite_id AND p.sequence_no<>NEW.sequence_no
    AND p.selection_status='selected' AND NEW.selection_status='selected'
    AND (p.selection_from_md_m<NEW.selection_to_md_m OR (NEW.upper_inclusive AND p.selection_from_md_m=NEW.selection_to_md_m))
    AND (NEW.selection_from_md_m<p.selection_to_md_m OR (p.upper_inclusive AND NEW.selection_from_md_m=p.selection_to_md_m))) THEN
  RAISE EXCEPTION 'Composite source selection windows overlap';
 END IF;
 RETURN NEW;
END $function$

```

```sql
CREATE OR REPLACE FUNCTION core.check_inserted_intervals()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'core'
AS $function$
BEGIN
 IF EXISTS (
   SELECT 1 FROM inserted_intervals c
   JOIN core.core_interval p ON p.id=c.parent_interval_id AND p.axis_id=c.axis_id
   WHERE c.interval_kind='section' AND
     (p.interval_kind<>'tray' OR c.sample_no_from<p.sample_no_from OR c.sample_no_to>p.sample_no_to)
 ) THEN
   RAISE EXCEPTION 'Section must belong to a containing tray on the same axis'
     USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $function$

```

```sql
CREATE OR REPLACE FUNCTION core.check_inserted_samples()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'core'
AS $function$
BEGIN
 IF EXISTS (
   SELECT 1 FROM inserted_samples s
   JOIN core.core_interval t ON t.id=s.tray_interval_id AND t.axis_id=s.axis_id
   JOIN core.core_interval c ON c.id=s.section_interval_id AND c.axis_id=s.axis_id
   JOIN core.sample_axis a ON a.id=s.axis_id
   WHERE t.interval_kind<>'tray' OR c.interval_kind<>'section'
      OR c.parent_interval_id IS DISTINCT FROM t.id
      OR s.sample_no NOT BETWEEN t.sample_no_from AND t.sample_no_to
      OR s.sample_no NOT BETWEEN c.sample_no_from AND c.sample_no_to
      OR s.tray_sample_no<>s.sample_no-t.sample_no_from+1
      OR s.section_sample_no<>s.sample_no-c.sample_no_from+1
      OR s.sample_no>=a.sample_count
      OR s.md_m NOT BETWEEN a.depth_min_m AND a.depth_max_m
 ) THEN
   RAISE EXCEPTION 'Sample interval kind, membership or position is inconsistent'
     USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $function$

```

```sql
CREATE OR REPLACE FUNCTION core.check_media_insert()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'core'
AS $function$
DECLARE f core.image_frame; r core.image_region; s core.core_interval; a core.spectral_array; n bigint; st core.spectral_stream;
BEGIN
 IF TG_TABLE_NAME='image_region' THEN
  SELECT * INTO STRICT f FROM core.image_frame WHERE id=NEW.image_frame_id;
  PERFORM pg_advisory_xact_lock(hashtextextended(f.id::text,5));
  IF NEW.x_px::bigint+NEW.width_px>f.width_px OR NEW.y_px::bigint+NEW.height_px>f.height_px THEN
   RAISE EXCEPTION 'Region exceeds source image'; END IF;
  IF EXISTS(SELECT 1 FROM core.image_region z WHERE z.image_frame_id=f.id AND
   z.x_px<NEW.x_px::bigint+NEW.width_px AND NEW.x_px<z.x_px::bigint+z.width_px AND
   z.y_px<NEW.y_px::bigint+NEW.height_px AND NEW.y_px<z.y_px::bigint+z.height_px) THEN
   RAISE EXCEPTION 'Overlapping visible core rows'; END IF;
 ELSIF TG_TABLE_NAME='image_sample_mapping' THEN
  SELECT * INTO STRICT r FROM core.image_region WHERE id=NEW.image_region_id;
  SELECT * INTO STRICT f FROM core.image_frame WHERE id=r.image_frame_id;
  SELECT * INTO STRICT s FROM core.core_interval WHERE id=NEW.section_interval_id;
  PERFORM pg_advisory_xact_lock(hashtextextended(r.id::text,6));
  IF f.axis_id<>NEW.axis_id OR s.interval_kind<>'section' OR s.parent_interval_id<>f.core_interval_id OR
    NEW.sample_no_from<s.sample_no_from OR NEW.sample_no_to>s.sample_no_to THEN
   RAISE EXCEPTION 'Image mapping crosses source tray, section or axis'; END IF;
  IF (SELECT count(*) FROM core.scan_sample WHERE axis_id=NEW.axis_id AND sample_no BETWEEN NEW.sample_no_from AND NEW.sample_no_to
     AND section_interval_id=NEW.section_interval_id)<>NEW.sample_no_to-NEW.sample_no_from+1 THEN
   RAISE EXCEPTION 'Image mapping crosses a missing or differently bound sample'; END IF;
  IF NEW.indicator_method='sample_index_linear' AND (NEW.sample_no_from<>s.sample_no_from OR NEW.sample_no_to<>s.sample_no_to OR
     EXISTS(SELECT 1 FROM core.image_sample_mapping WHERE image_region_id=r.id)) THEN
   RAISE EXCEPTION 'Index indicator requires one complete contiguous row range'; END IF;
 ELSIF TG_TABLE_NAME='image_region_asset' THEN
  SELECT * INTO STRICT r FROM core.image_region WHERE id=NEW.region_id;
  SELECT * INTO STRICT f FROM core.image_frame WHERE id=r.image_frame_id;
  IF f.log_id<>NEW.log_id THEN RAISE EXCEPTION 'Derived row has a different source image log'; END IF;
  IF NEW.representation_kind='native_lossless_png' AND (NEW.width_px<>r.width_px OR NEW.height_px<>r.height_px OR
   (NEW.transform->'crop_box_half_open') IS DISTINCT FROM jsonb_build_array(r.x_px,r.y_px,r.x_px+r.width_px,r.y_px+r.height_px) OR
   (NEW.transform->>'source_sha256') IS DISTINCT FROM (SELECT sha256 FROM core.asset WHERE id=f.asset_id)) THEN
   RAISE EXCEPTION 'Crop recipe or source content differs from region'; END IF;
 ELSIF TG_TABLE_NAME='spectral_array' THEN
  SELECT * INTO STRICT st FROM core.spectral_stream WHERE id=NEW.spectral_stream_id;
  IF st.wavelength_count<>NEW.channel_count OR
   (SELECT spectral_stream_id FROM core.scan_log WHERE id=NEW.log_id) IS DISTINCT FROM NEW.spectral_stream_id THEN
   RAISE EXCEPTION 'Spectrum wavelength/log mismatch'; END IF;
  SELECT byte_size INTO STRICT n FROM core.asset WHERE id=NEW.asset_id;
  IF n<>NEW.data_offset_bytes+NEW.sample_count*NEW.sample_stride_bytes THEN RAISE EXCEPTION 'Spectral byte extent differs'; END IF;
 ELSIF TG_TABLE_NAME='spectral_block' THEN
  SELECT * INTO STRICT a FROM core.spectral_array WHERE id=NEW.spectral_array_id;
  PERFORM pg_advisory_xact_lock(hashtextextended(a.id::text,7));
  IF NEW.source_row_to_exclusive>a.sample_count OR NEW.byte_offset<>a.data_offset_bytes+NEW.source_row_from*a.sample_stride_bytes OR
   NEW.byte_length<>(NEW.source_row_to_exclusive-NEW.source_row_from)*a.sample_stride_bytes THEN
   RAISE EXCEPTION 'Invalid spectral block byte range'; END IF;
  IF EXISTS(SELECT 1 FROM core.spectral_block b WHERE b.spectral_array_id=a.id AND b.source_row_from<NEW.source_row_to_exclusive AND NEW.source_row_from<b.source_row_to_exclusive) THEN
   RAISE EXCEPTION 'Overlapping spectral blocks'; END IF;
 ELSIF TG_TABLE_NAME='spectral_sample_map' THEN
  SELECT * INTO STRICT a FROM core.spectral_array WHERE id=NEW.spectral_array_id;
  PERFORM pg_advisory_xact_lock(hashtextextended(a.id::text,8));
  IF NEW.source_row_to>=a.sample_count OR a.layout_status<>'verified_sample_major' OR
   NOT EXISTS(SELECT 1 FROM core.log_axis_binding WHERE log_id=a.log_id AND axis_id=NEW.axis_id AND status='verified') THEN
   RAISE EXCEPTION 'Unverified or invalid spectral axis'; END IF;
  IF (SELECT count(*) FROM core.scan_sample WHERE axis_id=NEW.axis_id AND sample_no BETWEEN NEW.sample_no_from AND NEW.sample_no_to)<>NEW.sample_no_to-NEW.sample_no_from+1 THEN
   RAISE EXCEPTION 'Spectral mapping crosses a sample gap'; END IF;
  IF EXISTS(SELECT 1 FROM core.spectral_sample_map m WHERE m.spectral_array_id=a.id AND
   (m.source_row_from<=NEW.source_row_to AND NEW.source_row_from<=m.source_row_to OR
    m.axis_id=NEW.axis_id AND m.sample_no_from<=NEW.sample_no_to AND NEW.sample_no_from<=m.sample_no_to)) THEN
   RAISE EXCEPTION 'Ambiguous spectral mapping'; END IF;
 END IF;
 RETURN NEW;
END $function$

```

```sql
CREATE OR REPLACE FUNCTION core.reject_mutation()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN RAISE EXCEPTION 'Immutable prepared record: create a new revision instead' USING ERRCODE='55000'; END $function$

```

