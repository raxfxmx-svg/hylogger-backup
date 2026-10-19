# Two New Borehole Integrations

2026-09-29. Integrated 09ATRCD025 and 12BRDDH003 in `etl4_new_input_check` after fixing fixed-input assumptions. Copied 278 source files / 216,002,375 bytes from D:/100demo/data/raw and verified every SHA256. The later 09THD028 addition is documented in [RANDOM_INPUT_CHECK_REPORT.md](RANDOM_INPUT_CHECK_REPORT.md).

| Borehole | Instrument | Samples | Scalar source rows | Spectra | Trays | Row images |
|---|---|---:|---:|---:|---:|---:|
| 09ATRCD025 | HyLogger 2-2 | 22,780 | 1,822,604 | 1 | 34 | 170 |
| 12BRDDH003 | HyLogger 3-2 | 10,184 | 1,079,599 | 2 | 19 | 76 |
| Total | | 32,964 | 2,902,203 | 3 | 53 | 246 |

Allowed explicitly selected boreholes across preparation/import/validation while retaining path, source, membership and hash checks. Added scoped direction confirmations for new inputs and template counts from actual layouts (four layouts, eight representative images). Step 7 gained `--inputs-only` for existing instances. 05GJD001 was excluded because its profile payload was unavailable.

Steps 1-10 and 20-29 passed, generating 194 Parquet files and checking API ranges, duplicate-depth pagination, image bytes and profile boundaries. All 246 crop images matched source pixels. Official sampled spectral responses confirmed ordering; local complete matrices passed hash checks. Base reruns preserved 231 prepared files and all 35 business-table digests. Media reruns retained four base/media revisions and release `e1083bca-f551-59d6-967a-2853c0e8cfa1`.

An independent restoration matched 35 business tables, 86 foreign keys, migrations and the active release; dump size was 1,879,500 bytes. Sixty-one regression tests passed (12 processing, 7 input/direction, 17 version/failure, 8 structure, 17 integration). Observed seconds: preparation 29.942; steps 7-10 8.860; base replay 35.042; media replay 8.545. The original refactor database stayed at 13 datasets / 26 revisions and release `707bbb9e-6e0a-50f9-9638-96cb13a6daf3`.

Direct-SQL tests in a restored copy still exposed unresolved gaps: appending to published revisions/releases, activating empty releases, attaching another tray's crop within the same log, declaring an unapplied flip, and overlapping inserts under REPEATABLE READ were accepted. Cross-dataset image links and READ COMMITTED overlap were rejected. Normal Python workflow checks do not close these database permission/constraint gaps. No migration or role fix was applied here.

See [REFACTOR_RUNBOOK.md](REFACTOR_RUNBOOK.md), `_codex_work/etl4_new_input/`, and new_input_check/database reports 29_media_verification.json, 30_media_database_audit.json and 14_database_only_restore.json.
