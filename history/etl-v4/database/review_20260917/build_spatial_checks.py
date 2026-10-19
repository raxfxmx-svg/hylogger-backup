"""Generate read-only acceptance SQL from the offline dump/source baseline."""
from pathlib import Path
import json

OUT = Path(__file__).resolve().parent
baseline = json.loads((OUT / "spatial_baseline.json").read_text(encoding="utf-8"))
release = baseline["release_id"]
rows = baseline["current_release_source_comparison"]
assert len(rows) == 5 and all(r["dump_xy_exactly_match_source"] for r in rows)
assert len(baseline["all_borehole_revision_geometries"]) == 5


def quoted(value):
    return "'" + str(value).replace("'", "''") + "'"


values = []
for row in rows:
    values.append("  (" + ", ".join([
        quoted(row["hole_id"]), quoted(row["dataset_id"]) + "::uuid",
        quoted(row["dataset_revision_id"]) + "::uuid",
        quoted(row["borehole_revision_id"]) + "::uuid",
        repr(row["source_x"]) + "::double precision",
        repr(row["source_y"]) + "::double precision",
        quoted(row["geometry"]["ndr_ewkb_hex"]),
    ]) + ")")

expected = """expected(hole_id, dataset_id, dataset_revision_id, borehole_revision_id,
         source_longitude, source_latitude, dump_ewkb_hex) AS (
 VALUES
""" + ",\n".join(values) + "\n)"

sql = f"""-- ETL4 Aurora PostgreSQL 17.9 / PostGIS 3.5.1 isolated-restore acceptance.
-- Generated only from the selected dump and the original five borehole.json files.
-- Dump SHA256: {baseline['dump_sha256']}
-- Fixed release: {release}
-- Run on the isolated restored database, then repeat as the API reader.
-- No CREATE, ALTER, INSERT, UPDATE, DELETE, extension upgrade or repair is performed.
-- All named passed columns must be true. A SQL error is a failed/unavailable check.
-- Run the whole file in pgAdmin, or use psql -X --set=ON_ERROR_STOP=1 --file=...
-- These checks have NOT been executed against Aurora or a PostGIS 3.5.1 server.

BEGIN READ ONLY;

-- 1. Record actual engine/extension versions. Exact target check, not a gate override.
SELECT current_database() AS database_name, current_user AS login_role,
       version() AS server_build, current_setting('server_version_num')::integer AS server_version_num,
       current_setting('server_version_num')::integer = 170009 AS expected_pg_17_9;

SELECT ext.extversion, ns.nspname AS extension_schema,
       ext.extversion = '3.5.1' AND ns.nspname = 'public' AS expected_extension_passed
FROM pg_extension ext JOIN pg_namespace ns ON ns.oid=ext.extnamespace
WHERE ext.extname='postgis';
-- The previous query must return exactly one row; no row is not a pass.
SELECT public.postgis_full_version() AS postgis_build;

-- 2. Verify the only spatial column, its type modifier, and the restored GiST index.
SELECT count(*) = 1 AS spatial_column_count_passed,
       coalesce(bool_and(n.nspname='core' AND c.relname='borehole_revision'
          AND a.attname='collar_geom' AND t.typname='geometry'
          AND public.postgis_typmod_type(a.atttypmod)='Point'
          AND public.postgis_typmod_srid(a.atttypmod)=4326
          AND public.postgis_typmod_dims(a.atttypmod)=2), false) AS spatial_typmod_passed
FROM pg_attribute a
JOIN pg_class c ON c.oid=a.attrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
JOIN pg_type t ON t.oid=a.atttypid
WHERE n.nspname='core' AND a.attnum>0 AND NOT a.attisdropped
  AND c.relkind IN ('r','p') AND t.typname IN ('geometry','geography','raster');

SELECT count(*)=1 AND coalesce(bool_and(i.indisvalid AND i.indisready
       AND am.amname='gist' AND tbl.relname='borehole_revision'),false) AS spatial_index_passed
FROM pg_index i
JOIN pg_class idx ON idx.oid=i.indexrelid
JOIN pg_class tbl ON tbl.oid=i.indrelid
JOIN pg_namespace ns ON ns.oid=tbl.relnamespace
JOIN pg_am am ON am.oid=idx.relam
WHERE ns.nspname='core' AND idx.relname='borehole_collar_gist';

-- 3. Counts close the gap left by per-expected-row checks: no extra revision/member.
SELECT (SELECT count(*) FROM core.borehole_revision)=5 AS dump_collar_count_passed,
       (SELECT count(*) FROM core.release_dataset WHERE release_id='{release}'::uuid)=5
          AS fixed_release_membership_count_passed,
       (SELECT count(*) FROM core.active_release WHERE singleton AND release_id='{release}'::uuid)=1
          AS active_release_passed;

-- 4. Exact EWKB equality detects coordinate/SRID/dimension/precision changes.
-- ST_X/ST_Y also compare with the independently read original source x/y values.
-- Do not replace source coordinates with a transformed, rounded or swapped value.
WITH {expected}
SELECT e.hole_id, br.id AS actual_borehole_revision_id,
       public.ST_X(br.collar_geom) AS actual_longitude,
       public.ST_Y(br.collar_geom) AS actual_latitude,
       e.source_longitude, e.source_latitude,
       encode(public.ST_AsEWKB(br.collar_geom,'NDR'),'hex') AS actual_ewkb_hex,
       e.dump_ewkb_hex,
       coalesce(public.ST_AsEWKB(br.collar_geom,'NDR')=decode(e.dump_ewkb_hex,'hex'),false)
          AS exact_dump_geometry_passed,
       coalesce(public.ST_X(br.collar_geom)=e.source_longitude
          AND public.ST_Y(br.collar_geom)=e.source_latitude,false) AS source_xy_passed,
       coalesce(public.ST_GeometryType(br.collar_geom)='ST_Point'
          AND public.ST_SRID(br.collar_geom)=4326 AND public.ST_NDims(br.collar_geom)=2
          AND NOT public.ST_IsEmpty(br.collar_geom) AND public.ST_IsValid(br.collar_geom),false)
          AS geometry_semantics_passed,
       coalesce(b.source_hole_id=e.hole_id AND rd.dataset_id=e.dataset_id
          AND d.id=e.dataset_revision_id AND d.borehole_revision_id=br.id
          AND d.borehole_id=br.borehole_id,false) AS fixed_release_identity_passed,
       coalesce(br.coordinate_basis='project_owner_confirmed borehole.json x/y'
          AND br.horizontal_crs='EPSG:4326',false) AS coordinate_provenance_passed
FROM expected e
LEFT JOIN core.borehole_revision br ON br.id=e.borehole_revision_id
LEFT JOIN core.borehole b ON b.id=br.borehole_id
LEFT JOIN core.release_dataset rd ON rd.release_id='{release}'::uuid
  AND rd.dataset_id=e.dataset_id AND rd.dataset_revision_id=e.dataset_revision_id
LEFT JOIN core.dataset_revision d ON d.id=rd.dataset_revision_id
ORDER BY e.hole_id;
-- Exactly five rows; every *_passed value must be true.

-- 5. Exercise the API's actual GeoJSON and bounding-envelope operations.
-- Its default GeoJSON precision preserves these source coordinates (8 decimals).
WITH {expected}
SELECT e.hole_id, public.ST_AsGeoJSON(br.collar_geom)::jsonb AS collar_geometry,
       coalesce((public.ST_AsGeoJSON(br.collar_geom)::jsonb ->> 'type')='Point'
          AND (public.ST_AsGeoJSON(br.collar_geom)::jsonb -> 'coordinates' ->> 0)::double precision=e.source_longitude
          AND (public.ST_AsGeoJSON(br.collar_geom)::jsonb -> 'coordinates' ->> 1)::double precision=e.source_latitude,false)
          AS api_geojson_passed,
       coalesce(br.collar_geom && public.ST_MakeEnvelope(
          e.source_longitude-0.000001,e.source_latitude-0.000001,
          e.source_longitude+0.000001,e.source_latitude+0.000001,4326),false)
          AS api_inside_bbox_passed,
       coalesce(NOT (br.collar_geom && public.ST_MakeEnvelope(0,0,1,1,4326)),false)
          AS api_outside_bbox_passed
FROM expected e
LEFT JOIN core.borehole_revision br ON br.id=e.borehole_revision_id
ORDER BY e.hole_id;
-- Exactly five rows; every *_passed value must be true.

COMMIT;
"""
(OUT / "post_restore_spatial_checks.sql").write_text(sql, encoding="utf-8")
print("Generated post_restore_spatial_checks.sql for five dump-verified collars.")
