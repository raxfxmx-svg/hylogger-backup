# HyLogger Visualisation Backend

FastAPI backend for the 05GJD001 core visualisation tool.

## Setup & run

Dependencies are installed in the project-local venv (`../.venv`).
From the `hylogger-visualisation/` directory:

```bash
.venv/Scripts/python -m uvicorn server.app:app --port 8000
```

Then open `http://localhost:8000/` (static `web/` frontend is mounted at `/`
when the directory exists) or `http://localhost:8000/docs` for the OpenAPI UI.

## API

- `GET /api/holes` → `[{hole_id, depth_from, depth_to, n_trays, sensors}]`
- `GET /api/holes/{hole_id}/meta` → `{hole_id, depth_from, depth_to, sensors, trays:[{tray, tray_label, depth_from, depth_to, sections:[{section, row, depth_from, depth_to, strip, note}]}]}`
- `GET /api/holes/{hole_id}/intervals?sensor=vnir|tir` → `[{id, depth_from, depth_to, mineral, grp, wt1_avg, error_avg, nil_avg, status, flags, n_samples}]`
- `GET /api/holes/{hole_id}/strip/{filename}` → JPEG strip image (whitelist regex, `..` rejected, resolved path must stay inside `strips/`)
- `GET /api/holes/{hole_id}/spectrum?sensor=vnir|tir&sample=N` → `{wavelengths_nm, values}`; values `< -1e37` are returned as `null`; out-of-range `sample` → 422
- `POST /api/holes/{hole_id}/intervals/{interval_id}/status`, body `{status: "confirmed"|"doubtful", note?}` → updated interval; runs in a `BEGIN IMMEDIATE` transaction (`UPDATE intervals.status` + `INSERT annotations`); unknown hole/interval → 404, invalid status/sensor → 422
- `GET /api/holes/{hole_id}/nvcl/meta` → single `borehole_meta` row as JSON
- `GET /api/holes/{hole_id}/nvcl/logs` → `{datasets: [{dataset_id, dataset_name, borehole_uri, tray_id, section_id, domain_id, created_date, modified_date}], logs: [{log_id, dataset_id, log_name, log_type, algorithm_id, kind, sample_count}]}`
- `GET /api/holes/{hole_id}/nvcl/scalars?log_id=<id>&depth_from=<f>&depth_to=<f>&limit=<n>` → `[{id, log_id, depth, scalar_name, value_text, value_num}]` ordered by depth; `log_id` required (422 if missing), depth bounds optional and inclusive, `limit` defaults to 5000 and is capped at 50000

The `nvcl/*` routes read the tables written by the nvcl-kit ETL pipeline;
they return 404 (`hole <id> has no NVCL data`) when `hole.sqlite` or the
relevant NVCL table does not exist yet.

## Expected data layout

```
data/index.sqlite                      table holes
data/holes/<hole_id>/hole.sqlite       tables trays, intervals, annotations
                                       (strips optional, see below)
data/holes/<hole_id>/strips/           tray_XXXX_sec_S.jpg + strips.json
data/holes/<hole_id>/fixture/          vnir-wavelengths.csv, tir-wavelengths.csv
web/                                   static frontend (optional)
```

### index.sqlite

```sql
CREATE TABLE holes (
  hole_id    TEXT PRIMARY KEY,
  depth_from REAL,
  depth_to   REAL,
  n_trays    INTEGER,
  sensors    TEXT,   -- JSON array ('["vnir","tir"]') or comma-separated
  raw_dir    TEXT    -- directory holding the raw .bip files
);
```

### hole.sqlite

```sql
CREATE TABLE trays (
  tray INTEGER, tray_label TEXT, depth_from REAL, depth_to REAL
);
CREATE TABLE intervals (
  id INTEGER PRIMARY KEY,
  sensor TEXT,           -- 'vnir' | 'tir'
  depth_from REAL, depth_to REAL,
  mineral TEXT, grp TEXT,
  wt1_avg REAL, error_avg REAL, nil_avg REAL,
  status TEXT,           -- e.g. 'auto' | 'confirmed' | 'doubtful'
  flags TEXT, n_samples INTEGER
);
CREATE TABLE annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interval_id INTEGER, old_status TEXT, new_status TEXT,
  ts TEXT,               -- ISO-8601 UTC
  note TEXT
);
-- optional; when absent or empty, section metadata falls back to
-- strips/strips.json
CREATE TABLE strips (
  tray INTEGER, section INTEGER, row INTEGER,
  depth_from REAL, depth_to REAL, strip TEXT, note TEXT
);
-- optional, written by the nvcl-kit ETL pipeline; consumed by the
-- /api/holes/{hole_id}/nvcl/* routes
CREATE TABLE borehole_meta (nvcl_id TEXT PRIMARY KEY, name TEXT, lon REAL, ...);
CREATE TABLE nvcl_datasets (dataset_id TEXT PRIMARY KEY, dataset_name TEXT, ...);
CREATE TABLE nvcl_logs (log_id TEXT PRIMARY KEY, dataset_id TEXT, log_name TEXT, ...);
CREATE TABLE nvcl_scalar_data (
  id INTEGER PRIMARY KEY, log_id TEXT, depth REAL,
  scalar_name TEXT, value_text TEXT, value_num REAL
);
CREATE TABLE nvcl_tray_depths (
  id INTEGER PRIMARY KEY, log_id TEXT, sample_no TEXT,
  depth_from REAL, depth_to REAL
);
CREATE TABLE nvcl_images (
  file TEXT PRIMARY KEY, log_id TEXT, kind TEXT, sample_no TEXT,
  depth_from REAL, depth_to REAL, nbytes INTEGER
);
```

### Raw spectra (.bip)

`<raw_dir>/<hole_id>_tsg.bip` (vnir) and `<raw_dir>/<hole_id>_tsg_tir.bip`
(tir): little-endian float32, two planes of shape `(n_samples, n_bands)` in
plane-major order — plane 0 first, then plane 1. `n_bands` is the row count of
the matching `fixture/<sensor>-wavelengths.csv`; `n_samples` is derived from
the file size. Sample `N` is read on demand at byte offset
`N * n_bands * 4` via `mmap` + `struct`.
