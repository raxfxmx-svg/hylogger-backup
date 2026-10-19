# Random Input Check: 09DKRCD002

2026-09-30. Selected 09DKRCD002 once from 87 eligible complete single-dataset boreholes and verified 191 copied files / 350,001,298 bytes. Used new database `etl4_validation_check_20260930` on the existing local instance and separate work directory `etl4/validation_input_check_20260930`. Production code, rules and migrations were unchanged; original database release/member/version summaries stayed unchanged.

Results: 43,605 source samples at 68.80343-359.79828 m, including 6,539 duplicate-depth samples; 125 logs, 1,157 chunks, 68 trays, 323 lossless rows and two spectra (43,605×531 and 43,605×341). Twenty official reference spectra matched every channel. Base/media revisions each retain the full samples, giving 87,210 physical rows.

Base release: `e5ba9502-c672-5d59-a0e9-b5b7e20b7ab8`; test media release: `160b608d-2c9a-5e3c-a093-1e725782f367`. The original eleven-borehole release `43033059-8e6a-5f10-8247-b4487956cfc2` was not changed.

Ran steps 0-10 and 20-29. Reviewed five representatives across three image layouts and compared all crop pixels/source relationships. Replaying steps 9, 10, 28 and 29 preserved all 35 business-table counts/digests and added zero business records, revisions or releases. Rolled-back composition tests accepted complete records and rejected missing parts/compositions without constructing replacements.

| Step | First run (s) | Replay (s) |
|---|---:|---:|
| 9 | 1.958 | 0.850 |
| 10 | 2.324 | 2.180 |
| 28 | 3.613 | 1.331 |
| 29 | 2.624 | 2.643 |

Step 28 scans: 1,018 initially and 663 on replay. Both step-29 runs scanned 677 files / about 445.94 MB with 1,031 within-run cache hits. New validation rereads content. No HTTP/API test, backup restoration or multi-dataset validation ran.

Preserved coordinate declarations `(118.56937469, -27.10606189)` from borehole.json and `(118.569366, -27.106075)` from XML, selecting the former under existing rules. Unresolved domain_id `a381a666-efaf-4580-ae35-3fa0cb5b71c` remains explicit. Source/work/database sizes were about 333.79 / 109.02 / 43.78 MiB, excluding instance WAL. Evidence and scripts: `_codex_work/etl4_validation_20260930/`.
