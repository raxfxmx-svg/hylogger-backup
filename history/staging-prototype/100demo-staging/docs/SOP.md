# Borehole Processing and API Workflow

Create the Python environment, install dependencies, apply database migrations and configure separate local loader/API credentials. The password script prompts locally; `.env` is excluded from Git. Supply a complete downloader package under `data/raw/<hole_id>/`, not only JPEG files.

The process_hole command performs ETL3 transformation and verification, package precheck, transactional import and loaded coordinate/count/image-hash checks. It stops at the first failure and changes the current release only after success. Existing packages can use import_release.ps1 directly.

Start the API with run_api.ps1. Validate pipeline/verify.py, etl.verify_loaded, hole counts, first/middle/last section images and the passed ops.etl_runs entry. Keep the database backup together with its processed release directory; object files are not inside the dump.

## Commands

```powershell
cd D:\100demo
```

```powershell
$env:PGPASSWORD = '<POSTGRES_ADMIN_PASSWORD>'
.\db\apply_migrations.ps1 -Database hylogger_100demo
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -X -w `
  -h localhost -p 5432 -U postgres -d hylogger_100demo `
  -f .\db\set_local_passwords.sql
Remove-Item Env:PGPASSWORD
```

```powershell
$env:HYLOGGER_DB_USER = 'hylogger_loader_local'
$env:HYLOGGER_DB_PASSWORD = '<LOCAL_ETL_PASSWORD>'
.\scripts\process_hole.ps1 -HoleId 05GJD001
Remove-Item Env:HYLOGGER_DB_PASSWORD
Remove-Item Env:HYLOGGER_DB_USER
```

```powershell
.\scripts\run_api.ps1
```

The historical 100-hole batch first used --dry-run with two workers, ten-hole waves and a target of 100. Starting from six completed holes, it selected 94 remaining holes, recorded checkpoints each wave and replaced failed holes. Three consecutive failures within a wave paused the batch. API documentation used port 8100.
