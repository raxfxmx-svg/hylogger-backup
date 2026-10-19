# Frontend deployment

Explore, Compare and 3D consume the FastAPI `/v1` contract in `../backend`,
through `lib/v1-client.cjs`. They no longer use the legacy Django API. Deploy
the backend first; see `../backend/deployment/README.md`.

Set `NEXT_PUBLIC_API_BASE` in the Amplify **build** environment to the public
HTTPS API origin, e.g. `https://YOUR_FUNCTION.lambda-url.ap-southeast-2.on.aws`.
An existing `/api` suffix is tolerated and removed by the v1 client. Rebuild
after changing this variable: Next.js embeds it in browser JavaScript.
Never put database credentials, bearer tokens or AWS keys in frontend variables.

An explicit production HTTP/loopback URL fails the build. An absent URL permits
the build but displays a connection message; it does not mean data is connected.
Development defaults to `http://localhost:8000/api`. Set the backend's
`ETL4_ALLOWED_ORIGINS` to the frontend origin, including its local port.

## Data selection

- The catalogue deduplicates boreholes. Select dataset revision and sample axis
  explicitly when a hole has multiple datasets.
- Select the source log for minerals, scalar values, spectra or profiles.
  Variant/log IDs stay distinct. Missing payloads are shown as unavailable.
- Sample numbers, starting at zero, identify samples. Equal depths are not merged.
  Lists use cursor pagination; images and results come from the selected sample.
- The image-only default sends `include_results=false`, avoiding reads of every
  log. Ambiguous image logs require an explicit choice.
- Image markers show an approximate sample-order position, not calibrated mineral
  boundaries. Profiles use an uncalibrated position index.
- Confidence and survey stations are not supplied. The 3D page shows collar
  locations and missing-trajectory states without invented geometry.
- Compare keeps dataset/log selections independent with a shared depth range.
  Changing hole, dataset, log, sample or page clears stale responses.

## Verification

Run `npm test` and `npm run build` from `frontend`. Run
`python deployment/check_live.py` from `backend` with configured dependencies,
or append `--base-url https://YOUR_API` for a deployed service.

In Edge verify search, dataset/log selection, 100-sample pagination, sample 15
of 07THD002 (Muscovite, 531-channel VSWIR and PNG), and samples 129/130 of
05KCD001 (equal depth, different image assets). Check Compare swap/reset, shared
depth filtering, and missing trajectories on the 3D page. Confirm production
requests target the HTTPS API and return JSON with correct CORS.

## Basemap

Streets uses OpenStreetMap raster tiles with visible attribution. Keep caching
and referrer headers; do not add bulk downloads or offline prefetch. For higher
traffic configure a suitable tile provider in `config.js`.
See the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
