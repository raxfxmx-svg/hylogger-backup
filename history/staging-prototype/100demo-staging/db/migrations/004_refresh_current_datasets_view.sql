\set ON_ERROR_STOP on

BEGIN;

SET LOCAL ROLE hylogger_owner;

CREATE OR REPLACE VIEW api.current_datasets AS
SELECT d.*
FROM catalog.current_releases cr
JOIN catalog.datasets d
  ON d.release_id = cr.release_id AND d.hole_id = cr.hole_id;

GRANT SELECT ON api.current_datasets TO hylogger_api;

INSERT INTO ops.schema_migrations (version, name, sha256)
VALUES (4, '004_refresh_current_datasets_view', :'migration_sha');

COMMIT;
