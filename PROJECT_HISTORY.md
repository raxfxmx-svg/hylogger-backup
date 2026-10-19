# Project History

I developed the data workflow from a single-hole experiment into a cloud database supporting the team website.

| Stage | What I did | Problem solved |
| --- | --- | --- |
| August 9: pilot | Corrected the demonstration to use the real 05GJD001 data, absolute depths and available source fields. | Removed unsupported locations and misleading depth intervals. [C01](CONVERSATION_SOURCES.md#c01) |
| August 11: ETL1–2 | Separated downloading from processing and produced readable CSV tables. | Made the source data accessible before expanding the database. [C02](CONVERSATION_SOURCES.md#c02) |
| August 20–27: ETL3 and prototype | Stored scalars in Parquet, kept spectra in separate matrices, linked image strips and built a PostgreSQL/PostGIS prototype. | Preserved different data structures and connected files through stable sample identities. [C03](CONVERSATION_SOURCES.md#c03), [C04](CONVERSATION_SOURCES.md#c04), [C05](CONVERSATION_SOURCES.md#c05) |
| August 26–27: midterm demo | Expanded the prototype to repeatable batches, with 96 holes recorded as database-verified, 5,863,516 samples and 41,668 core-section image strips. | Continued from completed holes and replaced three failed candidates; four target slots remained pending. [Midterm results](evidence/midterm-demo/README.md) |
| September 7–16: ETL4 | Modelled spectral regions, interpretation settings, source metadata and sample-level media links. | Supported complete spectra and row images without losing source distinctions. [C06](CONVERSATION_SOURCES.md#c06) |
| September 24: multiple datasets | Defined succession rules for composite views while retaining each dataset for detailed comparison. | Resolved overlapping scans without deleting source records. [C06](CONVERSATION_SOURCES.md#c06) |
| September 28–October 5: batch delivery | Separated data identity from code formatting, simplified final-version imports and added cloud batch delivery. | Reduced duplicate storage and made processing practical within local disk limits. [C08](CONVERSATION_SOURCES.md#c08) |
| October 5–13: expansion | Processed additional batches, diagnosed failures and introduced external special handlers. | Handled inconsistent logs, missing profiles, core/cuttings selection and same-name boreholes. [C08](CONVERSATION_SOURCES.md#c08), [C11](CONVERSATION_SOURCES.md#c11) |
| October 5–16: integration | Connected the frontend to the API, fixed map/request issues and investigated missing anomaly results. | Restored data access and the display of 18 existing anomaly records and scores. [C09](CONVERSATION_SOURCES.md#c09), [C12](CONVERSATION_SOURCES.md#c12) |

## Key design choices

I used sample identity alongside depth because multiple samples can share the same depth. Scalar values, spectral arrays and images remain linked to their source dataset.

For overlapping scans, I separated storage from display selection. If two datasets cover 100–120 m and 110–130 m, the composite can switch at 110 m while the detailed view retains both complete datasets. The eight-hole delivery retained 654,778 complete samples and selected 638,331 for the composite. [Multi-dataset design](history/etl-v4/database/MULTI_DATASET_DELIVERY.md)

I kept the normal ETL stable and routed failed inputs to external handlers. The workflow records the failure, diagnoses its cause, applies a supported rule and returns the result to the normal process. [Special processing](history/github-handoff/special_processing/README.md)

To fit local storage limits, I processed batches locally, uploaded large files to S3 and merged structured records into PostgreSQL. One complete version per dataset replaced the earlier base/media duplication. [Batch workflow](history/etl-v4/database/LOCAL_BATCH_RUNBOOK.md)

## Delivery milestones

| Date, 2026 | Holes | Datasets | Samples |
| --- | ---: | ---: | ---: |
| October 4 | 12 | 17 | 732,206 |
| October 5 | 99 | 104 | 6,256,402 |
| October 10 | 247 | 252 | 14,337,925 |
| October 11 | 386 | 391 | 18,303,620 |
| October 11, after BSDD023 | 387 | 392 | 18,311,660 |
| October 13 | 405 | 410 | 19,147,718 |

The last delivery resolved 13 deferred source folders into 18 output holes through core selection and same-name borehole splitting. A teammate supplied BSDD023; I handled its verification and merge. [Delivery records](evidence/recorded-cloud-milestones.json)

The October 16 anomaly work restored existing results in the interface. I also compared 54,432 samples of 07THD003 and found unchanged values in four mineral channels, helping separate data changes from version and display mismatches. [Data comparison](history/working-snapshots/read_only_audit_20261016/comparison-summary.json)
