"""Verify source preservation, multi-dataset selection and media; then activate locally."""
import psycopg
from _multi_db import *
from _multi_reader import read_borehole_layout


def must_reject(conn, name, query, params):
    try:
        with conn.transaction():
            conn.execute(query,params)
            raise RuntimeError('Unsafe composite mutation was accepted: '+name)
    except psycopg.Error as exc:
        require(exc.sqlstate in ('23503','23505','23514','P0001'), 'Unexpected test failure: '+name)
        return {'case':name,'status':'rejected','sqlstate':exc.sqlstate}


def main():
    staged = read(MULTI/'34_import.json'); baseline = read(MULTI/'34_baseline.json')
    mc, mi = configure_media(); verifier = module('multi_media_verifier',ROOT/'29_verify_media_grain.py')
    release = staged['release_id']; dest = ROOT/staged['package_directory']; manifest = read(dest/'manifest.json')
    require(manifest['code_sha256']==mi.media_code_hash(), 'Processing/import code changed after staging')
    for rel, meta in manifest['files'].items(): require(sha(dest/rel)==meta['sha256'], 'Packaged evidence/crop changed')
    checks = []; tests = []; layouts = []
    with connection() as conn:
        require(conn.execute('SELECT pg_try_advisory_lock(%s) ok',(LOCK_KEY,)).fetchone()['ok'], 'Another import/validation is active')
        try:
            assert_schema(conn)
            # Newly populated axes need current planner statistics before full comparisons.
            for table in ('scan_sample','core_interval','image_sample_mapping','borehole_composite_part'):
                conn.execute(sql.SQL('ANALYZE core.{}').format(sql.Identifier(table)))
            for u in mc.units():
                print('Verify '+u['source_dataset_name'],flush=True)
                new = next(d for d in staged['datasets'] if d['dataset_id']==u['dataset_id'])
                checks.append(verifier.verify_dataset(conn,u,new,release))
                expected = set().union(*next(x['log_ids'].values() for x in audit()['datasets'] if x['source_dataset_id']==u['source_dataset_id']))
                actual = {r['source_log_id'] for r in conn.execute('SELECT source_log_id FROM core.scan_log WHERE dataset_revision_id=%s',(new['dataset_revision_id'],))}
                require(actual==expected, 'Dataset source log membership changed')
            for axis, expected in baseline['legacy_sample_hashes'].items(): require(sample_hash(conn,axis)==expected, 'Original five-hole samples changed')
            old = conn.execute('SELECT * FROM core.release_dataset WHERE release_id=%s ORDER BY dataset_id',(baseline['release_id'],)).fetchall()
            require(json.loads(encoded(old))==baseline['members'], 'Original release membership changed')
            decisions = read(ROOT/'multi_dataset_decisions.json')
            groups = install_composites(conn,release,decisions)
            for group in groups:
                layout = read_borehole_layout(conn,release,group['hole_id']); layouts.append(layout)
                full = layout['datasets_2d_full']; chosen = layout['parts_3d_selected']
                require(len(full)==len(group['datasets']), '2D dropped a source dataset')
                for d in full:
                    n=conn.execute('SELECT count(*) n FROM core.scan_sample WHERE axis_id=%s',(d['axis_id'],)).fetchone()['n']
                    require(n==d['sample_count'], '2D source samples truncated')
                for i,p in enumerate(chosen):
                    expected_n=(p['sample_no_to']-p['sample_no_from']+1) if p['sample_no_from'] is not None else 0
                    require(expected_n==p['selected_sample_count'], '3D sample range/count mismatch')
                    if i:
                        boundary=p['selection_from_md_m']
                        at=conn.execute('SELECT DISTINCT dataset_id FROM core.v_borehole_composite_samples WHERE composite_id=%s AND md_m=%s',(p['composite_id'],boundary)).fetchall()
                        require(at and all(r['dataset_id']==p['dataset_id'] for r in at), 'Boundary not assigned exclusively to successor')
                expected_total=sum(p['selected_sample_count'] for p in chosen)
                real=conn.execute('SELECT count(*) n FROM core.v_borehole_composite_samples WHERE composite_id=%s',(group['composite']['id'],)).fetchone()['n']
                require(real==expected_total, 'Composite view changed sample multiplicity')
            target=next(g for g in groups if g['hole_id']=='14KDD001'); part=target['parts'][0]
            tests.append(must_reject(conn,'wrong source sample index',
                'UPDATE core.borehole_composite_part SET sample_no_to=sample_no_to-1 WHERE composite_id=%s AND sequence_no=0',(part['composite_id'],)))
            tests.append(must_reject(conn,'overlap reintroduced into 3D',
                'UPDATE core.borehole_composite_part SET selection_to_md_m=%s,upper_inclusive=true,sample_no_to=%s WHERE composite_id=%s AND sequence_no=0',
                (target['datasets'][0]['depth_max_m'],target['datasets'][0]['sample_count']-1,part['composite_id'])))
            other=next(g for g in groups if g['hole_id']=='12CADD001')['parts'][0]
            tests.append(must_reject(conn,'cross-hole dataset assignment',
                'UPDATE core.borehole_composite_part SET dataset_id=%s,dataset_revision_id=%s WHERE composite_id=%s AND sequence_no=0',
                (other['dataset_id'],other['dataset_revision_id'],part['composite_id'])))
            three=next(g for g in groups if g['hole_id']=='15EIS001')['parts']
            tests.append(must_reject(conn,'wrong succession evidence',
                'UPDATE core.borehole_composite_part SET predecessor_relation_id=%s WHERE composite_id=%s AND sequence_no=3',
                (three[1]['predecessor_relation_id'],three[3]['composite_id'])))
            tests.append(must_reject(conn,'missing succession evidence',
                'UPDATE core.borehole_composite_part SET predecessor_relation_id=NULL WHERE composite_id=%s AND sequence_no=1',
                (three[1]['composite_id'],)))
            import _ingest as ingest
            repeat_base=[ingest.import_hole(conn,h)['action'] for h in prepared()]
            require(set(repeat_base)=={'already_present'}, 'Repeated source import creates new records')
            repeat=[mi.import_media(conn,u,staged['media_package_sha256'],dest,manifest)['action'] for u in mc.units()]
            require(set(repeat)=={'already_present'}, 'Repeated media import creates new records')
            relations={name:conn.execute(query).fetchone()['n'] for name,query in module('multi_relations',ROOT/'13_audit_database.py').RELATION_CHECKS.items()}
            require(not any(relations.values()), 'Source relationship verification failed')
            previous=str(conn.execute('SELECT release_id FROM core.active_release WHERE singleton').fetchone()['release_id'])
            require(previous in (baseline['release_id'],release), 'Another release was activated; do not overwrite it')
            with conn.transaction():
                for d in staged['datasets']:
                    conn.execute('''INSERT INTO core.revision_validation(dataset_revision_id,input_digest,verification_code_sha256,result)
                      VALUES(%s,%s,%s,%s) ON CONFLICT(dataset_revision_id) DO UPDATE SET validated_at=now(),
                      verification_code_sha256=EXCLUDED.verification_code_sha256,result=EXCLUDED.result''',
                      (d['dataset_revision_id'],staged['media_package_sha256'],sha(Path(__file__)),Jsonb({'status':'passed','scope':'multi-dataset-source-and-media-v1'})))
                conn.execute('UPDATE core.active_release SET release_id=%s,switched_at=now() WHERE singleton',(release,))
            assets,locations=verifier.write_manifest(conn,release)
            size_by_id={a['id']:a['byte_size'] for a in assets}; physical={l['object_key']:size_by_id[l['asset_id']] for l in locations if l['backend']=='local'}
            counts=conn.execute('''SELECT (SELECT count(*) FROM core.borehole) holes,
               (SELECT count(*) FROM core.release_dataset WHERE release_id=%s) datasets,
               (SELECT sum(a.sample_count) FROM core.sample_axis a JOIN core.release_dataset d ON d.dataset_revision_id=a.dataset_revision_id WHERE d.release_id=%s) full_samples,
               (SELECT count(*) FROM core.v_borehole_composite_samples WHERE release_id=%s) overview_samples,
               (SELECT count(*) FROM core.image_region r JOIN core.release_dataset d ON d.dataset_revision_id=r.dataset_revision_id WHERE d.release_id=%s) image_rows,
               (SELECT count(*) FROM core.spectral_array a JOIN core.release_dataset d ON d.dataset_revision_id=a.dataset_revision_id WHERE d.release_id=%s) spectral_arrays''',(release,)*5).fetchone()
            from _schema_docs import generate
            generate(conn)
            result={'status':'passed','release_id':release,'previous_release_id':baseline['release_id'],'activated':True,
                    'counts':counts,'new_dataset_checks':checks,'constraint_tests':tests,'repeat_import':repeat,'repeat_base_import':repeat_base,
                    'legacy_samples_unchanged':True,'relation_violations':relations,'layouts':layouts,
                    'database_bytes_with_history':conn.execute('SELECT pg_database_size(current_database()) n').fetchone()['n'],
                    'unique_file_count':len(physical),'unique_file_bytes':sum(physical.values()),
                    'schema_sha256':schema_hash(),'cloud_operations':False,'api_operations':False}
            write(MULTI/'35_verification.json',result); report('35_multi_dataset_verification.json',result)
        finally: conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_KEY,))
    print(f"Verified and activated {counts['holes']} holes / {counts['datasets']} datasets / {counts['full_samples']:,} full samples.")


if __name__=='__main__':
    main_guard(main)
