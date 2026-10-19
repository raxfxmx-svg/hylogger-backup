# ETL4 cloud API supplement

Prepared on 2026-09-23 for Contributor 3 and the API team.

The local `database.rar` dated 2026-09-13 does not contain `deployment/` or
`cloud_api/`. Those files were added during the later AWS deployment. This ZIP
provides the missing runtime and English instructions. It can run independently
of that older archive against the existing five-hole AWS deployment.

## Start here

1. Extract the entire ZIP into a new folder. Keep `deployment/` and `cloud_api/`
   next to this README. Do not move only `run_api.py` into the old database folder.
2. Read [the connection guide](deployment/TEAMMATE_START.md).
3. Confirm your own AWS read access with the project administrator. The last
   recorded TeamMemberA provisioning workflow was pending approval/password setup;
   distributing this ZIP does not grant or verify AWS permissions.
4. Install the requirements and run `deployment/run_api.py --check` as documented.
5. Start the local API and use [the route guide](cloud_api/README.md).

The cloud database and objects were previously deployed and validated. Do not
restore the old database dump, run migrations, upload data again or rebuild crops.
This ZIP has no images, spectra, database dump, virtual environment or credentials.
The API fetches the needed data from Aurora and private S3 at runtime.

## Files

| Path | Purpose |
| --- | --- |
| `deployment/run_api.py` | Launch the API or check the real Aurora/S3 connection |
| `deployment/requirements-cloud.txt` | Python runtime dependencies |
| `deployment/target.json` | Existing non-secret AWS target configuration |
| `deployment/TEAMMATE_START.md` | Setup, verification and startup instructions |
| `deployment/TEAMMEMBERA_SIGN_IN.md` | Planned personal login and CLI profile instructions |
| `deployment/runtime_policy.template.json` | Required scoped data permissions; administrator reference |
| `cloud_api/` | Complete cloud API runtime and route documentation |
| `docs/` | Database relationships and schema dictionary |
| `examples/DATASET_CATALOG.json` | Hole and log identifiers, including spectral logs |
| `validation/` | Historical cloud acceptance reports, not a new test of your identity |
| `PACKAGE_FILES.json` | File sizes and SHA256 digests |
| `verify_package.py` | Offline integrity check; needs only Python's standard library |

To add this supplement to the shared repository, keep both runtime directories
at the same repository level and retain the matching instructions/configuration.
If the repository already has either directory, compare changes before merging.
The existing reference database code is not required by this cloud runtime.

The API binds to `127.0.0.1:8000`. This ZIP does not create a hosted API URL or
cloud resources. Persistent hosting remains a separate deployment step.
