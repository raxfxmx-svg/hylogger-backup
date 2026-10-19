from pathlib import Path
import io
import tokenize

path = Path('etl4/database/32_prepare_multi_dataset_payloads.py')
text = path.read_text(encoding='utf-8-sig')
text = text.replace('import sys\n', '')
text = text.replace('MULTI, MULTI_HOLES, PROCESSING, audit, module, raw_metadata, require', 'MULTI, MULTI_HOLES, audit, raw_metadata, require')
text = text.replace('from _settings import StepParser', '''from _settings import StepParser
from processing._etl_common import DatasetContext, atomic_bytes, pipeline_id, write_json
from processing.payload_validation import validate_hole
from processing.metadata_normalization import normalize_hole
from processing.sample_alignment import align_hole
from processing.columnar_storage import build_hole''')
text = text.replace('def inventory(hole, r, u, code):', 'def inventory(hole, r, u, code, prepared_dir):')
text = text.replace('folder = PREPARED /', 'folder = prepared_dir /')
text = text.replace('def prepare_unit(unit, source, ec):', 'def prepare_unit(unit, source, prepared_dir, database_dir):')
text = text.replace('sha(ROOT / proof["path"])', 'sha(database_dir / proof["path"])')
text = text.replace('inventory(hole, projected, unit, code)', 'inventory(hole, projected, unit, code, prepared_dir)')
for name in ('pipeline_id', 'DatasetContext', 'atomic_bytes', 'write_json'):
    text = text.replace('ec.' + name, name)
start = text.index('    module("multi_validate"')
end = text.index('    hashes = {', start)
text = text[:start] + '''    validate_hole(hole, context=context)
    normalize_hole(
        hole, context=context, source_metadata=raw,
        dataset_selection={
            "source_dataset_id": unit["source_dataset_id"],
            "log_ids": unit["log_ids"],
            "membership_evidence": unit["membership_evidence"],
        },
        orientation_missing_reason="downhole_survey_not_provided",
        orientation_missing_reason_source="source_package_inspection; dataset XML orientation retained separately",
    )
    align_hole(hole, image_depth_policy="decimal_1e-5_or_same_float32", context=context)
    build_hole(hole, context=context)
    metadata = read(folder / "3_normalized_metadata.json")
''' + text[end:]
text = text.replace('    sys.path.insert(0, str(PROCESSING))\n    import _etl_common as ec\n', '')
text = text.replace('prepare_unit(unit, source, ec)', 'prepare_unit(unit, source, PREPARED, ROOT)')

# Separate result saving from processing and name rerun checks explicitly.
start = text.index('    hashes = {', text.index('def prepare_unit'))
end = text.index('\n\ndef main():', start)
save_body = text[start:end]
save_body = save_body.replace('write_json(completed, summary)', 'write_json(folder / "32_unit.json", summary)')
text = text[:start] + '    return save_prepared_result(unit, folder, inv, code, metadata)\n' + text[end:]
start = text.index('    completed = folder / "32_unit.json"')
end = text.index('    baseline = {', start)
reuse_body = text[start:end]
reuse_body = reuse_body.replace('unit[\'source_dataset_name\']', 'dataset_name')
text = text[:start] + '''    saved = reuse_prepared_result(folder, hole, inv, unit["source_dataset_name"])
    if saved is not None:
        return saved
''' + text[end:]
position = text.index('\ndef prepare_unit')
text = text[:position] + '\n\ndef reuse_prepared_result(folder, hole, inv, dataset_name):\n' + reuse_body + '\n\ndef save_prepared_result(unit, folder, inv, code, metadata):\n' + save_body + '\n' + text[position:]

# Rename variable tokens only; preserve persisted JSON fields.
names = {'u':'dataset', 'r':'metadata', 'did':'dataset_id', 'ids':'log_ids',
         'code':'processing_id', 'inv':'input_manifest', 'rel':'relative_path'}
tokens = []
for token in tokenize.generate_tokens(io.StringIO(text).readline):
    if token.type == tokenize.NAME and token.string in names:
        token = token._replace(string=names[token.string])
    tokens.append(token)
path.write_text(tokenize.untokenize(tokens), encoding='utf-8')

# Use normal package imports everywhere to avoid loading business modules multiple times.
files = list(Path('etl4/processing').glob('*.py')) + list(Path('etl4/database').glob('*.py'))
files += list(Path('etl4/processing/tests').glob('*.py')) + list(Path('etl4/database/tests').glob('*.py'))
for path in files:
    text = path.read_text(encoding='utf-8-sig')
    text = text.replace('from _etl_common import ', 'from processing._etl_common import ')
    text = text.replace('import _etl_common as ', 'from processing import _etl_common as ')
    for name in ('payload_validation', 'metadata_normalization', 'sample_alignment', 'columnar_storage'):
        text = text.replace('from ' + name + ' import ', 'from processing.' + name + ' import ')
        text = text.replace('import ' + name + ' as ', 'from processing import ' + name + ' as ')
    text = text.replace('__import__("columnar_storage")', '__import__("processing.columnar_storage", fromlist=["write_verified_parquet"])')
    if path.parent.name == 'processing' and path.name[0].isdigit():
        head, rest = text.split('\n', 1)
        text = head + '\n\nimport sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n' + rest
        # Step 6 already imports Path.
        first = text.index('from pathlib import Path')
        text = text[:first+len('from pathlib import Path')] + text[first+len('from pathlib import Path'):].replace('\nfrom pathlib import Path\n', '\n')
    if path.parent.name == 'tests' and path.parent.parent.name == 'processing':
        text = text.replace('sys.path.insert(0, str(ROOT))', 'sys.path.insert(0, str(ROOT.parent))')
    path.write_text(text, encoding='utf-8')

path = Path('etl4/database/_multi_db.py')
text = path.read_text(encoding='utf-8-sig').replace('def baseline_backup(source_release=None):', 'def load_or_record_source_release(source_release=None, work=None, dbname=None):')
text = text.replace('    path = MULTI / "34_baseline.json"', '    work = MULTI if work is None else work\n    path = work / "34_baseline.json"')
text = text.replace('with connection("reader") as conn:', 'with connection("reader", dbname=dbname) as conn:', 1)
path.write_text(text, encoding='utf-8')
