> Reference snapshot. See [API_HANDOFF.md](../API_HANDOFF.md) for current handoff scope and cloud status. Local addresses below are not cloud connection information.

# Local Read API Contract

Base URL: `http://127.0.0.1:58000`; interactive documentation: `/docs`. All business reads are release-scoped. If release_id is omitted, use the returned current release ID for subsequent pagination.

| GET route | Purpose and parameters |
|---|---|
| `/health` | Database connection and reader-role check |
| `/v1/boreholes` | Collars/basic fields; optional bbox=west,south,east,north in EPSG:4326 |
| `/v1/boreholes/{source_hole_id}/datasets` | Dataset revisions in the selected borehole/release |
| `/v1/datasets/{revision_id}/logs` | Logs, metrics, s/u, regions, units, bindings and availability |
| `/v1/datasets/{revision_id}/spectral-streams` | VSWIR/TIR wavelength axes and classification evidence |
| `/v1/datasets/{revision_id}/interpretation-sets` | Algorithm family, output region, s/u and available parameters; input links are currently empty |
| `/v1/datasets/{revision_id}/samples` | from_m/to_m, after_sample, limit; axis_id required when multiple axes exist |
| `/v1/datasets/{revision_id}/intervals` | Tray/section intervals; kind, axis_id, offset/limit |
| `/v1/logs/{log_id}/values` | Scalars/profiles; from_m/to_m, from_sample/to_sample, after_row/limit |
| `/v1/datasets/{revision_id}/images` | Thumbnail metadata, tray relationships, depth differences and paths; offset/limit |
| `/v1/images/{frame_id}/content` | Original associated thumbnail bytes, ETag and release ID |
| `/v1/datasets/{revision_id}/issues` | Processing issues, evidence and source-reference states |

revision_id/log_id are internal UUIDs returned by the catalogue, distinct from textual source IDs. The datasets route takes a revision ID, not a stable dataset_id. Page size defaults to 1000 and is capped at 5000. Samples sort by axis-local sample_no with next_after_sample; values sort by source row with next_after_row. Preserve duplicate depths and distinct axes.

Return normalised values and value_raw, retaining null. Tray/section bounds are inclusive sample indices; from_sample/to_sample performs interval intersection for these logs and sample filtering for dense scalars. Profile depth ranges use the validated axis before row-group access. read_stats measures local row-group reads, excluding initial whole-file hash verification and any cloud traffic.

- available: readable canonical payload.
- metadata_only: no payload in this package; empty items and an explicit reason.
- unavailable: payload capability is unverified, such as unknown spectral ordering; preserve source availability separately.
- HTTP 422: invalid parameters, units or axis selection.
- HTTP 404: entity absent from the selected release.
- HTTP 503: no active release, unreadable file, hash mismatch or missing storage adapter.

Return units, interpretation region, s/u, source log and revision; expose profile calibration separately. No derived confidence, threshold filtering, interpolation or mineral reclassification is provided. normalized_metadata preserves historical preparation states; use top-level axis_binding_status/axis_id for final binding. Source confidentiality flags are not API authorisation.

This is a minimal local reader. Frontend, authentication, remote storage and production orchestration are outside this implementation; larger-scale pagination/pooling require separate measurement.
