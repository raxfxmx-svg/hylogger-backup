# Local Batch Preparation and Two Validation Gates

2026-10-03. Unified raw/work/database/config options across numbered entry points and allowed external input/work directories. Asset locations use shared root-key/path resolution for imports, validation, publication and local reads. Unknown roots and escaped paths are rejected; directory locations do not affect dataset identity.

The first gate runs at `28 --package-only`, checking preparation reports, datasets, revisions, sample axes, manifests and file contents. Step 37 requires matching first-gate reports, imports complete base/media data once per dataset, then records an independent second validation. A failed rerun cannot inherit a previous passed status. The multi-dataset route uses the same gate.

Removed premature full scans from step 20 files-only and step 33 preparation; both validation boundaries still check actual content. Service-format evidence is shared, while missing official samples require explicit `--fetch-reference`. Existing 39 tables, six migrations, read fields and processing-rule version remain unchanged.

85 offline tests passed (15 new, 70 existing) in about 8.81 seconds; 62 Python files parsed and all numbered `--help` commands worked. Tests covered external directories, stable input identities, changed files including equal-size/equal-time tampering, missing reports, axis conflicts and failure-state updates. Database connections were blocked in the final offline suite. An earlier broad discovery attempt timed out before database creation/import and was replaced by explicit offline selection.

This iteration did not perform real imports, migrations, cloud uploads, cleanup or twelve-borehole reprocessing. Legacy packages need a real first-gate run before step 37; older specialised tools retain their original layout. Evidence is in `_codex_work/etl4_local_batch_20261003/`. See [LOCAL_BATCH_RUNBOOK.md](LOCAL_BATCH_RUNBOOK.md).
