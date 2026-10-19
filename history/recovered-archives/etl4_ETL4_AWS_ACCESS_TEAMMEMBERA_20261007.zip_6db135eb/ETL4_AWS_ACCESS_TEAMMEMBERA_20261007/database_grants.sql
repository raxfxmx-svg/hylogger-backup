-- Reviewed one-time grants; run transactionally using prepare_access.py.
CREATE ROLE etl4_teammembera_dev LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT rds_iam TO etl4_teammembera_dev;
GRANT CONNECT ON DATABASE etl4_core TO etl4_teammembera_dev;
GRANT USAGE ON SCHEMA core, public TO etl4_teammembera_dev;
GRANT SELECT ON ALL TABLES IN SCHEMA core TO etl4_teammembera_dev;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA core GRANT SELECT ON TABLES TO etl4_teammembera_dev;
CREATE SCHEMA dev_teammembera AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA dev_teammembera FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA dev_teammembera TO etl4_teammembera_dev;
ALTER ROLE etl4_teammembera_dev IN DATABASE etl4_core SET search_path TO dev_teammembera, core, public;
ALTER ROLE etl4_teammembera_dev IN DATABASE etl4_core SET default_transaction_read_only TO off;
ALTER ROLE etl4_teammembera_dev IN DATABASE etl4_core SET statement_timeout TO '120s';
ALTER ROLE etl4_teammembera_dev IN DATABASE etl4_core SET lock_timeout TO '5s';
ALTER ROLE etl4_teammembera_dev IN DATABASE etl4_core SET idle_in_transaction_session_timeout TO '60s';
