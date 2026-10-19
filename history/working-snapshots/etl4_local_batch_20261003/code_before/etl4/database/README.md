# ETL4 Database

This directory contains PostgreSQL/PostGIS migrations, dataset import, media relationships, read contracts, validation and backup/restore tools. It keeps source identities and historical revisions, preserves real sample numbers and repeated depths, and indexes large Parquet, F32 and image assets stored outside the database.

- `migrations/`: versioned schema, constraints and permissions.
- Numbered Python scripts: setup, import, media preparation, validation and delivery stages.
- Shared Python modules: storage, identity, querying and verification logic.
- `tests/`: small regression tests and separate database integration tools.
- `schema_dictionary.md`, `source_to_table_mapping.md`, `architecture.md`: fields, provenance and relationships.
- Read contracts: fields and behavior used by backend/frontend integration.
- Delivery and change reports: historical results and implementation decisions.

The initial five-hole import retained 261,892 samples, 583 log records and 6,777 Parquet row groups. The complete 25,955,670 scalar values remained in external files. The later five-hole media extension added 1,361 row images and eight sample-readable spectral matrices. Those phases are separate historical milestones.

The 2026-09-24 multi-dataset delivery contained eight holes, 13 datasets and 39 tables, preserving 654,778 source samples, 4,160 row images and 24 matrices. Confirmed 3D continuation selected 638,331 samples; 2D retained complete source datasets. See MULTI_DATASET_DELIVERY.md and MULTI_DATASET_READ_CONTRACT.md.

Runtime configuration and passwords are local. Use `.env.example` and the documented roles; raw files, runtime databases and backups are separate inputs/outputs rather than source-code dependencies bundled here. A database dump does not include object files.
