"""Additive import and source-preserving composite selection helpers."""
from _multi_common import *


def configure_media():
    import _media_common as mc
    mc.WORK = MULTI / 'media'; mc.EVIDENCE = MULTI_EVIDENCE
    import _media_import as mi
    files = [ROOT/n for n in ('_multi_common.py', '_multi_db.py', '33_prepare_multi_dataset_media.py',
                             '34_import_multi_dataset_database.py', '_ingest.py', '_media_import.py', '_media_common.py')]
    mi.media_code_hash = lambda: digest({p.name: sha(p) for p in files})
    return mc, mi


def sample_hash(conn, axis):
    h = hashlib.sha256()
    with conn.cursor().copy('COPY (SELECT row_to_json(s)::text FROM core.scan_sample s WHERE axis_id=' +
                            sql.Literal(str(axis)).as_string(conn) + '::uuid ORDER BY sample_no) TO STDOUT') as cp:
        for block in cp: h.update(block)
    return h.hexdigest()


def baseline_backup():
    path = MULTI / '34_baseline.json'
    if path.exists():
        baseline = read(path)
        require(sha(ROOT / baseline['backup_relative_path']) == baseline['backup_sha256'], 'Baseline backup changed')
        return baseline
    with connection() as conn:
        release = str(conn.execute('SELECT release_id FROM core.active_release WHERE singleton').fetchone()['release_id'])
        members = conn.execute('SELECT * FROM core.release_dataset WHERE release_id=%s ORDER BY dataset_id', (release,)).fetchall()
        axes = conn.execute('SELECT a.id FROM core.sample_axis a JOIN core.release_dataset d ON d.dataset_revision_id=a.dataset_revision_id WHERE d.release_id=%s', (release,)).fetchall()
        original = {str(a['id']): sample_hash(conn, a['id']) for a in axes}
    c = config(); env = os.environ.copy()
    env.update(PGHOST=c['host'], PGPORT=str(c['port']), PGUSER=c['roles']['owner']['user'], PGPASSWORD=c['roles']['owner']['password'], PGCLIENTENCODING='UTF8')
    backup = ROOT/'backups'/f'etl4_before_multi_{release}.dump'; backup.parent.mkdir(exist_ok=True)
    command([PG_BIN/'pg_dump.exe', '--format=custom', '--no-owner', '--file', backup, '--dbname', c['database']], env=env)
    baseline = {'release_id': release, 'members': members, 'legacy_sample_hashes': original,
                'backup_relative_path': backup.relative_to(ROOT).as_posix(), 'backup_sha256': sha(backup), 'recorded_at': now()}
    write(path, baseline)
    return baseline


def composite_rows(conn, release, decisions):
    records = conn.execute('''SELECT rd.dataset_id,rd.dataset_revision_id,d.source_dataset_id,d.borehole_id,
      b.source_hole_id,r.source_dataset_name,a.id axis_id,a.sample_count,a.depth_min_m,a.depth_max_m
      FROM core.release_dataset rd JOIN core.dataset d ON d.id=rd.dataset_id JOIN core.borehole b ON b.id=d.borehole_id
      JOIN core.dataset_revision r ON r.id=rd.dataset_revision_id JOIN core.sample_axis a ON a.dataset_revision_id=r.id
      WHERE rd.release_id=%s ORDER BY b.source_hole_id,d.source_dataset_id''', (release,)).fetchall()
    holes = {}
    for r in records: holes.setdefault(r['source_hole_id'], []).append(r)
    output = []
    for hole, members in holes.items():
        if len(members) > 1:
            order = decisions['orders'][hole]
            require(set(order) == {r['source_dataset_id'] for r in members} and len(order) == len(members), 'Confirmed order differs from dataset membership')
            members = sorted(members, key=lambda r: order.index(r['source_dataset_id']))
        require(all(a['depth_min_m'] <= b['depth_min_m'] for a,b in zip(members,members[1:])), 'Nonmonotone successor start requires explicit segment review')
        cid = uid('borehole-composite', release, members[0]['borehole_id'])
        definition = {'members': members, 'decisions': decisions if len(members)>1 else {'single_dataset': True}}
        composite = {'id': cid, 'release_id': release, 'borehole_id': members[0]['borehole_id'],
                     'composition_kind': 'confirmed_successor_chain' if len(members)>1 else 'single_dataset',
                     'boundary_rule': 'successor_first_actual_sample_md_m', 'missing_policy': 'preserve_no_fallback',
                     'trajectory_kind': 'display_composite_not_surveyed_path', 'definition_sha256': digest(definition),
                     'evidence': {'hole_id': hole, 'decisions': decisions if len(members)>1 else {'single_dataset': True},
                                  'depth_units': 'm', 'range_semantics': 'sample selection, not proof of continuous physical recovery'}}
        parts = []; relations = []
        for i, r in enumerate(members):
            cut = members[i+1]['depth_min_m'] if i+1 < len(members) else None
            a = r['depth_min_m']; b = min(r['depth_max_m'], cut) if cut is not None else r['depth_max_m']
            inclusive = cut is None or r['depth_max_m'] < cut
            chosen = conn.execute('''SELECT min(sample_no) a,max(sample_no) b,count(*) n FROM core.scan_sample
              WHERE axis_id=%s AND md_m>=%s AND (md_m<%s OR (%s AND md_m=%s))''', (r['axis_id'],a,b,inclusive,b)).fetchone()
            relation = None
            if i:
                prev = members[i-1]; relation = uid('dataset-succession',prev['dataset_revision_id'],r['dataset_revision_id'],digest(decisions))
                relations.append({'id': relation, 'borehole_id': r['borehole_id'], 'predecessor_revision_id': prev['dataset_revision_id'],
                                  'successor_revision_id': r['dataset_revision_id'], 'relation_kind': 'confirmed_display_successor',
                                  'switch_md_m': a, 'switch_basis': 'successor_first_actual_sample_md_m', 'confirmation_basis': decisions})
            parts.append({'composite_id': cid, 'release_id': release, 'borehole_id': r['borehole_id'], 'sequence_no': i,
                          **pick(r,'dataset_id','dataset_revision_id','axis_id'), 'predecessor_relation_id': relation,
                          'selection_from_md_m': a, 'selection_to_md_m': b, 'upper_inclusive': inclusive,
                          'sample_no_from': chosen['a'], 'sample_no_to': chosen['b'],
                          'selection_status': 'selected' if chosen['n'] else 'fully_superseded'})
        output.append({'hole_id': hole, 'composite': composite, 'parts': parts, 'relations': relations, 'datasets': members})
    return output


def install_composites(conn, release, decisions):
    groups = composite_rows(conn, release, decisions)
    for group in groups:
        c = group['composite']
        existing = conn.execute('SELECT definition_sha256 FROM core.borehole_composite WHERE id=%s',(c['id'],)).fetchone()
        if existing:
            require(existing['definition_sha256'] == c['definition_sha256'], 'Composite identity conflict')
            actual = conn.execute('SELECT * FROM core.borehole_composite_part WHERE composite_id=%s ORDER BY sequence_no',(c['id'],)).fetchall()
            require(json.loads(encoded(actual)) == json.loads(encoded(group['parts'])), 'Existing composite parts differ')
            continue
        for r in group['relations']:
            if not conn.execute('SELECT 1 FROM core.dataset_succession WHERE id=%s',(r['id'],)).fetchone(): insert(conn,'dataset_succession',r)
        insert(conn,'borehole_composite',c)
        for p in group['parts']: insert(conn,'borehole_composite_part',p)
    return groups
