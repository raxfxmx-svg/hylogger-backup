# Two New Borehole Imports — 2026-09-29

I extended the previously fixed five-hole input selection and validated 09ATRCD025 and 12BRDDH003 in an independent database. Original code required changes before these inputs worked. This snapshot retained explicit per-hole direction confirmation; that historical behavior differs from the later project-wide direction convention.

The 278 copied source files matched their originals by SHA256, totaling 216,002,375 bytes. 09ATRCD025 contributed 22,780 samples, 1,822,604 scalar records, one matrix, 34 trays and 170 row images. 12BRDDH003 contributed 10,184 samples, 1,079,599 scalar records, two matrices, 19 trays and 76 row images. Total: 32,964 samples, 2,902,203 scalar records, three matrices, 53 trays and 246 row images. 05GJD001 was excluded because its profilometer payload was unavailable rather than fabricated.

The test database used 39 tables and six unchanged migrations. Release e1083bca-f551-59d6-967a-2853c0e8cfa1 contained two datasets; four stored revisions represented separate base/media versions. The existing comparison database and its active release remained unchanged.

Changes replaced hard-coded input membership with explicit selections and verified manifests, checked direction-confirmation scope, generated review descriptions from the actual four layouts/eight representative images, and added --inputs-only for reuse of an existing database instance.

Steps 1–10 and 20–29 passed, producing 194 Parquet files. API range, repeated-depth, image-byte and profilometer checks passed. Spectral reference checks covered selected source sample/window boundaries; all local files were separately hashed. All 246 row crops matched source pixels. Base replay preserved 231 preparation files and 35 business-table digests; media replay retained four revisions and the same release. Backup/restore matched 35 business tables, 86 foreign keys and migrations; the dump was 1,879,500 bytes. Sixty-one tests passed. Recorded times were 29.942 seconds for 1–6, 8.860 for 7–10, 35.042 for base replay and 8.545 for media replay; these different scopes are not a controlled speedup comparison.

Direct SQL fault tests in a restored copy still accepted additions to sealed revisions/releases, activation of an empty unvalidated release, a same-log crop from another tray, an incorrect flip declaration and overlapping regions under REPEATABLE READ. Cross-dataset frames and READ COMMITTED overlaps were rejected. Normal workflow validation passed, but these database-level gaps remained unresolved in this snapshot.
