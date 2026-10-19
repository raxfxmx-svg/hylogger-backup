"""One-off source cleanup: expand wildcard imports using static name origins."""
import ast
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
import black

root = Path('etl4')
files = [*root.glob('_*.py'), *(root/'processing').glob('*.py'), *(root/'database').glob('*.py')]
modules = {p.stem: p for p in files}
trees = {name: ast.parse(path.read_text(encoding='utf-8-sig')) for name, path in modules.items()}
cache = {}


def targets(node):
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [name for item in node.elts for name in targets(item)]
    return []


def exports(name):
    if name in cache:
        return cache[name]
    result = {}
    cache[name] = result
    for node in trees[name].body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result[node.name] = ('from', name, node.name, None)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                for symbol in targets(target):
                    result[symbol] = ('from', name, symbol, None)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.split('.')[0]] = ('import', alias.name, None, alias.asname)
        elif isinstance(node, ast.ImportFrom) and node.module != '__future__':
            for alias in node.names:
                if alias.name == '*':
                    result.update(exports(node.module))
                else:
                    result[alias.asname or alias.name] = ('from', node.module, alias.name, alias.asname)
    return {k: v for k,v in result.items() if not k.startswith('_')}


step_docs = {
1:'Inventory raw files for the selected boreholes before content validation.',
2:'Check file hashes and formats while recording explainable source issues.',
3:'Normalize metadata and source identifiers while preserving original documents.',
4:'Map sample indices to depths and check tray and section ranges.',
5:'Write Parquet files and read them back to compare values, nulls, and row counts.',
6:'Check prepared data and depth-based reads without changing data content.',
7:'Register the selected input manifest and prepare an isolated local database instance.',
8:'Apply migrations in order and grant permissions to the import and reader roles.',
9:'Import prepared results transactionally; skip an already imported revision on reruns.',
10:'Compare the database with prepared outputs before publication; enable HTTP checks separately.',
11:'Measure database size, files, and read overhead separately.',
12:'Verify backup restoration and optional read endpoints in a separate database.',
13:'Independently check database relationships and migrations, and test invalid inputs in a trial database.',
14:'Verify database backup and restoration independently of HTTP services.',
20:'Select the source release for media processing and check spectra against the file manifest.',
21:'Check spectral order and sample numbers against cached official sample records.',
22:'Index byte blocks in the original spectra without copying entire arrays.',
23:'Build an image manifest by dataset, image log, and tray.',
24:'Propose crop regions from row sections and build contact sheets for review.',
25:'Check row boundaries, preserve all core pixels, and record visual review results.',
26:'Link image rows to actual sample intervals and retain the approximate-position explanation.',
27:'Create lossless row images and compare every pixel after reading them back.',
28:'Import media revisions from a sealed package; publish after independent validation.',
29:'Check media revisions against actual sources, then publish through the shared entry point.',
30:'Check the media database independently; run failure cases only in a restored copy.',
31:'Check log membership across multiple datasets using saved source evidence.',
32:'Prepare each dataset with an explicitly supplied parsing context.',
33:'Check spectra across multiple datasets and create separate row image assets.',
34:'Import complete dataset and media revisions, then create a combined release pending validation.',
35:'Validate complete sources and display selections, then publish through the shared entry point.',
36:'Back up the active release and compare business content and schema in an isolated restored database.',
}
helper_docs = {
'_etl_common':'Provide file I/O, rule versions, and dataset context for processing steps.',
'_db_common':'Shared database, file I/O and input-manifest utilities.',
'_ingest':'Map prepared data into the database while preserving source values and relationships.',
'_media_common':'Read files and calculate coordinates for image and spectral processing steps.',
'_media_import':'Package media evidence and import an independent revision for each dataset.',
'_media_reader':'Read results and media by dataset, sample axis, and sample number.',
'_media_tests':'Independently test media constraints using synthetic data that can be rolled back.',
'_multi_common':'Read the explicit source scope and prepared results for multiple datasets.',
'_multi_db':'Record the source release and build traceable display segments.',
'_multi_reader':'Read complete datasets and confirmed 3D display composites.',
'_schema_docs':'Generate field and source descriptions from the database schema.',
'_trial_support':'Create controlled trial databases and compare business-record digests.',
'_verification':'Compare prepared outputs with the database; enable API checks separately.',
}

for name, path in modules.items():
    source = path.read_text(encoding='utf-8-sig')
    tree = trees[name]
    loaded = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    lines = source.splitlines(keepends=True)
    replacements = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and any(a.name == '*' for a in node.names):
            origin = exports(node.module)
            statements = set()
            for symbol in loaded & origin.keys():
                kind, module, imported, alias = origin[symbol]
                statement = f'import {module}' if kind == 'import' else f'from {module} import {imported}'
                if alias:
                    statement += ' as ' + alias
                statements.add(statement)
            replacements.append((node.lineno-1, node.end_lineno, '\n'.join(sorted(statements))+'\n'))
    doc = step_docs.get(int(name.split('_')[0])) if name.split('_')[0].isdigit() else helper_docs.get(name)
    if doc and ast.get_docstring(tree):
        node=tree.body[0]
        replacements.append((node.lineno-1,node.end_lineno,f'"""{doc}"""\n'))
    for start,end,value in sorted(replacements,reverse=True):
        lines[start:end]=[value]
    source=''.join(lines)
    # Entry points without business arguments also support --help without executing work.
    if name.split('_')[0].isdigit() and 'StepParser(' not in source and path.parent.name=='database':
        source=source.replace('main_guard(main)', 'main_guard(main)')
        tree=ast.parse(source)
        for node in reversed(tree.body):
            if isinstance(node,ast.If) and '__name__' in ast.unparse(node.test):
                lines=source.splitlines(keepends=True)
                body='\n'.join('    '+line for line in ast.unparse(ast.Module(body=node.body,type_ignores=[])).splitlines())
                lines[node.lineno-1:node.end_lineno]=["if __name__ == '__main__':\n    from _db_common import StepParser\n    StepParser().parse_args()\n"+body+'\n']
                source=''.join(lines)
                break
    path.write_text(black.format_str(source, mode=black.Mode(line_length=100)),encoding='utf-8')
print('Formatted',len(files),'files; expanded wildcard imports')
