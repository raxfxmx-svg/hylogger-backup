# Media Structure Simplification and Incremental Import

2026-09-30. Simplified media processing and validated it in `etl4_refactor_check` without schema/rule changes. Existing-revision detection now precedes loading 17 clone tables. Crops decode each original once, compact manifest v2 shares dataset/frame metadata, `_media_rows.py` shares row algorithms, and readers batch selected-log queries. Existing manifests and entry points remain compatible.

| Measurement | Before | After |
|---|---:|---:|
| Existing clone SQL queries / returned rows | 19 / 3,016 | 3 / 3 |
| Clone seconds | 0.0565 | 0.0005 |
| Decodes for 320 rows | 320 | 80 |
| Crop seconds | 1.463 | 1.259 |
| Multi-dataset step 25-27 manifests | 449.21 MiB | 21.36 MiB |
| Six selected logs: queries / catalogue rows | 19 / 126 | 9 / 6 |
| All 126 logs: queries | 231 | 9 |

PNG bytes, expanded manifests and outputs matched. Eight multi-dataset identities, 696 originals/2,799 row mappings and 51 sample-read cases across 16 datasets remained equivalent. Fifty local tests passed (41 existing, 9 new). Measurements are individual observations, not general speed guarantees.

09THD028 replay reused its 42,880 samples/320 row images. All 35 business-table digests and the active release remained unchanged; one run record and existing validation results updated. Media import/validation still scanned 682/683 files; observed times changed 1.121→0.916 and 2.429→2.218 seconds.

Randomly selected 14CADD003 once from 86 complete eligible boreholes and verified all 145 copied files. It added 1,584 samples, three originals, 12 lossless rows and two matrices, with 16 official reference spectra checked. All three representative tray layouts were viewed, retaining empty final-tray sections. Replaying its new-format package added no business revision.

| Release scope | Before | After |
|---|---:|---:|
| Boreholes / datasets / revisions | 11 / 16 / 32 | 12 / 17 / 34 |
| Complete samples | 730,622 | 732,206 |
| Row images / matrices | 4,726 / 29 | 4,738 / 31 |
| Display samples | 714,175 | 715,759 |

Release `c8522bfa-7c4b-5886-a7b3-b002eea84f4d` selects 17 media revisions; base revisions remain historical. Original records and eleven-borehole display selections matched field by field. Thirty-four first/last sample reads passed after merge. No HTTP load test, AWS deployment or backup-restoration exercise ran. Evidence: `_codex_work/etl4_structure_20260930/`.
