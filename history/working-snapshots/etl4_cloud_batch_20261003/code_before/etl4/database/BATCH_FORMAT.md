# Independent Batch Format

`etl4-batch-v1` packages validated datasets for transfer without copying large assets. Step 38 exports; step 39 uploads. See [the runbook](LOCAL_BATCH_RUNBOOK.md).

The package contains `manifest.json`, 29 compressed business-table files, all 39 table definitions, six original migrations, both local acceptance records and `composites.json`. Empty tables retain files. Two tables represent validation/file locations, two represent local run management, and six release/display tables are represented through target publication definitions. New schema tables require an explicit export classification.

Dataset, revision, axis, sample and asset UUIDs remain unchanged. PostgreSQL emits typed JSON records sorted by primary key, with deterministic gzip headers and UTC/ISO session settings. Restore through PostgreSQL record types to retain numeric precision, NULL, arrays, JSON and UUID. Collar geometry uses hexadecimal EWKB including SRID, restored with `ST_GeomFromEWKB(decode(value,'hex'))`.

`batch_id` hashes the format, migrations, sorted dataset/input identities and display definitions. Times, run IDs and local paths are excluded. File SHA256 values separately identify transmitted bytes. Identical exports reuse the saved public package; conflicting business content for the same identity is rejected.

Large assets remain in place. `manifest.assets` records their IDs, versions, byte sizes, SHA256, media types and object keys. Equal content shares an object key while retaining distinct asset identities. `local_sources.json` binds the manifest digest to private local file paths and is not uploaded.

The default S3 prefix is `etl4`: assets use `<prefix>/objects/sha256/<first-two-hash-characters>/<sha256>`; package files use `<prefix>/batches/<batch_id>/<manifest_sha256>/<relative-path>`. The manifest uploads last. Receipts record the actual target, object keys and partial/complete progress. Matching remote full-object checksums allow reuse; conflicts are not overwritten. ETags or self-reported metadata alone do not prove integrity. Interrupted files restart from their beginning; completed objects can be reused.

This snapshot implements export and SDK upload. Cloud database merge was still planned: restore transactions, content conflicts, release relationships and S3 locations required the later merge implementation. A full database dump is for backup/restore, not for stacking batches into the target database.
