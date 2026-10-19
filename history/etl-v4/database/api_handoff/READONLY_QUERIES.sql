-- ETL4 read-only queries for five boreholes. Run sections separately in pgAdmin; SELECT statements do not create or modify objects.
-- Sections 2-6 are independent. Replace release_id / dataset_id / axis_id / sample_no in each section's params.
-- Example: 05KCD001 in the media release, sample_no=129. Use 130 to check the row boundary.
-- If no row is returned, check the four identity fields. Use sample_no rather than depth; retain all candidates instead of selecting the first.
-- Location rows register copies. The API must select a verified available backend, resolve root_key, and check the actual file.
-- This file was checked statically against migrations 001-005 and the reference reader; it has not been tested against a live database.

-- 1. Five-borehole catalog for the active release: obtain IDs for later queries without mixing historical revisions.
SELECT ar.release_id, b.source_hole_id, d.id AS dataset_id, d.source_dataset_id,
       rd.dataset_revision_id, ax.id AS axis_id, ax.sample_count
FROM core.active_release ar
JOIN core.release_dataset rd ON rd.release_id=ar.release_id
JOIN core.dataset d ON d.id=rd.dataset_id
JOIN core.borehole b ON b.id=d.borehole_id
JOIN core.sample_axis ax ON ax.dataset_revision_id=rd.dataset_revision_id
WHERE ar.singleton AND ar.release_id='fd02659c-dc3d-52ea-a8eb-c032b91e7624'::uuid
ORDER BY b.source_hole_id,d.id,ax.id;

-- 2. One real sample. md_m is source depth, not a value inferred from an image indicator.
WITH params(release_id,dataset_id,axis_id,sample_no) AS (
 VALUES ('fd02659c-dc3d-52ea-a8eb-c032b91e7624'::uuid,'8a3129ba-7d32-507b-b8fe-385ba208033f'::uuid,
         '6b1e2af2-3e03-522b-8d23-11615999ad18'::uuid,129::bigint)
)
SELECT p.release_id,p.dataset_id,rd.dataset_revision_id,s.*
FROM params p
JOIN core.release_dataset rd ON rd.release_id=p.release_id AND rd.dataset_id=p.dataset_id
JOIN core.sample_axis ax ON ax.id=p.axis_id AND ax.dataset_revision_id=rd.dataset_revision_id
JOIN core.scan_sample s ON s.axis_id=ax.id AND s.sample_no=p.sample_no;

-- 3. Result catalog for this revision, retaining original s/u variants, regions, availability, and bound axes.
-- Unbound or unverified logs remain in the catalog; their presence does not establish readable values for the selected sample.
WITH params(release_id,dataset_id,axis_id,sample_no) AS (
 VALUES ('fd02659c-dc3d-52ea-a8eb-c032b91e7624'::uuid,'8a3129ba-7d32-507b-b8fe-385ba208033f'::uuid,
         '6b1e2af2-3e03-522b-8d23-11615999ad18'::uuid,129::bigint)
)
SELECT l.id AS log_id,l.source_log_id,l.source_log_name,l.log_kind,l.metric_key,
       l.metric_code,l.component_rank,l.unit,l.availability_status,
       i.algorithm_family,i.output_region,i.variant_code,
       m.is_probability,lb.status AS binding_status,lb.axis_id AS bound_axis_id,
       lb.axis_id=p.axis_id AS bound_to_selected_axis
FROM params p
JOIN core.release_dataset rd ON rd.release_id=p.release_id AND rd.dataset_id=p.dataset_id
JOIN core.sample_axis ax ON ax.id=p.axis_id AND ax.dataset_revision_id=rd.dataset_revision_id
JOIN core.scan_sample s ON s.axis_id=ax.id AND s.sample_no=p.sample_no
JOIN core.scan_log l ON l.dataset_revision_id=rd.dataset_revision_id
LEFT JOIN core.log_axis_binding lb ON lb.log_id=l.id AND lb.dataset_revision_id=rd.dataset_revision_id
LEFT JOIN core.interpretation_set i ON i.id=l.interpretation_set_id AND i.dataset_revision_id=rd.dataset_revision_id
LEFT JOIN core.metric_definition m ON m.dataset_revision_id=rd.dataset_revision_id AND m.metric_key=l.metric_key
WHERE l.log_kind IN ('scalar','profile','spectral')
ORDER BY l.log_kind,l.source_log_name,l.id;

-- 4. Parquet row groups containing the selected sample, limited to verified dense scalar/profile results.
-- File row intervals are [from,to_exclusive); read the row_group, slice by row_offset, and check sample_no.
-- A file may have multiple storage copies. Deduplicate by log_id/asset_id/row_group before assessing index uniqueness.
WITH params(release_id,dataset_id,axis_id,sample_no) AS (
 VALUES ('fd02659c-dc3d-52ea-a8eb-c032b91e7624'::uuid,'8a3129ba-7d32-507b-b8fe-385ba208033f'::uuid,
         '6b1e2af2-3e03-522b-8d23-11615999ad18'::uuid,129::bigint)
)
SELECT l.id AS log_id,l.source_log_name,c.asset_id,c.row_group,c.source_row_from,
       c.source_row_to_exclusive,c.row_count,p.sample_no-c.source_row_from AS row_offset,
       c.coordinate_kind,c.logical_sha256,a.sha256 AS file_sha256,a.byte_size,
       loc.backend,loc.root_key,loc.object_key,loc.access_status,loc.verified_sha256
FROM params p
JOIN core.release_dataset rd ON rd.release_id=p.release_id AND rd.dataset_id=p.dataset_id
JOIN core.sample_axis ax ON ax.id=p.axis_id AND ax.dataset_revision_id=rd.dataset_revision_id
JOIN core.scan_sample s ON s.axis_id=ax.id AND s.sample_no=p.sample_no
JOIN core.scan_log l ON l.dataset_revision_id=rd.dataset_revision_id
JOIN core.log_axis_binding lb ON lb.log_id=l.id AND lb.dataset_revision_id=rd.dataset_revision_id
 AND lb.axis_id=ax.id AND lb.status='verified'
JOIN core.data_chunk c ON c.log_id=l.id AND c.dataset_revision_id=rd.dataset_revision_id AND c.axis_id=ax.id
 AND p.sample_no>=c.source_row_from AND p.sample_no<c.source_row_to_exclusive
JOIN core.log_asset la ON la.log_id=l.id AND la.asset_id=c.asset_id AND la.dataset_revision_id=rd.dataset_revision_id
JOIN core.asset a ON a.id=c.asset_id AND a.dataset_revision_id=rd.dataset_revision_id
LEFT JOIN core.asset_location loc ON loc.asset_id=a.id
WHERE l.log_kind IN ('scalar','profile') AND l.availability_status='payload_present' AND a.representation='canonical'
ORDER BY l.id,c.asset_id,c.row_group,loc.backend,loc.root_key,loc.object_key;

-- 5. All row-image candidates: matching axis and Section, with the sample inside inclusive [from,to].
-- LEFT JOIN retains candidates with missing crops or locations. The API checks region/mapping states and must not silently select the first image.
WITH params(release_id,dataset_id,axis_id,sample_no) AS (
 VALUES ('fd02659c-dc3d-52ea-a8eb-c032b91e7624'::uuid,'8a3129ba-7d32-507b-b8fe-385ba208033f'::uuid,
         '6b1e2af2-3e03-522b-8d23-11615999ad18'::uuid,129::bigint)
)
SELECT f.log_id AS image_log_id,f.id AS image_frame_id,f.asset_id AS source_asset_id,
       r.id AS image_region_id,r.region_ordinal,r.region_status,m.mapping_status,
       m.sample_no_from,m.sample_no_to,m.source_depth_direction,m.indicator_method,
       m.indicator_version,m.indicator_status,m.indicator_parameters,m.error_px,m.error_depth_m,
       ra.asset_id AS image_asset_id,ra.width_px,ra.height_px,ra.transform,
       a.sha256 AS file_sha256,a.byte_size,loc.backend,loc.root_key,loc.object_key,
       loc.access_status,loc.verified_sha256
FROM params p
JOIN core.release_dataset rd ON rd.release_id=p.release_id AND rd.dataset_id=p.dataset_id
JOIN core.sample_axis ax ON ax.id=p.axis_id AND ax.dataset_revision_id=rd.dataset_revision_id
JOIN core.scan_sample s ON s.axis_id=ax.id AND s.sample_no=p.sample_no
JOIN core.image_sample_mapping m ON m.axis_id=ax.id AND m.dataset_revision_id=rd.dataset_revision_id
 AND m.section_interval_id=s.section_interval_id AND p.sample_no BETWEEN m.sample_no_from AND m.sample_no_to
JOIN core.image_region r ON r.id=m.image_region_id AND r.dataset_revision_id=rd.dataset_revision_id
JOIN core.image_frame f ON f.id=r.image_frame_id AND f.dataset_revision_id=rd.dataset_revision_id AND f.axis_id=ax.id
 AND f.core_interval_id=s.tray_interval_id
JOIN core.scan_log l ON l.id=f.log_id AND l.dataset_revision_id=rd.dataset_revision_id AND l.log_kind='image'
LEFT JOIN core.image_region_asset ra ON ra.region_id=r.id AND ra.dataset_revision_id=rd.dataset_revision_id
 AND ra.log_id=f.log_id AND ra.representation_kind='native_lossless_png'
LEFT JOIN core.asset a ON a.id=ra.asset_id AND a.dataset_revision_id=rd.dataset_revision_id
LEFT JOIN core.asset_location loc ON loc.asset_id=a.id
ORDER BY f.log_id,r.id,ra.asset_id,loc.backend,loc.root_key,loc.object_key;

-- 6. Complete F32 spectra: sample mappings are inclusive; block row intervals are [from,to_exclusive).
-- Prefer reading the complete block and checking block_sha256, then decode <f4 using sample_offset_in_block.
-- S3 Range is bytes=range_start-range_end_inclusive; channel count must equal the wavelength count.
-- Multiple rows for one array/block may represent storage copies. Handle ambiguous mappings or blocks explicitly.
WITH params(release_id,dataset_id,axis_id,sample_no) AS (
 VALUES ('fd02659c-dc3d-52ea-a8eb-c032b91e7624'::uuid,'8a3129ba-7d32-507b-b8fe-385ba208033f'::uuid,
         '6b1e2af2-3e03-522b-8d23-11615999ad18'::uuid,129::bigint)
), selected AS (
 SELECT p.*,rd.dataset_revision_id
 FROM params p
 JOIN core.release_dataset rd ON rd.release_id=p.release_id AND rd.dataset_id=p.dataset_id
 JOIN core.sample_axis ax ON ax.id=p.axis_id AND ax.dataset_revision_id=rd.dataset_revision_id
 JOIN core.scan_sample s ON s.axis_id=ax.id AND s.sample_no=p.sample_no
), mapped AS (
 SELECT p.*,sa.id AS array_id,sa.log_id,sa.asset_id,sa.spectral_stream_id,
        sa.dtype_code,sa.matrix_order,sa.channel_count,sa.sample_stride_bytes,
        sa.data_offset_bytes,sa.value_unit,sa.scaling_applied,
        sm.id AS sample_map_id,sm.source_row_from+p.sample_no-sm.sample_no_from AS source_row
 FROM selected p
 JOIN core.scan_log l ON l.dataset_revision_id=p.dataset_revision_id
  AND l.log_kind='spectral' AND l.availability_status='payload_present'
 JOIN core.log_axis_binding lb ON lb.log_id=l.id AND lb.dataset_revision_id=p.dataset_revision_id
  AND lb.axis_id=p.axis_id AND lb.status='verified'
 JOIN core.spectral_array sa ON sa.log_id=l.id AND sa.dataset_revision_id=p.dataset_revision_id
  AND sa.spectral_stream_id=l.spectral_stream_id AND sa.layout_status='verified_sample_major'
 JOIN core.spectral_sample_map sm ON sm.spectral_array_id=sa.id AND sm.dataset_revision_id=p.dataset_revision_id
  AND sm.axis_id=p.axis_id AND sm.binding_status='verified' AND sm.mapping_kind='identity_range'
  AND p.sample_no BETWEEN sm.sample_no_from AND sm.sample_no_to
)
SELECT m.log_id,m.array_id,m.sample_map_id,m.source_row,m.dtype_code,m.matrix_order,
       m.channel_count,m.sample_stride_bytes,m.value_unit,m.scaling_applied,
       b.block_no,b.byte_offset AS range_start,b.byte_offset+b.byte_length-1 AS range_end_inclusive,
       b.byte_length,b.sha256 AS block_sha256,
       (m.source_row-b.source_row_from)*m.sample_stride_bytes AS sample_offset_in_block,
       st.region_code,st.wavelength_unit,st.wavelengths,a.id AS asset_id,
       a.sha256 AS file_sha256,a.byte_size,loc.backend,loc.root_key,loc.object_key,
       loc.access_status,loc.verified_sha256
FROM mapped m
JOIN core.spectral_block b ON b.spectral_array_id=m.array_id
 AND m.source_row>=b.source_row_from AND m.source_row<b.source_row_to_exclusive
JOIN core.spectral_stream st ON st.id=m.spectral_stream_id AND st.dataset_revision_id=m.dataset_revision_id
JOIN core.log_asset la ON la.log_id=m.log_id AND la.asset_id=m.asset_id AND la.dataset_revision_id=m.dataset_revision_id
JOIN core.asset a ON a.id=m.asset_id AND a.dataset_revision_id=m.dataset_revision_id
LEFT JOIN core.asset_location loc ON loc.asset_id=a.id
ORDER BY m.log_id,m.array_id,m.sample_map_id,b.block_no,loc.backend,loc.root_key,loc.object_key;
