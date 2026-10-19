# Midterm Demo Results

I expanded the single-hole workflow into repeatable batches with database reconciliation, failed-hole replacement and a read-only API.

The August 26–27, 2026 records show **96 verified holes, 96 datasets, 5,863,516 samples and 41,668 completed core-section image strips**. Four holes remained pending against the 100-hole target. The batch history includes three replacements after ETL failures.

| File or folder | Contents |
| --- | --- |
| [summary.json](summary.json) | Recorded totals and progress from 6 to 16, 93 and 96 holes. |
| [hole-status.csv](hole-status.csv) | The 100 target slots, final recorded status and release IDs. |
| [release-index.csv](release-index.csv) | Per-hole sample, tray, section and spectral-series counts. |
| [batch-runs/](batch-runs/) | Pilot and continuation snapshots, preflight checks and replacement history. |
| [quality-reports/](quality-reports/) | All 96 release quality reports, including source warnings and availability checks. |

The [100demo source](../../history/staging-prototype/100demo-staging/README.md) contains the downloader, ETL, database, API and tests. Its configuration preserves the earlier staging snapshot; `hole-status.csv` records the later midterm result. Large raw data and processed payloads are not included here.
