# Troubleshooting

- Failed package precheck: restore the missing or corrupted source file. Do not edit a manifest to conceal a hash mismatch.
- Existing release: reuse it when content matches; updated sources require a new content identity. Release directories are immutable.
- Failed import: the data transaction rolls back and the previous current release remains. Inspect `SELECT * FROM ops.etl_runs ORDER BY run_id DESC LIMIT 10;`, then fix code or add a new migration. Keep applied migrations unchanged.
- API authentication failure: check the local hylogger_api_local credentials and PostgreSQL service; configure passwords through db/set_local_passwords.sql.
- Image 404: check image.status and whether the corresponding release files were copied with the database.
- Image 500: verify registered size/path against disk using `python -m etl.verify_loaded <hole_id>` and restore matching files from the same release backup.
