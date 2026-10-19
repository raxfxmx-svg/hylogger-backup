# Code Structure Changes

2026-09-29. Split step 34 into sample/media import, member merge, transaction and result functions; its main function shrank from 124 to 22 lines. Moved steps 2-5 business functions into ordinary modules for direct use by step 32, whose prepare_unit shrank from 101 to 53 lines. Normalisation now writes complete source/selection information once, avoiding later report rewrites.

Entry points call configure(args) after full argument parsing. `_db_files.py`, `_run_reports.py` and `_prepared_inputs.py` separate database utilities. Clearer names include load_or_record_source_release(). Added seven ordinary modules; the main source contains 54 Python files including 31 numbered entry points. Line counts describe responsibility changes, not performance.

54 tests passed: 12 processing, 17 version/publication, eight configuration/transaction and 17 temporary-database integration tests. All 31 help commands and static checks for 54 source/seven test files passed. Six migration files and two reader signatures were unchanged.

Real preparation checks preserved 145 files for 05KCD001 (75.809 seconds) and 139 files for the 5,300-sample 14KDD001 dataset (17.900 seconds). Step 32 reused all eight multi-dataset outputs. With working-stage directories temporarily moved aside, sealed-package reruns of steps 9/28/29/34/35 took 2.982 / 12.392 / 24.941 / 50.233 / 68.090 seconds and added zero business rows. All 35 business-table digests matched.

The validation database retained 39 tables and release `707bbb9e-6e0a-50f9-9638-96cb13a6daf3`, covering eight boreholes, thirteen datasets and 654,778 samples. No full restoration was repeated; prior evidence remains in [REFACTOR_REPORT.md](REFACTOR_REPORT.md). Rules, identities and business fields were unchanged. See [CODE_STRUCTURE.md](CODE_STRUCTURE.md), [REFACTOR_RUNBOOK.md](REFACTOR_RUNBOOK.md) and `_codex_work/etl4_structure/`.
