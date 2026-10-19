"""Clean up imports and comments without changing processing logic."""
import ast
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
import black
from pyflakes.checker import Checker

paths = [*Path('etl4/database').glob('*.py'), *Path('etl4/processing').glob('*.py'), *Path('etl4').glob('_*.py')]
comments = {
'11_measure_capacity.py': ['Generate only the deployment file manifest here.'],
'13_audit_database.py': ['Verify registered prepared-file hashes during reads as well.','Check every image source field by field.','Roll back invalid inputs even if accepted; retain no synthetic review records.','Test bulk-insert triggers with an actual COPY operation.'],
'20_audit_spectral_sources.py': ['Accept prepared results for a single dataset here; multiple datasets use separate contexts.'],
'21_verify_spectral_bindings.py': ['Restore JSON decimals to float32 for bitwise comparison, preserving zeros and nonfinite values.'],
'24_detect_image_rows.py': ['Select the first and last images for each hole, image size, and row count.'],
'25_review_image_row_regions.py': ['Find brightness dividers near metadata positions while preserving dark core pixels.','Use the geometric template when dividers are unclear; preserve full row edges.'],
'29_verify_media_grain.py': ['Check the actual files for reused Parquet assets and newly created row images.','Preserve interpretation algorithm variants and original values when reading results.','Boundary values are often null; also check samples with mineral names and weights.','Locate prepared files through source logs, then read and compare them independently.','Compare official samples and offline reader results as float32 values.'],
'30_audit_media_database.py': ['Compare source images and crops using actual database associations.','A file may be registered repeatedly; a declared flip requires the matching geometric transformation.','Commit concurrency tests only in a disposable restored copy.','The restored database contains base images and media revisions; select the media revision for testing.'],
'34_import_multi_dataset_database.py': ['Pass one dataset context and input manifest at a time.'],
'35_verify_multi_dataset_database.py': ['Update statistics for new samples before subsequent joins.'],
'36_backup_multi_dataset_database.py': ['Allow longer timeouts for full restoration while continuing to report progress.'],
'7_preflight_database.py': ['Preserve inherited work directory permissions so the current environment retains access.','Windows returns this path using the system code page.'],
'8_apply_schema.py': ['Media version cloning uses a UUID mapping table scoped to the session.'],
'_db_common.py': ['Capture output in a temporary file so background processes do not keep a pipe open.','Connection settings may contain passwords; omit their contents from error messages.'],
'_ingest.py': ['EWKT preserves both the confirmed coordinate system and the two-dimensional coordinates.'],
'_media_common.py': ['Crop using decoded native coordinates and reject EXIF transformations that have not been reviewed.'],
'_media_import.py': ['Base revisions share borehole metadata; preserve existing references during copying.','SQL copies sample values unchanged and replaces only internal relationship IDs; source checks still run.','Evidence files may be shared, but asset records still belong to their respective data versions.'],
'_media_reader.py': ['Return all candidate images explicitly and let the caller select a log.'],
'_media_tests.py': ['Intentionally omit the sample mapping for the second row of the second log.','Intentionally omit the crop file for the second row of the first log.','Interrupt after copying samples and confirm that the entire new revision rolls back.'],
'_trial_support.py': ['Sort text consistently so the digest covers every record without relying on internal sequence numbers.'],
'4_align_samples.py': ['Source depths are decimal; avoid binary rounding at the 0.00001 m boundary.','A matching byte count alone does not establish alignment with the sample axis.'],
'5_build_columnar.py': ['Hash Python values to avoid this Windows Arrow null-fill issue without filling scientific data.','Decompress each NPZ array once instead of decompressing it again for every row.'],
'6_verify_prepared_data.py': ['Exercise the stored index used by depth-based queries.'],
}
import re
for path in paths:
    source = path.read_text(encoding='utf-8')
    if path.name == '_db_common.py':
        source = source.replace('DB_NAME, StepParser', 'DB_NAME, StepParser as StepParser')
    # Replace consecutive English comments by paragraph, retaining short processing explanations.
    entries = iter(comments.get(path.name, []))
    lines = source.splitlines(True)
    i = 0
    while i < len(lines):
        if re.match(r'\s*#',lines[i]) and re.search('[a-zA-Z]',lines[i]) and not re.search('[\u4e00-\u9fff]',lines[i]):
            end = i + 1
            while end < len(lines) and re.match(r'\s*#',lines[end]) and not re.search('[\u4e00-\u9fff]',lines[end]):
                end += 1
            translation = next(entries, None)
            if translation is not None:
                indent = lines[i][:len(lines[i])-len(lines[i].lstrip())]
                lines[i:end] = [indent + '# ' + translation + '\n']
        i += 1
    source = ''.join(lines)
    tree = ast.parse(source)
    warnings = Checker(tree, filename=str(path)).messages
    unused = {message.lineno: message.message_args[0] for message in warnings if type(message).__name__ == 'UnusedImport'}
    changes = []
    for node in ast.walk(tree):
        if isinstance(node,(ast.Import,ast.ImportFrom)) and node.lineno in unused:
            name = unused[node.lineno]
            aliases = [a for a in node.names if not (name == a.name or name.endswith('.'+a.name) or name.endswith(' as '+str(a.asname)))]
            if aliases:
                node.names = aliases
                replacement = ' ' * node.col_offset + ast.unparse(node) + '\n'
            else:
                replacement = ''
            changes.append((node.lineno-1,node.end_lineno,replacement))
    lines = source.splitlines(True)
    for a,b,value in sorted(changes,reverse=True): lines[a:b] = [value]
    source = ''.join(lines)
    # Merge explicit imports from the same module within a block without crossing path initialisation.
    tree = ast.parse(source); changes=[]; group=[]
    for node in [*tree.body, None]:
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            group.append(node); continue
        if group:
            imports={}; plain=[]
            for item in group:
                if isinstance(item,ast.ImportFrom):
                    key=(item.module,item.level)
                    imports.setdefault(key,{})
                    for alias in item.names: imports[key][(alias.name,alias.asname)]=alias
                else:
                    for alias in item.names:
                        code=ast.unparse(ast.Import(names=[alias]))
                        if code not in plain: plain.append(code)
            grouped=[ast.unparse(ast.ImportFrom(module=key[0],level=key[1],names=list(aliases.values()))) for key,aliases in imports.items()]
            future=[line for line in grouped if line.startswith('from __future__')]
            rest=[line for line in grouped if line not in future]
            changes.append((group[0].lineno-1,group[-1].end_lineno,'\n'.join(future+plain+rest)+'\n'))
            group=[]
    lines=source.splitlines(True)
    for a,b,value in reversed(changes): lines[a:b]=[value]
    source=''.join(lines)
    try: source = black.format_file_contents(source,fast=False,mode=black.Mode(line_length=100))
    except black.NothingChanged: pass
    path.write_text(source,encoding='utf-8')

for path in Path('etl4/database/tests').glob('*.py'):
    try: path.write_text(black.format_file_contents(path.read_text(encoding='utf-8'),fast=False,mode=black.Mode(line_length=100)),encoding='utf-8')
    except black.NothingChanged: pass
