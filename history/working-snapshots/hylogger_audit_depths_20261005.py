import csv,json
from decimal import Decimal
from pathlib import Path
import numpy as np

ROOT=Path('D:/hylogger_aws_batch_20261005')
RAW=Path('D:/100demo/data/raw')
inventory=json.loads((ROOT/'inventory.json').read_text())
report=[]
for hole in inventory['new_ready_holes']:
    folder=RAW/hole
    read=lambda name:json.loads((folder/name).read_text(encoding='utf-8-sig'))
    dataset=read('datasets.json')[0]
    scalars=read('scalar_manifest.json')
    by_id={e['log_id']:e for e in scalars}
    anchor=min([e for e in scalars if e['log_id'] not in (dataset['tray_id'],dataset['section_id'])],key=lambda x:x['log_id'])
    def rows(entry):
        with (folder/entry['file']).open(encoding='utf-8-sig',newline='') as stream:
            r=csv.reader(stream);next(r);return list(r)
    depth=[float(row[0]) for row in rows(anchor)]
    trays=rows(by_id[dataset['tray_id']])
    images=read('images_manifest.json')
    mismatch=[]
    for log in images['logs']:
        if log['log_name']!='Tray Thumbnail Images':continue
        for image in sorted([f for f in images['files'] if f['log_id']==log['log_id']],key=lambda x:int(x['sample_no'])):
            ordinal=int(image['sample_no']);tray=trays[ordinal]
            actual=(depth[int(float(tray[0]))],depth[int(float(tray[1]))])
            declared=(float(image['depth_from']),float(image['depth_to']))
            delta=[float(Decimal(str(a))-Decimal(str(b))) for a,b in zip(declared,actual)]
            if any(abs(x)>0.00001 for x in delta):
                mismatch.append({'tray':ordinal,'declared':declared,'sample_bounds':actual,'delta_m':delta,
                                 'identical_float32':all(np.float32(a).tobytes()==np.float32(b).tobytes() for a,b in zip(declared,actual))})
    if mismatch:
        report.append({'hole':hole,'dataset_id':dataset['dataset_id'],'mismatch_count':len(mismatch),
                       'all_identical_float32':all(r['identical_float32'] for r in mismatch),'details':mismatch})
        print(hole,len(mismatch),all(r['identical_float32'] for r in mismatch),flush=True)
(ROOT/'image_depth_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('DONE',len(report),flush=True)
