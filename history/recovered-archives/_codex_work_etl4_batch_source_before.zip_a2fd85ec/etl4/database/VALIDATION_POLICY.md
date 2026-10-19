# Validation Decisions

I retained content hashes, path boundaries, sample/depth alignment, crop pixels, spectral bindings, database constraints, transactions and publication checks while removing repeated work within a single run. New runs recheck actual content; file modification times do not replace content verification.

Preparation and validation use recorded inputs and source releases. Repeated depths, nulls and original values remain intact. Crop generation and checks group rows by source image; scalar checks read the required Parquet row groups. Each selected sample and crop is still compared. Confirmed display combinations are created during import and checked during acceptance, not silently repaired by acceptance.

Business identity follows parsing, alignment, crop and mapping rules. Comments, code formatting, verification-code changes and run timestamps do not create new business versions. Different output for the same identity is rejected. Existing migrations remain checked and unchanged; schema evolution uses new migrations. API checks, full-history reviews, fault injection, capacity and backup/restore remain separate tools.
