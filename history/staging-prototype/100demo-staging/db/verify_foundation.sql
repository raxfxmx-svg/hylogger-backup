\set ON_ERROR_STOP on

SELECT current_database() AS database_name,
       postgis_version() AS postgis_version;

SELECT nspname AS schema_name
FROM pg_namespace
WHERE nspname IN ('catalog', 'ops', 'api')
ORDER BY nspname;

SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname IN ('catalog', 'ops')
ORDER BY schemaname, tablename;

SELECT schemaname, viewname
FROM pg_views
WHERE schemaname = 'api'
ORDER BY viewname;

SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
FROM pg_roles
WHERE rolname IN ('hylogger_owner', 'hylogger_loader', 'hylogger_api')
ORDER BY rolname;

SELECT count(*) AS forbidden_trajectory_columns
FROM information_schema.columns
WHERE table_schema IN ('catalog', 'ops', 'api')
  AND column_name IN (
      'trajectory_geom',
      'trajectory_kind',
      'trajectory_source',
      'trajectory_status'
  );

BEGIN;
SET LOCAL ROLE hylogger_loader;
INSERT INTO ops.etl_runs (hole_id, stage, status, finished_at, detail)
VALUES ('FOUNDATION_PERMISSION_TEST', 'permission_test', 'passed', now(), '{"rolled_back": true}'::jsonb);
ROLLBACK;

SET ROLE hylogger_api;
SELECT count(*) AS api_visible_holes FROM api.current_holes;
RESET ROLE;
