# Batch processing verification results

Status: checks passed within the implemented processing scope; stated capability limits remain.

| Borehole | Samples | Scalar rows | Parquet files | Parquet bytes | Preserved samples with duplicate depths |
|---|---:|---:|---:|---:|---:|
| 09ATRCD025 | 22,780 | 1,822,604 | 84 | 34,185,788 | 3,378 |
| 12BRDDH003 | 10,184 | 1,079,599 | 110 | 22,125,832 | 1,254 |

Total: 278 source files, 190 scalar logs and 2,902,203 scalar rows.

Values and null masks in canonical payloads have passed batch-by-batch readback checks. This step also checks file hashes, version dependencies, and depth-range reads. Queries at duplicate depths preserve all matching samples.

Outside this step: sample spectra with confirmed ordering, true 3D trajectories, calibrated core surfaces, confidence scores, database import, and cloud upload.
