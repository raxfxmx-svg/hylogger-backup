from pathlib import Path
import csv,hashlib,json,io
import numpy as np

root=Path('D:/hylogger_aws_batch_20261005')
raw=Path('D:/100demo/data/raw')
def rows(folder,entry):
    data=(folder/entry['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==entry['sha256']
    reader=csv.reader(io.StringIO(data.decode('utf-8-sig')))
    next(reader)
    return list(reader)

results=[]
for hole in json.loads((root/'inventory.json').read_text())['new_ready_holes']:
    folder=raw/hole
    d=json.loads((folder/'datasets.json').read_text())[0]
    manifest=json.loads((folder/'scalar_manifest.json').read_text())
    by_id={x['log_id']:x for x in manifest}
    trays=rows(folder,by_id[d['tray_id']])
    sections=rows(folder,by_id[d['section_id']])
    n=int(float(trays[-1][1]))+1
    parents=np.full(n,-1,dtype=int)
    for i,(a,b,label) in enumerate(trays):parents[int(float(a)):int(float(b))+1]=i
    local=np.full(n,-1,dtype=int);global_labels=np.full(n,-1,dtype=float)
    counts={}
    for a,b,label in sections:
        a,b=int(float(a)),int(float(b));parent=int(parents[a])
        assert parent>=0 and np.all(parents[a:b+1]==parent)
        counts[parent]=counts.get(parent,0)+1
        local[a:b+1]=counts[parent];global_labels[a:b+1]=float(label)
    assert np.all(local>0)
    for entry in manifest:
        if entry['log_name']!='virtual_section':continue
        values=np.array([float(row[2]) if row[2] not in ('','null') else float('nan') for row in rows(folder,entry)])
        assert len(values)==n
        result={'hole':hole,'dataset_id':d['dataset_id'],'sample_count':n,'tray_count':len(trays),'section_count':len(sections),'global_mismatch':int(np.count_nonzero(values!=global_labels)),'within_tray_mismatch':int(np.count_nonzero(values!=local)),'raw_values_changed':False}
        results.append(result)
        if result['global_mismatch']:print(json.dumps(result),flush=True)
(root/'all_section_numbering_audit.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('Audited',len(results),'virtual section logs',flush=True)
