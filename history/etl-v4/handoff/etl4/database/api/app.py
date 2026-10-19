"""Version-scoped read-only API backed by PostgreSQL and local Parquet assets."""
from __future__ import annotations
import io
import math
from functools import lru_cache
from uuid import UUID

import pyarrow.parquet as pq
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from _db_common import *

class CountingFile(io.RawIOBase):
    def __init__(self,path): self.f=open(path,'rb'); self.bytes_read=0; self.read_calls=0
    def readable(self): return True
    def seekable(self): return True
    def read(self,n=-1):
        b=self.f.read(n); self.bytes_read+=len(b); self.read_calls+=1; return b
    def readinto(self,b):
        n=self.f.readinto(b); self.bytes_read+=n; self.read_calls+=1; return n
    def seek(self,*a): return self.f.seek(*a)
    def tell(self): return self.f.tell()
    def close(self):
        if not self.closed: self.f.close()
        super().close()

@lru_cache(maxsize=2048)
def verify_file(path,expected,size,mtime_ns):
    if sha(path)!=expected: raise HTTPException(503,detail={'code':'asset_checksum_mismatch'})
    return True

def local_path(location,asset):
    if location['backend']!='local' or location['root_key']!='etl4': raise HTTPException(503,detail={'code':'storage_backend_unavailable'})
    p=inside(ETL,ETL/location['object_key'])
    if not p.is_file(): raise HTTPException(503,detail={'code':'asset_unavailable'})
    st=p.stat()
    if st.st_size!=asset['byte_size']: raise HTTPException(503,detail={'code':'asset_size_mismatch'})
    verify_file(str(p),asset['sha256'],st.st_size,st.st_mtime_ns)
    return p

def release(conn,release_id=None):
    if release_id is None:
        r=conn.execute('SELECT r.* FROM core.active_release a JOIN core.data_release r ON r.id=a.release_id WHERE a.singleton').fetchone()
        if not r: raise HTTPException(503,detail={'code':'no_published_release'})
    else:
        r=conn.execute('SELECT * FROM core.data_release WHERE id=%s',(str(release_id),)).fetchone()
        if not r: raise HTTPException(404,detail={'code':'release_not_found'})
    return r

def allowed_revision(conn,release_id,revision_id):
    row=conn.execute('SELECT d.* FROM core.dataset_revision d JOIN core.release_dataset r ON r.dataset_revision_id=d.id WHERE r.release_id=%s AND d.id=%s',
                     (release_id,str(revision_id))).fetchone()
    if not row: raise HTTPException(404,detail={'code':'revision_not_in_release'})
    return row

def allowed_log(conn,release_id,log_id):
    row=conn.execute('''SELECT l.*, b.axis_id,b.status AS axis_binding_status,b.basis AS axis_binding_basis,
      i.output_region,i.variant_code,i.source_set_code FROM core.scan_log l
      JOIN core.release_dataset r ON r.dataset_revision_id=l.dataset_revision_id
      JOIN core.log_axis_binding b ON b.log_id=l.id LEFT JOIN core.interpretation_set i ON i.id=l.interpretation_set_id
      WHERE r.release_id=%s AND l.id=%s''',(release_id,str(log_id))).fetchone()
    if not row: raise HTTPException(404,detail={'code':'log_not_in_release'})
    return row

def create_app(dbname=None):
    app=FastAPI(title='ETL4 Core Data API',version='1.0.0')
    def db(): return connection('reader',dbname=dbname)

    @app.get('/health')
    def health():
        with db() as conn:
            row=conn.execute('SELECT current_database() AS database,current_user AS role').fetchone()
        return {'status':'ok',**row}

    @app.get('/v1/boreholes')
    def boreholes(release_id:UUID|None=None,bbox:str|None=None):
        with db() as conn:
            r=release(conn,release_id); params=[r['id']]; extra=''
            if bbox:
                try: x1,y1,x2,y2=map(float,bbox.split(','))
                except (ValueError,TypeError): raise HTTPException(422,detail='bbox requires west,south,east,north')
                if not all(map(math.isfinite,[x1,y1,x2,y2])) or not (-180<=x1<=x2<=180 and -90<=y1<=y2<=90): raise HTTPException(422,detail='invalid bbox')
                extra=' AND br.collar_geom && public.ST_MakeEnvelope(%s,%s,%s,%s,4326)'; params.extend([x1,y1,x2,y2])
            rows=conn.execute('''SELECT DISTINCT b.id,b.source_hole_id,br.source_name,br.provider_code,br.custodian_name,br.operator_name,br.driller_name,
               br.project_name,br.reported_length_m,br.trajectory_status,br.orientation_missing_reason,
               public.ST_AsGeoJSON(br.collar_geom)::jsonb AS collar_geometry
               FROM core.release_dataset rd JOIN core.dataset_revision d ON d.id=rd.dataset_revision_id
               JOIN core.borehole b ON b.id=d.borehole_id JOIN core.borehole_revision br ON br.id=d.borehole_revision_id
               WHERE rd.release_id=%s'''+extra+' ORDER BY b.source_hole_id',params).fetchall()
        return {'release_id':r['id'],'items':rows}

    @app.get('/v1/boreholes/{hole}/datasets')
    def datasets(hole:str,release_id:UUID|None=None):
        with db() as conn:
            r=release(conn,release_id)
            rows=conn.execute('''SELECT d.*,a.id AS axis_id,a.sample_count,a.depth_min_m,a.depth_max_m
               FROM core.dataset_revision d JOIN core.release_dataset rd ON rd.dataset_revision_id=d.id
               JOIN core.borehole b ON b.id=d.borehole_id LEFT JOIN core.sample_axis a ON a.dataset_revision_id=d.id
               WHERE rd.release_id=%s AND b.source_hole_id=%s ORDER BY d.source_dataset_name,d.id''',(r['id'],hole)).fetchall()
            if not rows: raise HTTPException(404,detail='borehole not found in release')
        return {'release_id':r['id'],'items':rows}

    @app.get('/v1/datasets/{revision_id}/logs')
    def logs(revision_id:UUID,release_id:UUID|None=None):
        with db() as conn:
            r=release(conn,release_id); allowed_revision(conn,r['id'],revision_id)
            rows=conn.execute('''SELECT l.*,b.axis_id,b.status AS axis_binding_status,b.basis AS axis_binding_basis,
                 i.output_region,i.variant_code,i.source_set_code,s.region_code AS spectral_region,
                 m.is_probability FROM core.scan_log l JOIN core.log_axis_binding b ON b.log_id=l.id
                 LEFT JOIN core.interpretation_set i ON i.id=l.interpretation_set_id
                 LEFT JOIN core.spectral_stream s ON s.id=l.spectral_stream_id
                 LEFT JOIN core.metric_definition m ON m.dataset_revision_id=l.dataset_revision_id AND m.metric_key=l.metric_key
                 WHERE l.dataset_revision_id=%s ORDER BY l.log_kind,l.source_log_name,l.source_log_id''',(str(revision_id),)).fetchall()
        # Keep raw evidence available, while the explicit binding fields describe the verified association.
        return {'release_id':r['id'],'dataset_revision_id':revision_id,'items':rows}

    @app.get('/v1/datasets/{revision_id}/samples')
    def samples(revision_id:UUID,release_id:UUID|None=None,axis_id:UUID|None=None,from_m:float|None=None,to_m:float|None=None,
                after_sample:int=Query(-1,ge=-1),limit:int=Query(1000,ge=1,le=5000)):
        validate_range(from_m,to_m)
        with db() as conn:
            r=release(conn,release_id); allowed_revision(conn,r['id'],revision_id)
            axes=conn.execute('SELECT id FROM core.sample_axis WHERE dataset_revision_id=%s',(str(revision_id),)).fetchall()
            chosen=choose_axis(axes,axis_id)
            rows=conn.execute('''SELECT s.* FROM core.scan_sample s JOIN core.sample_axis a ON a.id=s.axis_id
                 WHERE a.id=%s AND s.sample_no>%s AND (%s::float8 IS NULL OR s.md_m>=%s)
                 AND (%s::float8 IS NULL OR s.md_m<=%s) ORDER BY s.sample_no LIMIT %s''',
                 (chosen,after_sample,from_m,from_m,to_m,to_m,limit+1)).fetchall()
        return {'release_id':r['id'],'dataset_revision_id':revision_id,'items':rows[:limit],
                'next_after_sample':rows[limit-1]['sample_no'] if len(rows)>limit else None,'coordinate_kind':'measured_depth_m'}

    @app.get('/v1/datasets/{revision_id}/spectral-streams')
    def streams(revision_id:UUID,release_id:UUID|None=None):
        with db() as conn:
            r=release(conn,release_id); allowed_revision(conn,r['id'],revision_id)
            rows=conn.execute('SELECT * FROM core.spectral_stream WHERE dataset_revision_id=%s ORDER BY region_code',(str(revision_id),)).fetchall()
        return {'release_id':r['id'],'items':rows}

    @app.get('/v1/datasets/{revision_id}/interpretation-sets')
    def sets(revision_id:UUID,release_id:UUID|None=None):
        with db() as conn:
            r=release(conn,release_id); allowed_revision(conn,r['id'],revision_id)
            rows=conn.execute('SELECT * FROM core.interpretation_set WHERE dataset_revision_id=%s ORDER BY source_set_code',(str(revision_id),)).fetchall()
            inputs=conn.execute('SELECT * FROM core.interpretation_input WHERE dataset_revision_id=%s',(str(revision_id),)).fetchall()
        return {'release_id':r['id'],'items':rows,'inputs':inputs}

    @app.get('/v1/datasets/{revision_id}/intervals')
    def intervals(revision_id:UUID,release_id:UUID|None=None,axis_id:UUID|None=None,kind:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(200,ge=1,le=1000)):
        if kind not in (None,'tray','section'): raise HTTPException(422,detail='unknown interval kind')
        with db() as conn:
            r=release(conn,release_id); allowed_revision(conn,r['id'],revision_id)
            axes=conn.execute('SELECT id FROM core.sample_axis WHERE dataset_revision_id=%s',(str(revision_id),)).fetchall()
            chosen=choose_axis(axes,axis_id)
            rows=conn.execute('''SELECT i.* FROM core.core_interval i JOIN core.sample_axis a ON a.id=i.axis_id
               WHERE a.id=%s AND (%s::text IS NULL OR i.interval_kind=%s)
               ORDER BY i.interval_kind,i.ordinal OFFSET %s LIMIT %s''',(chosen,kind,kind,offset,limit+1)).fetchall()
        return {'release_id':r['id'],'items':rows[:limit],'next_offset':offset+limit if len(rows)>limit else None,'interval_bounds':'inclusive sample indices'}

    @app.get('/v1/logs/{log_id}/values')
    def values(log_id:UUID,release_id:UUID|None=None,from_m:float|None=None,to_m:float|None=None,
               from_sample:int|None=Query(None,ge=0),to_sample:int|None=Query(None,ge=0),
               after_row:int=Query(-1,ge=-1),limit:int=Query(1000,ge=1,le=5000)):
        validate_range(from_m,to_m)
        if from_sample is not None and to_sample is not None and from_sample>to_sample: raise HTTPException(422,detail='invalid sample range')
        with db() as conn:
            r=release(conn,release_id); log=allowed_log(conn,r['id'],log_id)
            context={'release_id':r['id'],'dataset_revision_id':log['dataset_revision_id'],'log_id':log['id'],
                     'source_log_id':log['source_log_id'],'metric_key':log['metric_key'],'unit':log['unit'],
                     'output_region':log['output_region'],'variant_code':log['variant_code'],'source_set_code':log['source_set_code'],
                     'availability_status':log['availability_status'],'axis_binding_status':log['axis_binding_status']}
            if log['availability_status']!='payload_present':
                return {**context,'status':'metadata_only','reason':log['omission_reason'],'items':[]}
            if log['log_kind']=='spectral':
                return {**context,'status':'unavailable','reason':'sample_wavelength_order_unconfirmed','items':[]}
            if log['log_kind'] not in ('scalar','profile'): raise HTTPException(422,detail='use image endpoints for image logs')
            interval=log['coordinate_kind']=='sample_index_closed_interval'
            if interval and (from_m is not None or to_m is not None): raise HTTPException(422,detail='interval log uses sample indices, not metres')
            if not interval and log['axis_binding_status']!='verified': return {**context,'status':'unavailable','reason':'axis_binding_unverified','items':[]}
            asset=conn.execute('''SELECT a.* FROM core.asset a JOIN core.log_asset la ON la.asset_id=a.id
                WHERE la.log_id=%s AND la.role='canonical' ''',(str(log_id),)).fetchone()
            if not asset: raise HTTPException(503,detail={'code':'canonical_asset_missing'})
            location=conn.execute("SELECT * FROM core.asset_location WHERE asset_id=%s AND backend='local' AND access_status='verified_local'",(asset['id'],)).fetchone()
            if not location: raise HTTPException(503,detail={'code':'asset_location_unavailable'})
            path=local_path(location,asset)
            # Depth filtering for profiles is resolved through the verified sample axis.
            profile_samples=None
            if log['log_kind']=='profile' and (from_m is not None or to_m is not None):
                rows=conn.execute('''SELECT sample_no FROM core.scan_sample WHERE axis_id=%s
                    AND (%s::float8 IS NULL OR md_m>=%s) AND (%s::float8 IS NULL OR md_m<=%s)
                    AND sample_no>%s AND (%s::bigint IS NULL OR sample_no>=%s) AND (%s::bigint IS NULL OR sample_no<=%s)
                    ORDER BY sample_no LIMIT %s''',(log['axis_id'],from_m,from_m,to_m,to_m,after_row,from_sample,from_sample,to_sample,to_sample,limit+1)).fetchall()
                profile_samples={row['sample_no'] for row in rows}
                if not profile_samples: return {**context,'status':'available','items':[],'next_after_row':None}
            groups=conn.execute('SELECT * FROM core.data_chunk WHERE asset_id=%s AND source_row_to_exclusive>%s ORDER BY row_group',
                                (asset['id'],after_row+1)).fetchall()
            result=[]; group_ids=[]
            with CountingFile(path) as counted:
                with pq.ParquetFile(counted) as parquet:
                    for g in groups:
                        if not interval and log['log_kind']=='scalar':
                            if from_m is not None and g['coordinate_max']<from_m: continue
                            if to_m is not None and g['coordinate_min']>to_m: continue
                        if log['log_kind']=='profile':
                            lower=min(profile_samples) if profile_samples else from_sample
                            upper=max(profile_samples) if profile_samples else to_sample
                            if lower is not None and g['coordinate_max']<lower: continue
                            if upper is not None and g['coordinate_min']>upper: continue
                        # Interval coordinate_max indexes interval starts; end overlap is filtered after reading.
                        if interval and to_sample is not None and g['coordinate_min']>to_sample: continue
                        if not interval:
                            if from_sample is not None and g['source_row_to_exclusive']<=from_sample: continue
                            if to_sample is not None and g['source_row_from']>to_sample: continue
                        group_ids.append(g['row_group'])
                        for row in parquet.read_row_group(g['row_group']).to_pylist():
                            idx=row.get('source_row',row.get('sample_no'))
                            if idx<=after_row: continue
                            if interval:
                                if from_sample is not None and row['sample_no_to']<from_sample: continue
                                if to_sample is not None and row['sample_no_from']>to_sample: continue
                            else:
                                if from_sample is not None and row['sample_no']<from_sample: continue
                                if to_sample is not None and row['sample_no']>to_sample: continue
                                if log['log_kind']=='profile':
                                    if profile_samples is not None and row['sample_no'] not in profile_samples: continue
                                else:
                                    if from_m is not None and row['depth_m']<from_m: continue
                                    if to_m is not None and row['depth_m']>to_m: continue
                            result.append(row)
                            if len(result)>limit: break
                        if len(result)>limit: break
                io_info={'payload_bytes_read':counted.bytes_read,'payload_read_calls':counted.read_calls,'row_groups':group_ids,
                         'checksum_validation_bytes_excluded':True,'backend':'local'}
        return {**context,'status':'available','items':result[:limit],
                'next_after_row':result[limit-1].get('source_row',result[limit-1].get('sample_no')) if len(result)>limit else None,
                'coordinate_kind':log['coordinate_kind'] or 'sample_index','physical_geometry_status':log['physical_geometry_status'],'read_stats':io_info}

    @app.get('/v1/datasets/{revision_id}/images')
    def images(revision_id:UUID,release_id:UUID|None=None,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500)):
        with db() as conn:
            r=release(conn,release_id); allowed_revision(conn,r['id'],revision_id)
            rows=conn.execute('SELECT * FROM core.image_frame WHERE dataset_revision_id=%s ORDER BY log_id,image_ordinal OFFSET %s LIMIT %s',
                              (str(revision_id),offset,limit+1)).fetchall()
        for row in rows: row['content_path']=f"/v1/images/{row['id']}/content?release_id={r['id']}"
        return {'release_id':r['id'],'items':rows[:limit],'next_offset':offset+limit if len(rows)>limit else None}

    @app.get('/v1/images/{frame_id}/content')
    def image_content(frame_id:UUID,release_id:UUID|None=None):
        with db() as conn:
            r=release(conn,release_id)
            frame=conn.execute('''SELECT f.* FROM core.image_frame f JOIN core.release_dataset rd ON rd.dataset_revision_id=f.dataset_revision_id
               WHERE f.id=%s AND rd.release_id=%s''',(str(frame_id),r['id'])).fetchone()
            if not frame: raise HTTPException(404,detail='image not in release')
            asset=conn.execute('SELECT * FROM core.asset WHERE id=%s',(frame['asset_id'],)).fetchone()
            loc=conn.execute("SELECT * FROM core.asset_location WHERE asset_id=%s AND backend='local' AND access_status='verified_local'",(asset['id'],)).fetchone()
            if not loc: raise HTTPException(503,detail='image asset unavailable')
            data=local_path(loc,asset).read_bytes()
        return Response(data,media_type=asset['media_type'],headers={'ETag':f'"{asset["sha256"]}"','X-Data-Release':str(r['id'])})

    @app.get('/v1/datasets/{revision_id}/issues')
    def issues(revision_id:UUID,release_id:UUID|None=None):
        with db() as conn:
            r=release(conn,release_id); allowed_revision(conn,r['id'],revision_id)
            rows=conn.execute('SELECT * FROM core.quality_issue WHERE dataset_revision_id=%s ORDER BY processing_step,code,id',(str(revision_id),)).fetchall()
            refs=conn.execute('SELECT * FROM core.source_reference WHERE dataset_revision_id=%s ORDER BY role',(str(revision_id),)).fetchall()
        return {'release_id':r['id'],'items':rows,'source_references':refs}

    return app

def validate_range(lo,hi):
    if any(x is not None and not math.isfinite(x) for x in (lo,hi)): raise HTTPException(422,detail='finite depth required')
    if lo is not None and hi is not None and lo>hi: raise HTTPException(422,detail='from_m exceeds to_m')

def choose_axis(axes,requested):
    if requested is not None:
        if str(requested) not in {str(a['id']) for a in axes}: raise HTTPException(404,detail='axis not in revision')
        return str(requested)
    if len(axes)!=1: raise HTTPException(422,detail='specify axis_id when a revision does not have exactly one axis')
    return axes[0]['id']

app=create_app()
