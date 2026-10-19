from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path('etl4/database').resolve()))
from psycopg import sql
from _db_common import CODE, connection, report

def counts():
    with connection('reader') as conn:
        return {table:conn.execute(sql.SQL('SELECT count(*) n FROM core.{}').format(sql.Identifier(table))).fetchone()['n']
                for table in ('borehole','dataset','dataset_revision','sample_axis','scan_sample','asset','data_release','release_dataset')}

before=counts();runs=[]
for script in ('28_import_media_revision.py','34_import_multi_dataset_database.py','35_verify_multi_dataset_database.py'):
    start=time.perf_counter()
    subprocess.run([sys.executable,str(CODE/script)],check=True)
    runs.append({'script':script,'elapsed_seconds':time.perf_counter()-start})
after=counts()
assert before==after
report('refactor_final_smoke.json',{'status':'passed','same_business_counts':True,'counts':after,'runs':runs,
    'purpose':'Reran the final source through the normal entry point; changes to explicit rule records inside the package do not create a new data version.'})
print('Final normal-entry replay: unchanged business counts',after,flush=True)
