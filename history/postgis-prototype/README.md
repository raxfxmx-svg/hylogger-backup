# HyLogger PostGIS Prototype

An independent PostgreSQL/PostGIS, ETL and read-only API prototype, originally named demo2. The recorded 05GJD001 milestone included ETL3 provenance validation, database import, section-image reads, automated checks and backup.

- `db/`: roles, migrations and database checks.
- `etl/`: package precheck, import and loaded-data verification.
- `pipeline/`: reused ETL3 transformation and release verification.
- `api/`: read-only FastAPI service.
- `scripts/`: processing, service startup and backup commands.
- `docs/`: API contract, operating workflow and troubleshooting.
- `.env.example`: local configuration template.

Runtime data belongs under data/raw and data/processed; private credentials stay in the ignored .env file. See [SOP](docs/SOP.md), [API](docs/API.md) and [troubleshooting](docs/TROUBLESHOOTING.md). Start with scripts/run_api.ps1 and open http://127.0.0.1:8000/docs.
