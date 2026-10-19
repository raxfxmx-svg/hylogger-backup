-- Run only on database-1 / etl4_core after restore verification.
-- Creates a new passwordless PostgreSQL login for existing IAM authorization.
-- Does not create AWS access keys, attach IAM policies, or modify postgres.
-- Refuses an existing same-named role; review it separately instead of altering it.
\set ON_ERROR_STOP on
BEGIN;
CREATE ROLE etl4_reader LOGIN PASSWORD NULL NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT rds_iam TO etl4_reader;
GRANT CONNECT ON DATABASE etl4_core TO etl4_reader;
GRANT USAGE ON SCHEMA core, public TO etl4_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA core TO etl4_reader;
ALTER ROLE etl4_reader SET default_transaction_read_only = on;
ALTER ROLE etl4_reader SET search_path = core, public;
COMMIT;
