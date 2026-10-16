# Backend

AI-generated FastAPI service for the HyLogger viewer.

| File | Purpose |
| --- | --- |
| `app.py` | Serves borehole metadata, mineral intervals, core images, spectra, review updates, NVCL data, and the web frontend. |
| `test_nvcl_endpoints.py` | Tests the NVCL API with temporary databases. |
| `__init__.py` | Marks the server directory as a Python package. |

The service reads `data/index.sqlite` and per-hole files under `data/holes/`. Spectrum requests also use the original `.bip` files referenced by the index database.
