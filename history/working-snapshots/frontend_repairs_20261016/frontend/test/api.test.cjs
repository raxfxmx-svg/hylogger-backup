const assert = require('node:assert/strict');
const { test } = require('node:test');
const { row, part, fixture } = require('./api-fixture.cjs');
const plain = (value) => JSON.parse(JSON.stringify(value));

test('catalog list merges all scan depths for a repeated hole regardless of row order', async () => {
  const holes = [
    { hole_id: 'TEST', project: 'Gruyere', scan_from_m: 0.00415, scan_to_m: 221.4977 },
    { hole_id: 'TEST', project: 'Gruyere', scan_from_m: 495.50299, scan_to_m: 1701.797 },
    { hole_id: 'TEST', project: 'Gruyere', scan_from_m: 429.20374, scan_to_m: 501.04172 },
    { hole_id: 'TEST', project: 'Gruyere', scan_from_m: 183.40323, scan_to_m: 501.9975 },
  ];
  const original = JSON.stringify(holes);
  for (const rows of [holes, [...holes].reverse()]) {
    const { api, calls } = fixture([], { holes: rows });
    const result = await api.getHoles();
    assert.equal(result.length, 1);
    assert.equal(result[0].logged_from_m, 0.00415);
    assert.equal(result[0].logged_to_m, 1701.797);
    assert.equal(result[0].drawn_length_m, 1701.797);
    assert.equal(calls.length, 1); // Uses the catalog response, no additional requests.
  }
  assert.equal(JSON.stringify(holes), original);
});

test('catalog extent merging handles missing depths and zero without adding reported lengths', async () => {
  const base = { hole_id: 'TEST', project: 'Catalog metadata', reported_length_m: 318.6 };
  const holes = [base, { ...base, scan_from_m: 0, scan_to_m: 1701.797 },
    { ...base, scan_from_m: null, scan_to_m: null }];
  const [hole] = await fixture([], { holes }).api.getHoles();
  assert.equal(hole.logged_from_m, 0);
  assert.equal(hole.logged_to_m, 1701.797);
  assert.equal(hole.drawn_length_m, 1701.797);
  assert.equal(hole.borehole_length_m, 318.6);
  const [withoutScan] = await fixture([], { holes: [base, base] }).api.getHoles();
  assert.equal(withoutScan.drawn_length_m, 318.6);
});

test('mineral_group is selected; INVALID stays in denominator without modifying source rows', async () => {
  const p = part('single', 10, Array.from({ length: 10 }, (_, i) => 10 + i / 100));
  p.swir.forEach((s, i) => { s.value_text = i < 8 ? 'INVALID' : 'CHLORITE'; });
  const original = JSON.stringify(p.swir);
  const { api } = fixture([p]);
  const [m] = await api.getMeasurements('TEST');
  assert.equal(m.mineral_1, 'CHLORITE');
  assert.equal(m.confidence, 0.2);
  assert.equal(m.mineral_1_pct, 0.2);
  assert.equal(JSON.stringify(p.swir), original);
  assert.deepEqual(plain((await api.getMineralLogs(0.5)).holes.TEST), [[10, 11, null]]);
});

test('all invalid samples retain interval and anomaly; unfamiliar minerals stay valid', async () => {
  const p = part('single', 10, [10.1, 10.2, 10.3], 'INVALID');
  p.anomalies = [{ depth_from_m: 10, depth_to_m: 11, anomaly_score: 98 }];
  const { api } = fixture([p]);
  const [m] = await api.getMeasurements('TEST');
  assert.equal(m.confidence, 0);
  assert.equal(m.quality_flag, 'missing');
  assert.equal(m.is_anomaly, true);
  assert.equal(m.anomaly_score, 98);
  for (const name of ['INVALID', ' invalid ', 'NULL', 'ASPECTRAL', '', null]) assert.equal(api.groupName(row(0, 0, name)), null);
  assert.equal(api.groupName(row(0, 0, 'White Mica')), 'WHITE-MICA');
  assert.equal(api.groupName(row(0, 0, 'PAL-SEP')), 'PAL-SEP');
});

test('two datasets are spliced by depth, preserving tails and replacing overlap even when input order differs', async () => {
  const a = part('main', 0, [0.1, 1.1, 2, 3.1, 4.1], 'CHLORITE');
  const b = part('wedge', 2, [2, 3.1, 5.1], 'WHITE-MICA');
  const { api } = fixture([b, a], { pageSize: 2 });
  const samples = await api.groupSamples('TEST');
  assert.deepEqual(plain(samples.map((s) => [s.depth_m, s.part])), [[0.1, 0], [1.1, 0], [2, 1], [3.1, 1], [5.1, 1]]);
  const ms = await api.getMeasurements('TEST');
  assert.deepEqual(plain(ms.map((m) => m.mineral_1)), ['CHLORITE', 'CHLORITE', 'WHITE-MICA', 'WHITE-MICA', 'WHITE-MICA']);
  const hole = await api.getHole('TEST');
  assert.equal(hole.logged_from_m, 0);
  assert.equal(hole.logged_to_m, 6);
});

test('four dataset sequence keeps the shallow sections and uses the correct wedge at each seam', async () => {
  const parts = [part('original', 0, [0.1, 183.4, 221.4]), part('wedge', 183.4, [183.4, 428.9, 500]),
    part('wedge2', 429.2, [429.2, 495.4, 501]), part('wedge3', 495.5, [495.5, 900, 1701.7])];
  const { api } = fixture(parts);
  const samples = await api.groupSamples('TEST');
  assert.deepEqual(plain(samples.map((s) => [s.depth_m, s.part])),
    [[0.1, 0], [183.4, 1], [428.9, 1], [429.2, 2], [495.4, 2], [495.5, 3], [900, 3], [1701.7, 3]]);
  const hole = await api.getHole('TEST');
  assert.equal(hole.logged_to_m, 1702);
});

test('equal start depth follows last API part; missing multi-part depths report an error rather than silently choosing one', async () => {
  const a = part('a', 0, [0, 1]);
  const b = part('b', 0, [0, 2]);
  assert.deepEqual(plain((await fixture([a, b]).api.groupSamples('TEST')).map((s) => s.part)), [1, 1]);
  delete b.depth_min_m;
  await assert.rejects(fixture([a, b]).api.getMeasurements('TEST'), /without start depths/);
  // Single legacy dataset has no splice boundary, so old responses still work.
  assert.equal((await fixture([b]).api.getMeasurements('TEST')).length, 2);
});

test('partial-metre seam combines only active samples; gaps remain gaps', async () => {
  const a = part('a', 10, [10.1, 10.2, 10.6], 'CHLORITE');
  const b = part('b', 10.5, [10.5, 12.2], 'WHITE-MICA');
  const ms = await fixture([a, b]).api.getMeasurements('TEST');
  assert.equal(ms[0].confidence, 2 / 3);
  assert.equal(ms.length, 2);
  assert.equal(ms[1].depth_from_m, 12);
});

test('cross-boundary anomalies are clipped and do not flag the next dataset', async () => {
  const a = part('a', 0, [0.1, 1.1, 3.1]);
  const b = part('b', 2, [2.1, 3.1]);
  a.anomalies = [{ depth_from_m: 1, depth_to_m: 4, anomaly_score: 95 }, { depth_from_m: 4, depth_to_m: 5 }];
  const { api } = fixture([a, b], { pageSize: 1 });
  assert.deepEqual(plain((await api.holeAnomalies('TEST')).map((a) => [a.depth_from_m, a.depth_to_m])), [[1, 2]]);
  assert.deepEqual(plain((await api.getMeasurements('TEST')).map((m) => m.is_anomaly)), [false, true, false, false]);
});

test('trays use their own dataset sample numbers, unique tray IDs, and retain crossing intervals', async () => {
  const a = part('main', 0, [0, 1, 3], 'CHLORITE');
  const b = part('wedge', 2, [2, 3, 4], 'WHITE-MICA');
  const { api } = fixture([a, b]);
  const trays = await api.getTrays('TEST');
  assert.deepEqual(plain(trays.map((t) => [t.tray_no, t.depth_from_m, t.depth_to_m, t.swir_vnir_mineral, t.tir_mineral])),
    [[1, 0, 2, 'CHLORITE', 'CHLORITE-TIR'], [2, 2, 4, 'WHITE-MICA', 'WHITE-MICA-TIR']]);
});

test('core photos use the correct revision/axis and crop the crossing image instead of stretching it', async () => {
  const a = part('main', 0, [0, 1, 4]);
  const b = part('wedge', 2, [2, 3, 4]);
  a.direction = 'right_to_left';
  const { api, calls } = fixture([a, b]);
  const strip = await api.getCoreStrip('TEST');
  assert.equal(strip.rows.length, 2);
  assert.equal(strip.rows[0].y_to_px, 200);
  assert.equal(strip.rows[0].crop_to, 0.5);
  assert.equal(strip.rows[0].flip, true);
  assert.equal(strip.rows[1].photo_url, '/v1/image-assets/photo-wedge/content');
  assert.equal(strip.rows[1].y_to_px, 400);
  assert.equal(strip.sheets[0].crop_to, 0.5);
  const photoCalls = calls.filter((url) => url.pathname.includes('/samples/'));
  assert.equal(photoCalls.length, 2);
  assert.ok(photoCalls.every((url) => url.searchParams.get('include_results') === 'false'));
});

test('18 spectral/mineral logs are requested in batches of 16 and 2 with no dropped channels', async () => {
  const { api, calls } = fixture([part('main', 0, [0, 1])]);
  const result = await api.getSpectralSample('TEST', 0);
  const requests = calls.filter((url) => url.pathname.includes('/samples/'));
  assert.deepEqual(requests.map((url) => url.searchParams.getAll('log_ids').length), [16, 2]);
  assert.deepEqual(plain(result.spectra.map((s) => s.region)), ['VSWIR', 'TIR']);
  assert.equal(result.minerals.length, 15); // Only INVALID is omitted from display.
  assert.equal(result.minerals.at(-1).mineral, 'MINERAL-min15');
});

test('spectral depth lookup routes a repeated sample number to the matching dataset', async () => {
  const { api, calls } = fixture([part('main', 0, [0, 1, 4]), part('wedge', 2, [2, 3, 5])]);
  const result = await api.getSpectralSample('TEST', 3);
  assert.equal(result.dataset_revision_id, 'wedge');
  assert.equal(result.sample_no, 1);
  assert.equal(result.md_m, 3);
  assert.ok(calls.filter((u) => u.pathname.includes('/samples/')).every((u) => u.pathname === '/v1/datasets/wedge/samples/1'));
});

test('spectral errors reject and a later retry succeeds without poisoning the loaded mineral log', async () => {
  const { api } = fixture([part('main', 0, [0.1, 1.1])], { spectralFailures: 1 });
  const ms = await api.getMeasurements('TEST');
  await assert.rejects(api.getSpectralSample('TEST'), /503/);
  assert.equal((await api.getSpectralSample('TEST')).spectra.length, 2);
  assert.strictEqual(await api.getMeasurements('TEST'), ms);
});

test('no usable spectral/mineral logs does not issue an unbounded default sample request', async () => {
  const p = part('main', 0, [0, 1]);
  p.logs = p.logs.filter((l) => l.metric_key === 'mineral_group');
  const { api, calls } = fixture([p]);
  assert.equal(await api.getSpectralSample('TEST'), null);
  assert.equal(calls.filter((u) => u.pathname.includes('/samples/')).length, 0);
});
