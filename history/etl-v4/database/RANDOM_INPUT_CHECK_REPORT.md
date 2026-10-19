# Random Borehole Validation: 09THD028

2026-09-29. Selected 09THD028 once with SystemRandom.choice from 88 eligible complete single-dataset boreholes. Preserved the selection and verified all 208 copied source files. Source dataset: `8ee07ba8-5646-45a0-b503-a0aeceec13b`, instrument HyLogger 3-2. Used `etl4_new_input_check` and separate work directory `etl4/new_input_check/random_09THD028` without production code or migration changes.

Results: 42,880 samples spanning 41.70344-330.60001 m; 4,631,440 scalar source rows; 112 columnar files; 130 logs; 80 trays; 320 row images; two spectra shaped 42,880×531 and 42,880×341. Steps 1-7, 9-10 and 20-29 passed using existing database structure.

Checked every sample, 1,212 data blocks, all image associations and complete-file hashes. Preserved 5,818 duplicate-depth samples. API checks covered pagination, ranges, profile row-group boundaries and image bytes. Viewed ten representatives across five layouts; all 320 crops matched source pixels. Twenty official sample spectra matched every float32 channel; later reruns used cached responses.

Reruns preserved 132 prepared files and 35 business-table digests, adding zero business rows/revisions. All 74,015 pre-existing records remained. The database now held three boreholes/datasets, six base/media revisions and 75,844 distinct source samples. `--no-publish` / `--no-activate` retained active release `e1083bca-f551-59d6-967a-2853c0e8cfa1`. New explicit releases: base `40dd8357-c9de-551c-9da2-db165127cbcc`, media `39dd22a0-0885-5505-a11a-ceddba05ddce`.

Retained two source warnings: domain_id `e2d61921-5806-497e-9f26-54f741a3fa1` has no matching raw log ID; borehole.json coordinates `(121.69693605, -24.10490764)` differ slightly from XML `(121.696900, -24.104900)`. Preserve both and use borehole.json under the existing rule. No names were used to invent missing references.

Storage: source copy about 330.46 MiB, outputs 115.98 MiB, evidence 2.91 MiB, excluding PostgreSQL/WAL; database reported 65.78 MiB. No full restoration or multi-dataset validation ran, and earlier direct-SQL constraint gaps remained unresolved. Evidence: `_codex_work/etl4_random_one/` and the separate work directory's validation reports.
