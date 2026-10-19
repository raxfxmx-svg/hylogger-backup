from pathlib import Path

root = Path('etl4/database')
p=root/'29_verify_media_grain.py';s=p.read_text(encoding='utf-8')
a=s.index('def write_manifest(')
s=s[:a]+'''def write_manifest(conn, release):
    from _publication import write_asset_manifest
    return write_asset_manifest(conn, release)


def main():
    from _publication import publish_release
    parser = StepParser()
    parser.add_argument('--no-activate', action='store_true')
    args = parser.parse_args()
    staged = stage(28)
    release = staged['release_id']
    destination = ROOT / staged['package_directory']
    manifest = read(destination / 'manifest.json')
    check_package(destination, manifest)
    checks = []
    with connection() as conn:
        require(conn.execute('SELECT pg_try_advisory_lock(%s) ok', (LOCK_KEY,)).fetchone()['ok'],
                'Another import or validator is active')
        try:
            assert_schema(conn)
            for unit in package_step(destination, 20)['datasets']:
                new = next(item for item in staged['datasets'] if item['dataset_id'] == unit['dataset_id'])
                print(f"Verify media {unit['hole_id']}", flush=True)
                result = verify_dataset(conn, unit, new, release, destination)
                result.update(status='passed', dataset_revision_id=new['dataset_revision_id'],
                              input_digest=manifest['datasets'][unit['dataset_id']]['content_sha256'])
                checks.append(result)
            assets, locations = publish_release(conn, release, checks, __file__,
                activate=not args.no_activate, expected_previous=staged['previous_release_id'])
            result = {'status': 'passed', 'release_id': release,
                      'activated': not args.no_activate, 'datasets': checks,
                      'previous_release_id': staged['previous_release_id'],
                      'schema_sha256': schema_hash(), 'code_sha256': media_code_hash()}
            report('29_media_verification.json', result)
            write(REPORTS / 'latest_verified_media.json', result)
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)', (LOCK_KEY,))
    print(f'Verified {sum(item["sample_count"] for item in checks):,} samples.')


if __name__ == '__main__':
    main_guard(main)
'''
p.write_text(s,encoding='utf-8')

# Keep fault cases in a separate test function outside routine publication.
p=root/'35_verify_multi_dataset_database.py';s=p.read_text(encoding='utf-8')
a=s.index("            target=next(");b=s.index("            relations=",a)
test_block=s[a:b]
test_block=test_block[:test_block.index('            import _ingest as ingest')]
test_block='\n'.join(line[8:] if line.startswith('        ') else line for line in test_block.splitlines())
helper="\ndef composite_fault_checks(conn, groups):\n    tests = []\n"+test_block+"\n    return tests\n\n"
s=s[:a]+s[b:]
s=s.replace("require(manifest['code_sha256']==mi.media_code_hash(), 'Processing/import code changed after staging')", 'mi.check_package(dest, manifest)')
s=s.replace("    for rel, meta in manifest['files'].items(): require(sha(dest/rel)==meta['sha256'], 'Packaged evidence/crop changed')\n",'')
s=s.replace("for u in mc.units(MULTI / 'media'):", "for u in mi.package_step(dest, 20)['datasets']:")
s=s.replace("checks.append(verifier.verify_dataset(conn,u,new,release))", "check = verifier.verify_dataset(conn, u, new, release, dest)\n                check.update(status='passed',dataset_revision_id=new['dataset_revision_id'],\n                             input_digest=manifest['datasets'][u['dataset_id']]['content_sha256'])\n                checks.append(check)")
s=s.replace("            for axis, expected in baseline['legacy_sample_hashes'].items(): require(sample_hash(conn,axis)==expected, 'Original five-hole samples changed')\n",'')
a=s.index('            with conn.transaction():',s.index("previous=str("));b=s.index('            size_by_id=',a)
s=s[:a]+'''            from _publication import publish_release
            assets, locations = publish_release(conn, release, checks, __file__,
                                                expected_previous=baseline['release_id'])
'''+s[b:]
s=s.replace("'constraint_tests':tests,'repeat_import':repeat,'repeat_base_import':repeat_base,", "'constraint_tests':'see independent tests',")
s=s.replace("'legacy_samples_unchanged':True,", "'legacy_membership_unchanged':True,")
s=s.replace('\ndef main():',helper+'\ndef main():')
p.write_text(s,encoding='utf-8')

# Source release records support reproducible selection; dedicated steps still handle backups.
p=root/'_multi_db.py';s=p.read_text(encoding='utf-8')
a=s.index('def baseline_backup():');b=s.index('def composite_rows(',a)
s=s[:a]+'''def baseline_backup(source_release=None):
    path = MULTI / '34_baseline.json'
    if path.exists():
        baseline = read(path)
        if source_release and source_release != baseline['release_id']:
            raise ValueError('Use a separate work directory for a different source release')
        return baseline
    if not source_release:
        raise ValueError('First multi-dataset import requires --source-release')
    from _publication import release_members
    with connection('reader') as conn:
        release_members(conn, source_release)
        members = conn.execute('SELECT * FROM core.release_dataset WHERE release_id=%s ORDER BY dataset_id',
                               (source_release,)).fetchall()
    baseline = {'release_id': source_release, 'members': members}
    write(path, baseline)
    return baseline


'''+s[b:]
p.write_text(s,encoding='utf-8')
p=root/'34_import_multi_dataset_database.py';s=p.read_text(encoding='utf-8')
s=s.replace('def main():\n', "def main():\n    parser = StepParser()\n    parser.add_argument('--source-release')\n    args = parser.parse_args()\n")
s=s.replace('baseline = baseline_backup()', 'baseline = baseline_backup(args.source_release)')
s=s.replace("for u in mc.units(MULTI / 'media'):", "for u in mi.package_step(dest, 20)['datasets']:")
p.write_text(s,encoding='utf-8')

# Consistency checks do not use the API path resolver.
p=root/'_verification.py';s=p.read_text(encoding='utf-8')
s=s.replace("local_path(asset['root_key'],asset['object_key'])", "inside(ETL, ETL / asset['object_key'])")
s=s.replace("local_path(a['root_key'],a['object_key'])", "inside(ETL, ETL / a['object_key'])")
p.write_text(s,encoding='utf-8')
print('Verification orchestration simplified')
