# Code Language Update

2026-10-03. Converted runtime messages, errors, CLI help, generated reports and field descriptions in 53 Python files and their source copies to English. At that stage, comments/docstrings were bilingual and group names/READMEs remained Chinese; this public archive now uses English throughout.

Ten persisted metric `display_name` values changed. Because they participate in prepared-content hashes, the preparation rule advanced from `etl4-preparation-v2` to `etl4-preparation-v3`. Metric keys, types, units, algorithms, source IDs and database structure stayed unchanged. Existing sealed v2 packages and databases were not rewritten. New preparation uses a new work directory.

All 53 files passed syntax, language and source/copy hash checks. The historical scan found zero Chinese runtime strings, 136 bilingual docstrings and 76 bilingual comments. AST comparisons preserved algorithm/control structure apart from translated text, CLI help selection and the explicit rule-version change. All ten metrics retained their keys/types/units.

243 offline tests passed in 61.781 seconds, with zero failures, errors, skips or database/network connection attempts. A temporary combined package imported all 53 modules without falling back to original-project code. No real processing or import ran. Evidence and original sources are under `_codex_work/english_code_20261003/`.
