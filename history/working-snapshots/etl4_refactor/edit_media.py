from pathlib import Path

root = Path('etl4/database')
p = root / '_media_import.py'
text = p.read_text(encoding='utf-8')
a = text.index('def prepare_package():'); b = text.index('def import_media(', a)
text = text[:a] + """MEDIA_RULE_VERSION = 'sample-media-v2'


def media_identity(unit, arrays, rows):
    \"\"\"Derive identity only from dataset inputs and rules; store the actual output digest separately.\"\"\"
    identity = digest({'dataset_id': unit['dataset_id'],
                       'source_revision_id': unit['source_revision_id'],
                       'source_snapshot_id': unit['source_snapshot_id'],
                       'rules': MEDIA_RULE_VERSION})
    spectra = [pick(a, 'log_id', 'sha256', 'shape', 'dtype_code', 'matrix_order',
                    'sample_map', 'blocks', 'value_unit', 'scaling_applied') for a in arrays]
    crops = [pick(r, 'source_log_id', 'source_frame_id', 'source_section_id', 'region_ordinal',
                  'source_sha256', 'x_px', 'y_px', 'width_px', 'height_px', 'crop_sha256',
                  'pixel_sha256', 'recipe', 'sample_no_from', 'sample_no_to',
                  'region_status', 'indicator_method', 'indicator_version', 'indicator_parameters',
                  'source_depth_direction', 'direction_status') for r in rows]
    return {'input_key': identity, 'content_sha256': digest({
        'arrays': sorted(spectra, key=lambda a: a['log_id']),
        'rows': sorted(crops, key=lambda r: (r['source_log_id'], r['source_frame_id'], r['region_ordinal']))})}


def package_step(destination, number):
    return read(destination / 'steps' / f'{number}.json')


def check_package(destination, manifest):
    for relative, item in manifest['files'].items():
        path = inside(destination, destination / relative)
        require(path.is_file() and path.stat().st_size == item['byte_size']
                and sha(path) == item['sha256'], f'Packaged file differs: {relative}')


def prepare_package(work=WORK, evidence_dir=EVIDENCE):
    require(stage(22, work)['status'] == 'passed' and stage(27, work)['status'] == 'passed',
            'Incomplete media preparation')
    payloads = {}
    steps = {n: stage(n, work) for n in range(20, 28)}
    # Sealed references point to evidence inside the package without relying on temporary preparation directories.
    for number, field in ((21, 'spectra'), (22, 'arrays')):
        for array in steps[number][field]:
            for proof in array.get('references', []):
                original = inside(ROOT, ROOT / proof['path'])
                relative = original.relative_to(evidence_dir).as_posix()
                proof['path'] = 'evidence/' + relative
    for number, value in steps.items():
        payloads[f'steps/{number}.json'] = encoded(value)
    files = {f'evidence/{p.relative_to(evidence_dir).as_posix()}': p
             for p in evidence_dir.rglob('*') if p.is_file()}
    for path in work.glob('*_review_*.png'):
        files['review/' + path.name] = path
    for row in steps[27]['rows']:
        files[row['crop_work_path']] = inside(work, work / row['crop_work_path'])
    inventory = {name: {'sha256': hashlib.sha256(data).hexdigest(), 'byte_size': len(data)}
                 for name, data in payloads.items()}
    inventory.update({name: {'sha256': sha(path), 'byte_size': path.stat().st_size}
                      for name, path in sorted(files.items())})
    datasets = {}
    for unit in steps[20]['datasets']:
        dataset = unit['dataset_id']
        arrays = [a for a in steps[22]['arrays'] if a['dataset_id'] == dataset]
        rows = [r for r in steps[27]['rows'] if r['dataset_id'] == dataset]
        datasets[dataset] = media_identity(unit, arrays, rows)
    manifest = {'contract': MEDIA_RULE_VERSION, 'datasets': datasets,
                'source_release_id': steps[20]['source_release_id'], 'files': inventory}
    key = digest(manifest)
    destination = ROOT / 'media_releases' / key
    for relative, data in payloads.items():
        target = inside(destination, destination / relative)
        if target.exists():
            require(sha(target) == inventory[relative]['sha256'], 'Packaged evidence was changed')
        else:
            write(target, data.decode('utf-8'))
    for relative, source in files.items():
        target = inside(destination, destination / relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            require(sha(target) == inventory[relative]['sha256'], 'Packaged artifact was changed')
        else:
            shutil.copyfile(source, target)
    write(destination / 'manifest.json', manifest)
    check_package(destination, manifest)
    report('media_package_run.json', {'package': key, 'code_sha256': media_code_hash(),
                                    'datasets': datasets, 'status': 'passed'})
    return key, destination, manifest


""" + text[b:]
text = text.replace("rev=uid('media-revision',u['dataset_id'],u['source_snapshot_id'],key)",
                    "identity = manifest['datasets'][u['dataset_id']]\n    rev = uid('media-revision-v2', u['dataset_id'], identity['input_key'])")
text = text.replace("stage(22)['arrays']", "package_step(dest, 22)['arrays']")
text = text.replace("stage(27)['rows']", "package_step(dest, 27)['rows']")
text = text.replace("clone_revision(conn,u,rev,manifest['code_sha256'],key,verified,fail)",
                    "clone_revision(conn,u,rev,MEDIA_RULE_VERSION,identity['content_sha256'],verified,fail)")
p.write_text(text,encoding='utf-8')

# Validate each dataset from its selected package and compare actual database crop associations.
p=root/'29_verify_media_grain.py';text=p.read_text(encoding='utf-8')
text=text.replace('from _media_import import import_media', 'from _media_import import import_media, package_step, check_package')
text=text.replace('def verify_dataset(conn,u,new,release):', 'def verify_dataset(conn,u,new,release,dest):')
text=text.replace("stage(27)['rows']", "package_step(dest, 27)['rows']")
text=text.replace("stage(22)['arrays']", "package_step(dest, 22)['arrays']")
text=text.replace("crop_path=ROOT/stage(28)['package_directory']/r['crop_work_path'];actual=decode(crop_path)", '''linked = conn.execute("""SELECT a.sha256, loc.object_key, a.provenance, reg.id
          FROM core.image_region reg JOIN core.image_region_asset link ON link.region_id=reg.id
          JOIN core.asset a ON a.id=link.asset_id JOIN core.asset_location loc ON loc.asset_id=a.id
          JOIN core.image_frame frame ON frame.id=reg.image_frame_id
          JOIN core.scan_log log ON log.id=frame.log_id
          WHERE reg.dataset_revision_id=%s AND frame.image_ordinal=%s
          AND log.source_log_id=%s AND reg.region_ordinal=%s AND loc.backend='local'""",
          (rev, r['image_ordinal'], r['source_log_id'], r['region_ordinal'])).fetchall()
        require(len(linked) == 1, 'Image region must have exactly one native crop')
        asset = linked[0]
        require(asset['sha256'] == r['crop_sha256'] and asset['provenance']['recipe'] == r['recipe'],
                'Crop source or recipe differs')
        crop_path = inside(ETL, ETL / asset['object_key'])
        actual = decode(crop_path)''')
text=text.replace("read(ROOT/ref['path'])", "read(inside(dest, dest / ref['path']))")
p.write_text(text,encoding='utf-8')
print('Sealed package and dataset identities installed')
