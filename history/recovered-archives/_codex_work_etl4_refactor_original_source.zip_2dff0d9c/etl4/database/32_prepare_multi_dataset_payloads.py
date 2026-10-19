"""Prepare each source dataset independently using the reviewed scalar/axis parsers."""
import argparse
import copy
from contextlib import contextmanager
from _multi_common import *


def selected_metadata(raw, u):
    r = copy.deepcopy(raw); did = u['source_dataset_id']; ids = u['log_ids']
    r['datasets.json'] = [d for d in r['datasets.json'] if d['dataset_id'] == did]
    for kind, names in {'scalar': ('logs_scalar.json', 'scalar_manifest.json'),
                        'spectral': ('logs_spectral.json', 'spectral_manifest.json'),
                        'profile': ('logs_profilometer.json', 'profilometer_manifest.json'),
                        'image': ('logs_image.json', 'image_logs_by_dataset.json')}.items():
        for name in names:
            r[name] = [x for x in r[name] if x['log_id'] in ids[kind]]
    r['images_manifest.json'] = {k: [x for x in v if x['dataset_id'] == did] for k, v in r['images_manifest.json'].items()}
    r['tray_depths.json'] = {k: v for k, v in r['tray_depths.json'].items() if k in ids['image']}
    return r


def inventory(hole, r, u, code):
    references = {}
    for kind, name in [('scalar', 'scalar_manifest.json'), ('spectral', 'spectral_manifest.json'),
                       ('profile', 'profilometer_manifest.json'), ('image', 'images_manifest.json')]:
        entries = r[name]['files'] if kind == 'image' else r[name]
        for e in entries:
            if e.get('file'):
                require(e['file'] not in references, 'Duplicate raw file reference')
                references[e['file']] = {'kind': kind, 'manifest': name, 'entry': e}
    files = []
    for rel in sorted(set(references) | set(r) | {'download-report.txt'}):
        path = inside(ETL / hole, ETL / hole / rel)
        require(path.is_file() and not path.is_symlink(), 'Missing or indirect source file')
        stat = path.stat(); ref = references.get(rel)
        if ref:
            require(stat.st_size == ref['entry']['nbytes'], 'Source size differs from manifest')
        files.append({'path': rel, 'size_bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                      'kind': ref['kind'] if ref else 'metadata', 'manifest_reference': ref,
                      'expected_sha256': ref['entry']['sha256'] if ref else sha(path)})
    source_id = digest({'dataset': u['source_dataset_id'], 'membership': u['membership_evidence'],
                        'files': [{k: f[k] for k in ('path', 'size_bytes', 'expected_sha256')} for f in files]})
    folder = PROCESSING / 'outputs' / 'multidataset' / hole / u['source_dataset_id'] / source_id[:16] / code[:16]
    return folder, {'step': 1, 'hole_id': hole, 'status': 'passed', 'pipeline_id': code,
                    'source_snapshot_id': source_id, 'source_dataset_id': u['source_dataset_id'],
                    'file_count': len(files), 'source_bytes': sum(f['size_bytes'] for f in files), 'files': files,
                    'membership_evidence': u['membership_evidence'],
                    'raw_metadata_scope': 'Full hole-level documents; parsers receive an explicit dataset projection'}


@contextmanager
def dataset_context(hole, folder, inv, projected, baseline):
    """Inject an explicit context only within this process; legacy files stay unchanged."""
    import _etl_common as ec
    names = ('ALLOWED', 'source_json', 'snapshot', 'baseline_for')
    previous = {k: getattr(ec, k) for k in names}
    ec.ALLOWED = MULTI_HOLES
    ec.source_json = lambda selected, name: copy.deepcopy(projected[name]) if selected == hole else (_ for _ in ()).throw(ValueError('Cross-hole context'))
    ec.snapshot = lambda selected: (folder, inv) if selected == hole else (_ for _ in ()).throw(ValueError('Cross-hole context'))
    ec.baseline_for = lambda selected: baseline if selected == hole else (_ for _ in ()).throw(ValueError('Cross-hole context'))
    try:
        yield ec
    finally:
        for k, v in previous.items():
            setattr(ec, k, v)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--holes', nargs='+', choices=MULTI_HOLES, default=list(MULTI_HOLES))
    args = parser.parse_args(); source = audit(); units = []
    sys.path.insert(0, str(PROCESSING))
    import _etl_common as ec
    code_files = [Path(__file__), ROOT / '_multi_common.py'] + list(PROCESSING.glob('[1-5]_*.py')) + [PROCESSING / '_etl_common.py']
    code = digest({'files': {p.name: sha(p) for p in code_files}, 'environment': ec.environment(), 'contract': 'multi-dataset-context-v1'})
    for u in source['datasets']:
        if u['hole_id'] not in args.holes:
            continue
        hole = u['hole_id']; raw = raw_metadata(hole)
        require(all(sha(ETL / hole / n) == checksum for n, checksum in source['raw_metadata_sha256'][hole].items()), 'Raw metadata changed since step 31')
        for proof in u['membership_evidence'].values():
            if 'path' in proof:
                require(sha(ROOT / proof['path']) == proof['sha256'], 'Membership evidence changed')
        r = selected_metadata(raw, u); folder, inv = inventory(hole, r, u, code)
        completed = folder / '32_unit.json'
        if completed.exists():
            cached = read(completed)
            require(all(sha(folder / rel) == checksum for rel, checksum in cached['prepared_hashes'].items()), 'Cached prepared bytes changed')
            original = read(folder / '1_inventory.json')
            require(original == inv, 'Source file inventory changed; revalidation required')
            units.append(cached); print(f"Reuse verified dataset {u['source_dataset_name']}", flush=True); continue
        baseline = {**u, 'scalar_log_count': len(r['scalar_manifest.json']),
                    'spectral_array_count': sum(bool(x.get('file')) for x in r['spectral_manifest.json'])}
        print(f"Prepare {hole}/{u['source_dataset_name']} ({u['sample_count']:,} samples)", flush=True)
        with dataset_context(hole, folder, inv, r, baseline):
            ec.write_json(folder / '1_inventory.json', inv)
            module('multi_validate', PROCESSING / '2_validate_payloads.py').validate_hole(hole)
            module('multi_normalize', PROCESSING / '3_normalize_metadata.py').normalize_hole(hole)
            module('multi_align', PROCESSING / '4_align_samples.py').align_hole(hole, image_depth_policy='decimal_1e-5_or_same_float32')
            # Restore complete source documents before storage/import. The projection
            # is a parser input, never represented as the original downloaded bytes.
            m = read(folder / '3_normalized_metadata.json')
            m['raw_metadata'] = raw
            m['selected_dataset_context'] = {'source_dataset_id': u['source_dataset_id'], 'log_ids': u['log_ids'],
                                             'membership_evidence': u['membership_evidence']}
            m['borehole']['orientation_missing_reason'] = 'downhole_survey_not_provided'
            m['borehole']['orientation_missing_reason_source'] = 'source_package_inspection; dataset XML orientation retained separately'
            ec.write_json(folder / '3_normalized_metadata.json', m)
            report3 = read(folder / '3_metadata_report.json'); report3['normalized_metadata_sha256'] = sha(folder / '3_normalized_metadata.json')
            ec.write_json(folder / '3_metadata_report.json', report3)
            report4 = read(folder / '4_alignment_report.json'); report4['previous_report_sha256'] = sha(folder / '3_metadata_report.json')
            ec.write_json(folder / '4_alignment_report.json', report4)
            module('multi_columnar', PROCESSING / '5_build_columnar.py').build_hole(hole)
        hashes = {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob('*')) if p.is_file() and p.name != '32_unit.json'}
        summary = {**u, 'status': 'passed', 'prepared_directory': folder.relative_to(ETL).as_posix(),
                   'pipeline_id': code, 'dataset_id': m['dataset']['id'], 'dataset_revision_id': m['dataset_revision']['id'],
                   'axis_id': m['proposed_axis_id'], 'source_snapshot_id': inv['source_snapshot_id'], 'prepared_hashes': hashes,
                   'report_sha256': {n: hashes[n] for n in ('2_integrity.json', '3_metadata_report.json', '4_alignment_report.json', '5_storage_report.json')}}
        ec.write_json(completed, summary); units.append(summary)
        write(MULTI / '32_progress.json', {'status': 'in_progress', 'datasets': units})
    require(len(units) == len(source['datasets']), 'Partial scope prepared; run all three holes before import')
    write(MULTI / '32_prepared.json', {'status': 'passed', 'source_audit_sha256': sha(MULTI / '31_source_audit.json'), 'datasets': units})
    print(f'Prepared {len(units)} independent datasets; original five-hole preparation unchanged.')


if __name__ == '__main__':
    main_guard(main)
