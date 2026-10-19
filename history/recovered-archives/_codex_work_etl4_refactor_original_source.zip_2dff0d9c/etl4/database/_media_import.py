"""Create additive immutable revisions; reuse original physical asset locations."""
import shutil
from _media_common import *
from _ingest import add_asset

CLONE_TABLES=('sample_axis','core_interval','spectral_stream','interpretation_set','interpretation_input',
 'metric_definition','scan_log','log_axis_binding','asset','asset_location','log_asset','data_chunk',
 'image_frame','source_document','source_reference','quality_issue','dataset_segment')

def remap(value, ids):
    if isinstance(value,uuid.UUID): return ids.get(str(value),str(value))
    if isinstance(value,str): return ids.get(value,value)
    if isinstance(value,list): return [remap(v,ids) for v in value]
    if isinstance(value,dict): return {k:remap(v,ids) for k,v in value.items()}
    return value

def select_revision(conn,table,rev,axis):
    if table=='core_interval': return conn.execute('SELECT * FROM core.core_interval WHERE axis_id=%s ORDER BY (interval_kind=\'section\'),ordinal',(axis,)).fetchall()
    if table=='asset_location': return conn.execute('SELECT l.* FROM core.asset_location l JOIN core.asset a ON a.id=l.asset_id WHERE a.dataset_revision_id=%s',(rev,)).fetchall()
    return conn.execute(sql.SQL('SELECT * FROM core.{} WHERE dataset_revision_id=%s').format(sql.Identifier(table)),(rev,)).fetchall()

def clone_revision(conn,u,newrev,pipeline,input_digest,verified,fail=False):
    old=u['source_revision_id'];axis=u['source_axis_id'];ids={old:newrev}
    previous=conn.execute('SELECT * FROM core.dataset_revision WHERE id=%s',(old,)).fetchone()
    require(previous,'Source revision missing')
    rows={t:select_revision(conn,t,old,axis) for t in CLONE_TABLES}
    for table,records in rows.items():
        for r in records:
            if 'id' in r: ids[str(r['id'])]=uid('media-clone',newrev,table,r['id'])
    axis_new=ids[axis]
    existing=conn.execute('SELECT input_digest FROM core.dataset_revision WHERE id=%s',(newrev,)).fetchone()
    if existing:
        require(existing['input_digest']==input_digest,'Revision identity conflict')
        return ids,False
    r=remap(previous,ids);r.update(pipeline_id=pipeline,input_digest=input_digest,mapping_version=2)
    # v1 happened to reuse the revision UUID for borehole metadata. The collar
    # revision is deliberately shared, not remapped into a nonexistent record.
    r['borehole_revision_id']=previous['borehole_revision_id']
    r['normalized_metadata']={**r['normalized_metadata'],'pipeline_id':pipeline,'derived_from_revision_id':old,
        'media_contract':'sample-media-v1','input_digest':input_digest}
    insert(conn,'dataset_revision',r)
    for table,records in rows.items():
        json_columns={c['column_name'] for c in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='core' AND table_name=%s AND data_type='jsonb'",(table,))}
        for oldrow in records:
            row=remap(oldrow,ids)
            if table=='source_document':
                row['content_json']=Jsonb(oldrow['content_json']) if oldrow['content_json'] is not None else None
                row['content_text']=oldrow['content_text']
            if table=='scan_log' and str(oldrow['id']) in verified:
                row.update(array_layout_status='verified_sample_major',per_sample_publication_allowed=True)
                row['normalized_metadata'].update(array_layout_status='verified_sample_major',per_sample_publication_allowed=True,
                    axis_binding_status='verified',binding_basis=verified[str(oldrow['id'])]['binding_basis'])
            if table=='log_axis_binding' and str(oldrow['log_id']) in verified:
                row.update(axis_id=axis_new,status='verified',basis=verified[str(oldrow['log_id'])]['binding_basis'])
            if table=='asset' and row['logical_path'].endswith('.f32'):
                row['semantic_status']='verified_sample_major_float32'
            if table=='asset':
                row['provenance'].update(reused_from_asset_id=str(oldrow['id']),source_revision_id=old,
                    source_axis_id=axis,physical_file_metadata_preserved=True)
            for col in json_columns:
                if row[col] is not None and not isinstance(row[col],Jsonb): row[col]=Jsonb(row[col])
            insert(conn,table,row)
        if table=='core_interval':
            # All sample values copied by SQL exactly; only the three internal
            # relationship IDs change. Statement-level source checks still run.
            conn.execute('CREATE TEMP TABLE IF NOT EXISTS media_id_map(old_id uuid PRIMARY KEY,new_id uuid NOT NULL) ON COMMIT DROP')
            conn.execute('TRUNCATE pg_temp.media_id_map')
            with conn.cursor().copy('COPY pg_temp.media_id_map(old_id,new_id) FROM STDIN') as copy:
                for a,b in ids.items(): copy.write_row((a,b))
            conn.execute('''INSERT INTO core.scan_sample
              SELECT %s,s.sample_no,s.md_m,t.new_id,c.new_id,s.tray_sample_no,s.section_sample_no,s.section_distance_mm
              FROM core.scan_sample s JOIN pg_temp.media_id_map t ON t.old_id=s.tray_interval_id
              JOIN pg_temp.media_id_map c ON c.old_id=s.section_interval_id WHERE s.axis_id=%s''',(axis_new,axis))
            if fail: raise ValueError('Injected media interruption after sample copy')
    return ids,True

def prepare_package():
    require(stage(22)['status']=='passed' and stage(27)['status']=='passed','Incomplete media preparation')
    files={f'steps/{n}.json':WORK/f'{n}.json' for n in range(20,28)}
    files.update({f'evidence/{p.relative_to(EVIDENCE).as_posix()}':p for p in EVIDENCE.rglob('*') if p.is_file()})
    files.update({f'review/{p.name}':p for p in WORK.glob('25_review_*.png')})
    for r in stage(27)['rows']: files[r['crop_work_path']]=WORK/r['crop_work_path']
    manifest={'contract':'sample-media-v1','source_release_id':stage(20)['source_release_id'],'code_sha256':media_code_hash(),
        'schema_sha256':schema_hash(),'files':{key:{'sha256':sha(p),'byte_size':p.stat().st_size} for key,p in sorted(files.items())}}
    key=digest(manifest);dest=ROOT/'media_releases'/key
    for relative,source in files.items():
        target=inside(dest,dest/relative);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists(): require(sha(target)==manifest['files'][relative]['sha256'],'Published artifact was changed')
        else: shutil.copyfile(source,target)
    write(dest/'manifest.json',manifest)
    return key,dest,manifest

def import_media(conn,u,key,dest,manifest,fail=False):
    rev=uid('media-revision',u['dataset_id'],u['source_snapshot_id'],key)
    spectra=[a for a in stage(22)['arrays'] if a['dataset_id']==u['dataset_id']]
    verified={a['source_log_pk']:a for a in spectra}
    ids,created=clone_revision(conn,u,rev,manifest['code_sha256'],key,verified,fail)
    if not created:return {'dataset_id':u['dataset_id'],'dataset_revision_id':rev,'axis_id':ids[u['source_axis_id']],'action':'already_present'}
    axis=ids[u['source_axis_id']]
    # Evidence files are shared on disk, but each asset registration belongs to
    # its own revision. Source bytes and old asset locations remain reusable.
    evidence={}
    for relative,meta in manifest['files'].items():
        if relative.startswith('crops/'): continue
        evidence[relative]=add_asset(conn,rev,'evidence','media/'+relative,'media_evidence',meta['byte_size'],meta['sha256'],
            (dest/relative).relative_to(ETL).as_posix(),'processing_evidence',{'media_package_sha256':key})
    for a in spectra:
        oldasset=conn.execute("SELECT id FROM core.asset WHERE dataset_revision_id=%s AND representation='raw' AND logical_path=%s",(u['source_revision_id'],a['file'])).fetchone()['id']
        array=uid('spectral-array',rev,a['log_id']);asset=ids[str(oldasset)];log=ids[a['source_log_pk']]
        insert(conn,'spectral_array',{'id':array,'dataset_revision_id':rev,'log_id':log,'asset_id':asset,
            'spectral_stream_id':ids[a['spectral_stream_id']],'sample_count':a['sample_count'],'channel_count':a['band_count'],
            **pick(a,'dtype_code','matrix_order','data_offset_bytes','sample_stride_bytes','channel_stride_bytes','layout_status','value_unit','scaling_applied'),
            'evidence_asset_id':evidence['steps/21.json'],'evidence':{'binding_basis':a['binding_basis'],'references':a['references'],
                'official_commit':a['contract_commit'],'verification_scope':a['verification_scope']}})
        sm=a['sample_map']
        insert(conn,'spectral_sample_map',{'id':uid('spectral-map',array,0),'dataset_revision_id':rev,'spectral_array_id':array,
            'axis_id':axis,**pick(sm,'source_row_from','source_row_to','sample_no_from','sample_no_to'),
            'mapping_kind':'identity_range','binding_status':'verified','evidence_asset_id':evidence['steps/21.json'],'basis':a['binding_basis']})
        for block in a['blocks']: insert(conn,'spectral_block',{'spectral_array_id':array,**block})
    for r in [r for r in stage(27)['rows'] if r['dataset_id']==u['dataset_id']]:
        region=uid('image-region',rev,r['source_log_id'],r['source_frame_id'],r['region_ordinal'])
        log=ids[conn.execute('SELECT id FROM core.scan_log WHERE dataset_revision_id=%s AND source_log_id=%s AND log_kind=%s',
                            (u['source_revision_id'],r['source_log_id'],'image')).fetchone()['id'].__str__()]
        insert(conn,'image_region',{'id':region,'dataset_revision_id':rev,'image_frame_id':ids[r['source_frame_id']],
            'region_kind':'core_row',**pick(r,'region_ordinal','x_px','y_px','width_px','height_px','coordinate_basis','region_status','detection_method','review_basis'),
            'valid_area':None,'evidence_asset_id':evidence['steps/25.json']})
        insert(conn,'image_sample_mapping',{'id':uid('image-map',region,0),'dataset_revision_id':rev,'image_region_id':region,
            'axis_id':axis,'section_interval_id':ids[r['source_section_id']],
            **pick(r,'sample_no_from','sample_no_to','anchor_points','source_depth_direction','direction_status','direction_basis',
                'mapping_level','mapping_status','mapping_method','indicator_method','indicator_version','indicator_status','indicator_parameters','error_px','error_depth_m'),
            'direction_evidence_asset_id':evidence['steps/26.json'],'evidence_asset_id':evidence['steps/26.json']})
        rel=r['crop_work_path'];meta=manifest['files'][rel]
        asset=add_asset(conn,rev,'canonical',rel,'core_row_image',meta['byte_size'],meta['sha256'],(dest/rel).relative_to(ETL).as_posix(),
            'lossless_source_crop',{'region_id':region,'source_frame_id':ids[r['source_frame_id']],'recipe':r['recipe'],'pixel_sha256':r['pixel_sha256']})
        insert(conn,'log_asset',{'log_id':log,'asset_id':asset,'dataset_revision_id':rev,'role':'derived_core_row'})
        insert(conn,'image_region_asset',{'region_id':region,'dataset_revision_id':rev,'asset_id':asset,'log_id':log,
            'representation_kind':'native_lossless_png','width_px':r['width_px'],'height_px':r['height_px'],'transform':r['recipe'],'recipe_version':1})
    return {'dataset_id':u['dataset_id'],'dataset_revision_id':rev,'axis_id':axis,'action':'inserted'}
