# Multi-Dataset Delivery

2026-09-24. Imported and validated eight independent datasets from 12CADD001, 14KDD001 and 15EIS001 alongside the original five boreholes. Local release `177d1720-d327-534c-90da-5e3f517d8807` uses `127.0.0.1:55432 / etl4_core`. AWS upload and API changes were outside this iteration.

| Current scope | Value |
|---|---:|
| Boreholes / datasets | 8 / 13 |
| Tables / new reader views | 39 / 2 |
| Complete 2D samples | 654,778 |
| Selected 3D samples | 638,331 |
| Tray images / row PNGs | 945 / 4,160 |
| Complete spectral matrices | 24 |
| Unique object files / bytes | 8,571 / 6,722,411,576 |
| Database including history | 517,450,899 bytes |
| Verified backup | 27,024,708 bytes |

The historical scan_sample table has 1,309,556 rows across base/media revisions. Always select release and axis for current reads.

Explicit project-owner decisions in [multi_dataset_decisions.json](multi_dataset_decisions.json) define succession and first-sample switches. Preserve full 2D sources; apply half-open 3D ranges until the final inclusive endpoint.

| Dataset | Full depth range (m) | Full samples | 3D window (m) | 3D samples |
|---|---|---:|---|---:|
| 12CADD001 original | 0.00368-324.18823 | 49,104 | [0.00368,324.18823] | 49,104 |
| 12CADD001 wedge | 324.20358-537.09998 | 30,632 | [324.20358,537.09998] | 30,632 |
| 14KDD001 original | 3.50234-27.49838 | 5,300 | [3.50234,25.50151) | 4,657 |
| 14KDD001 wedge | 25.50151-144.19881 | 33,150 | [25.50151,144.19881] | 33,150 |
| 15EIS001 original | 0.00415-221.49770 | 36,716 | [0.00415,183.40323) | 30,616 |
| 15EIS001 wedge | 183.40323-501.99750 | 47,972 | [183.40323,429.20374) | 39,239 |
| 15EIS001 wedge2 | 429.20374-501.04172 | 10,452 | [429.20374,495.50299) | 9,481 |
| 15EIS001 wedge3 | 495.50299-1701.79700 | 179,560 | [495.50299,1701.79700] | 179,560 |

New boreholes retain 392,886 full samples; 376,439 enter 3D and 16,447 remain available in 2D. The 0.01535 m sample gap in 12CADD001 is preserved without invented samples or a claim of physical core loss. Do not fill newer NULLs from older segments, renumber samples or return to an older segment after its successor ends.

Added dataset_succession (five confirmed relations), borehole_composite (eight release/borehole compositions) and borehole_composite_part (thirteen source selections). Full dataset_segment ranges remain separate. `trajectory_kind=display_composite_not_surveyed_path` identifies a display composition without invented surveys.

Generated 2,799 new row PNGs from 696 trays with 3/4/5-row layouts. Reviewed first/last representatives for 51 templates and checked all bounds, provenance, sample coverage and crop pixels. Each sample maps within its own dataset. Direction remains left-to-right; sample_index_linear is approximate. Sixteen new spectral matrices passed layout/channel/block checks and saved official sample comparisons. Decimal depth differences beyond 1e-5 m are accepted only when reconstructed IEEE float32 bits are identical; source depths remain unchanged.

Steps 31-36 cover source ownership, independent preparation, media, transactional import, 2D/3D validation and independent restoration. Use `--fetch-reference` only for missing official evidence and `--record-reviewed` after inspecting generated layouts. Invalid ranges, overlaps, cross-borehole links and missing succession evidence were rejected. Restoration matched 35 business-table digests, core structures/views, release and 3D counts.

See [reader contract](MULTI_DATASET_READ_CONTRACT.md), [schema](schema_dictionary.md), validation (`reports/35_multi_dataset_verification.json`, historical file not included here) and [restoration](reports/36_multi_dataset_restore.json). Pair the latest backup with the same release's asset manifest; dumps exclude external objects. Preserve evidence and prepared files even when Git ignores them. Previously deferred publication/editing issues were not resolved by this delivery.
