# Batch processing verification results

Status: checks passed within the implemented processing scope; stated capability limits remain.

| Borehole | Samples | Scalar rows | Parquet files | Parquet bytes | Preserved samples with duplicate depths |
|---|---:|---:|---:|---:|---:|
| 09DKRCD002 | 43,605 | 4,491,706 | 107 | 80,788,378 | 6,539 |

Total: 191 source files, 105 scalar logs and 4,491,706 scalar rows.

Values and null masks in canonical payloads have passed batch-by-batch readback checks. This step also checks file hashes, version dependencies, and depth-range reads. Queries at duplicate depths preserve all matching samples.

Outside this step: sample spectra with confirmed ordering, true 3D trajectories, calibrated core surfaces, confidence scores, database import, and cloud upload.
