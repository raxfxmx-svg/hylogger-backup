"""Compare the uploaded revision with the published revision using SELECT only."""
import gzip,hashlib,json,ssl,zipfile
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import boto3,psycopg
from psycopg.rows import dict_row
from psycopg import sql
root=Path.home()/'audit_12DHDD0002_20261011'
audit=json.loads((root/'audit_report.json').read_text())
export=root/'export'
def rows(name):
    with gzip.open(export/'tables'/(name+'.jsonl.gz'),'rt') as f:return [json.loads(x) for x in f]
def plain(x):return json.loads(json.dumps(x,default=str))
new=rows('dataset_revision')[0]
session=boto3.Session(region_name='ap-southeast-2')
host='db.example.com'
token=session.client('rds').generate_db_auth_token(DBHostname=host,Port=5432,DBUsername='postgres')
report={'checked_at':datetime.now(timezone.utc).isoformat(),'batch_id':audit['batch_id'],'read_only':True,'incoming_revision':new}
with psycopg.connect(host=host,dbname='etl4_core',user='postgres',password=token,sslmode='verify-full',sslrootcert=ssl.get_default_verify_paths().cafile,autocommit=True,row_factory=dict_row,connect_timeout=60,options='-c default_transaction_read_only=on -c statement_timeout=60000') as conn:
    with conn.transaction():
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        old=plain(conn.execute('SELECT r.* FROM core.active_release a JOIN core.release_dataset rd ON rd.release_id=a.release_id JOIN core.dataset_revision r ON r.id=rd.dataset_revision_id WHERE rd.dataset_id=%s',(new['dataset_id'],)).fetchone())
        report['active_release']=plain(conn.execute('SELECT * FROM core.active_release WHERE singleton').fetchone())
        report['published_revision']=old
        if not old:raise ValueError('Existing dataset is not active; review separately')
        oldid=old['id']
        report['revision_field_changes']={k:{'published':old.get(k),'incoming':v} for k,v in new.items() if k!='normalized_metadata' and old.get(k)!=v}
        oldf=old['normalized_metadata'].get('final_identity',{});newf=new['normalized_metadata'].get('final_identity',{})
        report['processing_identity_changes']={k:{'published':oldf.get(k),'incoming':v} for k,v in newf.items() if k!='raw_files' and oldf.get(k)!=v}
        oraw={x[0]:x[1:] for x in oldf.get('raw_files',[])};nraw={x[0]:x[1:] for x in newf.get('raw_files',[])}
        report['raw_file_comparison']={'published_count':len(oraw),'incoming_count':len(nraw),'unchanged':sum(oraw.get(k)==v for k,v in nraw.items()),'added':[k for k in nraw if k not in oraw],'removed':[k for k in oraw if k not in nraw],'changed':[{'path':k,'published':oraw[k],'incoming':v} for k,v in nraw.items() if k in oraw and oraw[k]!=v]}
        oldassets=plain(conn.execute('SELECT * FROM core.asset WHERE dataset_revision_id=%s',(oldid,)).fetchall());newassets=rows('asset')
        report['published_assets']=oldassets
        amap=lambda a:{(r['asset_kind'],r['representation'],r['logical_path']):(r['sha256'],r['byte_size']) for r in a}
        oa,na=amap(oldassets),amap(newassets)
        same=[k for k,v in na.items() if oa.get(k)==v]
        changed=[k for k,v in na.items() if k in oa and oa[k]!=v]
        report['asset_comparison']={'published_count':len(oldassets),'incoming_count':len(newassets),'same_logical_path_and_hash':len(same),'same_by_kind':dict(Counter(k[0] for k in same)),'changed_by_kind':dict(Counter(k[0] for k in changed)),'changed_same_logical_path':[{'kind':k[0],'representation':k[1],'path':k[2],'published':oa[k],'incoming':na[k]} for k in changed],'added_logical_paths':len(set(na)-set(oa)),'removed_logical_paths':len(set(oa)-set(na))}
        report['published_sample_axes']=plain(conn.execute('SELECT * FROM core.sample_axis WHERE dataset_revision_id=%s',(oldid,)).fetchall())
        report['published_quality_issues']=plain(conn.execute('SELECT * FROM core.quality_issue WHERE dataset_revision_id=%s',(oldid,)).fetchall())
        report['published_spectral_arrays']=plain(conn.execute('SELECT * FROM core.spectral_array WHERE dataset_revision_id=%s',(oldid,)).fetchall())
        report['published_spectral_maps']=plain(conn.execute('SELECT * FROM core.spectral_sample_map WHERE dataset_revision_id=%s',(oldid,)).fetchall())
        report['published_counts']={}
        report['identity_collision_checks']=[]
        for name in ('sample_axis','asset','scan_log','image_frame','image_region','image_sample_mapping','spectral_array','spectral_sample_map','data_chunk'):
            report['published_counts'][name]=conn.execute(sql.SQL('SELECT count(*) n FROM core.{} WHERE dataset_revision_id=%s').format(sql.Identifier(name)),(oldid,)).fetchone()['n']
            if name=='data_chunk':continue
            newrows=rows(name);ids=[r['id'] for r in newrows]
            collisions=plain(conn.execute(sql.SQL('SELECT id,dataset_revision_id FROM core.{} WHERE id=ANY(%s::uuid[])').format(sql.Identifier(name)),(ids,)).fetchall())
            report['identity_collision_checks'].append({'table':name,'incoming_ids':len(ids),'existing_id_matches':collisions})
        chunks=plain(conn.execute('SELECT c.logical_sha256,c.row_count,c.coordinate_kind,c.source_row_from,c.source_row_to_exclusive,l.source_log_id,a.logical_path FROM core.data_chunk c LEFT JOIN core.scan_log l ON l.id=c.log_id JOIN core.asset a ON a.id=c.asset_id WHERE c.dataset_revision_id=%s',(oldid,)).fetchall())
        nl={x['id']:x['source_log_id'] for x in rows('scan_log')}
        nap={x['id']:x['logical_path'] for x in newassets}
        def cmap(cr,lookup=None):
            return {((r.get('source_log_id') or r['logical_path']) if lookup is None else (lookup.get(r['log_id']) or nap[r['asset_id']]),r['source_row_from'],r['source_row_to_exclusive']):(r['logical_sha256'],r['row_count'],r['coordinate_kind']) for r in cr}
        oc,nc=cmap(chunks),cmap(rows('data_chunk'),nl)
        report['scalar_logical_chunks']={'published_count':len(oc),'incoming_count':len(nc),'unchanged':sum(oc.get(k)==v for k,v in nc.items()),'changed':sum(k in oc and oc[k]!=v for k,v in nc.items()),'added':len(set(nc)-set(oc)),'removed':len(set(oc)-set(nc))}
(root/'revision_comparison.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
summary={k:report[k] for k in ('revision_field_changes','processing_identity_changes','raw_file_comparison','scalar_logical_chunks')}
summary['asset_comparison']={k:v for k,v in report['asset_comparison'].items() if k!='changed_same_logical_path'}
summary['id_collisions']={v['table']:len(v['existing_id_matches']) for v in report['identity_collision_checks']}
print('COMPARISON '+json.dumps(summary,default=str),flush=True)
package=Path.home()/'audit_12DHDD0002_20261011_final.zip'
with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob('*'):
        if p.is_file():z.write(p,p.relative_to(root).as_posix())
print('FINAL_ARCHIVE '+json.dumps({'path':str(package),'bytes':package.stat().st_size,'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}),flush=True)
