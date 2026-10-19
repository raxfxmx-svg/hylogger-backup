\set ON_ERROR_STOP on

BEGIN;

DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hylogger_owner') THEN
        CREATE ROLE hylogger_owner NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hylogger_loader') THEN
        CREATE ROLE hylogger_loader NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hylogger_api') THEN
        CREATE ROLE hylogger_api NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hylogger_loader_local') THEN
        CREATE ROLE hylogger_loader_local LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hylogger_api_local') THEN
        CREATE ROLE hylogger_api_local LOGIN;
    END IF;
END
$roles$;

ALTER ROLE hylogger_owner
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE hylogger_loader
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE hylogger_api
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE hylogger_loader_local
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE hylogger_api_local
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

GRANT hylogger_owner TO postgres WITH ADMIN OPTION;
GRANT hylogger_loader TO hylogger_loader_local;
GRANT hylogger_api TO hylogger_api_local;
GRANT CONNECT, CREATE ON DATABASE :"DBNAME" TO hylogger_owner;
GRANT CONNECT ON DATABASE :"DBNAME" TO hylogger_loader, hylogger_api,
    hylogger_loader_local, hylogger_api_local;

COMMIT;
