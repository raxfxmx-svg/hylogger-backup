# Project Files

This archive brings together my data exploration, ETL development, database work, cloud delivery and integration history.

## Main source folders

| Folder under history/ | Purpose |
| --- | --- |
| [exploration](history/exploration/) | Initial notebooks, queries and tray-data experiments. |
| [hylogger-visualisation](history/hylogger-visualisation/) | Early parsing, image strips and visualisation work. |
| [hylogger-demo](history/hylogger-demo/) | A demonstration using the real pilot data. |
| [early-exploration](history/early-exploration/) | The earlier English exploration package. |
| [etl-v1](history/etl-v1/) | Initial NVCL acquisition and processing. |
| [etl-v2](history/etl-v2/) | Separate downloads, resumable acquisition and readable CSV outputs. |
| [etl-v3](history/etl-v3/) | Versioned processing with Parquet, spectral matrices and image mappings. |
| [postgis-prototype](history/postgis-prototype/) | PostgreSQL/PostGIS, API and integration prototype. |
| [staging-prototype](history/staging-prototype/) | Midterm demo source: batch processing, PostgreSQL/PostGIS, a read-only API and tests. |
| [etl-v4](history/etl-v4/) | Source preparation, database imports, media links and delivery workflows. |
| [english-delivery-20261004](history/english-delivery-20261004/) | The English ETL4 delivery snapshot from October 4. |
| [github-upload](history/github-upload/) | Earlier source packages assembled for sharing. |
| [github-handoff](history/github-handoff/) | Consolidated ETL4 code, special handlers, examples and instructions. |
| [geological-branch-inspection](history/geological-branch-inspection/) | A 2D branch-comparison demonstration script. |
| [proposal-tools](history/proposal-tools/) | Scripts used to prepare and inspect project documents. |
| [team-frontend](history/team-frontend/) | Team frontend code used for integration. |
| [working-snapshots](history/working-snapshots/) | Saved refactoring, delivery and debugging stages. |
| [recovered-archives](history/recovered-archives/) | Earlier source versions recovered from compressed archives. |

## Consolidated handoff

The [github-handoff folder](history/github-handoff/) is the shortest route into the organised processing code.

| Path within the handoff | Purpose |
| --- | --- |
| etl4/processing/ | Check raw inputs, organise metadata, align samples and prepare outputs. |
| etl4/database/ | Define the schema, link media, import datasets, validate results and deliver cloud batches. |
| special_processing/ | Diagnose failed inputs and apply 13 case-specific handlers. |
| docs/ | Explain dataset selection, special cases and their source details. |
| examples/ | Provide configuration and input examples. |
| requirements.txt | List Python dependencies. |

## Supporting folders

- [evidence/](evidence/) contains test results, data comparisons, delivery milestones and integration commits.
- [evidence/midterm-demo/](evidence/midterm-demo/README.md) contains the 96-hole midterm results, batch history and per-release quality reports.
- [manifests/](manifests/) lists the files and their checksums.

Start with [My Contribution](CONTRIBUTIONS.md) for the work summary and [Project History](PROJECT_HISTORY.md) for the development sequence.
