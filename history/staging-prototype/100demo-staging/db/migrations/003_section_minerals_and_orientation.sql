\set ON_ERROR_STOP on

BEGIN;

SET LOCAL ROLE hylogger_owner;

ALTER TABLE catalog.datasets
    ADD COLUMN azimuth_deg double precision,
    ADD COLUMN inclination_deg double precision,
    ADD COLUMN orientation_status text NOT NULL DEFAULT 'missing',
    ADD CONSTRAINT datasets_azimuth_deg_check
        CHECK (azimuth_deg IS NULL OR (azimuth_deg >= 0 AND azimuth_deg < 360)),
    ADD CONSTRAINT datasets_inclination_deg_check
        CHECK (inclination_deg IS NULL OR (inclination_deg >= -90 AND inclination_deg <= 90)),
    ADD CONSTRAINT datasets_orientation_status_check
        CHECK (orientation_status IN ('reported', 'source_zero_placeholder', 'missing', 'invalid')),
    ADD CONSTRAINT datasets_orientation_values_check
        CHECK (
            (orientation_status = 'reported' AND azimuth_deg IS NOT NULL AND inclination_deg IS NOT NULL)
            OR
            (orientation_status <> 'reported' AND azimuth_deg IS NULL AND inclination_deg IS NULL)
        );

WITH parsed AS (
    SELECT release_id,
           dataset_id,
           btrim(source_xml_azimuth) AS azimuth_text,
           btrim(source_xml_inclination) AS inclination_text,
           btrim(source_xml_azimuth) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$' AS azimuth_numeric,
           btrim(source_xml_inclination) ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$' AS inclination_numeric
    FROM catalog.datasets
), classified AS (
    SELECT release_id,
           dataset_id,
           CASE
               WHEN azimuth_text IS NULL OR azimuth_text = ''
                 OR inclination_text IS NULL OR inclination_text = '' THEN 'missing'
               WHEN NOT azimuth_numeric OR NOT inclination_numeric THEN 'invalid'
               WHEN azimuth_text::double precision < 0 OR azimuth_text::double precision >= 360
                 OR inclination_text::double precision < -90 OR inclination_text::double precision > 90 THEN 'invalid'
               WHEN azimuth_text::double precision = 0 AND inclination_text::double precision = 0
                 THEN 'source_zero_placeholder'
               ELSE 'reported'
           END AS status,
           CASE WHEN azimuth_numeric THEN azimuth_text::double precision END AS parsed_azimuth,
           CASE WHEN inclination_numeric THEN inclination_text::double precision END AS parsed_inclination
    FROM parsed
)
UPDATE catalog.datasets AS d
SET orientation_status = c.status,
    azimuth_deg = CASE WHEN c.status = 'reported' THEN c.parsed_azimuth END,
    inclination_deg = CASE WHEN c.status = 'reported' THEN c.parsed_inclination END
FROM classified AS c
WHERE c.release_id = d.release_id
  AND c.dataset_id = d.dataset_id;

CREATE TABLE catalog.section_minerals (
    release_id text NOT NULL,
    hole_id text NOT NULL,
    dataset_id text NOT NULL,
    section_index integer NOT NULL CHECK (section_index >= 0),
    primary_raw text,
    primary_fraction double precision,
    secondary_raw text,
    secondary_fraction double precision,
    display_group text,
    display_color text NOT NULL,
    confidence double precision NOT NULL,
    quality text NOT NULL,
    classified_sample_count integer NOT NULL CHECK (classified_sample_count >= 0),
    total_sample_count integer NOT NULL CHECK (total_sample_count > 0),
    source_log_name text,
    source_log_id text,
    source_algorithm_id text,
    aggregation text NOT NULL DEFAULT 'section_mode_v1',
    PRIMARY KEY (release_id, dataset_id, section_index),
    FOREIGN KEY (release_id, hole_id)
        REFERENCES catalog.holes(release_id, hole_id) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, dataset_id, section_index)
        REFERENCES catalog.sections(release_id, dataset_id, section_index) ON DELETE RESTRICT,
    FOREIGN KEY (release_id, dataset_id, source_log_id)
        REFERENCES catalog.scalar_series(release_id, dataset_id, source_log_id) ON DELETE RESTRICT,
    CHECK (primary_fraction IS NULL OR (primary_fraction >= 0 AND primary_fraction <= 1)),
    CHECK (secondary_fraction IS NULL OR (secondary_fraction >= 0 AND secondary_fraction <= 1)),
    CHECK (confidence >= 0 AND confidence <= 1),
    CHECK (classified_sample_count <= total_sample_count),
    CHECK (display_color ~ '^#[0-9a-fA-F]{6}$'),
    CHECK (quality IN ('ok', 'low_confidence', 'unclassified', 'source_unavailable')),
    CHECK (aggregation = 'section_mode_v1')
);

CREATE INDEX section_minerals_hole_idx
    ON catalog.section_minerals (hole_id, dataset_id, section_index);

CREATE VIEW api.current_section_minerals AS
SELECT sm.*
FROM catalog.current_releases cr
JOIN catalog.section_minerals sm
  ON sm.release_id = cr.release_id AND sm.hole_id = cr.hole_id;

GRANT SELECT, INSERT, UPDATE, DELETE ON catalog.section_minerals TO hylogger_loader;
GRANT SELECT ON api.current_section_minerals TO hylogger_api;

INSERT INTO ops.schema_migrations (version, name, sha256)
VALUES (3, '003_section_minerals_and_orientation', :'migration_sha');

COMMIT;
