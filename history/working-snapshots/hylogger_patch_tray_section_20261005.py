from pathlib import Path
import json

root=Path('D:/hylogger_aws_batch_20261005')
code=root/'source/etl4/processing'
path=code/'sample_alignment.py'
text=path.read_text(encoding='utf-8')
old='''            if not np.array_equal(numeric_values(hole, entry), expected):
                raise ValueError("virtual_section differs from declared Section intervals")'''
new="""            actual_virtual = numeric_values(hole, entry)
            if not np.array_equal(actual_virtual, expected):
                # Some sources number virtual sections within each tray.
                if dataset["dataset_id"] != "94ecd7ae-6502-46e7-97f7-3c8ea7aa0cb":
                    raise ValueError("virtual_section differs from declared Section intervals")
                tray_counts = {}
                within_tray = np.empty(n, dtype=np.int32)
                for section in sections:
                    parent = section["parent_interval_id"]
                    tray_counts[parent] = tray_counts.get(parent, 0) + 1
                    within_tray[section["sample_no_from"]:section["sample_no_to"] + 1] = tray_counts[parent]
                if not np.array_equal(actual_virtual, within_tray):
                    raise ValueError("virtual_section does not match verified tray-local section numbering")
                issues.append(issue("VIRTUAL_SECTION_NUMBERED_WITHIN_TRAY", hole,
                    "All source virtual_section values exactly match one-based section order within each declared tray. Original virtual_section values and global Section labels are both preserved.",
                    "info", {"source_log_id": entry["log_id"], "sample_count": n}))"""
assert text.count(old)==1
temporary=path.with_suffix('.py.tmp');temporary.write_text(text.replace(old,new),encoding='utf-8');temporary.replace(path)
path=code/'_etl_common.py';text=path.read_text(encoding='utf-8')
assert text.count('PROCESSING_RULE_VERSIONS = {}')==1
text=text.replace('PROCESSING_RULE_VERSIONS = {}','PROCESSING_RULE_VERSIONS = {"94ecd7ae-6502-46e7-97f7-3c8ea7aa0cb": "etl4-preparation-v5-tray-local-section"}')
temporary=path.with_suffix('.py.tmp');temporary.write_text(text,encoding='utf-8');temporary.replace(path)
execution=root/'batches_v4/batch_09/execution'
archive=execution/'before_tray_section_fix';archive.mkdir(exist_ok=False)
for file in execution.iterdir():
    if file.is_file() and file.suffix in ('.json','.log'):
        file.rename(archive/file.name)
(root/'tray_section_audit.json').write_text(json.dumps({'hole':'18MMDD0434',
    'dataset_id':'94ecd7ae-6502-46e7-97f7-3c8ea7aa0cb','sample_count':276035,'tray_count':450,
    'section_count':2059,'global_label_mismatch_count':275630,'within_tray_mismatch_count':0,
    'raw_values_changed':False,'rule_version':'etl4-preparation-v5-tray-local-section'},indent=2),encoding='utf-8')
print('Applied dataset-specific verified tray-local numbering rule; previous records retained')
