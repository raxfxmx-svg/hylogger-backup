# ETL4 Source Package

This snapshot groups data preparation, local database import and the supplementary tools selected at that stage. Numbered scripts show the execution order; shared modules implement file access, validation, identity, database operations and media reads.

The complete-version workflow is raw precheck (0), single-dataset preparation (1–6, 7 --inputs-only, 20 --files-only, 21–27) or multi-dataset preparation (31–33), first package acceptance (28), schema setup (8), then complete import and second acceptance (37). Earlier two-stage tools are historical utilities. Numbers 15–19 were not present in the original project.

Supplementary `etl4/` trees, where included, merge into the main `etl4/` tree and share its common modules. This source selection does not contain raw data, virtual environments, databases, passwords or every runtime resource. Running it requires migrations 001–006, official spectral-format evidence with its original license, Python dependencies, PostgreSQL/PostGIS and local configuration. Required evidence includes NVCLDataSvcDao.java, SpectralDataVo.java and getspectraldatausage.html. The frontend/API is a separate integration component.

- [etl4](etl4/): preparation and local import.
- [review-and-recovery](review-and-recovery/README.md): backup and restore validation.
- [cloud-batch-processing](cloud-batch-processing/README.md): export, upload, cloud merge and cleanup preview.
