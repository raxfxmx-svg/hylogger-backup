"""Prepare an isolated disposable server to test the portable handoff."""
from pathlib import Path
import json, os, secrets, socket, subprocess, sys, tempfile
import psycopg
from psycopg.conninfo import make_conninfo
from datetime import datetime, timezone

WORK = Path(__file__).resolve().parent
PACKAGE = WORK.parents[1] / 'handoff'
PG = Path('C:/Program Files/PostgreSQL/17/bin')
state = WORK / ('test_cluster_' + secrets.token_hex(4))
state.mkdir()
data = state / 'pgdata'
password = secrets.token_urlsafe(28)
reader_password = secrets.token_urlsafe(28)
with socket.socket() as s:
    s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]


def run(argv, env=None, expected=0):
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        r = subprocess.run([str(x) for x in argv], env=env, stdout=out, stderr=err,
                           timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
        out.seek(0); err.seek(0)
        message = (out.read()+err.read()).decode('utf-8', errors='replace')
    if r.returncode != expected:
        raise RuntimeError(message.replace(password, '[redacted]').replace(reader_password, '[redacted]'))
    return message


started = False
checks = {}
try:
    pw = state / 'init_password.tmp'
    pw.write_text(password + '\n')
    try:
        run([PG/'initdb.exe', '-D', data, '-U', 'handoff_test_admin', '--pwfile', pw,
             '--auth', 'scram-sha-256', '--encoding', 'UTF8', '--locale', 'C'])
    finally:
        pw.unlink(missing_ok=True)
    (data/'HANDOFF_TEST_ONLY').write_text('Isolated package acceptance test; never a production database.')
    run([PG/'pg_ctl.exe','-D', data, '-l', state/'postgres.log','-o',f'-h 127.0.0.1 -p {port}','start','-w','-t','30'])
    started=True
    admin=make_conninfo(host='127.0.0.1',port=port,user='handoff_test_admin',password=password,dbname='postgres')
    with psycopg.connect(admin,autocommit=True) as c:
        c.execute('CREATE DATABASE handoff_acceptance TEMPLATE template0')
    env=os.environ.copy()
    env['ETL4_ADMIN_DSN']=make_conninfo(admin,dbname='handoff_acceptance')
    env['ETL4_READER_PASSWORD']=reader_password
    env['ETL4_READ_DSN']=make_conninfo(host='127.0.0.1',port=port,user='handoff_package_reader',password=reader_password,dbname='handoff_acceptance')
    tool=[sys.executable,'-X','utf8',PACKAGE/'tools/handoff.py']
    run(tool+['restore','--database','handoff_acceptance','--pg-restore',PG/'pg_restore.exe'],env)
    checks['empty_database_restore']=True;print('Empty database restore passed',flush=True)
    text=run(tool+['restore','--database','handoff_acceptance','--pg-restore',PG/'pg_restore.exe'],env,expected=1)
    assert 'not empty' in text; checks['nonempty_restore_refused']=True
    run(tool+['create-reader','--role','handoff_package_reader'],env)
    run(tool+['check-db'],env);checks['readonly_role_and_13_fixtures']=True
    print('Read-only role and database fixtures passed',flush=True)
    output=PACKAGE/'validation/sample15_test.json'
    run(tool+['sample','--hole','07THD002','--sample','15','--log-id','a4a5c7d3-0fe8-53be-97a2-02a5c7771ae8','--output',output],env)
    sample=json.loads(output.read_text(encoding='utf-8'))
    assert sample['md_m']==62.50175 and sample['results'][0]['value']['value_text']=='Muscovite'
    assert sample['images'][0]['width_px']==399 and sample['images'][0]['height_px']==25
    assert (PACKAGE/'etl4'/sample['images'][0]['object_key']).is_file()
    checks['portable_sample_scalar_and_image']=True
    queries=(PACKAGE/'examples/READONLY_QUERIES.sql').read_text(encoding='utf-8')
    rows=[]
    with psycopg.connect(env['ETL4_READ_DSN'],autocommit=True) as c:
        for q in queries.split(';'):
            if not q.strip():continue
            # Query comments contain semicolons, so strip comments before splitting below.
        import re
        clean=re.sub(r'--[^\n]*','',queries)
        for q in clean.split(';'):
            if q.strip():rows.append(len(c.execute(q).fetchall()))
        assert len(rows)==6 and all(rows)
    checks['six_sql_queries_executed']=rows
    catalog=json.loads((PACKAGE/'examples/DATASET_CATALOG.json').read_text(encoding='utf-8'))
    spectra=[]
    for d in catalog['datasets']:
        for a in d['spectral_arrays']:
            outfile=PACKAGE/'validation'/f"spectrum_{a['array_id']}.json"
            run(tool+['sample','--hole',d['hole_id'],'--sample','15','--log-id',a['log_id'],'--output',outfile],env)
            result=json.loads(outfile.read_text(encoding='utf-8'))['results'][0]
            assert result['status']=='available' and len(result['wavelength'])==len(result['spectra'])==a['channel_count']
            spectra.append({'hole':d['hole_id'],'region':a['region_code'],'channels':a['channel_count']})
    checks['eight_spectral_arrays_read']=spectra
    checks['no_sender_local_config']=not (PACKAGE/'etl4/database/runtime/local_config.json').exists()
    print('Sample, six SQL queries and eight spectra passed',flush=True)
finally:
    if started:
        run([PG/'pg_ctl.exe','-D',data,'stop','-m','fast','-w','-t','30'])
        checks['isolated_test_server_stopped']=True

report={'status':'passed','tested_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Isolated local PostgreSQL 17.4/PostGIS 3.6.2 restore using copied package files; no source database or AWS operations',
        'checks':checks,'aws_account_tested':False,'s3_transfer_tested_against_aws':False}
(PACKAGE/'validation/PREPARATION_TESTS.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
