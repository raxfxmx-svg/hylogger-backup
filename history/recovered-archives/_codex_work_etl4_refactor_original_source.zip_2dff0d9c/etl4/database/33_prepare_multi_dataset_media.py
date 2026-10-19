"""Verify per-sample spectra and review/crop dataset-specific core rows."""
import argparse
import math
import shutil
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image, ImageDraw
from _multi_common import *

MEDIA = MULTI / 'media'


def media_context():
    import _media_common as mc
    mc.WORK = MEDIA; mc.EVIDENCE = MULTI_EVIDENCE
    return mc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fetch-reference', action='store_true')
    parser.add_argument('--record-reviewed', action='store_true')
    args = parser.parse_args()
    mc = media_context(); datasets = []; spectra = []
    for h in prepared():
        m = h['metadata']; d = m['dataset']; r = m['dataset_revision']
        u = {'hole_id': h['summary']['hole_id'], 'dataset_id': d['id'], 'source_dataset_id': d['source_dataset_id'],
             'source_dataset_name': d['source_dataset_name'], 'source_revision_id': r['id'], 'source_axis_id': m['proposed_axis_id'],
             'source_snapshot_id': r['source_snapshot_id'], 'sample_count': h['alignment']['sample_count'],
             'prepared_directory': h['folder'].relative_to(PREPARED).as_posix()}
        datasets.append(u)
        streams = {s['id']: s for s in m['spectral_streams']}
        for l in m['logs']:
            if l['log_kind'] != 'spectral': continue
            a = l['source_manifest']; st = streams[l['spectral_stream_id']]
            spectra.append({**u, **a, 'source_log_pk': l['id'], 'spectral_stream_id': st['id'],
                            'region_code': st['region_code'], 'wavelengths': st['wavelengths'], 'wavelength_unit': st['wavelength_unit'],
                            'value_unit': l['unit'], 'script_raw': l['source_script_raw'], 'layout_status': 'unconfirmed', 'binding_status': 'unconfirmed'})
    mc.save_stage(20, {'status': 'passed', 'datasets': datasets, 'spectra': spectra, 'source_release_id': None,
                       'scope': 'New datasets only; source samples remain in their independent axes'})
    official = MULTI_EVIDENCE / 'official'; official.mkdir(parents=True, exist_ok=True)
    for p in (ROOT / 'media_evidence' / 'official').glob('*'):
        if p.is_file():
            target = official / p.name
            if target.exists(): require(sha(target) == sha(p), 'Official contract evidence changed')
            else: shutil.copyfile(p, target)
    verifier = module('multi_spectral_verifier', ROOT / '21_verify_spectral_bindings.py')
    with ThreadPoolExecutor(max_workers=4) as pool:
        verified = list(pool.map(lambda a: verifier.verify_one(a, args.fetch_reference), spectra))
    mc.save_stage(21, {'status': 'passed', 'spectra': verified, 'official_commit': verifier.COMMIT,
                       'official_evidence_sha256': {p.name: sha(p) for p in official.glob('*') if p.is_file()}})
    module('multi_spectral_blocks', ROOT / '22_prepare_spectral_access.py').main()
    frames = []; rows = []; templates = defaultdict(list)
    for u in datasets:
        folder = mc.source_folder(u); intervals = read(folder / '4_core_intervals.json')
        groups = read(mc.source_path(u, 'image_logs_by_dataset.json'))
        for f in read(folder / '4_image_frames.json'):
            require(sum(g['dataset_id'] == u['source_dataset_id'] and g['log_id'] == f['source_log_id'] for g in groups) == 1, 'Wrong image dataset')
            sections = sorted((s for s in intervals if s['interval_kind'] == 'section' and s['parent_interval_id'] == f['core_interval_id']), key=lambda s: s['ordinal'])
            require(sections, 'Tray has no sections')
            im = mc.decode(mc.source_path(u, f['source_path'])); width, height = im.size; n = len(sections); pitch = height / n
            require(im.size == (f['width_px'], f['height_px']), 'Image dimensions changed')
            frame = {**u, **f, 'source_sha256': sha(mc.source_path(u, f['source_path'])), 'sections': sections, 'row_count': n}
            frames.append(frame)
            profile = np.median(np.asarray(im, dtype=float)[:, 8:-8, :].mean(axis=2), axis=1)
            boundaries = [0]; checks = []
            for i in range(1, n):
                center = round(i * pitch); radius = max(2, round(.12 * pitch))
                options = range(max(3, center-radius), min(height-3, center+radius+1))
                scores = {y: float(profile[y] - (profile[y-3]+profile[y+3])/2) for y in options}
                require(scores, 'Image too small for section layout')
                best = max(scores, key=scores.get); cut = best if scores[best] >= 12 else center
                boundaries.append(cut); checks.append({'expected': center, 'cut': cut, 'ridge_score': scores[best]})
            boundaries.append(height)
            key = f"{u['source_dataset_name']}_{width}x{height}_{n}rows"
            templates[key].append({'frame': frame, 'boundaries': boundaries, 'divider_checks': checks})
            for i, s in enumerate(sections):
                top, bottom = boundaries[i:i+2]
                require(0 <= top < bottom <= height and bottom-top <= pitch*1.35, 'Suspect row bounds')
                rows.append({**{k:v for k,v in frame.items() if k != 'sections'}, 'source_frame_id': f['id'],
                             'source_section_id': s['id'], 'section': s, 'region_ordinal': i, 'x_px': 0, 'y_px': top,
                             'width_px': width, 'height_px': bottom-top, 'template_key': key,
                             'row_key': uid('multi-row', u['dataset_id'], u['source_snapshot_id'], f['id'], i),
                             'coordinate_basis': 'native_decoded_pixels_top_left_xy_half_open', 'region_status': 'candidate',
                             'detection_method': 'section_pitch_local_divider_ridge_preserve_cell_v1', 'review_basis': 'awaiting_visual_review'})
    chosen = [v[i] for _, v in sorted(templates.items()) for i in sorted({0, len(v)-1})]
    sheets = {}
    for start in range(0, len(chosen), 12):
        subset = chosen[start:start+12]; cell_h = max(x['frame']['height_px'] for x in subset)+42
        sheet = Image.new('RGB', (1260, math.ceil(len(subset)/3)*cell_h), 'white'); draw = ImageDraw.Draw(sheet)
        for j, v in enumerate(subset):
            f = v['frame']; im = mc.decode(mc.source_path(f, f['source_path'])); pen = ImageDraw.Draw(im)
            for y in v['boundaries'][1:-1]: pen.line((0, y, im.width-1, y), fill=(255,0,70), width=1)
            x = j%3*420+8; y = j//3*cell_h
            draw.text((x,y+3), f"{f['source_dataset_name']} tray {f['image_ordinal']+1}", fill='black')
            draw.text((x,y+17), f"{f['row_count']} rows; {f['width_px']}x{f['height_px']}", fill='black')
            sheet.paste(im, (x,y+34))
        dest = MEDIA / f'33_review_{start//12+1}.png'; dest.parent.mkdir(parents=True, exist_ok=True); sheet.save(dest)
        sheets[dest.name] = sha(dest)
    if args.record_reviewed:
        prior = mc.stage(25)
        require(prior['contact_sheet_sha256'] == sheets, 'Review images changed; inspect current sheets first')
    basis = f"Visual review of first/last representatives of {len(templates)} dataset/dimension/section-count classes; all-frame bounds and source identity checks"
    for r in rows:
        if args.record_reviewed: r.update(region_status='reviewed', review_basis=basis)
    mc.save_stage(23, {'status': 'passed', 'frames': frames})
    mc.save_stage(24, {'status': 'candidates_ready', 'template_counts': {k:len(v) for k,v in templates.items()}})
    mc.save_stage(25, {'status': 'reviewed' if args.record_reviewed else 'awaiting_visual_review', 'rows': rows,
                       'contact_sheet_sha256': sheets, 'review_basis': basis if args.record_reviewed else None})
    if not args.record_reviewed:
        print('Inspect contact sheets before --record-reviewed; no database rows inserted.'); return
    mapped = []; covered = defaultdict(int)
    for r in rows:
        s = r['section']; a, b = s['sample_no_from'], s['sample_no_to']; covered[r['dataset_id']] += b-a+1
        mapped.append({**r, 'sample_no_from': a, 'sample_no_to': b, 'mapping_level': 'section_interval',
                       'mapping_status': 'metadata_associated', 'mapping_method': 'source_section_order_with_layout_template',
                       'source_depth_direction': 'left_to_right', 'direction_status': 'confirmed',
                       'direction_basis': 'project_owner_manual_confirmation_all_trays_left_to_right',
                       'indicator_method': 'sample_index_linear', 'indicator_version': 1, 'indicator_status': 'approximate',
                       'indicator_parameters': mc.INDICATOR, 'anchor_points': None, 'error_px': None, 'error_depth_m': None})
    require(all(covered[u['dataset_id']] == u['sample_count'] for u in datasets), 'Incomplete image sample coverage')
    mc.save_stage(26, {'status': 'passed', 'rows': mapped, 'sample_counts': dict(covered)})
    module('multi_crop', ROOT / '27_build_image_row_assets.py').main()
    write(MULTI / '33_media_ready.json', {'status': 'passed', 'dataset_count': len(datasets), 'row_count': len(rows),
                                        'code_sha256': sha(Path(__file__)), 'contact_sheets': sheets,
                                        'spectral_arrays': len(mc.stage(22)['arrays'])})


if __name__ == '__main__':
    main_guard(main)
