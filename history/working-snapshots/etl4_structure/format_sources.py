import ast
from pathlib import Path
import sys

sys.path.insert(0, '_codex_work/etl4_refactor/vendor')
import black
from pyflakes.checker import Checker
from pyflakes import messages

files = list(Path('etl4/database').glob('*.py')) + list(Path('etl4/processing').glob('*.py'))
files += list(Path('etl4').glob('*.py')) + list(Path('etl4/database/tests').glob('*.py'))
files += list(Path('etl4/processing/tests').glob('*.py'))
for path in files:
    text = path.read_text(encoding='utf-8-sig')
    tree = ast.parse(text)
    unused = {msg.message_args[0] for msg in Checker(tree,str(path)).messages if isinstance(msg,messages.UnusedImport)}
    lines = text.splitlines(keepends=True)
    for node in sorted((node for node in ast.walk(tree) if isinstance(node,(ast.Import,ast.ImportFrom))), key=lambda node:node.lineno, reverse=True):
        prefix = node.module + '.' if isinstance(node,ast.ImportFrom) else ''
        keep = [item for item in node.names if prefix + item.name not in unused]
        if len(keep) == len(node.names):
            continue
        if not keep:
            lines[node.lineno-1:node.end_lineno] = []
        else:
            prefix = 'from ' + node.module + ' import ' if isinstance(node,ast.ImportFrom) else 'import '
            lines[node.lineno-1:node.end_lineno] = [' '*node.col_offset + prefix + ', '.join(item.name + (' as '+item.asname if item.asname else '') for item in keep) + '\n']
    text = ''.join(lines)
    try:
        text = black.format_file_contents(text, fast=False, mode=black.Mode(line_length=100))
    except black.NothingChanged:
        pass
    path.write_text(text, encoding='utf-8')
print('Formatted', len(files), 'files')
