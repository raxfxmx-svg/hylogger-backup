const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { createJsonClient } = require('./reference-transport.cjs');
const original = fs.readFileSync(path.join(__dirname, '../source/frontend/lib/api.js'), 'utf8');
// Isolate request/error behaviour from the already diagnosed group-log typo.
const schemaFixed = original.replace('l.metric_key === "mineral_name" && usable(l)', 'l.metric_key === "mineral_group" && usable(l)');
const report = { scope: 'Offline simulated transport using actual frontend code. Fetch concurrency is not measured Lambda concurrency.', tests: {} };
const pause = () => new Promise(resolve => setTimeout(resolve, 1));

function service({ holes = 1, failAnomalyOnce = false, failSectionOnce = false, failValues = false } = {}) {
  const counters = { active: 0, peak: 0, requests: 0, anomaly: 0, exactSample: 0, paths: {} };
  const ids = Array.from({ length: holes }, (_, i) => `H${i}`);
  const fetch = async input => {
    const url = new URL(input);
    const pathname = url.pathname;
    counters.requests++;
    counters.paths[pathname] = (counters.paths[pathname] || 0) + 1;
    counters.active++;
    counters.peak = Math.max(counters.peak, counters.active);
    await pause();
    let body, status = 200;
    if (pathname === '/v1/boreholes') body = { items: ids.map(hole_id => ({ hole_id })) };
    else if (pathname.endsWith('/datasets')) {
      const id = pathname.split('/')[3];
      body = { items: [{ dataset_revision_id: id, axis_id: 'axis', sample_count: 2 }] };
    } else if (pathname.endsWith('/logs')) body = { items: [{ log_id: 'group', log_kind: 'scalar', metric_key: 'mineral_group', source_log_name: 'Grp1 sTSAS', output_region: 'SWIR', availability_status: 'payload_present', axis_binding_status: 'verified' }] };
    else if (pathname.endsWith('/values')) {
      if (failValues) status = 503;
      body = { items: [0, 1].map(sample_no => ({ sample_no, depth_m: sample_no + 0.1, value_text: 'CHLORITE', status: 'available' })), next_after_sample: null };
    } else if (pathname.endsWith('/anomalies')) {
      counters.anomaly++;
      if (failAnomalyOnce && counters.anomaly === 1) status = 503;
      body = { items: [{ depth_from_m: 0, depth_to_m: 1, anomaly_score: 99 }], next_offset: null };
    } else if (pathname.endsWith('/intervals')) body = { items: [0, 1].map(i => ({ ordinal: i, sample_no_from: i, sample_no_to: i })), next_offset: null };
    else if (/\/samples\/\d+$/.test(pathname)) {
      counters.exactSample++;
      if (failSectionOnce && counters.exactSample === 1) status = 503;
      const sample_no = Number(pathname.split('/').at(-1));
      body = { sample_no, images: [{ status: 'available', image_asset_id: `asset-${sample_no}`, width_px: 399, height_px: 24 }] };
    } else throw new Error(`Unexpected path ${pathname}`);
    // Successful bodies deliberately complete after headers. This catches
    // schedulers that release their slot too early, before response.json().
    let finished = false;
    const finish = () => { if (!finished) { finished = true; counters.active--; } };
    if (status >= 400) finish();
    return { ok: status === 200, status, headers: { get: () => null }, body: { cancel: async () => finish() }, json: async () => { await pause(); finish(); return body; } };
  };
  return { fetch, counters };
}

function api(source, server, limited = false) {
  let code = source.replace('import { API_BASE } from "@/config";', 'const API_BASE = "https://offline.example";').replace(/export const /g, 'const ');
  const sandbox = { URLSearchParams, fetch: server.fetch };
  if (limited) {
    const start = code.indexOf('async function get(path) {');
    const end = code.indexOf('\nconst qs =', start);
    code = code.slice(0, start) + 'const get = path => transport.get(`${API_BASE}${path}`);\n' + code.slice(end);
    sandbox.transport = createJsonClient(server.fetch, { retries: 0 });
  }
  vm.createContext(sandbox);
  vm.runInContext(code + '\nthis.api = { getMeasurements, getStats, getMineralLogs, getCoreStrip, getHoles };', sandbox);
  return sandbox.api;
}

test('99-hole map and stats share cache, but launch unbounded fetch calls; shared transport caps them at 4', async () => {
  const baseline = service({ holes: 99 });
  const oldApi = api(schemaFixed, baseline);
  const [oldStats] = await Promise.all([oldApi.getStats(), oldApi.getMineralLogs(0.5)]);
  const bounded = service({ holes: 99 });
  const newApi = api(schemaFixed, bounded, true);
  const [newStats] = await Promise.all([newApi.getStats(), newApi.getMineralLogs(0.5)]);
  assert.equal(oldStats.measurements, 198);
  assert.equal(newStats.measurements, 198);
  assert.ok(baseline.counters.peak > 10);
  assert.ok(bounded.counters.peak <= 4);
  assert.equal(baseline.counters.paths['/v1/boreholes'], 1);
  assert.equal(baseline.counters.paths['/v1/boreholes/H0/datasets'], 1);
  assert.equal(baseline.counters.requests, bounded.counters.requests);
  report.tests.fanout = { original_peak_fetch: baseline.counters.peak, bounded_peak_fetch: bounded.counters.peak, requests_each: bounded.counters.requests, duplicated_hole_context: false };
});

test('anomaly failure becomes permanently cached false until error swallowing is removed', async () => {
  const before = service({ failAnomalyOnce: true });
  const oldApi = api(schemaFixed, before);
  const first = await oldApi.getMeasurements('H0');
  const second = await oldApi.getMeasurements('H0');
  assert.equal(first[0].is_anomaly, false);
  assert.equal(second[0].is_anomaly, false);
  assert.equal(before.counters.anomaly, 1);
  const after = service({ failAnomalyOnce: true });
  const corrected = schemaFixed.replace('holeAnomalies(holeId).catch(() => [])', 'holeAnomalies(holeId)');
  const newApi = api(corrected, after);
  await assert.rejects(newApi.getMeasurements('H0'), /503/);
  const recovered = await newApi.getMeasurements('H0');
  assert.equal(recovered[0].is_anomaly, true);
  assert.equal(after.counters.anomaly, 2);
  report.tests.anomaly_cache = { old_returned_false_twice: true, old_backend_attempts: 1, corrected_first_request_rejected: true, corrected_second_request_recovered: true };
});

test('stats reports zero and map reports empty when scalar API fails', async () => {
  const oldApi = api(schemaFixed, service({ failValues: true }));
  const [stats, map] = await Promise.all([oldApi.getStats(), oldApi.getMineralLogs(0.5)]);
  assert.equal(stats.measurements, 0);
  assert.equal(map.holes.H0.length, 0);
  const strict = schemaFixed.replaceAll('getMeasurements(h.hole_id).catch(() => [])', 'getMeasurements(h.hole_id)');
  await assert.rejects(api(strict, service({ failValues: true })).getStats(), /503/);
  report.tests.false_zero = { original_stats_measurements: 0, original_map_rows: 0, strict_error_propagated: true };
});

test('failed photo sample silently produces a partial cached strip', async () => {
  const before = service({ failSectionOnce: true });
  const oldApi = api(schemaFixed, before);
  const first = await oldApi.getCoreStrip('H0');
  const second = await oldApi.getCoreStrip('H0');
  assert.equal(first.rows.length, 1);
  assert.equal(second.rows.length, 1);
  assert.equal(before.counters.exactSample, 2);
  const after = service({ failSectionOnce: true });
  const strict = schemaFixed.replace(').catch(() => null);\n      const image', ');\n      const image');
  const newApi = api(strict, after);
  await assert.rejects(newApi.getCoreStrip('H0'), /503/);
  const recovered = await newApi.getCoreStrip('H0');
  assert.equal(recovered.rows.length, 2);
  report.tests.photo_cache = { original_rows: 1, original_second_read_rows: 1, corrected_recovered_rows: 2 };
});

test('429 Retry-After is respected and exhausted retries reject; ordinary 4xx do not retry', async () => {
  let attempts = 0;
  const waits = [];
  const fetch = async () => ({ ok: false, status: (++attempts, 429), headers: { get: () => '2' }, body: { cancel: async () => {} } });
  const client = createJsonClient(fetch, { random: () => 0, sleep: async ms => waits.push(ms) });
  await assert.rejects(client.get('https://offline.example/a'), /429/);
  assert.equal(attempts, 3);
  assert.deepEqual(waits, [2000, 2000]);
  let badAttempts = 0;
  await assert.rejects(createJsonClient(async () => ({ ok: false, status: (++badAttempts, 404), headers: { get: () => null } })).get('https://offline.example/b'), /404/);
  assert.equal(badAttempts, 1);
  report.tests.retries = { throttle_attempts: attempts, backoff_ms: waits, not_found_attempts: badAttempts };
});

test('retry backoff releases the shared concurrency slot for other requests', async () => {
  let resume;
  let count = 0;
  const seen = [];
  const client = createJsonClient(async url => {
    seen.push(url);
    const status = url.endsWith('/a') && ++count === 1 ? 503 : 200;
    return { ok: status === 200, status, headers: { get: () => null }, json: async () => ({ url }) };
  }, { concurrency: 1, sleep: () => new Promise(resolve => { resume = resolve; }) });
  const a = client.get('https://offline.example/a');
  while (!resume) await pause();
  await client.get('https://offline.example/b');
  resume();
  await a;
  assert.deepEqual(seen, ['https://offline.example/a', 'https://offline.example/b', 'https://offline.example/a']);
});

process.on('exit', () => fs.writeFileSync(path.join(__dirname, 'verification-result.json'), JSON.stringify(report, null, 2)));
