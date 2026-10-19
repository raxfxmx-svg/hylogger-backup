# Single-Hole PostgreSQL Importer

`load_release.py` accepts a prepared single-hole package with quality status pass. Before connecting, it checks every manifest file's size/SHA256 and all Parquet row counts. `--check-only` performs the precheck without importing.

Import runs transactionally. The current release changes only after reconciliation; failures roll back business data and retain a failed ops.etl_runs record. Reimporting the same release is idempotent. The verifier checks all table counts, EPSG:4326 collars, section/asset relationships and every section image hash. Configure credentials locally; the historical foundation commands below use the loader role.

## Commands

```powershell
.\.venv\Scripts\python -m etl.load_release `
  .\data\processed\releases\<release_id> --check-only
```

```powershell
$env:HYLOGGER_DB_USER = 'postgres'
$env:PGPASSWORD = '<local postgres password>'
.\.venv\Scripts\python -m etl.load_release `
  .\data\processed\releases\<release_id> `
  --set-role hylogger_loader
Remove-Item Env:PGPASSWORD
Remove-Item Env:HYLOGGER_DB_USER
```

```powershell
$env:HYLOGGER_DB_USER = 'postgres'
$env:PGPASSWORD = '<local postgres password>'
.\.venv\Scripts\python -m etl.verify_loaded 05GJD001 `
  --set-role hylogger_loader
Remove-Item Env:PGPASSWORD
Remove-Item Env:HYLOGGER_DB_USER
```
