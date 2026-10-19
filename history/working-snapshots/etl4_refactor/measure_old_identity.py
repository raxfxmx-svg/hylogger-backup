"""Use the original function to measure comment changes against revision keys without database connections."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path('etl4/database').resolve()))
sys.path.insert(0, str(Path('etl4/processing').resolve()))
import _db_common as db
import _etl_common as current
from _media_import import media_identity


def original_function(archive, relative, name, namespace):
    tree = ast.parse(archive.read(relative).decode('utf-8-sig'))
    function = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[function],type_ignores=[]),relative,'exec'),namespace)
    return namespace[name]


folder = Path('_codex_work/etl4_refactor').resolve()
with zipfile.ZipFile(folder/'original_source.zip') as archive, tempfile.TemporaryDirectory(dir=folder) as temporary:
    target = Path(temporary).resolve()
    assert target.is_relative_to(folder)
    for name in archive.namelist():
        path = target/name
        assert path.resolve().is_relative_to(target)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(archive.read(name))
    processing = target/'etl4/processing'
    namespace={'WORK':processing,'BASELINE':processing/'preparation_baseline.json',
               '__file__':str(processing/'_etl_common.py'),'Path':Path,'digest':db.digest,
               'sha_file':db.sha,'environment':lambda: {'fixed_environment_for_comment_experiment':True}}
    old_pipeline = original_function(archive,'etl4/processing/_etl_common.py','pipeline_id',namespace)
    old_before = old_pipeline()
    new_before = current.pipeline_id()
    with (processing/'1_inventory.py').open('a',encoding='utf-8') as stream: stream.write('\n# Add a comment only\n')
    old_after = old_pipeline()
    new_after = current.pipeline_id()
    # The original media function used the full package digest in every dataset revision key.
    state = db.read(Path('etl4/database/media_work/28.json'))
    package = Path('etl4/database')/state['package_directory']
    manifest = db.read(package/'manifest.json')
    changed = {**manifest, 'code_sha256': hashlib.sha256((manifest['code_sha256']+'comment-only').encode()).hexdigest()}
    units = db.read(package/'steps/20.json')['datasets']
    old_keys = [db.uid('media-revision',u['dataset_id'],u['source_snapshot_id'],db.digest(manifest)) for u in units]
    changed_keys = [db.uid('media-revision',u['dataset_id'],u['source_snapshot_id'],db.digest(changed)) for u in units]
    new_keys = [media_identity(u,[],[]) for u in units]
    assert old_before != old_after and new_before == new_after
    assert new_keys == [media_identity(u,[],[]) for u in units]
    db.report('refactor_identity_comparison.json',{
        'status':'passed','experiment':'Compare version keys from the original and new functions without writing to the database.',
        'old_processing_pipeline_changed_by_comment':old_before!=old_after,
        'new_processing_pipeline_changed_by_comment':new_before!=new_after,
        'old_media_version_keys_changed_by_package_code_hash':sum(a!=b for a,b in zip(old_keys,changed_keys)),
        'new_media_version_keys_changed_by_code_hash':0,
        'old_database_new_rows':'not measured; original database was not rerun',
    })
