--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: check_inserted_intervals(); Type: FUNCTION; Schema: core; Owner: -
--

CREATE FUNCTION core.check_inserted_intervals() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'core'
    AS $$
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
END $$;


--
-- Name: check_inserted_samples(); Type: FUNCTION; Schema: core; Owner: -
--

CREATE FUNCTION core.check_inserted_samples() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'core'
    AS $$
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
END $$;


--
-- Name: check_media_insert(); Type: FUNCTION; Schema: core; Owner: -
--

CREATE FUNCTION core.check_media_insert() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'core'
    AS $$
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
END $$;


--
-- Name: reject_mutation(); Type: FUNCTION; Schema: core; Owner: -
--

CREATE FUNCTION core.reject_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN RAISE EXCEPTION 'Immutable prepared record: create a new revision instead' USING ERRCODE='55000'; END $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: active_release; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.active_release (
    singleton boolean DEFAULT true NOT NULL,
    release_id uuid NOT NULL,
    switched_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT active_release_singleton_check CHECK (singleton)
);


--
-- Name: asset; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.asset (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    asset_kind text NOT NULL,
    representation text NOT NULL,
    logical_path text NOT NULL,
    sha256 text NOT NULL,
    byte_size bigint NOT NULL,
    media_type text NOT NULL,
    payload_status text DEFAULT 'present'::text NOT NULL,
    semantic_status text NOT NULL,
    provenance jsonb NOT NULL,
    CONSTRAINT asset_byte_size_check CHECK ((byte_size >= 0)),
    CONSTRAINT asset_representation_check CHECK ((representation = ANY (ARRAY['raw'::text, 'canonical'::text, 'evidence'::text]))),
    CONSTRAINT asset_sha256_check CHECK ((sha256 ~ '^[a-f0-9]{64}$'::text))
);


--
-- Name: asset_location; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.asset_location (
    id uuid NOT NULL,
    asset_id uuid NOT NULL,
    backend text NOT NULL,
    root_key text NOT NULL,
    object_key text NOT NULL,
    access_status text NOT NULL,
    verified_sha256 text NOT NULL,
    CONSTRAINT asset_location_object_key_check CHECK ((object_key !~ '(^[/\\]|(^|[/\\])\.\.([/\\]|$)|:)'::text))
);


--
-- Name: borehole; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.borehole (
    id uuid NOT NULL,
    provider_code text NOT NULL,
    source_hole_id text NOT NULL,
    source_identifier text
);


--
-- Name: borehole_branch; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.borehole_branch (
    id uuid NOT NULL,
    borehole_id uuid NOT NULL,
    parent_branch_id uuid,
    source_branch_id text,
    branch_depth_m double precision,
    evidence jsonb NOT NULL,
    CONSTRAINT borehole_branch_check CHECK (((parent_branch_id IS NULL) OR (parent_branch_id <> id)))
);


--
-- Name: borehole_revision; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.borehole_revision (
    id uuid NOT NULL,
    borehole_id uuid NOT NULL,
    source_name text NOT NULL,
    provider_code text,
    custodian_name text,
    driller_name text,
    operator_name text,
    project_name text,
    drilling_method text,
    reported_length_m double precision,
    drill_start_date date,
    drill_end_date date,
    actual_drill_date_precision text NOT NULL,
    collar_geom public.geometry(Point,4326),
    coordinate_basis text,
    horizontal_crs text,
    vertical_crs text,
    elevation_m double precision,
    azimuth_deg double precision,
    inclination_deg double precision,
    inclination_convention text,
    orientation_missing_reason text,
    orientation_missing_reason_source text,
    trajectory_status text NOT NULL,
    normalized_metadata jsonb NOT NULL
);


--
-- Name: core_interval; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.core_interval (
    id uuid NOT NULL,
    axis_id uuid NOT NULL,
    interval_kind text NOT NULL,
    ordinal integer NOT NULL,
    source_label text NOT NULL,
    parent_interval_id uuid,
    sample_no_from bigint NOT NULL,
    sample_no_to bigint NOT NULL,
    observed_depth_min_m double precision,
    observed_depth_max_m double precision,
    source_log_id text NOT NULL,
    source_data_row bigint NOT NULL,
    source_interval_convention text NOT NULL,
    CONSTRAINT core_interval_check CHECK ((sample_no_from <= sample_no_to)),
    CONSTRAINT core_interval_check1 CHECK ((((interval_kind = 'tray'::text) AND (parent_interval_id IS NULL)) OR ((interval_kind = 'section'::text) AND (parent_interval_id IS NOT NULL)))),
    CONSTRAINT core_interval_interval_kind_check CHECK ((interval_kind = ANY (ARRAY['tray'::text, 'section'::text]))),
    CONSTRAINT core_interval_ordinal_check CHECK ((ordinal >= 0)),
    CONSTRAINT core_interval_sample_no_from_check CHECK ((sample_no_from >= 0)),
    CONSTRAINT core_interval_source_interval_convention_check CHECK ((source_interval_convention = 'closed'::text))
);


--
-- Name: data_chunk; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.data_chunk (
    asset_id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    axis_id uuid NOT NULL,
    log_id uuid,
    row_group integer NOT NULL,
    source_row_from bigint NOT NULL,
    source_row_to_exclusive bigint NOT NULL,
    row_count integer NOT NULL,
    coordinate_kind text NOT NULL,
    coordinate_min double precision NOT NULL,
    coordinate_max double precision NOT NULL,
    logical_sha256 text NOT NULL,
    CONSTRAINT data_chunk_check CHECK (((source_row_to_exclusive - source_row_from) = row_count)),
    CONSTRAINT data_chunk_check1 CHECK ((coordinate_min <= coordinate_max)),
    CONSTRAINT data_chunk_row_count_check CHECK ((row_count > 0)),
    CONSTRAINT data_chunk_row_group_check CHECK ((row_group >= 0)),
    CONSTRAINT data_chunk_source_row_from_check CHECK ((source_row_from >= 0))
);


--
-- Name: data_release; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.data_release (
    id uuid NOT NULL,
    manifest_sha256 text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    release_kind text DEFAULT 'local_verified'::text NOT NULL,
    manifest jsonb NOT NULL
);


--
-- Name: dataset; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.dataset (
    id uuid NOT NULL,
    borehole_id uuid NOT NULL,
    source_dataset_id text NOT NULL
);


--
-- Name: dataset_revision; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.dataset_revision (
    id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    borehole_id uuid NOT NULL,
    borehole_revision_id uuid NOT NULL,
    source_dataset_name text,
    source_borehole_uri text,
    source_project_name text,
    instrument_name text,
    owner_name text,
    source_snapshot_id text NOT NULL,
    pipeline_id text NOT NULL,
    input_digest text NOT NULL,
    mapping_version integer NOT NULL,
    source_created_at timestamp with time zone,
    source_modified_at timestamp with time zone,
    source_download_started_at timestamp with time zone,
    source_download_finished_at timestamp with time zone,
    normalized_metadata jsonb NOT NULL
);


--
-- Name: dataset_segment; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.dataset_segment (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    borehole_id uuid NOT NULL,
    branch_id uuid,
    axis_id uuid NOT NULL,
    sample_no_from bigint NOT NULL,
    sample_no_to bigint NOT NULL,
    sequence_no integer,
    evidence jsonb NOT NULL,
    CONSTRAINT dataset_segment_check CHECK ((sample_no_from <= sample_no_to))
);


--
-- Name: image_frame; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.image_frame (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    axis_id uuid NOT NULL,
    core_interval_id uuid NOT NULL,
    log_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    image_kind text NOT NULL,
    image_ordinal integer NOT NULL,
    source_tray_label text NOT NULL,
    width_px integer NOT NULL,
    height_px integer NOT NULL,
    depth_from_m double precision NOT NULL,
    depth_to_m double precision NOT NULL,
    depth_from_difference_m double precision NOT NULL,
    depth_to_difference_m double precision NOT NULL,
    depth_comparison_tolerance_m double precision NOT NULL,
    association_basis text NOT NULL,
    pixel_depth_mapping jsonb,
    CONSTRAINT image_frame_check CHECK ((depth_from_m <= depth_to_m)),
    CONSTRAINT image_frame_height_px_check CHECK ((height_px > 0)),
    CONSTRAINT image_frame_width_px_check CHECK ((width_px > 0))
);


--
-- Name: image_region; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.image_region (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    image_frame_id uuid NOT NULL,
    region_kind text NOT NULL,
    region_ordinal integer NOT NULL,
    x_px integer NOT NULL,
    y_px integer NOT NULL,
    width_px integer NOT NULL,
    height_px integer NOT NULL,
    valid_area jsonb,
    coordinate_basis text NOT NULL,
    region_status text NOT NULL,
    detection_method text NOT NULL,
    review_basis text NOT NULL,
    evidence_asset_id uuid NOT NULL,
    CONSTRAINT image_region_height_px_check CHECK ((height_px > 0)),
    CONSTRAINT image_region_region_kind_check CHECK ((region_kind = 'core_row'::text)),
    CONSTRAINT image_region_region_ordinal_check CHECK ((region_ordinal >= 0)),
    CONSTRAINT image_region_region_status_check CHECK ((region_status = ANY (ARRAY['candidate'::text, 'reviewed'::text, 'unavailable'::text]))),
    CONSTRAINT image_region_width_px_check CHECK ((width_px > 0)),
    CONSTRAINT image_region_x_px_check CHECK ((x_px >= 0)),
    CONSTRAINT image_region_y_px_check CHECK ((y_px >= 0))
);


--
-- Name: image_region_asset; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.image_region_asset (
    region_id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    log_id uuid NOT NULL,
    representation_kind text NOT NULL,
    width_px integer NOT NULL,
    height_px integer NOT NULL,
    transform jsonb NOT NULL,
    recipe_version integer NOT NULL,
    CONSTRAINT image_region_asset_height_px_check CHECK ((height_px > 0)),
    CONSTRAINT image_region_asset_recipe_version_check CHECK ((recipe_version > 0)),
    CONSTRAINT image_region_asset_width_px_check CHECK ((width_px > 0))
);


--
-- Name: image_sample_mapping; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.image_sample_mapping (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    image_region_id uuid NOT NULL,
    axis_id uuid NOT NULL,
    section_interval_id uuid NOT NULL,
    sample_no_from bigint NOT NULL,
    sample_no_to bigint NOT NULL,
    anchor_points jsonb,
    source_depth_direction text NOT NULL,
    direction_status text NOT NULL,
    direction_basis text NOT NULL,
    direction_evidence_asset_id uuid NOT NULL,
    mapping_level text NOT NULL,
    mapping_status text NOT NULL,
    mapping_method text NOT NULL,
    indicator_method text NOT NULL,
    indicator_version integer NOT NULL,
    indicator_status text NOT NULL,
    indicator_parameters jsonb NOT NULL,
    error_px double precision,
    error_depth_m double precision,
    evidence_asset_id uuid NOT NULL,
    CONSTRAINT image_sample_mapping_check CHECK ((sample_no_from <= sample_no_to)),
    CONSTRAINT image_sample_mapping_check1 CHECK (((indicator_method <> 'sample_index_linear'::text) OR ((indicator_version = 1) AND (indicator_status = 'approximate'::text) AND (source_depth_direction = 'left_to_right'::text) AND (indicator_parameters = '{"range_basis": "row_sample_interval", "endpoint_rule": "first_last_pixel_center", "coordinate_space": "row_crop_pixels", "single_sample_rule": "center"}'::jsonb) AND (error_px IS NULL) AND (error_depth_m IS NULL)))),
    CONSTRAINT image_sample_mapping_error_depth_m_check CHECK (((error_depth_m IS NULL) OR ((error_depth_m >= (0)::double precision) AND (error_depth_m < 'Infinity'::double precision)))),
    CONSTRAINT image_sample_mapping_error_px_check CHECK (((error_px IS NULL) OR ((error_px >= (0)::double precision) AND (error_px < 'Infinity'::double precision)))),
    CONSTRAINT image_sample_mapping_indicator_status_check CHECK ((indicator_status = ANY (ARRAY['approximate'::text, 'unavailable'::text, 'calibrated'::text])))
);


--
-- Name: ingest_run; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.ingest_run (
    id uuid NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    input_digest text NOT NULL,
    code_sha256 text NOT NULL,
    schema_sha256 text NOT NULL,
    holes jsonb NOT NULL,
    status text NOT NULL,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ingest_run_status_check CHECK ((status = ANY (ARRAY['running'::text, 'staged'::text, 'failed'::text])))
);


--
-- Name: interpretation_input; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.interpretation_input (
    interpretation_set_id uuid NOT NULL,
    spectral_stream_id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    evidence jsonb NOT NULL
);


--
-- Name: interpretation_set; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.interpretation_set (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    source_set_code text NOT NULL,
    algorithm_family text,
    output_region text,
    variant_code text,
    algorithm_version text,
    actual_mineral_library text,
    parameters jsonb,
    grouping_basis text NOT NULL,
    input_association_status text NOT NULL
);


--
-- Name: log_asset; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.log_asset (
    log_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    role text NOT NULL
);


--
-- Name: log_axis_binding; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.log_axis_binding (
    log_id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    axis_id uuid,
    status text NOT NULL,
    basis text NOT NULL,
    CONSTRAINT log_axis_binding_check CHECK (((status <> 'verified'::text) OR (axis_id IS NOT NULL)))
);


--
-- Name: metric_definition; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.metric_definition (
    dataset_revision_id uuid NOT NULL,
    metric_key text NOT NULL,
    display_name text NOT NULL,
    value_type text,
    unit text,
    definition_status text NOT NULL,
    is_probability boolean,
    source_log_id text
);


--
-- Name: COLUMN metric_definition.is_probability; Type: COMMENT; Schema: core; Owner: -
--

COMMENT ON COLUMN core.metric_definition.is_probability IS 'Probability semantics from the source/canonical dictionary: true, false, or NULL for unknown/inapplicable values; Wt is explicitly false.';


--
-- Name: COLUMN metric_definition.source_log_id; Type: COMMENT; Schema: core; Owner: -
--

COMMENT ON COLUMN core.metric_definition.source_log_id IS 'Source log identity in the auxiliary metric dictionary; register each source ID separately when general semantics are unconfirmed.';


--
-- Name: quality_issue; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.quality_issue (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    processing_step integer NOT NULL,
    code text NOT NULL,
    severity text NOT NULL,
    scope text NOT NULL,
    detail text NOT NULL,
    evidence jsonb,
    impact text NOT NULL
);


--
-- Name: release_dataset; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.release_dataset (
    release_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL
);


--
-- Name: revision_validation; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.revision_validation (
    dataset_revision_id uuid NOT NULL,
    validated_at timestamp with time zone DEFAULT now() NOT NULL,
    input_digest text NOT NULL,
    verification_code_sha256 text NOT NULL,
    result jsonb NOT NULL
);


--
-- Name: sample_axis; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.sample_axis (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    sample_count bigint NOT NULL,
    depth_min_m double precision NOT NULL,
    depth_max_m double precision NOT NULL,
    coordinate_kind text DEFAULT 'measured_depth_m'::text NOT NULL,
    alignment_evidence jsonb NOT NULL,
    CONSTRAINT sample_axis_check CHECK ((depth_min_m <= depth_max_m)),
    CONSTRAINT sample_axis_sample_count_check CHECK ((sample_count > 0))
);


--
-- Name: scan_log; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.scan_log (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    source_log_id text NOT NULL,
    source_log_name text NOT NULL,
    log_kind text NOT NULL,
    source_log_type text,
    source_algorithm_id text,
    source_mask_log_id text,
    source_is_public boolean,
    source_created_at timestamp with time zone,
    source_modified_at timestamp with time zone,
    source_status text,
    metric_key text,
    metric_code text,
    component_rank integer,
    interpretation_set_id uuid,
    spectral_stream_id uuid,
    coordinate_kind text,
    observed_row_count bigint,
    observed_value_kind text,
    unit text,
    origin text,
    availability_status text NOT NULL,
    omission_reason text,
    definition_status text NOT NULL,
    array_layout_status text,
    per_sample_publication_allowed boolean DEFAULT false NOT NULL,
    declared_channel_count integer,
    observed_channel_count integer,
    physical_geometry_status text,
    null_tokens jsonb,
    source_metadata_file text NOT NULL,
    normalized_metadata jsonb NOT NULL,
    CONSTRAINT scan_log_component_rank_check CHECK (((component_rank IS NULL) OR (component_rank > 0)))
);


--
-- Name: scan_sample; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.scan_sample (
    axis_id uuid NOT NULL,
    sample_no bigint NOT NULL,
    md_m double precision NOT NULL,
    tray_interval_id uuid NOT NULL,
    section_interval_id uuid NOT NULL,
    tray_sample_no bigint NOT NULL,
    section_sample_no bigint NOT NULL,
    section_distance_mm double precision,
    CONSTRAINT scan_sample_md_m_check CHECK (((md_m > '-Infinity'::double precision) AND (md_m < 'Infinity'::double precision))),
    CONSTRAINT scan_sample_sample_no_check CHECK ((sample_no >= 0)),
    CONSTRAINT scan_sample_section_sample_no_check CHECK ((section_sample_no > 0)),
    CONSTRAINT scan_sample_tray_sample_no_check CHECK ((tray_sample_no > 0))
);


--
-- Name: schema_migration; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.schema_migration (
    name text NOT NULL,
    sha256 text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: source_document; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.source_document (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    document_name text NOT NULL,
    content_json jsonb,
    content_text text,
    CONSTRAINT source_document_check CHECK (((content_json IS NOT NULL) OR (content_text IS NOT NULL)))
);


--
-- Name: source_reference; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.source_reference (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    role text NOT NULL,
    source_target_id text NOT NULL,
    target_log_id uuid,
    status text NOT NULL,
    evidence jsonb NOT NULL,
    CONSTRAINT source_reference_check CHECK (((status <> 'resolved'::text) OR (target_log_id IS NOT NULL)))
);


--
-- Name: spectral_array; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.spectral_array (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    log_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    spectral_stream_id uuid NOT NULL,
    sample_count bigint NOT NULL,
    channel_count integer NOT NULL,
    dtype_code text NOT NULL,
    matrix_order text NOT NULL,
    data_offset_bytes bigint NOT NULL,
    sample_stride_bytes bigint NOT NULL,
    channel_stride_bytes integer NOT NULL,
    layout_status text NOT NULL,
    value_unit text,
    scaling_applied boolean NOT NULL,
    evidence_asset_id uuid NOT NULL,
    evidence jsonb NOT NULL,
    CONSTRAINT spectral_array_channel_count_check CHECK ((channel_count > 0)),
    CONSTRAINT spectral_array_channel_stride_bytes_check CHECK ((channel_stride_bytes = 4)),
    CONSTRAINT spectral_array_check CHECK ((sample_stride_bytes = ((channel_count)::bigint * 4))),
    CONSTRAINT spectral_array_data_offset_bytes_check CHECK ((data_offset_bytes >= 0)),
    CONSTRAINT spectral_array_dtype_code_check CHECK ((dtype_code = '<f4'::text)),
    CONSTRAINT spectral_array_layout_status_check CHECK ((layout_status = ANY (ARRAY['verified_sample_major'::text, 'unconfirmed'::text]))),
    CONSTRAINT spectral_array_matrix_order_check CHECK ((matrix_order = 'C'::text)),
    CONSTRAINT spectral_array_sample_count_check CHECK ((sample_count > 0)),
    CONSTRAINT spectral_array_scaling_applied_check CHECK ((NOT scaling_applied))
);


--
-- Name: spectral_block; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.spectral_block (
    spectral_array_id uuid NOT NULL,
    block_no integer NOT NULL,
    source_row_from bigint NOT NULL,
    source_row_to_exclusive bigint NOT NULL,
    byte_offset bigint NOT NULL,
    byte_length bigint NOT NULL,
    sha256 text NOT NULL,
    CONSTRAINT spectral_block_block_no_check CHECK ((block_no >= 0)),
    CONSTRAINT spectral_block_byte_length_check CHECK ((byte_length > 0)),
    CONSTRAINT spectral_block_byte_offset_check CHECK ((byte_offset >= 0)),
    CONSTRAINT spectral_block_check CHECK ((source_row_to_exclusive > source_row_from)),
    CONSTRAINT spectral_block_sha256_check CHECK ((sha256 ~ '^[a-f0-9]{64}$'::text)),
    CONSTRAINT spectral_block_source_row_from_check CHECK ((source_row_from >= 0))
);


--
-- Name: spectral_sample_map; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.spectral_sample_map (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    spectral_array_id uuid NOT NULL,
    axis_id uuid NOT NULL,
    source_row_from bigint NOT NULL,
    source_row_to bigint NOT NULL,
    sample_no_from bigint NOT NULL,
    sample_no_to bigint NOT NULL,
    mapping_kind text NOT NULL,
    binding_status text NOT NULL,
    evidence_asset_id uuid NOT NULL,
    basis text NOT NULL,
    CONSTRAINT spectral_sample_map_binding_status_check CHECK ((binding_status = 'verified'::text)),
    CONSTRAINT spectral_sample_map_check CHECK ((source_row_from <= source_row_to)),
    CONSTRAINT spectral_sample_map_check1 CHECK ((sample_no_from <= sample_no_to)),
    CONSTRAINT spectral_sample_map_check2 CHECK (((source_row_to - source_row_from) = (sample_no_to - sample_no_from))),
    CONSTRAINT spectral_sample_map_mapping_kind_check CHECK ((mapping_kind = 'identity_range'::text)),
    CONSTRAINT spectral_sample_map_source_row_from_check CHECK ((source_row_from >= 0))
);


--
-- Name: spectral_stream; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.spectral_stream (
    id uuid NOT NULL,
    dataset_revision_id uuid NOT NULL,
    region_code text NOT NULL,
    wavelength_unit text NOT NULL,
    wavelength_count integer NOT NULL,
    wavelengths double precision[] NOT NULL,
    classification_basis text NOT NULL,
    CONSTRAINT spectral_stream_check CHECK ((cardinality(wavelengths) = wavelength_count)),
    CONSTRAINT spectral_stream_wavelength_count_check CHECK ((wavelength_count > 0))
);


--
-- Name: survey_station; Type: TABLE; Schema: core; Owner: -
--

CREATE TABLE core.survey_station (
    id uuid NOT NULL,
    borehole_id uuid NOT NULL,
    branch_id uuid,
    survey_version text NOT NULL,
    md_m double precision NOT NULL,
    azimuth_deg double precision NOT NULL,
    inclination_deg double precision NOT NULL,
    angle_convention text NOT NULL,
    evidence jsonb NOT NULL,
    CONSTRAINT survey_station_azimuth_deg_check CHECK (((azimuth_deg >= (0)::double precision) AND (azimuth_deg < (360)::double precision)))
);


--
-- Name: active_release active_release_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.active_release
    ADD CONSTRAINT active_release_pkey PRIMARY KEY (singleton);


--
-- Name: asset asset_dataset_revision_id_representation_logical_path_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.asset
    ADD CONSTRAINT asset_dataset_revision_id_representation_logical_path_key UNIQUE (dataset_revision_id, representation, logical_path);


--
-- Name: asset asset_id_dataset_revision_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.asset
    ADD CONSTRAINT asset_id_dataset_revision_id_key UNIQUE (id, dataset_revision_id);


--
-- Name: asset asset_id_sha256_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.asset
    ADD CONSTRAINT asset_id_sha256_key UNIQUE (id, sha256);


--
-- Name: asset_location asset_location_asset_id_backend_root_key_object_key_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.asset_location
    ADD CONSTRAINT asset_location_asset_id_backend_root_key_object_key_key UNIQUE (asset_id, backend, root_key, object_key);


--
-- Name: asset_location asset_location_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.asset_location
    ADD CONSTRAINT asset_location_pkey PRIMARY KEY (id);


--
-- Name: asset asset_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.asset
    ADD CONSTRAINT asset_pkey PRIMARY KEY (id);


--
-- Name: borehole_branch borehole_branch_id_borehole_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.borehole_branch
    ADD CONSTRAINT borehole_branch_id_borehole_id_key UNIQUE (id, borehole_id);


--
-- Name: borehole_branch borehole_branch_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.borehole_branch
    ADD CONSTRAINT borehole_branch_pkey PRIMARY KEY (id);


--
-- Name: borehole borehole_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.borehole
    ADD CONSTRAINT borehole_pkey PRIMARY KEY (id);


--
-- Name: borehole borehole_provider_code_source_hole_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.borehole
    ADD CONSTRAINT borehole_provider_code_source_hole_id_key UNIQUE (provider_code, source_hole_id);


--
-- Name: borehole_revision borehole_revision_id_borehole_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.borehole_revision
    ADD CONSTRAINT borehole_revision_id_borehole_id_key UNIQUE (id, borehole_id);


--
-- Name: borehole_revision borehole_revision_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.borehole_revision
    ADD CONSTRAINT borehole_revision_pkey PRIMARY KEY (id);


--
-- Name: core_interval core_interval_axis_id_interval_kind_ordinal_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.core_interval
    ADD CONSTRAINT core_interval_axis_id_interval_kind_ordinal_key UNIQUE (axis_id, interval_kind, ordinal);


--
-- Name: core_interval core_interval_id_axis_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.core_interval
    ADD CONSTRAINT core_interval_id_axis_id_key UNIQUE (id, axis_id);


--
-- Name: core_interval core_interval_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.core_interval
    ADD CONSTRAINT core_interval_pkey PRIMARY KEY (id);


--
-- Name: data_chunk data_chunk_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.data_chunk
    ADD CONSTRAINT data_chunk_pkey PRIMARY KEY (asset_id, row_group);


--
-- Name: data_release data_release_manifest_sha256_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.data_release
    ADD CONSTRAINT data_release_manifest_sha256_key UNIQUE (manifest_sha256);


--
-- Name: data_release data_release_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.data_release
    ADD CONSTRAINT data_release_pkey PRIMARY KEY (id);


--
-- Name: dataset dataset_borehole_id_source_dataset_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset
    ADD CONSTRAINT dataset_borehole_id_source_dataset_id_key UNIQUE (borehole_id, source_dataset_id);


--
-- Name: dataset dataset_id_borehole_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset
    ADD CONSTRAINT dataset_id_borehole_id_key UNIQUE (id, borehole_id);


--
-- Name: dataset dataset_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset
    ADD CONSTRAINT dataset_pkey PRIMARY KEY (id);


--
-- Name: dataset_revision dataset_revision_dataset_id_source_snapshot_id_pipeline_id__key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_revision
    ADD CONSTRAINT dataset_revision_dataset_id_source_snapshot_id_pipeline_id__key UNIQUE (dataset_id, source_snapshot_id, pipeline_id, mapping_version);


--
-- Name: dataset_revision dataset_revision_id_borehole_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_revision
    ADD CONSTRAINT dataset_revision_id_borehole_id_key UNIQUE (id, borehole_id);


--
-- Name: dataset_revision dataset_revision_id_dataset_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_revision
    ADD CONSTRAINT dataset_revision_id_dataset_id_key UNIQUE (id, dataset_id);


--
-- Name: dataset_revision dataset_revision_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_revision
    ADD CONSTRAINT dataset_revision_pkey PRIMARY KEY (id);


--
-- Name: dataset_segment dataset_segment_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_segment
    ADD CONSTRAINT dataset_segment_pkey PRIMARY KEY (id);


--
-- Name: image_frame image_frame_id_dataset_revision_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_frame
    ADD CONSTRAINT image_frame_id_dataset_revision_id_key UNIQUE (id, dataset_revision_id);


--
-- Name: image_frame image_frame_log_id_image_ordinal_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_frame
    ADD CONSTRAINT image_frame_log_id_image_ordinal_key UNIQUE (log_id, image_ordinal);


--
-- Name: image_frame image_frame_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_frame
    ADD CONSTRAINT image_frame_pkey PRIMARY KEY (id);


--
-- Name: image_region_asset image_region_asset_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_region_asset
    ADD CONSTRAINT image_region_asset_pkey PRIMARY KEY (region_id, asset_id);


--
-- Name: image_region image_region_id_dataset_revision_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_region
    ADD CONSTRAINT image_region_id_dataset_revision_id_key UNIQUE (id, dataset_revision_id);


--
-- Name: image_region image_region_image_frame_id_region_ordinal_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_region
    ADD CONSTRAINT image_region_image_frame_id_region_ordinal_key UNIQUE (image_frame_id, region_ordinal);


--
-- Name: image_region image_region_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_region
    ADD CONSTRAINT image_region_pkey PRIMARY KEY (id);


--
-- Name: image_sample_mapping image_sample_mapping_image_region_id_axis_id_sample_no_from_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_sample_mapping
    ADD CONSTRAINT image_sample_mapping_image_region_id_axis_id_sample_no_from_key UNIQUE (image_region_id, axis_id, sample_no_from);


--
-- Name: image_sample_mapping image_sample_mapping_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_sample_mapping
    ADD CONSTRAINT image_sample_mapping_pkey PRIMARY KEY (id);


--
-- Name: ingest_run ingest_run_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.ingest_run
    ADD CONSTRAINT ingest_run_pkey PRIMARY KEY (id);


--
-- Name: interpretation_input interpretation_input_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.interpretation_input
    ADD CONSTRAINT interpretation_input_pkey PRIMARY KEY (interpretation_set_id, spectral_stream_id);


--
-- Name: interpretation_set interpretation_set_dataset_revision_id_source_set_code_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.interpretation_set
    ADD CONSTRAINT interpretation_set_dataset_revision_id_source_set_code_key UNIQUE (dataset_revision_id, source_set_code);


--
-- Name: interpretation_set interpretation_set_id_dataset_revision_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.interpretation_set
    ADD CONSTRAINT interpretation_set_id_dataset_revision_id_key UNIQUE (id, dataset_revision_id);


--
-- Name: interpretation_set interpretation_set_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.interpretation_set
    ADD CONSTRAINT interpretation_set_pkey PRIMARY KEY (id);


--
-- Name: log_asset log_asset_log_id_asset_id_dataset_revision_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.log_asset
    ADD CONSTRAINT log_asset_log_id_asset_id_dataset_revision_id_key UNIQUE (log_id, asset_id, dataset_revision_id);


--
-- Name: log_asset log_asset_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.log_asset
    ADD CONSTRAINT log_asset_pkey PRIMARY KEY (log_id, asset_id);


--
-- Name: log_axis_binding log_axis_binding_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.log_axis_binding
    ADD CONSTRAINT log_axis_binding_pkey PRIMARY KEY (log_id);


--
-- Name: metric_definition metric_definition_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.metric_definition
    ADD CONSTRAINT metric_definition_pkey PRIMARY KEY (dataset_revision_id, metric_key);


--
-- Name: quality_issue quality_issue_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.quality_issue
    ADD CONSTRAINT quality_issue_pkey PRIMARY KEY (id);


--
-- Name: release_dataset release_dataset_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.release_dataset
    ADD CONSTRAINT release_dataset_pkey PRIMARY KEY (release_id, dataset_id);


--
-- Name: revision_validation revision_validation_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.revision_validation
    ADD CONSTRAINT revision_validation_pkey PRIMARY KEY (dataset_revision_id);


--
-- Name: sample_axis sample_axis_id_dataset_revision_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.sample_axis
    ADD CONSTRAINT sample_axis_id_dataset_revision_id_key UNIQUE (id, dataset_revision_id);


--
-- Name: sample_axis sample_axis_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.sample_axis
    ADD CONSTRAINT sample_axis_pkey PRIMARY KEY (id);


--
-- Name: scan_log scan_log_dataset_revision_id_log_kind_source_log_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_log
    ADD CONSTRAINT scan_log_dataset_revision_id_log_kind_source_log_id_key UNIQUE (dataset_revision_id, log_kind, source_log_id);


--
-- Name: scan_log scan_log_id_dataset_revision_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_log
    ADD CONSTRAINT scan_log_id_dataset_revision_id_key UNIQUE (id, dataset_revision_id);


--
-- Name: scan_log scan_log_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_log
    ADD CONSTRAINT scan_log_pkey PRIMARY KEY (id);


--
-- Name: scan_sample scan_sample_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_sample
    ADD CONSTRAINT scan_sample_pkey PRIMARY KEY (axis_id, sample_no);


--
-- Name: schema_migration schema_migration_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.schema_migration
    ADD CONSTRAINT schema_migration_pkey PRIMARY KEY (name);


--
-- Name: source_document source_document_dataset_revision_id_document_name_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.source_document
    ADD CONSTRAINT source_document_dataset_revision_id_document_name_key UNIQUE (dataset_revision_id, document_name);


--
-- Name: source_document source_document_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.source_document
    ADD CONSTRAINT source_document_pkey PRIMARY KEY (id);


--
-- Name: source_reference source_reference_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.source_reference
    ADD CONSTRAINT source_reference_pkey PRIMARY KEY (id);


--
-- Name: spectral_array spectral_array_id_dataset_revision_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_array
    ADD CONSTRAINT spectral_array_id_dataset_revision_id_key UNIQUE (id, dataset_revision_id);


--
-- Name: spectral_array spectral_array_log_id_asset_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_array
    ADD CONSTRAINT spectral_array_log_id_asset_id_key UNIQUE (log_id, asset_id);


--
-- Name: spectral_array spectral_array_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_array
    ADD CONSTRAINT spectral_array_pkey PRIMARY KEY (id);


--
-- Name: spectral_block spectral_block_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_block
    ADD CONSTRAINT spectral_block_pkey PRIMARY KEY (spectral_array_id, block_no);


--
-- Name: spectral_block spectral_block_spectral_array_id_source_row_from_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_block
    ADD CONSTRAINT spectral_block_spectral_array_id_source_row_from_key UNIQUE (spectral_array_id, source_row_from);


--
-- Name: spectral_sample_map spectral_sample_map_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_sample_map
    ADD CONSTRAINT spectral_sample_map_pkey PRIMARY KEY (id);


--
-- Name: spectral_sample_map spectral_sample_map_spectral_array_id_source_row_from_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_sample_map
    ADD CONSTRAINT spectral_sample_map_spectral_array_id_source_row_from_key UNIQUE (spectral_array_id, source_row_from);


--
-- Name: spectral_stream spectral_stream_id_dataset_revision_id_key; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_stream
    ADD CONSTRAINT spectral_stream_id_dataset_revision_id_key UNIQUE (id, dataset_revision_id);


--
-- Name: spectral_stream spectral_stream_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_stream
    ADD CONSTRAINT spectral_stream_pkey PRIMARY KEY (id);


--
-- Name: survey_station survey_station_pkey; Type: CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.survey_station
    ADD CONSTRAINT survey_station_pkey PRIMARY KEY (id);


--
-- Name: borehole_collar_gist; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX borehole_collar_gist ON core.borehole_revision USING gist (collar_geom);


--
-- Name: chunk_range_idx; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX chunk_range_idx ON core.data_chunk USING btree (log_id, coordinate_min, coordinate_max);


--
-- Name: image_mapping_sample_idx; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX image_mapping_sample_idx ON core.image_sample_mapping USING btree (axis_id, section_interval_id, sample_no_from, sample_no_to);


--
-- Name: sample_depth_idx; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX sample_depth_idx ON core.scan_sample USING btree (axis_id, md_m, sample_no);


--
-- Name: scan_log_filter_idx; Type: INDEX; Schema: core; Owner: -
--

CREATE INDEX scan_log_filter_idx ON core.scan_log USING btree (dataset_revision_id, log_kind, interpretation_set_id, metric_key);


--
-- Name: asset immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.asset FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: borehole immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.borehole FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: borehole_branch immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.borehole_branch FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: borehole_revision immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.borehole_revision FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: core_interval immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.core_interval FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: data_chunk immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.data_chunk FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: data_release immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.data_release FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: dataset immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.dataset FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: dataset_revision immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.dataset_revision FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: dataset_segment immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.dataset_segment FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: image_frame immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.image_frame FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: image_region immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.image_region FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: image_region_asset immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.image_region_asset FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: image_sample_mapping immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.image_sample_mapping FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: interpretation_input immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.interpretation_input FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: interpretation_set immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.interpretation_set FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: log_asset immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.log_asset FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: log_axis_binding immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.log_axis_binding FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: metric_definition immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.metric_definition FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: quality_issue immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.quality_issue FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: release_dataset immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.release_dataset FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: sample_axis immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.sample_axis FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: scan_log immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.scan_log FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: scan_sample immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.scan_sample FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: source_document immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.source_document FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: source_reference immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.source_reference FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: spectral_array immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.spectral_array FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: spectral_block immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.spectral_block FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: spectral_sample_map immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.spectral_sample_map FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: spectral_stream immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.spectral_stream FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: survey_station immutable_record; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER immutable_record BEFORE DELETE OR UPDATE ON core.survey_station FOR EACH ROW EXECUTE FUNCTION core.reject_mutation();


--
-- Name: core_interval validate_interval_relations; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER validate_interval_relations AFTER INSERT ON core.core_interval REFERENCING NEW TABLE AS inserted_intervals FOR EACH STATEMENT EXECUTE FUNCTION core.check_inserted_intervals();


--
-- Name: image_region validate_media; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER validate_media BEFORE INSERT ON core.image_region FOR EACH ROW EXECUTE FUNCTION core.check_media_insert();


--
-- Name: image_region_asset validate_media; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER validate_media BEFORE INSERT ON core.image_region_asset FOR EACH ROW EXECUTE FUNCTION core.check_media_insert();


--
-- Name: image_sample_mapping validate_media; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER validate_media BEFORE INSERT ON core.image_sample_mapping FOR EACH ROW EXECUTE FUNCTION core.check_media_insert();


--
-- Name: spectral_array validate_media; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER validate_media BEFORE INSERT ON core.spectral_array FOR EACH ROW EXECUTE FUNCTION core.check_media_insert();


--
-- Name: spectral_block validate_media; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER validate_media BEFORE INSERT ON core.spectral_block FOR EACH ROW EXECUTE FUNCTION core.check_media_insert();


--
-- Name: spectral_sample_map validate_media; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER validate_media BEFORE INSERT ON core.spectral_sample_map FOR EACH ROW EXECUTE FUNCTION core.check_media_insert();


--
-- Name: scan_sample validate_sample_relations; Type: TRIGGER; Schema: core; Owner: -
--

CREATE TRIGGER validate_sample_relations AFTER INSERT ON core.scan_sample REFERENCING NEW TABLE AS inserted_samples FOR EACH STATEMENT EXECUTE FUNCTION core.check_inserted_samples();


--
-- Name: TRIGGER validate_sample_relations ON scan_sample; Type: COMMENT; Schema: core; Owner: -
--

COMMENT ON TRIGGER validate_sample_relations ON core.scan_sample IS 'Validate sample trays, sections, axis bounds, and positions within sections in batches; repeated depths are allowed.';


--
-- Name: active_release active_release_release_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.active_release
    ADD CONSTRAINT active_release_release_id_fkey FOREIGN KEY (release_id) REFERENCES core.data_release(id);


--
-- Name: asset asset_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.asset
    ADD CONSTRAINT asset_dataset_revision_id_fkey FOREIGN KEY (dataset_revision_id) REFERENCES core.dataset_revision(id);


--
-- Name: asset_location asset_location_asset_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.asset_location
    ADD CONSTRAINT asset_location_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES core.asset(id);


--
-- Name: asset_location asset_location_content_identity_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.asset_location
    ADD CONSTRAINT asset_location_content_identity_fkey FOREIGN KEY (asset_id, verified_sha256) REFERENCES core.asset(id, sha256);


--
-- Name: CONSTRAINT asset_location_content_identity_fkey ON asset_location; Type: COMMENT; Schema: core; Owner: -
--

COMMENT ON CONSTRAINT asset_location_content_identity_fkey ON core.asset_location IS 'The content hash declared by a copy must match the asset identity; validation does not depend on external APIs.';


--
-- Name: borehole_branch borehole_branch_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.borehole_branch
    ADD CONSTRAINT borehole_branch_borehole_id_fkey FOREIGN KEY (borehole_id) REFERENCES core.borehole(id);


--
-- Name: borehole_branch borehole_branch_parent_branch_id_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.borehole_branch
    ADD CONSTRAINT borehole_branch_parent_branch_id_borehole_id_fkey FOREIGN KEY (parent_branch_id, borehole_id) REFERENCES core.borehole_branch(id, borehole_id);


--
-- Name: borehole_revision borehole_revision_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.borehole_revision
    ADD CONSTRAINT borehole_revision_borehole_id_fkey FOREIGN KEY (borehole_id) REFERENCES core.borehole(id);


--
-- Name: core_interval core_interval_axis_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.core_interval
    ADD CONSTRAINT core_interval_axis_id_fkey FOREIGN KEY (axis_id) REFERENCES core.sample_axis(id);


--
-- Name: core_interval core_interval_axis_id_sample_no_from_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.core_interval
    ADD CONSTRAINT core_interval_axis_id_sample_no_from_fkey FOREIGN KEY (axis_id, sample_no_from) REFERENCES core.scan_sample(axis_id, sample_no) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: core_interval core_interval_axis_id_sample_no_to_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.core_interval
    ADD CONSTRAINT core_interval_axis_id_sample_no_to_fkey FOREIGN KEY (axis_id, sample_no_to) REFERENCES core.scan_sample(axis_id, sample_no) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: core_interval core_interval_parent_interval_id_axis_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.core_interval
    ADD CONSTRAINT core_interval_parent_interval_id_axis_id_fkey FOREIGN KEY (parent_interval_id, axis_id) REFERENCES core.core_interval(id, axis_id);


--
-- Name: data_chunk data_chunk_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.data_chunk
    ADD CONSTRAINT data_chunk_asset_id_dataset_revision_id_fkey FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES core.asset(id, dataset_revision_id);


--
-- Name: data_chunk data_chunk_axis_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.data_chunk
    ADD CONSTRAINT data_chunk_axis_id_dataset_revision_id_fkey FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES core.sample_axis(id, dataset_revision_id);


--
-- Name: data_chunk data_chunk_log_asset_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.data_chunk
    ADD CONSTRAINT data_chunk_log_asset_fkey FOREIGN KEY (log_id, asset_id) REFERENCES core.log_asset(log_id, asset_id);


--
-- Name: data_chunk data_chunk_log_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.data_chunk
    ADD CONSTRAINT data_chunk_log_id_dataset_revision_id_fkey FOREIGN KEY (log_id, dataset_revision_id) REFERENCES core.scan_log(id, dataset_revision_id);


--
-- Name: dataset dataset_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset
    ADD CONSTRAINT dataset_borehole_id_fkey FOREIGN KEY (borehole_id) REFERENCES core.borehole(id);


--
-- Name: dataset_revision dataset_revision_borehole_revision_id_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_revision
    ADD CONSTRAINT dataset_revision_borehole_revision_id_borehole_id_fkey FOREIGN KEY (borehole_revision_id, borehole_id) REFERENCES core.borehole_revision(id, borehole_id);


--
-- Name: dataset_revision dataset_revision_dataset_id_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_revision
    ADD CONSTRAINT dataset_revision_dataset_id_borehole_id_fkey FOREIGN KEY (dataset_id, borehole_id) REFERENCES core.dataset(id, borehole_id);


--
-- Name: dataset_segment dataset_segment_axis_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_segment
    ADD CONSTRAINT dataset_segment_axis_id_dataset_revision_id_fkey FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES core.sample_axis(id, dataset_revision_id);


--
-- Name: dataset_segment dataset_segment_axis_id_sample_no_from_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_segment
    ADD CONSTRAINT dataset_segment_axis_id_sample_no_from_fkey FOREIGN KEY (axis_id, sample_no_from) REFERENCES core.scan_sample(axis_id, sample_no);


--
-- Name: dataset_segment dataset_segment_axis_id_sample_no_to_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_segment
    ADD CONSTRAINT dataset_segment_axis_id_sample_no_to_fkey FOREIGN KEY (axis_id, sample_no_to) REFERENCES core.scan_sample(axis_id, sample_no);


--
-- Name: dataset_segment dataset_segment_branch_id_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_segment
    ADD CONSTRAINT dataset_segment_branch_id_borehole_id_fkey FOREIGN KEY (branch_id, borehole_id) REFERENCES core.borehole_branch(id, borehole_id);


--
-- Name: dataset_segment dataset_segment_dataset_revision_id_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.dataset_segment
    ADD CONSTRAINT dataset_segment_dataset_revision_id_borehole_id_fkey FOREIGN KEY (dataset_revision_id, borehole_id) REFERENCES core.dataset_revision(id, borehole_id);


--
-- Name: image_frame image_frame_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_frame
    ADD CONSTRAINT image_frame_asset_id_dataset_revision_id_fkey FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES core.asset(id, dataset_revision_id);


--
-- Name: image_frame image_frame_axis_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_frame
    ADD CONSTRAINT image_frame_axis_id_dataset_revision_id_fkey FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES core.sample_axis(id, dataset_revision_id);


--
-- Name: image_frame image_frame_core_interval_id_axis_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_frame
    ADD CONSTRAINT image_frame_core_interval_id_axis_id_fkey FOREIGN KEY (core_interval_id, axis_id) REFERENCES core.core_interval(id, axis_id);


--
-- Name: image_frame image_frame_log_asset_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_frame
    ADD CONSTRAINT image_frame_log_asset_fkey FOREIGN KEY (log_id, asset_id) REFERENCES core.log_asset(log_id, asset_id);


--
-- Name: image_frame image_frame_log_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_frame
    ADD CONSTRAINT image_frame_log_id_dataset_revision_id_fkey FOREIGN KEY (log_id, dataset_revision_id) REFERENCES core.scan_log(id, dataset_revision_id);


--
-- Name: image_region_asset image_region_asset_log_id_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_region_asset
    ADD CONSTRAINT image_region_asset_log_id_asset_id_dataset_revision_id_fkey FOREIGN KEY (log_id, asset_id, dataset_revision_id) REFERENCES core.log_asset(log_id, asset_id, dataset_revision_id);


--
-- Name: image_region_asset image_region_asset_region_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_region_asset
    ADD CONSTRAINT image_region_asset_region_id_dataset_revision_id_fkey FOREIGN KEY (region_id, dataset_revision_id) REFERENCES core.image_region(id, dataset_revision_id);


--
-- Name: image_region image_region_evidence_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_region
    ADD CONSTRAINT image_region_evidence_asset_id_dataset_revision_id_fkey FOREIGN KEY (evidence_asset_id, dataset_revision_id) REFERENCES core.asset(id, dataset_revision_id);


--
-- Name: image_region image_region_image_frame_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_region
    ADD CONSTRAINT image_region_image_frame_id_dataset_revision_id_fkey FOREIGN KEY (image_frame_id, dataset_revision_id) REFERENCES core.image_frame(id, dataset_revision_id);


--
-- Name: image_sample_mapping image_sample_mapping_axis_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_sample_mapping
    ADD CONSTRAINT image_sample_mapping_axis_id_dataset_revision_id_fkey FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES core.sample_axis(id, dataset_revision_id);


--
-- Name: image_sample_mapping image_sample_mapping_axis_id_sample_no_from_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_sample_mapping
    ADD CONSTRAINT image_sample_mapping_axis_id_sample_no_from_fkey FOREIGN KEY (axis_id, sample_no_from) REFERENCES core.scan_sample(axis_id, sample_no);


--
-- Name: image_sample_mapping image_sample_mapping_axis_id_sample_no_to_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_sample_mapping
    ADD CONSTRAINT image_sample_mapping_axis_id_sample_no_to_fkey FOREIGN KEY (axis_id, sample_no_to) REFERENCES core.scan_sample(axis_id, sample_no);


--
-- Name: image_sample_mapping image_sample_mapping_direction_evidence_asset_id_dataset_r_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_sample_mapping
    ADD CONSTRAINT image_sample_mapping_direction_evidence_asset_id_dataset_r_fkey FOREIGN KEY (direction_evidence_asset_id, dataset_revision_id) REFERENCES core.asset(id, dataset_revision_id);


--
-- Name: image_sample_mapping image_sample_mapping_evidence_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_sample_mapping
    ADD CONSTRAINT image_sample_mapping_evidence_asset_id_dataset_revision_id_fkey FOREIGN KEY (evidence_asset_id, dataset_revision_id) REFERENCES core.asset(id, dataset_revision_id);


--
-- Name: image_sample_mapping image_sample_mapping_image_region_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_sample_mapping
    ADD CONSTRAINT image_sample_mapping_image_region_id_dataset_revision_id_fkey FOREIGN KEY (image_region_id, dataset_revision_id) REFERENCES core.image_region(id, dataset_revision_id);


--
-- Name: image_sample_mapping image_sample_mapping_section_interval_id_axis_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.image_sample_mapping
    ADD CONSTRAINT image_sample_mapping_section_interval_id_axis_id_fkey FOREIGN KEY (section_interval_id, axis_id) REFERENCES core.core_interval(id, axis_id);


--
-- Name: interpretation_input interpretation_input_interpretation_set_id_dataset_revisio_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.interpretation_input
    ADD CONSTRAINT interpretation_input_interpretation_set_id_dataset_revisio_fkey FOREIGN KEY (interpretation_set_id, dataset_revision_id) REFERENCES core.interpretation_set(id, dataset_revision_id);


--
-- Name: interpretation_input interpretation_input_spectral_stream_id_dataset_revision_i_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.interpretation_input
    ADD CONSTRAINT interpretation_input_spectral_stream_id_dataset_revision_i_fkey FOREIGN KEY (spectral_stream_id, dataset_revision_id) REFERENCES core.spectral_stream(id, dataset_revision_id);


--
-- Name: interpretation_set interpretation_set_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.interpretation_set
    ADD CONSTRAINT interpretation_set_dataset_revision_id_fkey FOREIGN KEY (dataset_revision_id) REFERENCES core.dataset_revision(id);


--
-- Name: log_asset log_asset_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.log_asset
    ADD CONSTRAINT log_asset_asset_id_dataset_revision_id_fkey FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES core.asset(id, dataset_revision_id);


--
-- Name: log_asset log_asset_log_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.log_asset
    ADD CONSTRAINT log_asset_log_id_dataset_revision_id_fkey FOREIGN KEY (log_id, dataset_revision_id) REFERENCES core.scan_log(id, dataset_revision_id);


--
-- Name: log_axis_binding log_axis_binding_axis_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.log_axis_binding
    ADD CONSTRAINT log_axis_binding_axis_id_dataset_revision_id_fkey FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES core.sample_axis(id, dataset_revision_id);


--
-- Name: log_axis_binding log_axis_binding_log_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.log_axis_binding
    ADD CONSTRAINT log_axis_binding_log_id_dataset_revision_id_fkey FOREIGN KEY (log_id, dataset_revision_id) REFERENCES core.scan_log(id, dataset_revision_id);


--
-- Name: metric_definition metric_definition_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.metric_definition
    ADD CONSTRAINT metric_definition_dataset_revision_id_fkey FOREIGN KEY (dataset_revision_id) REFERENCES core.dataset_revision(id);


--
-- Name: quality_issue quality_issue_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.quality_issue
    ADD CONSTRAINT quality_issue_dataset_revision_id_fkey FOREIGN KEY (dataset_revision_id) REFERENCES core.dataset_revision(id);


--
-- Name: release_dataset release_dataset_dataset_revision_id_dataset_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.release_dataset
    ADD CONSTRAINT release_dataset_dataset_revision_id_dataset_id_fkey FOREIGN KEY (dataset_revision_id, dataset_id) REFERENCES core.dataset_revision(id, dataset_id);


--
-- Name: release_dataset release_dataset_release_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.release_dataset
    ADD CONSTRAINT release_dataset_release_id_fkey FOREIGN KEY (release_id) REFERENCES core.data_release(id);


--
-- Name: revision_validation revision_validation_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.revision_validation
    ADD CONSTRAINT revision_validation_dataset_revision_id_fkey FOREIGN KEY (dataset_revision_id) REFERENCES core.dataset_revision(id);


--
-- Name: sample_axis sample_axis_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.sample_axis
    ADD CONSTRAINT sample_axis_dataset_revision_id_fkey FOREIGN KEY (dataset_revision_id) REFERENCES core.dataset_revision(id);


--
-- Name: scan_log scan_log_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_log
    ADD CONSTRAINT scan_log_dataset_revision_id_fkey FOREIGN KEY (dataset_revision_id) REFERENCES core.dataset_revision(id);


--
-- Name: scan_log scan_log_dataset_revision_id_metric_key_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_log
    ADD CONSTRAINT scan_log_dataset_revision_id_metric_key_fkey FOREIGN KEY (dataset_revision_id, metric_key) REFERENCES core.metric_definition(dataset_revision_id, metric_key);


--
-- Name: scan_log scan_log_interpretation_set_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_log
    ADD CONSTRAINT scan_log_interpretation_set_id_dataset_revision_id_fkey FOREIGN KEY (interpretation_set_id, dataset_revision_id) REFERENCES core.interpretation_set(id, dataset_revision_id);


--
-- Name: scan_log scan_log_spectral_stream_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_log
    ADD CONSTRAINT scan_log_spectral_stream_id_dataset_revision_id_fkey FOREIGN KEY (spectral_stream_id, dataset_revision_id) REFERENCES core.spectral_stream(id, dataset_revision_id);


--
-- Name: scan_sample scan_sample_axis_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_sample
    ADD CONSTRAINT scan_sample_axis_id_fkey FOREIGN KEY (axis_id) REFERENCES core.sample_axis(id);


--
-- Name: scan_sample scan_sample_section_interval_id_axis_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_sample
    ADD CONSTRAINT scan_sample_section_interval_id_axis_id_fkey FOREIGN KEY (section_interval_id, axis_id) REFERENCES core.core_interval(id, axis_id);


--
-- Name: scan_sample scan_sample_tray_interval_id_axis_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.scan_sample
    ADD CONSTRAINT scan_sample_tray_interval_id_axis_id_fkey FOREIGN KEY (tray_interval_id, axis_id) REFERENCES core.core_interval(id, axis_id);


--
-- Name: source_document source_document_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.source_document
    ADD CONSTRAINT source_document_asset_id_dataset_revision_id_fkey FOREIGN KEY (asset_id, dataset_revision_id) REFERENCES core.asset(id, dataset_revision_id);


--
-- Name: source_reference source_reference_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.source_reference
    ADD CONSTRAINT source_reference_dataset_revision_id_fkey FOREIGN KEY (dataset_revision_id) REFERENCES core.dataset_revision(id);


--
-- Name: source_reference source_reference_target_log_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.source_reference
    ADD CONSTRAINT source_reference_target_log_id_dataset_revision_id_fkey FOREIGN KEY (target_log_id, dataset_revision_id) REFERENCES core.scan_log(id, dataset_revision_id);


--
-- Name: spectral_array spectral_array_evidence_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_array
    ADD CONSTRAINT spectral_array_evidence_asset_id_dataset_revision_id_fkey FOREIGN KEY (evidence_asset_id, dataset_revision_id) REFERENCES core.asset(id, dataset_revision_id);


--
-- Name: spectral_array spectral_array_log_id_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_array
    ADD CONSTRAINT spectral_array_log_id_asset_id_dataset_revision_id_fkey FOREIGN KEY (log_id, asset_id, dataset_revision_id) REFERENCES core.log_asset(log_id, asset_id, dataset_revision_id);


--
-- Name: spectral_array spectral_array_spectral_stream_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_array
    ADD CONSTRAINT spectral_array_spectral_stream_id_dataset_revision_id_fkey FOREIGN KEY (spectral_stream_id, dataset_revision_id) REFERENCES core.spectral_stream(id, dataset_revision_id);


--
-- Name: spectral_block spectral_block_spectral_array_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_block
    ADD CONSTRAINT spectral_block_spectral_array_id_fkey FOREIGN KEY (spectral_array_id) REFERENCES core.spectral_array(id);


--
-- Name: spectral_sample_map spectral_sample_map_axis_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_sample_map
    ADD CONSTRAINT spectral_sample_map_axis_id_dataset_revision_id_fkey FOREIGN KEY (axis_id, dataset_revision_id) REFERENCES core.sample_axis(id, dataset_revision_id);


--
-- Name: spectral_sample_map spectral_sample_map_axis_id_sample_no_from_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_sample_map
    ADD CONSTRAINT spectral_sample_map_axis_id_sample_no_from_fkey FOREIGN KEY (axis_id, sample_no_from) REFERENCES core.scan_sample(axis_id, sample_no);


--
-- Name: spectral_sample_map spectral_sample_map_axis_id_sample_no_to_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_sample_map
    ADD CONSTRAINT spectral_sample_map_axis_id_sample_no_to_fkey FOREIGN KEY (axis_id, sample_no_to) REFERENCES core.scan_sample(axis_id, sample_no);


--
-- Name: spectral_sample_map spectral_sample_map_evidence_asset_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_sample_map
    ADD CONSTRAINT spectral_sample_map_evidence_asset_id_dataset_revision_id_fkey FOREIGN KEY (evidence_asset_id, dataset_revision_id) REFERENCES core.asset(id, dataset_revision_id);


--
-- Name: spectral_sample_map spectral_sample_map_spectral_array_id_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_sample_map
    ADD CONSTRAINT spectral_sample_map_spectral_array_id_dataset_revision_id_fkey FOREIGN KEY (spectral_array_id, dataset_revision_id) REFERENCES core.spectral_array(id, dataset_revision_id);


--
-- Name: spectral_stream spectral_stream_dataset_revision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.spectral_stream
    ADD CONSTRAINT spectral_stream_dataset_revision_id_fkey FOREIGN KEY (dataset_revision_id) REFERENCES core.dataset_revision(id);


--
-- Name: survey_station survey_station_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.survey_station
    ADD CONSTRAINT survey_station_borehole_id_fkey FOREIGN KEY (borehole_id) REFERENCES core.borehole(id);


--
-- Name: survey_station survey_station_branch_id_borehole_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: -
--

ALTER TABLE ONLY core.survey_station
    ADD CONSTRAINT survey_station_branch_id_borehole_id_fkey FOREIGN KEY (branch_id, borehole_id) REFERENCES core.borehole_branch(id, borehole_id);


--
-- PostgreSQL database dump complete
--

