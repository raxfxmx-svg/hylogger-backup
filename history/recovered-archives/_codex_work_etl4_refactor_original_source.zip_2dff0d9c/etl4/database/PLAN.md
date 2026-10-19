# Initial Database Plan

The 2026-09-08 plan was to build a reproducible local PostgreSQL/PostGIS import for five boreholes, validate read contracts and measure storage. Cloud selection and deployment were outside this plan. Actual results are recorded separately in README.md and DELIVERY.md.

I separated stable borehole/dataset identities, immutable revisions, real sample axes, tray/Section intervals, spectral streams, interpretation results, logs, assets, source evidence and release manifests. PostgreSQL stores relationships and indexes; external files retain full scalar values, spectra and images. Sample identity is `(axis_id, sample_no)`, and repeated depths remain valid. Wt values, masks and nulls are preserved without inventing probabilities or trajectories.

The planned sequence was field mapping → migrations → first-hole import → five-hole import → range reads, replay and failure recovery → capacity and asset reports. Imports use transactions and explicit versions; publication follows validation. Owner, ingest and read roles are separate, and configuration comes from local environment settings.

The initial input comprised 834 raw files (1,846,272,422 bytes), 507 Parquet files (488,295,090 bytes), 261,892 samples, 583 logs, 25,955,670 scalar records, 6,777 row groups and 249 thumbnails. Eight physical spectral arrays and 53 metadata-only spectral logs had distinct availability states.

Measurements separate database size, tables/indexes, external object files and compressed backups. Local timings do not establish cloud network performance. Read validation retains versions, source units and availability, and checks bounded file reads rather than loading every scalar value into PostgreSQL.
