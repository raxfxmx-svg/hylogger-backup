"""Use the existing project reader without copying credentials to the repository."""
import json
import os
import sys
from pathlib import Path
import psycopg.conninfo

workspace = Path(__file__).resolve().parents[2]
config = json.loads((workspace / 'etl4/database/runtime/local_config.json').read_text(encoding='utf-8-sig'))
reader = config['roles']['reader']
os.environ['ETL4_READ_DSN'] = psycopg.conninfo.make_conninfo(
    host=config['host'], port=config['port'], dbname=config['database'],
    user=reader.get('user') or reader.get('username') or reader.get('name'),
    password=reader['password'], connect_timeout=5,
)
os.environ['ETL4_DB_AUTH'] = 'password'
os.environ['ETL4_ASSET_BACKEND'] = 'local'
os.environ['ETL4_ROOT'] = str(workspace / 'etl4')
sys.path.insert(0, str(workspace / '_codex_work/hylogger_bugfix_20261005/backend'))

if __name__ == '__main__':
    if '--check' in sys.argv:
        from app.repository import get_backend_health, get_boreholes_v1, get_datasets_by_hole, get_logs_by_revision
        print(json.dumps(get_backend_health(), default=str))
        holes = get_boreholes_v1()
        print(json.dumps({'rows':len(holes), 'holes':len({h['hole_id'] for h in holes}), 'first':holes[0]}, default=str))
        datasets = get_datasets_by_hole('07THD002')
        print(json.dumps({'datasets': datasets}, default=str))
        logs = get_logs_by_revision(str(datasets[0]['dataset_revision_id']))
        print(json.dumps({'log_count':len(logs), 'example_logs':logs[:5]}, default=str))
    else:
        import uvicorn
        uvicorn.run('app.main:app', host='127.0.0.1', port=8017, access_log=False)
