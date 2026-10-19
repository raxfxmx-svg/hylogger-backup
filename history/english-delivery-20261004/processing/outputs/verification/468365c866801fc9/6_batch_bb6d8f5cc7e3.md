# Batch processing verification results

Status: checks passed within the implemented processing scope; stated capability limits remain.

| Borehole | Samples | Scalar rows | Parquet files | Parquet bytes | Preserved samples with duplicate depths |
|---|---:|---:|---:|---:|---:|
| 05KCD001 | 22,356 | 2,794,701 | 129 | 55,071,022 | 3,008 |
| 07THD002 | 116,424 | 12,225,059 | 109 | 223,062,578 | 11,047 |
| 07THD003 | 54,432 | 5,715,612 | 109 | 107,647,256 | 4,888 |
| 09ATD015 | 46,030 | 3,498,695 | 80 | 68,853,911 | 6,176 |
| 09ATD019 | 22,650 | 1,721,603 | 80 | 33,660,323 | 2,984 |
| 09ATRCD025 | 22,780 | 1,822,604 | 84 | 34,185,788 | 3,378 |
| 09THD028 | 42,880 | 4,631,440 | 112 | 84,985,617 | 5,818 |
| 12BRDDH003 | 10,184 | 1,079,599 | 110 | 22,125,832 | 1,254 |
| 14CADD003 | 1,584 | 193,263 | 126 | 3,819,505 | 564 |

Total: 1465 source files, 921 scalar logs, and 33,682,576 scalar rows.

Values and null masks in canonical payloads have passed batch-by-batch readback checks. This step also checks file hashes, version dependencies, and depth-range reads. Queries at duplicate depths preserve all matching samples.

Outside this step: sample spectra with confirmed ordering, true 3D trajectories, calibrated core surfaces, confidence scores, database import, and cloud upload.
