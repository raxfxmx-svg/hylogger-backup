"""Seal visually reviewed preparation, import into isolated local databases, and export."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
import zipfile

ROOT=Path('D:/hylogger_aws_batch_20261005')
spec=importlib.util.spec_from_file_location('preparation',ROOT/'run_preparation.py')
prep=importlib.util.module_from_spec(spec);spec.loader.exec_module(prep)

def finish(batch):
    work=Path(batch['work_dir'])
    review=json.loads((work/'visual_review.json').read_text(encoding='utf-8'))
    assert review['status']=='reviewed' and review['batch']==batch['name']
    for file in review['sheets']:
        path=work/file['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==file['sha256']
    for step,script,args in [('25_reviewed','25_review_image_row_regions.py',['--record-reviewed']),
        ('26','26_bind_image_rows_to_samples.py',[]),('27','27_build_image_row_assets.py',[]),('28','28_import_media_revision.py',[])]:
        prep.run(batch,step,'database/'+script,args)
    package=json.loads((work/'database/reports/28_media_package.json').read_text(encoding='utf-8'))['package_object_key']
    prep.save(work/'batch.json',{'packages':[{'directory':package,'prepared_work_dir':str(work)}]})
    prep.run(batch,'08','database/8_apply_schema.py')
    prep.run(batch,'37','database/37_import_final_version.py',['--batch',work/'batch.json'])
    prep.run(batch,'38','database/38_export_batch.py',['--acceptance',work/'database/reports/local_acceptance_2.json','--output-dir',ROOT/'exports'])
    exports=[]
    for path in (ROOT/'exports').glob('*/manifest.json'):
        manifest=json.loads(path.read_text(encoding='utf-8'))
        holes={row['source_hole_id'] for row in manifest['datasets']}
        if holes==set(batch['holes']):exports.append((path.parent,manifest))
    assert len(exports)==1, 'The batch export must be uniquely identified'
    directory,manifest=exports[0]
    zip_path=ROOT/(batch['name']+'_public.zip')
    with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in ['manifest.json',*manifest['files']]:
            path=(directory/relative).resolve()
            assert path.is_relative_to(directory.resolve()) and path.is_file()
            assert path.name not in ('local_sources.json','local_config.json')
            archive.write(path,'exports/'+directory.name+'/'+relative)
    result={'status':'locally_accepted','batch':batch['name'],'holes':batch['holes'],
            'export_dir':str(directory),'batch_id':directory.name,'public_zip':str(zip_path),
            'public_zip_sha256':hashlib.sha256(zip_path.read_bytes()).hexdigest(),'public_zip_bytes':zip_path.stat().st_size}
    prep.save(work/'execution/delivery.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('batches',nargs='+');args=parser.parse_args()
    plan=json.loads((ROOT/'batch_plan.json').read_text())
    for batch in plan:
        if batch['name'] in args.batches:finish(batch)

if __name__=='__main__':main()
