# Read-Only API

Default address: `http://127.0.0.1:8000`; interactive documentation: `/docs`; schema: `/openapi.json`. Business routes are GET-only.

| Route | Purpose |
|---|---|
| `/api/v1/health` | Database/PostGIS status and hole, section and image counts |
| `/api/v1/holes` | GeoJSON collar points; bbox, limit and offset filters |
| `/api/v1/holes/{hole_id}` | Hole details, datasets and counts |
| `/api/v1/datasets/{dataset_id}/sections` | Sections and image mappings for the cylinder display |
| `/api/v1/datasets/{dataset_id}/sections/{section_index}` | One selected section |
| `/api/v1/assets/{asset_id}/content` | Registered JPEG content |

Bounding boxes use EPSG:4326 and `min_lon,min_lat,max_lon,max_lat`, for example `118,-34,120,-33`. Sections expose depth bounds, tray/row, sample ranges and image metadata. Image quality is `thumbnail_derived`. Registered relative paths must stay within the release directory; size and existence checks accompany SHA256 ETags.

Read holes → select a hole/dataset → load sections → display the selected image.url. Missing resources return 404; invalid bounds, pagination or section indices return 422.
