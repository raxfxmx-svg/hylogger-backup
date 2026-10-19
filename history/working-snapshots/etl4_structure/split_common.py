import ast
from pathlib import Path

path = Path('etl4/database/_db_common.py')
text = path.read_text(encoding='utf-8')
tree = ast.parse(text)
lines = text.splitlines(keepends=True)
groups = {
    '_db_files': ['serial','encoded','digest','read','sha','inside','write'],
    '_run_reports': ['now','command','report','main_guard','run_report_directory'],
    '_prepared_inputs': ['load_lock','prepared_holes'],
}
headers = {
    '_db_files': """\"\"\"JSON encoding, file access, and content digests for database manifests.\"\"\"
import hashlib
import json
import os
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from _settings import settings
""",
    '_run_reports': """\"\"\"Save run reports and provide shared command execution and entry-point error handling.\"\"\"
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from _db_files import write
from _settings import settings
""",
    '_prepared_inputs': """\"\"\"Read the selected preparation manifest and check its file references.\"\"\"
from _db_files import inside, read, sha
from _settings import BASE_HOLES, settings

ALLOWED = BASE_HOLES
""",
}
remove = set()
for module,names in groups.items():
    functions=[]
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in names:
            source=''.join(lines[node.lineno-1:node.end_lineno])
            if node.name=='main_guard':
                source=source.replace('    from _file_checks import run_record', '    from _file_checks import run_record\n    from _db_common import config')
            functions.append(source.rstrip())
            remove.update(range(node.lineno-1,node.end_lineno))
    (path.parent/(module+'.py')).write_text(headers[module]+'\n\n'+'\n\n\n'.join(functions)+'\n',encoding='utf-8')

text=''.join(line for index,line in enumerate(lines) if index not in remove)
text=text.replace('"""Shared database, file I/O and input-manifest utilities."""', '"""Database connections, identifiers, inserts, and schema checks."""')
text=text.replace('from _settings import SOURCE_ROOT', 'from _settings import SOURCE_ROOT, BASE_HOLES')
text=text.replace('ALLOWED = ("05KCD001", "07THD002", "07THD003", "09ATD015", "09ATD019")','ALLOWED = BASE_HOLES')
# Preserve exported names for existing tools; current business code uses the owning modules.
for module,names in groups.items():
    text += '\nfrom '+module+' import (\n'+''.join('    '+name+' as '+name+',\n' for name in names if name!='run_report_directory')+')\n'
path.write_text(text,encoding='utf-8')

exports={name:module for module,names in groups.items() for name in names}
files=list(Path('etl4/database').glob('*.py'))+list(Path('etl4/database/tests').glob('*.py'))+list(Path('etl4/database/api').glob('*.py'))
for path in files:
    if path.name in ('_db_common.py','_run_reports.py'):
        continue
    text=path.read_text(encoding='utf-8-sig')
    # Replace wildcard imports in legacy tests with the names actually used.
    if path.name=='test_database_contracts.py':
        text=text.replace('from _db_common import *', 'from _db_common import ETL, LOCK_KEY, connection, digest, insert, inside, prepared_holes, report, sha, uid')
    tree=ast.parse(text)
    lines=text.splitlines(keepends=True)
    for node in sorted((n for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module=='_db_common'),key=lambda n:n.lineno,reverse=True):
        grouped={}
        for item in node.names:
            module=exports.get(item.name,'_db_common')
            grouped.setdefault(module,[]).append(item)
        # Load database modules first so legacy direct execution can locate the etl4 root.
        statements=[]
        if '_db_common' not in grouped:
            statements.append('import _db_common')
        for module in sorted(grouped,key=lambda name:name!='_db_common'):
            statements.append('from '+module+' import '+', '.join(item.name+(' as '+item.asname if item.asname else '') for item in grouped[module]))
        indent=' '*node.col_offset
        lines[node.lineno-1:node.end_lineno]=[indent+statement+'\n' for statement in statements]
    path.write_text(''.join(lines),encoding='utf-8')

# Shared configuration stores scope data without running checks.
path=Path('etl4/_settings.py')
text=path.read_text(encoding='utf-8').replace('SOURCE_ROOT = Path(__file__).resolve().parent', 'SOURCE_ROOT = Path(__file__).resolve().parent\nBASE_HOLES = ("05KCD001", "07THD002", "07THD003", "09ATD015", "09ATD019")')
path.write_text(text,encoding='utf-8')
