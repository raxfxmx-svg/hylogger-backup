"""One-off migration of legacy path constants using syntax nodes, preserving business comments and persisted fields."""
import ast
from pathlib import Path

exports = {
    '_settings': {'WORK_DIR':'work_dir', 'DB_NAME':'dbname'},
    '_db_common': {'ROOT':'database_dir', 'PREPARED':'prepared_dir', 'RUNTIME':'runtime_dir', 'REPORTS':'reports_dir'},
    '_etl_common': {'WORK':'processing_dir', 'OUTPUT':'prepared_dir'},
    '_media_common': {'WORK':'media_work_dir', 'EVIDENCE':'media_evidence_dir'},
    '_multi_common': {'MULTI':'multi_work_dir', 'MULTI_EVIDENCE':'multi_evidence_dir'},
}
paths = list(Path('etl4/database').glob('*.py')) + list(Path('etl4/processing').glob('*.py'))
paths += list(Path('etl4/database/tests').glob('*.py')) + list(Path('etl4/processing/tests').glob('*.py'))
paths += list(Path('etl4/database/api').glob('*.py'))

for path in paths:
    text = path.read_text(encoding='utf-8-sig')
    if 'from _settings import settings' in text or 'from _settings import configure' in text:
        continue
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    def offset(line, byte_column):
        return starts[line-1] + len(lines[line-1].encode('utf-8')[:byte_column].decode('utf-8'))
    def span(node):
        return offset(node.lineno,node.col_offset), offset(node.end_lineno,node.end_col_offset)
    edits = []
    protected = []
    names = dict(exports.get(path.stem, {}))
    if path.stem == '33_prepare_multi_dataset_media':
        names['MEDIA'] = 'multi_media_dir'
    aliases = {}
    has_configure = False
    needs_configure = False
    config_import = None
    bootstrap_import = None
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for item in node.names:
                module = item.name.rsplit('.',1)[-1]
                if module in exports:
                    aliases[item.asname or item.name] = module
        if isinstance(node,ast.ImportFrom):
            module = (node.module or '').rsplit('.',1)[-1]
            if module in exports:
                if module == '_settings' and node.col_offset == 0:
                    config_import = node
                    has_configure = any(item.name == 'configure' for item in node.names)
                if module in ('_db_common','_etl_common') and bootstrap_import is None and node.col_offset == 0:
                    bootstrap_import = node
                kept = []
                for item in node.names:
                    if item.name in exports[module]:
                        names[item.asname or item.name] = exports[module][item.name]
                    else:
                        kept.append(item)
                        if item.name == '*':
                            names.update(exports[module])
                if len(kept) != len(node.names):
                    a,b = span(node)
                    replacement = 'from ' + node.module + ' import ' + ', '.join(item.name + (' as ' + item.asname if item.asname else '') for item in kept) if kept else ''
                    edits.append((a,b,replacement))
                    protected.append((a,b))
                for item in node.names:
                    if item.name in exports:
                        aliases[item.asname or item.name] = item.name

    # Do not retain old runtime-directory constants at module scope.
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id in names for target in node.targets):
            a,b = span(node)
            edits.append((a,b,''))
            protected.append((a,b))

    # Resolve default directories at call time so import order cannot freeze the work directory.
    for node in ast.walk(tree):
        if isinstance(node,ast.FunctionDef):
            args = node.args.posonlyargs + node.args.args
            defaults = list(zip(args[len(args)-len(node.args.defaults):],node.args.defaults))
            defaults += list(zip(node.args.kwonlyargs,node.args.kw_defaults))
            initializers = []
            for arg, default in defaults:
                if isinstance(default,ast.Name) and default.id in names:
                    a,b = span(default)
                    edits.append((a,b,'None'))
                    protected.append((a,b))
                    initializers.append(f'{arg.arg} = settings.{names[default.id]} if {arg.arg} is None else {arg.arg}')
            if initializers:
                anchor = node.body[0]
                if isinstance(anchor,ast.Expr) and isinstance(anchor.value,ast.Constant) and isinstance(anchor.value.value,str):
                    where = starts[anchor.end_lineno]
                else:
                    where = starts[anchor.lineno-1]
                indent = ' ' * (node.col_offset + 4)
                edits.append((where,where,''.join(indent+line+'\n' for line in initializers)))

    for node in ast.walk(tree):
        a,b = span(node) if hasattr(node,'lineno') else (-1,-1)
        if any(left<=a and b<=right for left,right in protected):
            continue
        if isinstance(node,ast.Name) and node.id in names and isinstance(node.ctx,ast.Load):
            edits.append((a,b,'settings.'+names[node.id]))
        if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id in aliases:
            field = exports[aliases[node.value.id]].get(node.attr)
            if field:
                edits.append((a,b,'settings.'+field))

    # Parse full arguments once, then explicitly initialise configuration in each entry point.
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr == 'parse_args':
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                where = starts[node.end_lineno]
                edits.append((where,where,' '*node.col_offset+f'configure({node.targets[0].id})\n'))
                needs_configure = True
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr == 'parse_args':
            a,b=span(node)
            edits.append((a,b,'args = '+ast.get_source_segment(text,node.value)+'\n'+' '*node.col_offset+'configure(args)'))
            needs_configure=True
        if isinstance(node,ast.Return) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr == 'parse_args':
            a,b=span(node)
            edits.append((a,b,'args = '+ast.get_source_segment(text,node.value)+'\n'+' '*node.col_offset+'configure(args)\n'+' '*node.col_offset+'return args'))
            needs_configure=True

    uses_settings = any('settings.' in replacement for _,_,replacement in edits)
    imports = []
    if uses_settings:
        imports.append('settings')
    if needs_configure and not has_configure:
        imports.append('configure')
    if imports:
        anchor = config_import or bootstrap_import
        if anchor is not None:
            where=starts[anchor.end_lineno]
        else:
            top_imports=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
            where=starts[top_imports[-1].end_lineno] if top_imports else 0
        edits.append((where,where,'from _settings import '+', '.join(imports)+'\n'))
    for a,b,replacement in sorted(edits,reverse=True):
        text=text[:a]+replacement+text[b:]
    ast.parse(text)
    path.write_text(text,encoding='utf-8')

# Resolve the run-record directory after entry-point configuration.
for filename, function, expression in (
    ('etl4/database/_db_common.py','run_report_directory','settings.reports_dir / "runs"'),
    ('etl4/processing/_etl_common.py','run_report_directory','settings.processing_dir / "runs"'),
):
    path=Path(filename)
    text=path.read_text(encoding='utf-8')
    text=text.replace('run_record('+expression+', fn)', 'run_record('+function+', fn)')
    text += '\n\ndef '+function+'():\n    return '+expression+'\n'
    path.write_text(text,encoding='utf-8')
