# Shared Module Simplification

2026-10-03. Replaced dynamic handoff loading in step 39 with direct `_s3_upload.py` imports, removed `_db_common.py` re-export indirection, and separated historical media/verification code into `_legacy_media_import.py` and `_legacy_verification.py`. Current callers import functions from their owning modules.

Step 28 now always seals inputs and runs the first local validation, including when `--package-only` is omitted; step 37 performs complete imports. Historical entry points retain compatibility but the current 28→37 and 38-41 route does not load legacy/API modules. Schema documentation now describes current steps 37/40, root locations, digests and direction rules.

AST checks preserved verification/upload logic, identities, processing rules and transactions. Content/source/sample/image/spectral checks, conditional writes, object reuse/conflict rejection and multipart cleanup remain. Six migrations and API/deployment files were unchanged.

243 offline tests passed in 67.766 seconds with zero failures/errors/skips and zero database/network attempts. An isolated combined upload package imported all 53 Python files without original-source fallback; every copy matched source SHA256. Twenty-nine SQL/API/deployment files were unchanged.

The upload collection contains 46 main-flow, one recovery (step 14) and six cloud-batch Python files. Source size fell from 548,477 to 507,696 bytes, a reduction of 40,781 bytes without a claimed runtime speedup. Execution still requires migrations, format evidence, dependencies and local configuration. No real database, AWS or API operation ran. Evidence: `_codex_work/github_optimize_20261003/`. See [runbook](LOCAL_BATCH_RUNBOOK.md) and [module guide](CODE_STRUCTURE.md).
