-- Read-only inspection. Connect to postgres first; do not restore into postgres.
\set ON_ERROR_STOP on
\pset pager off
BEGIN READ ONLY;
SELECT current_database() AS database_name, current_user AS login_role,
       current_setting('server_version') AS postgres_version,
       pg_is_in_recovery() AS is_reader;
SELECT aurora_version();
SELECT ssl, version AS tls_version
FROM pg_stat_ssl WHERE pid = pg_backend_pid();
SELECT name, version, installed FROM pg_available_extension_versions
WHERE name = 'postgis' ORDER BY version;
SELECT e.extname, e.extversion, n.nspname AS extension_schema
FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
WHERE e.extname = 'postgis';
SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY datname;
SELECT count(*) AS core_relation_count FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'core';
COMMIT;
