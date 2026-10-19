"""Import eight complete datasets and stage a combined release; validation activates it."""
import shutil
from _multi_db import *


def main():
    require(read(MULTI/'33_media_ready.json')['status']=='passed', 'Media is not reviewed and prepared')
    selected = prepared(); baseline = baseline_backup(); decisions = read(ROOT/'multi_dataset_decisions.json')
    require(decisions['confirmed_by']=='project_owner', 'Unconfirmed succession policy')
    # Migration 006 is additive. Existing scientific rows and old release remain.
    module('multi_schema', ROOT/'8_apply_schema.py').main()
    mc, mi = configure_media()
    for p in (MULTI/'media').glob('33_review_*.png'):
        dest = MULTI_EVIDENCE/'review'/p.name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,dest)
    key,dest,manifest = mi.prepare_package()
    import _ingest as ingest
    results = []; run_id = str(uuid.uuid4())
    with connection('ingest') as conn:
        require(conn.execute('SELECT pg_try_advisory_lock(%s) ok',(LOCK_KEY,)).fetchone()['ok'], 'Another importer or validator is active')
        insert(conn,'ingest_run',{'id':run_id,'input_digest':key,'code_sha256':mi.media_code_hash(),'schema_sha256':schema_hash(),
                                 'holes':Jsonb(list(MULTI_HOLES)),'status':'running'})
        try:
            with conn.transaction():
                for h in selected:
                    u = h['summary']; hole = u['hole_id']
                    print(f"Import complete dataset {u['source_dataset_name']}",flush=True)
                    # Legacy importer consumes one explicit dataset context; its
                    # evidence list is supplied per unit, never by ambiguous hole name.
                    ingest.load_lock = lambda h=h: {'prepared_hashes':{h['summary']['hole_id']:h['summary']['prepared_hashes']}}
                    ingest.import_hole(conn,h)
                    seg = uid('full-source-segment',u['dataset_revision_id'])
                    if not conn.execute('SELECT 1 FROM core.dataset_segment WHERE id=%s',(seg,)).fetchone():
                        insert(conn,'dataset_segment',{'id':seg,'dataset_revision_id':u['dataset_revision_id'],
                            'borehole_id':h['metadata']['borehole']['id'],'branch_id':None,'axis_id':u['axis_id'],
                            'sample_no_from':0,'sample_no_to':u['sample_count']-1,'sequence_no':None,
                            'evidence':{'scope':'complete independent dataset; no 3D clipping','source_dataset_id':u['source_dataset_id']}})
                for u in mc.units():
                    print(f"Import row images and spectra {u['source_dataset_name']}",flush=True)
                    results.append(mi.import_media(conn,u,key,dest,manifest))
                members = [pick(r,'dataset_id','dataset_revision_id') for r in baseline['members']] + [pick(r,'dataset_id','dataset_revision_id') for r in results]
                members.sort(key=lambda x:str(x['dataset_id']))
                require(len({str(r['dataset_id']) for r in members})==len(members), 'Duplicate dataset in combined release')
                release_manifest = {'dataset_revisions':members,'source_release_id':baseline['release_id'],
                    'multi_media_package_sha256':key,'succession_decisions':decisions,'schema_sha256':schema_hash()}
                release = uid('multi-dataset-release',digest(release_manifest))
                if not conn.execute('SELECT 1 FROM core.data_release WHERE id=%s',(release,)).fetchone():
                    insert(conn,'data_release',{'id':release,'manifest_sha256':digest(release_manifest),
                                               'release_kind':'local_multi_dataset_staged','manifest':release_manifest})
                    for r in members: insert(conn,'release_dataset',{'release_id':release,**r})
                groups = install_composites(conn,release,decisions)
            conn.execute("UPDATE core.ingest_run SET status='staged',finished_at=now(),detail=%s WHERE id=%s",(Jsonb({'release_id':release,'datasets':results}),run_id))
        except Exception as exc:
            conn.execute("UPDATE core.ingest_run SET status='failed',finished_at=now(),detail=%s WHERE id=%s",(Jsonb({'error_type':type(exc).__name__,'message':str(exc)}),run_id)); raise
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_KEY,))
    staged = {'status':'staged','release_id':release,'datasets':results,'media_package_sha256':key,
              'package_directory':dest.relative_to(ROOT).as_posix(),'previous_release_id':baseline['release_id'],
              'composites':groups,'source_units':mc.units(),'run_id':run_id}
    mc.save_stage(28,staged); write(MULTI/'34_import.json',staged)
    print(f'Staged {len(members)} datasets in {len(groups)} holes; active release awaits step 35.')


if __name__=='__main__':
    main_guard(main)
