"""Full comparisons, rerun measurements and independent restoration; read the original 11-borehole database only."""
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'etl4/database'), str(ROOT / 'etl4/database/tests')]
from _db_common import ETL, PG_BIN, config, connection
from _db_files import encoded, read, sha, write
from _file_checks import FileChecks
from _final_import import run_final_import
from _settings import settings
from _trial_support import create_trial, drop_trial, fingerprints
from compare_reference import compare

OUT = Path(__file__).parent
settings.work_dir = ETL / 'single_final_check_20260930'
settings.dbname = 'etl4_test_single_final_20260930'


def counts(name):
    with connection(dbname=name) as conn:
        release = conn.execute('SELECT release_id FROM core.active_release').fetchone()['release_id']
        values = {'release_id': str(release)}
        for table in ('borehole', 'dataset', 'dataset_revision', 'scan_sample', 'image_region', 'spectral_array', 'data_release'):
            values[table] = conn.execute('SELECT count(*) n FROM core.' + table).fetchone()['n']
        values['overview_samples'] = conn.execute('SELECT count(*) n FROM core.v_borehole_composite_samples WHERE release_id=%s', (release,)).fetchone()['n']
        values['database_bytes'] = conn.execute('SELECT pg_database_size(current_database()) n').fetchone()['n']
        return values


def main():
    old = counts('etl4_refactor_check')
    new = counts(settings.dbname)
    assert new['dataset_revision'] == new['dataset'] == 16
    assert new['scan_sample'] == 730622
    assert new['image_region'] == 4726 and new['spectral_array'] == 29
    with FileChecks() as scans:
        with connection('reader') as current, connection('reader', dbname='etl4_refactor_check') as reference:
            comparison = compare(current, reference, reference_release='43033059-8e6a-5f10-8247-b4487956cfc2')
        comparison['file_checks'] = scans.stats()
    write(settings.reports_dir / 'final_reference_comparison.json', comparison)
    before = fingerprints()
    with FileChecks() as scans:
        replay = run_final_import(read(settings.work_dir / 'batch.json'))
        replay_stats = scans.stats()
    assert fingerprints() == before and all(r['action'] == 'already_present' for r in replay['datasets'])
    print('Full replay: zero new business records', flush=True)

    helper = importlib.import_module('36_backup_multi_dataset_database')
    cfg = config()
    env = os.environ.copy()
    env.update(PGHOST=cfg['host'], PGPORT=str(cfg['port']), PGUSER=cfg['roles']['owner']['user'],
               PGPASSWORD=cfg['roles']['owner']['password'], PGCLIENTENCODING='UTF8')
    backup = settings.database_dir / 'backups/final_version_20260930.dump'
    backup.parent.mkdir(parents=True, exist_ok=True)
    helper.backup_command([PG_BIN / 'pg_dump.exe', '--format=custom', '--no-owner', '--file', backup, '--dbname', settings.dbname], env)
    trial = create_trial('restore')
    try:
        helper.backup_command([PG_BIN / 'pg_restore.exe', '--no-owner', '--exit-on-error', '--dbname', trial, backup], env)
        assert fingerprints(trial) == before
        with connection() as current, connection(dbname=trial) as restored:
            assert helper.view_definitions(current) == helper.view_definitions(restored)
        restored_counts = counts(trial)
        assert {k:v for k,v in restored_counts.items() if k != 'database_bytes'} == {k:v for k,v in new.items() if k != 'database_bytes'}
        print('Independent restore: business tables, views and active release match', flush=True)
    finally:
        drop_trial(trial)
    source_after = fingerprints('etl4_refactor_check')
    assert source_after == read(OUT / 'target_before.json')
    result = {
        'status': 'passed', 'old': old, 'new': new, 'restored': restored_counts,
        'replay': {'new_business_records': 0, 'elapsed_seconds': replay['elapsed_seconds'], **replay_stats},
        'backup': {'path': str(backup), 'sha256': sha(backup), 'bytes': backup.stat().st_size},
        'reference_database_business_tables_unchanged': True,
        'reference_release_id': comparison['reference_release_id'],
    }
    write(settings.reports_dir / 'final_evaluation.json', result)
    print(encoded(result).decode('utf-8'))


if __name__ == '__main__':
    main()
