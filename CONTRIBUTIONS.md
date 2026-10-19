# My Contribution

I worked on the data pipeline, database and integration for the HyLogger visualisation project.

| Problem | What I did | Related work |
| --- | --- | --- |
| Source files were fragmented and difficult to inspect. | Built resumable downloads and converted the data into readable tables and structured processing outputs. | [ETL1](history/etl-v1/README.md), [ETL2](history/etl-v2/README.md) |
| Scalars and spectra had different structures, and depths could repeat. | Separated scalar tables from spectral matrices and used dataset/sample identities to preserve alignment. | [ETL3](history/etl-v3/README.md) |
| The midterm demo needed a reliable workflow for many holes. | Added batch continuation, database reconciliation and failed-hole replacement, reaching 96 verified holes and 5,863,516 samples in the recorded run. | [Midterm results](evidence/midterm-demo/README.md), [batch runner](history/staging-prototype/100demo-staging/scripts/batch_100.py) |
| The website needed consistent access to data and large files. | Designed PostgreSQL/PostGIS relationships and file indexes, then organised cloud storage and API reading contracts. | [Database](history/etl-v4/database/), [prototype](history/postgis-prototype/README.md) |
| Images, spectra and overlapping scans needed to stay connected. | Linked real samples to row images and complete spectra; defined composite display rules while retaining every dataset. | [Media contract](history/etl-v4/database/MEDIA_READ_CONTRACT.md), [multi-dataset delivery](history/etl-v4/database/MULTI_DATASET_DELIVERY.md) |
| Local storage was limited and imports repeated data. | Simplified version handling and built batch preparation, validation, upload, merge and recovery workflows. | [Final-version design](history/etl-v4/database/SINGLE_FINAL_VERSION.md), [batch runbook](history/etl-v4/database/LOCAL_BATCH_RUNBOOK.md) |
| Some source packages failed the normal workflow. | Added external diagnosis and 13 handlers for source inconsistencies, core selection and same-name boreholes. | [Special processing](history/github-handoff/special_processing/README.md) |
| The frontend and backend used different conventions. | Worked on API integration, map and request fixes, anomaly display and teammate handoff documentation. | [Integration commits](evidence/recorded-integration-commits.txt), [handoff](history/github-handoff/README.md) |

The October 13 delivery reached **405 holes, 410 datasets and 19,147,718 samples**. The final-version design also reduced 32 versions to 16 in the 11-hole comparison while preserving all 730,622 source samples. [Delivery records](evidence/recorded-cloud-milestones.json)

Teammates developed the original frontend and anomaly model. My related work focused on integration and diagnosis.
