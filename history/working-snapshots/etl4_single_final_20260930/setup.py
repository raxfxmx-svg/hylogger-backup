from pathlib import Path
import sys
import shutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'etl4/database'))
from _db_common import ETL, connection
from _db_files import read, encoded
from _settings import settings
from _trial_support import trial_schema, fingerprints
from psycopg import sql

OUT = Path(__file__).parent
WORK = ETL / 'single_final_check_20260930'
NAME = 'etl4_test_single_final_20260930'
WORK.joinpath('database/runtime').mkdir(parents=True, exist_ok=True)
target = WORK / 'database/runtime/local_config.json'
if not target.exists():
    shutil.copyfile(ETL / 'refactor_work/database/runtime/local_config.json', target)
settings.work_dir = WORK
settings.dbname = NAME
with connection(dbname='postgres') as conn:
    if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (NAME,)).fetchone():
        conn.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0 ENCODING {}').format(sql.Identifier(NAME), sql.Literal('UTF8')))
        trial_schema(NAME)
if not (OUT / 'target_before.json').exists():
    (OUT / 'target_before.json').write_bytes(encoded(fingerprints('etl4_refactor_check')))

batch = {'packages': []}
for work, stagefile in (
    ('refactor_work', 'database/media_work/28.json'),
    ('refactor_work', 'database/multi_work/34_import.json'),
    ('new_input_check', 'database/media_work/28.json'),
    ('new_input_check/random_09THD028', 'database/media_work/28.json'),
):
    stage = read(ETL / work / stagefile)
    print(work, list(stage.keys()))
    package = stage.get('package_directory')
    if package is None:
        raise ValueError('Resolve multi package explicitly')
    batch['packages'].append({'directory': f'{work}/database/{package}', 'prepared_work_dir': work})
with connection(dbname='etl4_refactor_check') as conn:
    active = conn.execute('SELECT r.id,r.manifest FROM core.data_release r JOIN core.active_release a ON a.release_id=r.id').fetchone()
    batch['decisions'] = active['manifest']['succession_decisions']
    (OUT / 'reference_release.json').write_bytes(encoded(active))
(WORK / 'batch.json').write_bytes(encoded(batch))
one = {'packages': batch['packages'][-1:]}
(WORK / 'one_hole.json').write_bytes(encoded(one))
print(NAME, WORK)
