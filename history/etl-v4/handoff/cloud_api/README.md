# Five-hole private cloud API pilot

This small API validates the fixed ETL4 release `fd02659c-dc3d-52ea-a8eb-c032b91e7624` against PostgreSQL and **S3 only**. It covers the five verified holes and does not implement the full reference API or ingestion for 2,000+ holes. No local data fallback, global monkeypatch, public bucket, credentials file, or cloud resource creation is used.

The implementation is adapted from the packaged reference reader's SQL relationships and scientific result semantics. This directory is separate from that unchanged reference code. Offline tests use mocked S3/database responses, the real sample-15 Parquet and PNG, and explicitly synthetic F32 bytes. **This is preparation evidence, not proof of a successful AWS deployment.**

## Before running

For the existing Sydney target, use [the teammate guide](../deployment/TEAMMATE_START.md)
and `deployment/run_api.py`. The database has already been restored. This target
requires IAM authentication and public CA roots; generic password/restore advice
below applies only to other newly provisioned targets.

Live acceptance for this Sydney deployment passed on 2026-09-18: five holes,
13 image/indicator fixtures and eight full scientific spectrum comparisons.
See `validation/cloud_api_acceptance.json` and `validation/deployment_summary.json`.
New database connections allow up to 60 seconds for Aurora to resume from its
configured auto-pause state. This does not create a persistent public API service.

Restore the package to an empty compatible database using `tools/handoff.py`. Create a separate reader role, upload and verify all package assets, and register the verified S3 locations. Run `check-db` using that reader. See the package operations document for these steps.

The API identity needs `s3:GetObject` for the selected prefix and, if applicable, permission to decrypt the bucket's KMS key. The S3 bucket must remain private. Use the normal AWS credential provider (an instance role, an AWS profile/SSO session, or your approved equivalent). Do not put AWS credentials in these files.

The database connection is independent of the sender's `runtime/local_config.json`. Each connection sets read-only transactions, verifies that the role lacks core table write and schema CREATE permissions and elevated PostgreSQL role flags, verifies TLS, and checks the active release. Use the dedicated reader; the administrator is refused.

## Environment configuration

Run from the **package root**, the folder containing this `cloud_api/` directory. Install the existing `requirements.txt` and `requirements-aws.txt` with Python 3.12. Set these variables in your process through your chosen secret/configuration mechanism:

| Variable | Required value |
| --- | --- |
| `ETL4_READ_DSN` | libpq DSN: real host, port, database, reader user, `sslmode=verify-full`, official CA path in `sslrootcert`; password when using password authentication |
| `ETL4_API_TOKEN` | A private randomly generated bearer token of at least 32 characters |
| `S3_BUCKET` | The private bucket used by `upload-s3` |
| `AWS_REGION` | `ap-southeast-2` for the Sydney pilot |
| `S3_PREFIX` | Exact object prefix used during upload, default `data` |
| `ETL4_S3_ROOT_KEY` | Registered logical root, default `etl4_s3_primary` |
| `ETL4_DB_AUTH` | `password` (default), or `iam` |

The `root_key` to bucket/region/prefix mapping must match `validation/s3_mapping.json` and `validation/s3_receipt.json`. Do not reuse an existing logical root for a different bucket. The app reads the exact registered database object key; it does not prepend the prefix again. It refuses keys outside the configured prefix and ambiguous locations. No endpoint accepts a caller-supplied S3 key or bucket.

For IAM database authentication, omit `password` from the DSN. The app generates a fresh token before each new connection using the actual database hostname, port, username and region. The DB user must already have `rds_iam`; the AWS identity needs the matching `rds-db:connect` permission. A successful token generation alone does not prove those permissions. Token expiry does not terminate an already established connection. Never paste IAM tokens into source files or send them to the API as its bearer token.

Configuration values and credentials are deliberately not supplied as a ready-to-use example command. The app does not automatically load a `.env` file. Do not write secrets into shared shell history.

## Start locally

With the environment configured, start one worker bound to loopback:

```powershell
python -m uvicorn cloud_api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --limit-concurrency 8 --no-access-log
```

This command **does not publish or host a public API**. A local process may connect to AWS if its network route and identity permit it. Public hosting, HTTPS termination, application identities, rate limiting and production connection pooling remain deployment decisions. Do not expose this plain-HTTP loopback pilot directly to the Internet. Its shared bearer token is intended for this controlled pilot, not a final multi-user authentication system.

Every route, including images and health, requires `Authorization: Bearer <ETL4_API_TOKEN>`. Images are returned through the authenticated API; no public or presigned S3 URLs are created. Documentation and OpenAPI HTTP endpoints are disabled for this small pilot. CORS is not configured.

## API routes

| Method and path | Behavior |
| --- | --- |
| `GET /health` | Checks database/release; explicitly does not claim S3 access has been tested |
| `GET /v1/holes` | Lists the five holes, dataset/revision/axis IDs and counts |
| `GET /v1/holes/{hole}/logs` | Lists result and image log IDs for selection |
| `GET /v1/holes/{hole}/samples/{sample_no}` | Depth, sample identity and row-image candidates; results omitted by default |
| `GET /v1/images/{asset_id}/content` | Verified PNG bytes, restricted to reviewed row images in this release |

For sample results repeat the `log_id` query parameter (at most 16 UUIDs). Scalar, profile and spectral logs share this endpoint. Add `image_log_id` to select an image log when multiple candidates exist. Results follow the reference reader's ordering, not the order of submitted IDs.

Example authenticated sample request from PowerShell after environment configuration:

```powershell
$etl4Headers = @{ Authorization = "Bearer $env:ETL4_API_TOKEN" }
$etl4Sample = Invoke-RestMethod -Headers $etl4Headers -Uri 'http://127.0.0.1:8000/v1/holes/07THD002/samples/15?log_id=a4a5c7d3-0fe8-53be-97a2-02a5c7771ae8&log_id=1936b71e-f3bc-56d8-ae0e-d284edf0a86b'
$etl4Sample.md_m
$etl4Sample.results
Invoke-WebRequest -Headers $etl4Headers -Uri ('http://127.0.0.1:8000' + $etl4Sample.images[0].content_path) -OutFile 'validation/cloud_sample15.png'
```

Expected sample-15 depth is `62.50175`; the selected scalar is `Muscovite`; its PNG is 399 by 25 pixels. The selected VSWIR spectrum has 531 channels. `examples/DATASET_CATALOG.json` lists all eight spectral logs (531 VSWIR or 341 TIR channels). Check 05KCD001 samples 129 and 130 as well: equal depth must still select different row images. Record those checks separately as cloud evidence after they really succeed.

## Storage and scientific boundaries

- Locations must be S3, `verified_remote`, in the configured logical root, and match the asset SHA256. The process never reads package-local data files.
- Parquet and PNG objects are fetched on demand and checked against their full asset SHA256. Encoded bytes use an LRU cache capped at 128 MiB; one full object is capped at 64 MiB. Decoded Parquet row groups, responses and concurrent requests need additional memory. Cache state is per worker, hence the single-worker pilot command.
- F32 matrices are never fetched as whole files. Each read requests the inclusive HTTP byte range for an existing verified `spectral_block`, checks range metadata, length and block SHA256, and then reads the selected sample's little-endian Float32 values. A block is capped at 16 MiB.
- Cached values are content-verified bytes. Restart the process to clear the cache when diagnosing S3 changes. Keep the fixed-release prefix controlled; it is not a mutable upload target for the API identity.
- Sample numbers are zero-based; repeated depths remain different samples. Images use the same axis and section plus a closed sample interval. Multiple image candidates remain explicit. An indicator is approximate sample-index position, not an exact depth or mineral location in the image.
- Null source values remain null; spectral NaN/infinity become JSON null with their channel indexes listed. No scaling or normalization is applied. Profile values retain the uncalibrated status. Sparse interval logs remain unavailable through this dense sample endpoint.
- Responses contain an authenticated image `content_path`, not a local path or S3 object key. Authentication errors return 401; cross-release selection returns 404/422; provider/connection failures return a generic 503 without DSN or filesystem details.

## Offline verification

From the package root, without AWS credentials or a running database:

```powershell
python -m unittest cloud_api.test_cloud_api -v
```

The tests exercise authentication, fixed five-hole scope, exact sample-15 scalar/indicator and actual image checksum, F32 Range reads and nonfinite handling, checksum corruption, incorrect range metadata, bounded caching, read-role rejection and secret-safe errors. The mock database does not prove the SQL against Aurora; complete the real restore, reader checks and cloud sample checks before calling the deployment successful.
