from pathlib import Path

root = Path('etl4/processing')
steps = [
    ('2_validate_payloads.py', 'payload_validation', 'validate_hole', 'step 2 validate payloads'),
    ('3_normalize_metadata.py', 'metadata_normalization', 'normalize_hole', 'step 3 normalize metadata'),
    ('4_align_samples.py', 'sample_alignment', 'align_hole', 'step 4 align samples'),
    ('5_build_columnar.py', 'columnar_storage', 'build_hole', 'step 5 build columnar'),
]
for filename, module, function, label in steps:
    path = root / filename
    text = path.read_text(encoding='utf-8-sig')
    body, tail = text.split('\ndef main():', 1)
    body = body.replace('    fail_main,\n', '').replace('    run_holes,\n', '')
    (root / (module + '.py')).write_text(body.rstrip() + '\n', encoding='utf-8')
    path.write_text(
        text.splitlines()[0] + '\n\n'
        + 'from _etl_common import fail_main, run_holes\n'
        + f'from {module} import {function}\n\n\n'
        + 'def main():\n'
        + f'    run_holes("{label}", {function})\n\n\n'
        + 'if __name__ == "__main__":\n    fail_main(main)\n', encoding='utf-8'
    )

path = root / 'metadata_normalization.py'
text = path.read_text(encoding='utf-8')
text = text.replace('def normalize_hole(hole, context=None):', """def normalize_hole(
    hole, context=None, *, source_metadata=None, dataset_selection=None,
    orientation_missing_reason="withheld_for_confidentiality",
    orientation_missing_reason_source="project_owner_statement",
):
    \"\"\"Parse selected datasets and record complete provenance and missing-data reasons on the first write.\"\"\"""")
text = text.replace('"orientation_missing_reason": "withheld_for_confidentiality",', '"orientation_missing_reason": orientation_missing_reason,')
text = text.replace('"orientation_missing_reason_source": "project_owner_statement",', '"orientation_missing_reason_source": orientation_missing_reason_source,')
text = text.replace('"raw_metadata": raw,', '"raw_metadata": source_metadata if source_metadata is not None else raw,')
text = text.replace('    write_json(folder / "3_normalized_metadata.json", data)', '''    if dataset_selection is not None:
        data["selected_dataset_context"] = dataset_selection
    write_json(folder / "3_normalized_metadata.json", data)''')
text += '\n'
path.write_text(text, encoding='utf-8')

# Alignment reads only the selected dataset; retain complete source documents as evidence.
path = root / 'sample_alignment.py'
text = path.read_text(encoding='utf-8')
text = text.replace('    meta = read_json(folder / "3_normalized_metadata.json")', '''    meta = read_json(folder / "3_normalized_metadata.json")
    raw = context.metadata if context is not None else meta["raw_metadata"]''')
text = text.replace('meta["raw_metadata"][', 'raw[')
path.write_text(text, encoding='utf-8')

# Tests import business functions directly; numbered scripts are command-line entry points.
path = root / 'tests/test_data_contracts.py'
text = path.read_text(encoding='utf-8-sig')
start = text.index('\ndef load(')
end = text.index('\n\nclass DataContracts', start)
text = text[:start] + '''
import payload_validation as validation
import metadata_normalization as normalization
import sample_alignment as alignment
import columnar_storage as columnar
''' + text[end:]
text = text.replace('import importlib.util\n', '')
path.write_text(text, encoding='utf-8')

path = Path('etl4/database/tests/test_refactor.py')
text = path.read_text(encoding='utf-8-sig')
start = text.index('\ndef load_step(')
end = text.index('\n\nclass RefactorContracts', start)
text = text[:start] + text[end:]
text = text.replace('import importlib.util\n', '')
text = text.replace('load_step("5_build_columnar.py")', '__import__("columnar_storage")')
path.write_text(text, encoding='utf-8')
