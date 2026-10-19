# Five-hole cloud API route guide

Start with [the connection guide](../deployment/TEAMMATE_START.md) and use
`deployment/run_api.py`. Install only `deployment/requirements-cloud.txt` for this
standalone supplement. No files from the old database archive are needed at runtime.

Every route requires `Authorization: Bearer <your-api-token>`. There are no public
or presigned S3 image links. Swagger/OpenAPI HTTP pages and CORS are not enabled.
The bearer-token scheme and single local worker serve the pilot; persistent HTTPS
hosting and production application authentication are separate deployment work.

In the example below, set `ETL4_API_TOKEN` in your HTTP-client terminal through
your private secret handling to the same token entered in the server terminal.
If writing the PNG output, run from this package's top-level folder.

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
