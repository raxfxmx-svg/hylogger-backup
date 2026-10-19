"""Scientific selection semantics adapted from the packaged _media_reader.py.

The SQL relationships and result statuses are retained. Storage is explicitly
injected instead of changing the reference reader's module globals.
"""
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from .storage import APIError, require

RELEASE = 'fd02659c-dc3d-52ea-a8eb-c032b91e7624'
HOLES = ('05KCD001', '07THD002', '07THD003', '09ATD015', '09ATD019')
INDICATOR = {'range_basis': 'row_sample_interval', 'endpoint_rule': 'first_last_pixel_center',
             'single_sample_rule': 'center', 'coordinate_space': 'row_crop_pixels'}


def context(conn, hole):
    if hole not in HOLES:
        raise APIError('hole_not_in_release', 404)
    rows = conn.execute('''SELECT rd.dataset_id,rd.dataset_revision_id,a.id AS axis_id,a.sample_count
      FROM core.release_dataset rd JOIN core.dataset d ON d.id=rd.dataset_id
      JOIN core.borehole b ON b.id=d.borehole_id
      JOIN core.sample_axis a ON a.dataset_revision_id=rd.dataset_revision_id
      WHERE rd.release_id=%s AND b.source_hole_id=%s''', (RELEASE, hole)).fetchall()
    require(len(rows) == 1, 'release_axis_mismatch')
    return rows[0]


def logs(conn, revision):
    return conn.execute('''SELECT l.*,b.status AS binding_status,b.axis_id,
      i.variant_code,i.algorithm_family,i.output_region
      FROM core.scan_log l LEFT JOIN core.log_axis_binding b ON b.log_id=l.id
      LEFT JOIN core.interpretation_set i ON i.id=l.interpretation_set_id
      WHERE l.dataset_revision_id=%s AND l.log_kind IN ('scalar','spectral','profile')
      ORDER BY l.log_kind,l.source_log_name,l.id''', (revision,)).fetchall()


def result(conn, store, log, axis, sample_no):
    base = {k: log[k] for k in ('id', 'source_log_id', 'source_log_name', 'log_kind', 'unit',
        'interpretation_set_id', 'variant_code', 'algorithm_family', 'output_region', 'component_rank', 'metric_key')}
    base['log_id'] = base.pop('id')
    if log['availability_status'] != 'payload_present':
        return {**base, 'status': log['availability_status'], 'value': None}
    if log['binding_status'] != 'verified' or str(log['axis_id']) != str(axis):
        return {**base, 'status': 'axis_binding_unavailable', 'value': None}
    if log['log_kind'] == 'spectral':
        arrays = conn.execute('''SELECT a.*,m.source_row_from,m.sample_no_from,m.sample_no_to
          FROM core.spectral_array a JOIN core.spectral_sample_map m ON m.spectral_array_id=a.id
          WHERE a.log_id=%s AND m.axis_id=%s AND %s BETWEEN m.sample_no_from AND m.sample_no_to
          AND m.binding_status='verified' AND a.layout_status='verified_sample_major' ''',
          (log['id'], axis, sample_no)).fetchall()
        if len(arrays) != 1:
            return {**base, 'status': 'spectral_mapping_unavailable', 'value': None}
        arr = arrays[0]
        row = arr['source_row_from'] + sample_no - arr['sample_no_from']
        blocks = conn.execute('''SELECT * FROM core.spectral_block WHERE spectral_array_id=%s
          AND source_row_from<=%s AND source_row_to_exclusive>%s''', (arr['id'], row, row)).fetchall()
        require(len(blocks) == 1, 'ambiguous_spectral_block')
        block = blocks[0]
        asset = store.asset(conn, arr['asset_id'])
        if asset is None:
            return {**base, 'status': 'asset_unavailable', 'value': None}
        require(arr['dtype_code'] == '<f4' and arr['sample_stride_bytes'] == arr['channel_count'] * 4,
                'unverified_spectral_layout')
        data = store.block(asset, block)
        offset = (row - block['source_row_from']) * arr['sample_stride_bytes']
        require(offset >= 0 and offset + arr['channel_count'] * 4 <= len(data), 'spectral_extent_mismatch')
        values = np.frombuffer(data, dtype='<f4', count=arr['channel_count'], offset=offset)
        stream = conn.execute('SELECT * FROM core.spectral_stream WHERE id=%s', (arr['spectral_stream_id'],)).fetchone()
        require(stream is not None and len(stream['wavelengths']) == arr['channel_count'], 'wavelength_count_mismatch')
        return {**base, 'status': 'available', 'source_row': row, 'region_code': stream['region_code'],
            'wavelength': stream['wavelengths'], 'wavelength_unit': stream['wavelength_unit'],
            'spectra': [float(x) if np.isfinite(x) else None for x in values],
            'nonfinite_channels': [i for i, x in enumerate(values) if not np.isfinite(x)],
            'value_unit': arr['value_unit'], 'scaling_applied': False, 'array_id': arr['id']}
    chunks = conn.execute('''SELECT c.*,a.sha256 FROM core.data_chunk c JOIN core.asset a ON a.id=c.asset_id
      WHERE c.log_id=%s AND c.axis_id=%s AND c.source_row_from<=%s AND c.source_row_to_exclusive>%s''',
      (log['id'], axis, sample_no, sample_no)).fetchall()
    if len(chunks) != 1:
        return {**base, 'status': 'sample_result_unavailable', 'value': None}
    chunk = chunks[0]
    asset = store.asset(conn, chunk['asset_id'])
    if asset is None:
        return {**base, 'status': 'asset_unavailable', 'value': None}
    with pq.ParquetFile(pa.BufferReader(store.full(asset))) as parquet:
        group = parquet.read_row_group(chunk['row_group'])
        index = sample_no - chunk['source_row_from']
        require(0 <= index < group.num_rows, 'canonical_extent_mismatch')
        selected = group.slice(index, 1).to_pylist()[0]
    require(selected['sample_no'] == sample_no, 'canonical_sample_mismatch')
    status = ('source_null' if selected['value_numeric'] is None and selected['value_text'] is None else 'available') \
        if log['log_kind'] == 'scalar' else 'available_uncalibrated_profile'
    return {**base, 'status': status, 'value': selected}


def read_sample(conn, store, hole, sample_no, log_ids, image_log_id=None):
    ctx = context(conn, hole)
    axis = ctx['axis_id']
    sample = conn.execute('SELECT * FROM core.scan_sample WHERE axis_id=%s AND sample_no=%s',
                          (axis, sample_no)).fetchone()
    if sample is None:
        raise APIError('sample_not_found', 404)
    available_logs = logs(conn, ctx['dataset_revision_id'])
    wanted = set(map(str, log_ids))
    if not wanted <= {str(log['id']) for log in available_logs}:
        raise APIError('log_outside_dataset_revision', 422)
    selected_logs = [log for log in available_logs if str(log['id']) in wanted]
    images = conn.execute('''SELECT m.*,r.region_status,f.log_id,f.asset_id AS source_asset_id,
      ra.asset_id,ra.width_px,ra.height_px,ra.transform FROM core.image_sample_mapping m
      JOIN core.image_region r ON r.id=m.image_region_id JOIN core.image_frame f ON f.id=r.image_frame_id
      LEFT JOIN core.image_region_asset ra ON ra.region_id=r.id AND ra.representation_kind='native_lossless_png'
      WHERE m.axis_id=%s AND m.section_interval_id=%s AND %s BETWEEN m.sample_no_from AND m.sample_no_to
      ORDER BY f.log_id,r.region_ordinal,ra.asset_id''', (axis, sample['section_interval_id'], sample_no)).fetchall()
    if image_log_id is not None:
        valid = conn.execute('''SELECT 1 FROM core.scan_log WHERE id=%s AND dataset_revision_id=%s
          AND log_kind='image' ''', (str(image_log_id), ctx['dataset_revision_id'])).fetchone()
        if not valid:
            raise APIError('image_log_outside_dataset_revision', 422)
        images = [row for row in images if str(row['log_id']) == str(image_log_id)]
    candidates = []
    for row in images:
        asset = store.asset(conn, row['asset_id']) if row['asset_id'] else None
        available = asset is not None and row['region_status'] == 'reviewed' and row['mapping_status'] == 'metadata_associated'
        indicator = None
        if available:
            # A registered DB location alone is insufficient evidence of readable bytes.
            store.full(asset)
            if row['indicator_method'] == 'sample_index_linear' and row['indicator_version'] == 1 and row['indicator_status'] == 'approximate':
                require(row['indicator_parameters'] == INDICATOR, 'unknown_indicator_contract')
                first, last, width = row['sample_no_from'], row['sample_no_to'], row['width_px']
                require(0 <= first <= sample_no <= last and width >= 1, 'invalid_indicator_extent')
                p = (sample_no - first) / (last - first) if last > first else .5
                indicator = {'method': 'sample_index_linear', 'version': 1, 'status': 'approximate', 'p': p, 'x_px': p * (width - 1)}
        candidates.append({'image_region_id': row['image_region_id'], 'image_asset_id': row['asset_id'],
            'image_log_id': row['log_id'], 'source_image_asset_id': row['source_asset_id'],
            'status': 'available' if available else 'image_unavailable',
            'content_path': f"/v1/images/{row['asset_id']}/content" if available else None,
            'width_px': row['width_px'], 'height_px': row['height_px'],
            'sample_no_from': row['sample_no_from'], 'sample_no_to': row['sample_no_to'], 'indicator': indicator,
            **{key: row[key] for key in ('mapping_level', 'mapping_status', 'source_depth_direction', 'error_px', 'error_depth_m')}})
    return {'release_id': RELEASE, 'hole_id': hole, **ctx, 'sample_no': sample_no, 'md_m': sample['md_m'],
        'sample': sample, 'results': [result(conn, store, log, axis, sample_no) for log in selected_logs],
        'image_status': 'image_unavailable' if not candidates else 'selection_required' if len(candidates) > 1 else candidates[0]['status'],
        'images': candidates,
        'indicator_label': 'The marker estimates position by sample index; depth and results belong to the selected sample.'}
