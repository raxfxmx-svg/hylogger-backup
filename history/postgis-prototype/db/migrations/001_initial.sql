\set ON_ERROR_STOP on

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;

SET LOCAL ROLE hylogger_owner;

CREATE SCHEMA IF NOT EXISTS catalog AUTHORIZATION hylogger_owner;
CREATE SCHEMA IF NOT EXISTS ops AUTHORIZATION hylogger_owner;
CREATE SCHEMA IF NOT EXISTS api AUTHORIZATION hylogger_owner;

CREATE TABLE ops.schema_migrations (
    version integer PRIMARY KEY,
    name text NOT NULL UNIQUE,
    sha256 text NOT NULL CHECK (length(sha256) = 64),
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ops.etl_runs (
    run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hole_id text,
    release_id text,
    stage text NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'passed', 'failed')),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK ((status = 'running' AND finished_at IS NULL) OR status <> 'running')
);

CREATE TABLE catalog.releases (
    release_id text PRIMARY KEY,
    schema_version text NOT NULL,
    source_content_fingerprint text NOT NULL UNIQUE,
    source_package_status text NOT NULL,
    release_key text NOT NULL UNIQUE,
    quality_status text NOT NULL CHECK (quality_status IN ('pass', 'fail')),
    created_at timestamptz NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    manifest jsonb NOT NULL,
    quality_report jsonb NOT NULL,
    CHECK (release_key <> ''),
    CHECK (source_content_fingerprint <> '')
);

CREATE TABLE catalog.holes (
    release_id text NOT NULL REFERENCES catalog.releases(release_id) ON DELETE RESTRICT,
    hole_id text NOT NULL,
    source_nvcl_id text,
    source_name text,
    source_x double precision,
    source_y double precision,
    source_z double precision,
    collar geometry(Point, 4326),
    source_href text,
    source_borehole_length text,
    borehole_length_m double precision,
    source_drilling_method text,
    source_operator text,
    source_drill_start_date text,
    drill_start_date date,
    dataset_count integer NOT NULL DEFAULT 0 CHECK (dataset_count >= 0),
    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (release_id, hole_id),
    CHECK (hole_id <> ''),
    CHECK (borehole_length_m IS NULL OR borehole_length_m >= 0),
    CHECK ((source_x IS NULL) = (source_y IS NULL)),
    CHECK (source_x IS NULL OR source_x BETWEEN -180 AND 180),
    CHECK (source_y IS NULL OR source_y BETWEEN -90 AND 90),
    CHECK ((source_x IS NULL AND collar IS NULL) OR (source_x IS NOT NULL AND collar IS NOT NULL))
);

CREATE TABLE catalog.current_releases (
    hole_id text PRIMARY KEY,
    release_id text NOT NULL,
    activated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (release_id, hole_id)
        REFERENCES catalog.holes(release_id, hole_id) ON DELETE RESTRICT
);

CREATE TABLE catalog.datasets (
    release_id text NOT NULL REFERENCES catalog.releases(release_id) ON DELETE RESTRICT,
    dataset_id text NOT NULL,
    hole_id text NOT NULL,
    source_dataset_name text,
    source_borehole_uri text,
    source_tray_log_id text,
    source_section_log_id text,
    source_domain_log_id text,
    description_xml text,
    description_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
    xml_parse_status text,
    source_xml_datum text,
    source_xml_latitude text,
    source_xml_longitude text,
    source_xml_azimuth text,
    source_xml_inclination text,
    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (release_id, dataset_id),
    FOREIGN KEY (release_id, hole_id)
        REFERENCES catalog.holes(release_id, hole_id) ON DELETE RESTRICT,
    CHECK (dataset_id <> '')
);

CREATE TABLE catalog.samples (
    release_id text NOT NULL,
    dataset_id text NOT NULL,
    sample_index integer NOT NULL CHECK (sample_index >= 0),
    source_start_depth text,
    source_end_depth text,
    depth_from_m double precision,
    depth_to_m double precision,
    PRIMARY KEY (release_id, dataset_id, sample_index),
    FOREIGN KEY (release_id, dataset_id)
        REFERENCES catalog.datasets(release_id, dataset_id) ON DELETE RESTRICT,
    CHECK (depth_from_m IS NULL OR depth_to_m IS NULL OR depth_to_m >= depth_from_m)
);

CREATE TABLE catalog.assets (
    release_id text NOT NULL,
    asset_id text NOT NULL,
    hole_id text NOT NULL,
    dataset_id text,
    source_log_id text,
    source_log_name text,
    asset_kind text NOT NULL,
    source_status text NOT NULL,
    source_sample_no text,
    source_depth_from double precision,
    source_depth_to double precision,
    mapping_precision text,
    storage_key text,
    nbytes bigint,
    sha256 text,
    image_format text,
    pixel_width integer,
    pixel_height integer,
    derived_from_asset_id text,
    section_index integer,
    tray_index integer,
    section_index_within_tray integer,
    image_quality text,
    depth_direction text,
    PRIMARY KEY (release_id, asset_id),
    FOREIGN KEY (release_id, hole_id)
        REFERENCES catalog.holes(release_id, hole_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, dataset_id)
        REFERENCES catalog.datasets(release_id, dataset_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, derived_from_asset_id)
        REFERENCES catalog.assets(release_id, asset_id) DEFERRABLE INITIALLY DEFERRED,
    CHECK (asset_id <> ''),
    CHECK (nbytes IS NULL OR nbytes >= 0),
    CHECK (pixel_width IS NULL OR pixel_width > 0),
    CHECK (pixel_height IS NULL OR pixel_height > 0),
    CHECK (source_depth_from IS NULL OR source_depth_to IS NULL OR source_depth_to >= source_depth_from),
    CHECK (sha256 IS NULL OR length(sha256) = 64)
);

CREATE TABLE catalog.trays (
    release_id text NOT NULL,
    dataset_id text NOT NULL,
    tray_index integer NOT NULL CHECK (tray_index >= 0),
    source_tray_value text,
    source_range_start text,
    source_range_end text,
    sample_index_from integer NOT NULL CHECK (sample_index_from >= 0),
    sample_index_to integer NOT NULL CHECK (sample_index_to >= sample_index_from),
    range_mapping_status text NOT NULL,
    sample_axis_start_value text,
    sample_axis_end_value text,
    depth_from_m double precision,
    depth_to_m double precision,
    thumbnail_asset_id text,
    image_mapping_precision text,
    PRIMARY KEY (release_id, dataset_id, tray_index),
    FOREIGN KEY (release_id, dataset_id)
        REFERENCES catalog.datasets(release_id, dataset_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, thumbnail_asset_id)
        REFERENCES catalog.assets(release_id, asset_id) DEFERRABLE INITIALLY DEFERRED,
    CHECK (depth_from_m IS NULL OR depth_to_m IS NULL OR depth_to_m >= depth_from_m)
);

CREATE TABLE catalog.sections (
    release_id text NOT NULL,
    dataset_id text NOT NULL,
    section_index integer NOT NULL CHECK (section_index >= 0),
    source_section_value text,
    tray_index integer NOT NULL CHECK (tray_index >= 0),
    section_index_within_tray integer NOT NULL CHECK (section_index_within_tray >= 0),
    source_range_start text,
    source_range_end text,
    sample_index_from integer NOT NULL CHECK (sample_index_from >= 0),
    sample_index_to integer NOT NULL CHECK (sample_index_to >= sample_index_from),
    range_mapping_status text NOT NULL,
    sample_axis_start_value text,
    sample_axis_end_value text,
    depth_from_m double precision NOT NULL,
    depth_to_m double precision NOT NULL,
    PRIMARY KEY (release_id, dataset_id, section_index),
    FOREIGN KEY (release_id, dataset_id, tray_index)
        REFERENCES catalog.trays(release_id, dataset_id, tray_index) ON DELETE RESTRICT,
    CHECK (depth_to_m >= depth_from_m)
);

CREATE TABLE catalog.section_images (
    release_id text NOT NULL,
    hole_id text NOT NULL,
    dataset_id text NOT NULL,
    section_index integer NOT NULL,
    section_number integer NOT NULL CHECK (section_number > 0),
    tray_index integer NOT NULL CHECK (tray_index >= 0),
    tray_label text,
    section_index_within_tray integer NOT NULL CHECK (section_index_within_tray >= 0),
    row_number integer NOT NULL CHECK (row_number > 0),
    sample_index_from integer NOT NULL CHECK (sample_index_from >= 0),
    sample_index_to integer NOT NULL CHECK (sample_index_to >= sample_index_from),
    depth_from_m double precision NOT NULL,
    depth_to_m double precision NOT NULL,
    strip_asset_id text,
    storage_key text,
    source_thumbnail_asset_id text,
    source_thumbnail_storage_key text,
    image_status text NOT NULL,
    image_quality text,
    mapping_precision text,
    depth_direction text,
    crop_method text,
    crop_left_px integer,
    crop_top_px integer,
    crop_right_px integer,
    crop_bottom_px integer,
    source_pixel_width integer,
    source_pixel_height integer,
    pixel_width integer,
    pixel_height integer,
    nbytes bigint,
    sha256 text,
    note text NOT NULL DEFAULT '',
    PRIMARY KEY (release_id, dataset_id, section_index),
    FOREIGN KEY (release_id, hole_id)
        REFERENCES catalog.holes(release_id, hole_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, dataset_id, section_index)
        REFERENCES catalog.sections(release_id, dataset_id, section_index) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, strip_asset_id)
        REFERENCES catalog.assets(release_id, asset_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (release_id, source_thumbnail_asset_id)
        REFERENCES catalog.assets(release_id, asset_id) DEFERRABLE INITIALLY DEFERRED,
    CHECK (depth_to_m >= depth_from_m),
    CHECK (nbytes IS NULL OR nbytes >= 0),
    CHECK (pixel_width IS NULL OR pixel_width > 0),
    CHECK (pixel_height IS NULL OR pixel_height > 0),
    CHECK (sha256 IS NULL OR length(sha256) = 64)
);

CREATE TABLE catalog.availability (
    availability_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_id text NOT NULL,
    hole_id text NOT NULL,
    dataset_id text NOT NULL,
    data_kind text NOT NULL,
    source_log_id text,
    source_log_name text,
    source_status text NOT NULL,
    expected_count bigint NOT NULL DEFAULT 0 CHECK (expected_count >= 0),
    available_count bigint NOT NULL DEFAULT 0 CHECK (available_count >= 0),
    FOREIGN KEY (release_id, hole_id)
        REFERENCES catalog.holes(release_id, hole_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, dataset_id)
        REFERENCES catalog.datasets(release_id, dataset_id) ON DELETE RESTRICT,
    UNIQUE NULLS NOT DISTINCT (release_id, dataset_id, data_kind, source_log_id),
    CHECK (available_count <= expected_count OR expected_count = 0)
);

CREATE TABLE catalog.scalar_series (
    release_id text NOT NULL,
    hole_id text NOT NULL,
    dataset_id text NOT NULL,
    source_log_id text NOT NULL,
    source_log_name text,
    source_status text NOT NULL,
    source_log_type text,
    source_algorithm_id text,
    source_mask_log_id text,
    source_file text,
    source_sha256 text,
    alignment_status text,
    row_count bigint NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    non_empty_count bigint NOT NULL DEFAULT 0 CHECK (non_empty_count >= 0),
    distinct_non_empty_count bigint NOT NULL DEFAULT 0 CHECK (distinct_non_empty_count >= 0),
    numeric_parseable boolean,
    value_sequence_sha256 text,
    physical_column text,
    is_canonical_physical_column boolean NOT NULL DEFAULT false,
    physical_storage_key text,
    identical_value_series_count integer NOT NULL DEFAULT 1 CHECK (identical_value_series_count > 0),
    PRIMARY KEY (release_id, dataset_id, source_log_id),
    FOREIGN KEY (release_id, hole_id)
        REFERENCES catalog.holes(release_id, hole_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, dataset_id)
        REFERENCES catalog.datasets(release_id, dataset_id) ON DELETE RESTRICT,
    CHECK (source_sha256 IS NULL OR length(source_sha256) = 64),
    CHECK (value_sequence_sha256 IS NULL OR length(value_sequence_sha256) = 64)
);

CREATE TABLE catalog.spectral_axes (
    release_id text NOT NULL REFERENCES catalog.releases(release_id) ON DELETE RESTRICT,
    axis_id text NOT NULL,
    wavelength_units text,
    band_count integer NOT NULL CHECK (band_count > 0),
    values_sha256 text NOT NULL CHECK (length(values_sha256) = 64),
    storage_key text NOT NULL,
    PRIMARY KEY (release_id, axis_id)
);

CREATE TABLE catalog.spectral_series (
    release_id text NOT NULL,
    series_id text NOT NULL,
    hole_id text NOT NULL,
    dataset_id text NOT NULL,
    source_log_id text NOT NULL,
    source_log_name text,
    source_status text NOT NULL,
    sample_count bigint NOT NULL DEFAULT 0 CHECK (sample_count >= 0),
    band_count integer NOT NULL CHECK (band_count > 0),
    dtype text,
    byte_order text,
    axis_id text NOT NULL,
    axis_storage_key text,
    sample_alignment_status text,
    values_storage_key text,
    manifest_storage_key text,
    nbytes bigint NOT NULL DEFAULT 0 CHECK (nbytes >= 0),
    sha256 text,
    finite_value_count bigint,
    nonfinite_value_count bigint,
    finite_min double precision,
    finite_max double precision,
    PRIMARY KEY (release_id, series_id),
    FOREIGN KEY (release_id, hole_id)
        REFERENCES catalog.holes(release_id, hole_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, dataset_id)
        REFERENCES catalog.datasets(release_id, dataset_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, axis_id)
        REFERENCES catalog.spectral_axes(release_id, axis_id) ON DELETE RESTRICT,
    CHECK (sha256 IS NULL OR length(sha256) = 64),
    CHECK (finite_value_count IS NULL OR finite_value_count >= 0),
    CHECK (nonfinite_value_count IS NULL OR nonfinite_value_count >= 0),
    CHECK (finite_min IS NULL OR finite_max IS NULL OR finite_max >= finite_min)
);

CREATE INDEX idx_etl_runs_hole_started
    ON ops.etl_runs (hole_id, started_at DESC);
CREATE INDEX idx_holes_collar_gist
    ON catalog.holes USING gist (collar) WHERE collar IS NOT NULL;
CREATE INDEX idx_current_releases_release
    ON catalog.current_releases (release_id);
CREATE INDEX idx_datasets_hole
    ON catalog.datasets (release_id, hole_id);
CREATE INDEX idx_samples_depth
    ON catalog.samples (release_id, dataset_id, depth_from_m, depth_to_m);
CREATE INDEX idx_assets_hole_kind
    ON catalog.assets (release_id, hole_id, asset_kind, source_status);
CREATE INDEX idx_sections_depth
    ON catalog.sections (release_id, dataset_id, depth_from_m, depth_to_m);
CREATE INDEX idx_section_images_asset
    ON catalog.section_images (release_id, strip_asset_id);
CREATE INDEX idx_availability_hole_kind
    ON catalog.availability (release_id, hole_id, data_kind, source_status);
CREATE INDEX idx_scalar_series_hole
    ON catalog.scalar_series (release_id, hole_id, source_status);
CREATE INDEX idx_spectral_series_hole
    ON catalog.spectral_series (release_id, hole_id, source_status);

CREATE VIEW api.current_holes AS
SELECT h.*
FROM catalog.current_releases cr
JOIN catalog.holes h
  ON h.release_id = cr.release_id AND h.hole_id = cr.hole_id;

CREATE VIEW api.current_datasets AS
SELECT d.*
FROM catalog.current_releases cr
JOIN catalog.datasets d
  ON d.release_id = cr.release_id AND d.hole_id = cr.hole_id;

CREATE VIEW api.current_trays AS
SELECT t.*
FROM catalog.current_releases cr
JOIN catalog.datasets d
  ON d.release_id = cr.release_id AND d.hole_id = cr.hole_id
JOIN catalog.trays t
  ON t.release_id = d.release_id AND t.dataset_id = d.dataset_id;

CREATE VIEW api.current_sections AS
SELECT s.*
FROM catalog.current_releases cr
JOIN catalog.datasets d
  ON d.release_id = cr.release_id AND d.hole_id = cr.hole_id
JOIN catalog.sections s
  ON s.release_id = d.release_id AND s.dataset_id = d.dataset_id;

CREATE VIEW api.current_assets AS
SELECT a.*
FROM catalog.current_releases cr
JOIN catalog.assets a
  ON a.release_id = cr.release_id AND a.hole_id = cr.hole_id;

CREATE VIEW api.current_section_images AS
SELECT si.*
FROM catalog.current_releases cr
JOIN catalog.section_images si
  ON si.release_id = cr.release_id AND si.hole_id = cr.hole_id;

CREATE VIEW api.current_availability AS
SELECT av.*
FROM catalog.current_releases cr
JOIN catalog.availability av
  ON av.release_id = cr.release_id AND av.hole_id = cr.hole_id;

REVOKE ALL ON SCHEMA catalog, ops, api FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA catalog, ops, api FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA catalog, ops, api FROM PUBLIC;

GRANT USAGE ON SCHEMA catalog, ops TO hylogger_loader;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA catalog, ops TO hylogger_loader;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA catalog, ops TO hylogger_loader;

GRANT USAGE ON SCHEMA api TO hylogger_api;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO hylogger_api;

ALTER DEFAULT PRIVILEGES FOR ROLE hylogger_owner IN SCHEMA catalog
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hylogger_loader;
ALTER DEFAULT PRIVILEGES FOR ROLE hylogger_owner IN SCHEMA ops
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hylogger_loader;
ALTER DEFAULT PRIVILEGES FOR ROLE hylogger_owner IN SCHEMA catalog
    GRANT USAGE, SELECT ON SEQUENCES TO hylogger_loader;
ALTER DEFAULT PRIVILEGES FOR ROLE hylogger_owner IN SCHEMA ops
    GRANT USAGE, SELECT ON SEQUENCES TO hylogger_loader;
ALTER DEFAULT PRIVILEGES FOR ROLE hylogger_owner IN SCHEMA api
    GRANT SELECT ON TABLES TO hylogger_api;

INSERT INTO ops.schema_migrations (version, name, sha256)
VALUES (1, '001_initial', :'migration_sha');

COMMIT;
