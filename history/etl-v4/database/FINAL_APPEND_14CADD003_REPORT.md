# Incremental 14CADD003 Import with One Final Revision

2026-09-30. Added 14CADD003 to the eleven-borehole test release through `37_import_final_version.py`. The new borehole adds one dataset/revision, 1,584 samples, 12 row images and two spectral matrices. Source dataset: `978822fb-de28-4603-b02e-af6882e5951`; complete revision: `984f74b7-3ba5-5d14-bf9d-9f8f783d1506`.

| Same twelve-borehole scope | Old route | New route |
|---|---:|---:|
| Boreholes / datasets | 12 / 17 | 12 / 17 |
| Revisions | 34 base/media | 17 complete |
| Physical sample rows | 1,464,412 | 732,206 |
| Complete source samples | 732,206 | 732,206 |
| Row images / spectra | 4,738 / 31 | 4,738 / 31 |
| 3D display samples | 715,759 | 715,759 |

The reduction removes duplicated base-version records, preserving source samples and necessary history. Full comparisons matched sample/depth/interval values, original assets, Parquet values, crop pixels, spectra, metadata, geometry and 3D selections. Existing eleven-borehole records and 16 dataset references remained unchanged. Repeating the increment added zero business rows, revisions or releases. An independent backup restoration also passed.

Retained old comparison release `c8522bfa-7c4b-5886-a7b3-b002eea84f4d` and original new-route eleven-borehole release `aa9899e8-e81e-5f5a-b5a0-74818c50cb1c`; current twelve-borehole release: `541df521-79c1-5488-b3ab-130a2e7065f5`. Initial import took 16.10 seconds; rerun 15.25 seconds, scanning 10,422 files / 7,985,334,054 bytes across the full publication boundary.

Backup `etl4/single_final_check_20260930/database/backups/final_12_holes_20260930.dump`: 18,107,407 bytes; SHA256 `8a2a641080c46fc66bf879c626ae5549892fdeadb1dbb541767ef8ebfb2bc8fa`. External prepared/source assets remain necessary.

`batch.json` now covers twelve boreholes and five packages; `batch_11_holes.json` preserves the older scope. Reports include `final_append_14CADD003.json`, `final_12_holes_comparison.json` and `asset_manifest_541df521-79c1-5488-b3ab-130a2e7065f5.json`. Supporting snapshots/scripts are under `_codex_work/etl4_final_append_14CADD003/`.

```powershell
& .\etl4\database\.venv\Scripts\python.exe -B -X utf8 `
  etl4/database/37_import_final_version.py `
  --work-dir etl4/single_final_check_20260930 `
  --dbname etl4_test_single_final_20260930 `
  --batch etl4/single_final_check_20260930/append_14CADD003.json
```
