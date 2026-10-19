# PostgreSQL/PostGIS database foundation

This directory owns the versioned database foundation for the local
`hylogger` database. SQLite is not part of this path.

## Roles

- `hylogger_owner`: owns schemas and database objects; cannot log in.
- `hylogger_loader`: ETL data privileges; cannot log in directly.
- `hylogger_api`: read-only access to views in the `api` schema; cannot log in directly.

Application login roles inherit one of the two least-privilege roles, so no
application needs to connect as `postgres`.

`bootstrap_roles.sql` creates `hylogger_loader_local` and
`hylogger_api_local` as login roles with no initial password. The current
local demo has already configured them. On a new machine or when rotating
credentials, set both interactively without writing passwords into SQL:

```powershell
$env:PGPASSWORD = '<local postgres password>'
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -X -w `
  -h localhost -p 5432 -U postgres -d hylogger `
  -f .\db\set_local_passwords.sql
Remove-Item Env:PGPASSWORD
```

## Apply migrations

From PowerShell, set the administrator password only for the current process,
run the migration wrapper, and remove it afterwards:

```powershell
$env:PGPASSWORD = '<local postgres password>'
& .\db\apply_migrations.ps1
Remove-Item Env:PGPASSWORD
```

The wrapper bootstraps the logical roles, applies numbered SQL files in order,
and records the SHA-256 of every applied migration. Never edit an applied SQL
file; add the next numbered migration instead.

## Verify

```powershell
$env:PGPASSWORD = '<local postgres password>'
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -X -w `
  -h localhost -p 5432 -U postgres -d hylogger `
  -f .\db\verify_foundation.sql
Remove-Item Env:PGPASSWORD
```

The verification script checks PostGIS, schemas, objects, non-login roles,
the absence of deferred trajectory columns, loader write permission inside a
rolled-back transaction, and API read access through the current-data views.
