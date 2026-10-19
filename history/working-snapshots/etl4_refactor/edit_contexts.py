from pathlib import Path
import re

root = Path('etl4')

def edit(file, old, new):
    p = root / file
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise ValueError((file, old[:80]))
    p.write_text(text.replace(old, new), encoding='utf-8')

p = root / 'database/32_prepare_multi_dataset_payloads.py'
text = p.read_text(encoding='utf-8')
text = text.replace('from contextlib import contextmanager\n', '')
text = text.replace("'mtime_ns': stat.st_mtime_ns,", '')
text = text.replace("PROCESSING / 'outputs' / 'multidataset'", "PREPARED / 'multidataset'")
text = text[:text.index('@contextmanager')] + """def prepare_unit(unit, source, ec):
    hole = unit['hole_id']
    raw = raw_metadata(hole)
    for name, checksum in source['raw_metadata_sha256'][hole].items():
        require(sha(ETL / hole / name) == checksum, 'Raw metadata changed since step 31')
    for proof in unit['membership_evidence'].values():
        if 'path' in proof:
            require(sha(ROOT / proof['path']) == proof['sha256'], 'Membership evidence changed')
    projected = selected_metadata(raw, unit)
    code = ec.pipeline_id({'image_depth_policy': 'decimal_1e-5_or_same_float32'})
    folder, inv = inventory(hole, projected, unit, code)
    completed = folder / '32_unit.json'
    if completed.exists():
        cached = read(completed)
        require(all(sha(folder / rel) == checksum for rel, checksum in cached['prepared_hashes'].items()), 'Cached prepared bytes changed')
        for item in inv['files']:
            require(sha(ETL / hole / item['path']) == item['expected_sha256'], 'Source content changed')
        print(f"Reuse verified dataset {unit['source_dataset_name']}", flush=True)
        return cached
    baseline = {**unit, 'scalar_log_count': len(projected['scalar_manifest.json']),
                'spectral_array_count': sum(bool(x.get('file')) for x in projected['spectral_manifest.json'])}
    context = ec.DatasetContext(hole, folder, inv, projected, baseline)
    print(f"Prepare {hole}/{unit['source_dataset_name']}", flush=True)
    ec.write_json(folder / '1_inventory.json', inv)
    module('multi_validate', PROCESSING / '2_validate_payloads.py').validate_hole(hole, context=context)
    module('multi_normalize', PROCESSING / '3_normalize_metadata.py').normalize_hole(hole, context=context)
    module('multi_align', PROCESSING / '4_align_samples.py').align_hole(
        hole, image_depth_policy='decimal_1e-5_or_same_float32', context=context)
    # Parse only the selected dataset while retaining all raw evidence.
    metadata = read(folder / '3_normalized_metadata.json')
    metadata['raw_metadata'] = raw
    metadata['selected_dataset_context'] = {
        'source_dataset_id': unit['source_dataset_id'], 'log_ids': unit['log_ids'],
        'membership_evidence': unit['membership_evidence']}
    metadata['borehole']['orientation_missing_reason'] = 'downhole_survey_not_provided'
    metadata['borehole']['orientation_missing_reason_source'] = 'source_package_inspection; dataset XML orientation retained separately'
    ec.write_json(folder / '3_normalized_metadata.json', metadata)
    report3 = read(folder / '3_metadata_report.json')
    report3['normalized_metadata_sha256'] = sha(folder / '3_normalized_metadata.json')
    ec.write_json(folder / '3_metadata_report.json', report3)
    module('multi_columnar', PROCESSING / '5_build_columnar.py').build_hole(hole, context=context)
    hashes = {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob('*'))
              if p.is_file() and p.name != '32_unit.json'}
    summary = {**unit, 'status': 'passed', 'prepared_directory': folder.relative_to(ETL).as_posix(),
               'pipeline_id': code, 'dataset_id': metadata['dataset']['id'],
               'dataset_revision_id': metadata['dataset_revision']['id'],
               'axis_id': metadata['proposed_axis_id'], 'source_snapshot_id': inv['source_snapshot_id'],
               'prepared_hashes': hashes,
               'report_sha256': {n: hashes[n] for n in (
                   '2_integrity.json', '3_metadata_report.json', '4_alignment_report.json', '5_storage_report.json')}}
    ec.write_json(completed, summary)
    return summary


def main():
    parser = StepParser()
    parser.add_argument('--holes', nargs='+', choices=MULTI_HOLES, default=list(MULTI_HOLES))
    args = parser.parse_args()
    source = audit()
    sys.path.insert(0, str(PROCESSING))
    import _etl_common as ec
    units = []
    for unit in source['datasets']:
        if unit['hole_id'] in args.holes:
            units.append(prepare_unit(unit, source, ec))
            write(MULTI / '32_progress.json', {'status': 'in_progress', 'datasets': units})
    require(units, 'No selected datasets')
    write(MULTI / '32_prepared.json', {
        'status': 'passed', 'source_audit_sha256': sha(MULTI / '31_source_audit.json'), 'datasets': units})
    print(f'Prepared {len(units)} independent datasets.')


if __name__ == '__main__':
    main_guard(main)
"""
p.write_text(text, encoding='utf-8')

edit('database/_media_common.py', 'def stage(number): return read(WORK/', 'def stage(number, work=WORK): return read(work/')
edit('database/_media_common.py', 'def save_stage(number, value):\n    write(WORK/', 'def save_stage(number, value, work=WORK):\n    write(work/')
edit('database/_media_common.py', "def units(): return stage(20)['datasets']", "def units(work=WORK): return stage(20, work)['datasets']")
edit('database/21_verify_spectral_bindings.py', 'def verify_one(a, fetch):', 'def verify_one(a, fetch, evidence_dir=EVIDENCE):')
edit('database/21_verify_spectral_bindings.py', "p=EVIDENCE/'spectra'", "p=evidence_dir/'spectra'")
edit('database/21_verify_spectral_bindings.py', "require(n==a['sample_count'] and n==next(u['sample_count'] for u in units() if u['dataset_id']==a['dataset_id']), 'Axis length mismatch')", "require(n == read(source_folder(u) / '4_alignment_report.json')['sample_count'], 'Axis length mismatch')")
for name in ('22_prepare_spectral_access.py', '27_build_image_row_assets.py'):
    p = root / 'database' / name
    text = p.read_text(encoding='utf-8').replace('def main():', 'def main(work=WORK):')
    text = re.sub(r'stage\((\d+)\)', r'stage(\1, work)', text)
    text = text.replace('inside(WORK,WORK/rel)', 'inside(work,work/rel)')
    # Add keyword arguments only to the outer save_stage call.
    text = text.replace("'array_bytes_duplicated':0})", "'array_bytes_duplicated':0}, work=work)")
    text = text.replace("'lossless_decoded_pixel_equality':True})", "'lossless_decoded_pixel_equality':True}, work=work)")
    p.write_text(text, encoding='utf-8')

p = root / 'database/33_prepare_multi_dataset_media.py'
text = p.read_text(encoding='utf-8')
a = text.index('def media_context():'); b = text.index('def main():',a)
text = text[:a] + text[b:]
text = text.replace('    mc = media_context(); datasets = []; spectra = []', '    import _media_common as mc\n    datasets = []; spectra = []')
text = text.replace("(ROOT / 'media_evidence' / 'official')", "(CODE / 'media_evidence' / 'official')")
text = text.replace('verifier.verify_one(a, args.fetch_reference)', 'verifier.verify_one(a, args.fetch_reference, MULTI_EVIDENCE)')
text = text.replace("'22_prepare_spectral_access.py').main()", "'22_prepare_spectral_access.py').main(work=MEDIA)")
text = text.replace("'27_build_image_row_assets.py').main()", "'27_build_image_row_assets.py').main(work=MEDIA)")
text = re.sub(r'mc.stage\((\d+)\)', r'mc.stage(\1, MEDIA)', text)
# Locate call endings with AST to avoid changing parentheses inside multiline dictionaries.
import ast
tree = ast.parse(text)
lines = text.splitlines(keepends=True); offsets=[];pos=0
for line in lines: offsets.append(pos);pos+=len(line)
insertions=[]
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr=='save_stage':
        # Call indentation and syntax are ASCII; inline Chinese text does not precede the closing parenthesis.
        end=offsets[node.end_lineno-1]+len(lines[node.end_lineno-1].encode('utf-8')[:node.end_col_offset].decode('utf-8'))-1
        insertions.append(end)
for pos in sorted(insertions,reverse=True): text=text[:pos]+', work=MEDIA'+text[pos:]
p.write_text(text,encoding='utf-8')

# Remove configuration functions that mutate module globals.
p=root/'database/_multi_db.py';text=p.read_text(encoding='utf-8')
a=text.index('def configure_media():');b=text.index('def sample_hash(',a)
text=text[:a]+text[b:];p.write_text(text,encoding='utf-8')
for name in ('34_import_multi_dataset_database.py','35_verify_multi_dataset_database.py'):
    p=root/'database'/name;text=p.read_text(encoding='utf-8')
    text=text.replace('mc, mi = configure_media()', 'import _media_common as mc\n    import _media_import as mi')
    text=text.replace("ingest.load_lock = lambda h=h: {'prepared_hashes':{h['summary']['hole_id']:h['summary']['prepared_hashes']}}", '')
    text=text.replace('mi.prepare_package()', "mi.prepare_package(work=MULTI / 'media', evidence_dir=MULTI_EVIDENCE)")
    text=text.replace('mc.units()', "mc.units(MULTI / 'media')")
    text=text.replace('mc.save_stage(28,staged)', "mc.save_stage(28,staged,work=MULTI / 'media')")
    p.write_text(text,encoding='utf-8')

print('Explicit contexts installed')
