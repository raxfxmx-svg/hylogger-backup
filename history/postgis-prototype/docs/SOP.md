# Borehole Processing and API Workflow

Create the Python environment, install dependencies, apply database migrations and configure separate local loader/API credentials. The password script prompts locally; `.env` is excluded from Git. Supply a complete downloader package under `data/raw/<hole_id>/`, not only JPEG files.

The process_hole command performs ETL3 transformation and verification, package precheck, transactional import and loaded coordinate/count/image-hash checks. It stops at the first failure and changes the current release only after success. Existing packages can use import_release.ps1 directly.

Start the API with run_api.ps1. Validate pipeline/verify.py, etl.verify_loaded, hole counts, first/middle/last section images and the passed ops.etl_runs entry. Keep the database backup together with its processed release directory; object files are not inside the dump.

## Commands

```powershell
cd C:\path\to\project\demo2
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

```powershell
$env:PGPASSWORD = '<POSTGRES_ADMIN_PASSWORD>'
.\db\apply_migrations.ps1
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -X -w `
  -h localhost -p 5432 -U postgres -d hylogger `
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

API documentation uses http://127.0.0.1:8000/docs. Configure listening address, firewall and allowed frontend origins separately for a network demonstration.
