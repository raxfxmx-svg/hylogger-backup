import sys, zipfile
from pathlib import Path
sys.path[:0] = ['C:\\path\\to\\project\\etl4\\database', 'C:\\path\\to\\project\\etl4']
with zipfile.ZipFile('C:\\path\\to\\project\\_codex_work\\etl4_batch\\source_before.zip') as archive:
    source=archive.read("etl4/database/7_preflight_database.py").decode("utf-8-sig")
exec(compile(source,'C:\\path\\to\\project\\etl4\\database\\7_preflight_database.py',"exec"), {"__name__":"__main__", "__file__":'C:\\path\\to\\project\\etl4\\database\\7_preflight_database.py'})
