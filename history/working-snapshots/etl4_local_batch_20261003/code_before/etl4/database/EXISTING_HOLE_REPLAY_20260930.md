# Existing-Borehole Rerun

2026-09-30. Replayed 09THD028 in the original `etl4_refactor_check` database using its existing prepared files and sealed package. Base and media imports returned `already_present`. All 35 business-table counts and full-row SHA256 digests remained identical; no business rows, revisions or releases were added.

The borehole contains 42,880 samples, 130 logs, 80 tray images, 320 row images and two spectral matrices. Validation compared every sample, 1,212 chunks, source images/crop pixels and 20 saved official reference spectra. No network download was required. Steps 9, 10, 28 and 29 shared functions ran under one import lock/transaction with `activate=False`; unexpected business changes would roll back.

The active release remained `43033059-8e6a-5f10-8247-b4487956cfc2`: 11 boreholes, 16 datasets and 730,622 complete source samples. Total revisions stayed at 32. Base revision `f7378f37-84f0-5a59-9992-79dee8716b01` and media revision `66d273c5-3cf4-57e3-8ec5-e186df76d018` were reused. One ingest_run was added and existing validation records updated.

Observed seconds: before digest 3.491; base import 0.810; base validation 1.998; media import 1.121; media validation 2.429; after digest 3.254. These are run measurements, not a performance comparison. No steps 1-6, API, restoration or multi-dataset batch test ran.

Original work: `etl4/new_input_check/random_09THD028`. Separate reports: `etl4/replay_existing_20260930_09THD028`. Evidence under `_codex_work/etl4_existing_replay_20260930/`: `before.json`, `after_in_transaction.json`, `after_commit.json`, `result.json` and `replay.py`.
