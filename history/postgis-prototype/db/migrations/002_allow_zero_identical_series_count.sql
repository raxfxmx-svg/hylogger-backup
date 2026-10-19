\set ON_ERROR_STOP on

BEGIN;

SET LOCAL ROLE hylogger_owner;

ALTER TABLE catalog.scalar_series
    DROP CONSTRAINT scalar_series_identical_value_series_count_check;

ALTER TABLE catalog.scalar_series
    ADD CONSTRAINT scalar_series_identical_value_series_count_check
    CHECK (identical_value_series_count >= 0);

INSERT INTO ops.schema_migrations (version, name, sha256)
VALUES (2, '002_allow_zero_identical_series_count', :'migration_sha');

COMMIT;
