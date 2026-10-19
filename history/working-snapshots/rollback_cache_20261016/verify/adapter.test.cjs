const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const root = "C:\\path\\to\\project\\_codex_work\\live_diagnosis_20261008";
const read = file => JSON.parse(fs.readFileSync(path.join(root, file), 'utf8').replace(/^\uFEFF/, ''));
const original = fs.readFileSync(path.join(root, 'source/frontend/lib/api.js'), 'utf8');
const proposed = fs.readFileSync(path.join(__dirname, '../frontend/lib/api.js'), 'utf8');
const metricOnly = original.replace('l.metric_key === "mineral_name" && usable(l)', 'l.metric_key === "mineral_group" && usable(l)');
const sample = (value_text, sample_no, depth_m = 10 + sample_no / 100) => ({ sample_no, depth_m, value_text, value_raw: value_text, status: value_text === null ? 'source_null' : 'available' });

function adapter(source, rows, options = {}) {
  const logs = options.logs || [{ log_id: 'group', source_log_name: 'Grp1 sTSAS', metric_key: 'mineral_group', log_kind: 'scalar', output_region: 'SWIR', availability_status: 'payload_present', axis_binding_status: 'verified' }];
  const revision = options.revision || 'revision';
  const axis = options.axis || 'axis';
  const hole = options.hole || 'TEST';
  const selectedLog = options.selectedLog || 'group';
  const calls = [];
  const sandbox = {
    URLSearchParams, TextEncoder, setTimeout, clearTimeout,
    fetch: async input => {
      const url = new URL(input);
      const endpoint = url.pathname;
      calls.push(endpoint);
      if (options.failAnomalies && endpoint.endsWith("/anomalies")) return {ok:false,status:503};
      let body;
      if (endpoint === '/v1/boreholes') body = { items: [{ hole_id: hole }] };
      else if (endpoint === `/v1/boreholes/${hole}/datasets`) body = { items: [{ dataset_revision_id: revision, axis_id: axis, sample_count: rows.length }] };
      else if (endpoint === `/v1/datasets/${revision}/logs`) body = { items: logs };
      else if (endpoint === `/v1/datasets/${revision}/anomalies`) body = { items: options.anomalies || [], next_offset: null };
      else if (endpoint === `/v1/datasets/${revision}/logs/${selectedLog}/values`) {
        const remaining = rows.filter(row => row.sample_no > Number(url.searchParams.get('after_sample')));
        const limit = Number(url.searchParams.get('limit'));
        const items = remaining.slice(0, limit);
        body = { items, next_after_sample: remaining.length > limit ? items.at(-1).sample_no : null };
      } else if (endpoint === `/v1/datasets/${revision}/samples/${options.exactSample?.sample_no}`) body = options.exactSample;
      else throw new Error(`Unexpected endpoint: ${endpoint}`);
      return { ok: true, json: async () => body };
    }
  };
  vm.createContext(sandbox);
  const cacheSource = '';
  source = source.replace('import { cached, CATALOG_TTL } from "./dataCache";', '').replace('export { clearDataCache } from "./dataCache";', '');
  const prefix = source.includes('datasetOnce') ? cacheSource + '\n' : '';
  const runnable = prefix + source.replace('import { API_BASE } from "@/config";', 'const API_BASE = "https://fixture.example";').replace(/export const /g, 'const ');
  vm.runInContext(runnable + '\nthis.api = { groupName, getMeasurements, getMineralLogs, getSpectralSample };', sandbox);
  return { api: sandbox.api, calls };
}

test('non-mineral labels become null; real unfamiliar minerals and raw records remain intact', () => {
  const { api } = adapter(proposed, []);
  for (const label of ['INVALID', ' invalid ', 'ASPECTRAL', 'NULL', '', '   ', null]) {
    const row = sample(label, 0);
    const before = JSON.stringify(row);
    assert.equal(api.groupName(row), null);
    assert.equal(JSON.stringify(row), before);
  }
  assert.equal(api.groupName(sample('White Mica', 0)), 'WHITE-MICA');
  assert.equal(api.groupName(sample('PAL-SEP', 0)), 'PAL-SEP');
  assert.equal(api.groupName({ value_text: 'CHLORITE', status: 'source_null' }), null);
});

test('80% INVALID does not turn 20% real calls into 100% confidence or a coloured map interval', async () => {
  const rows = Array.from({ length: 10 }, (_, i) => sample(i < 8 ? 'INVALID' : 'CHLORITE', i));
  const { api } = adapter(proposed, rows);
  const measurements = await api.getMeasurements('TEST');
  assert.equal(measurements.length, 1);
  assert.equal(measurements[0].mineral_1, 'CHLORITE');
  assert.equal(measurements[0].confidence, 0.2);
  assert.equal(measurements[0].mineral_1_pct, 0.2);
  const map = await api.getMineralLogs(0.5);
  assert.equal(map.groups.length, 0);
  assert.deepEqual(JSON.parse(JSON.stringify(map.holes.TEST)), [[10, 11, null]]);
});

test('entirely invalid intervals retain depth and anomaly overlays with missing mineral status', async () => {
  const rows = ['INVALID', 'ASPECTRAL', null].map((label, i) => sample(label, i));
  const { api } = adapter(proposed, rows, { anomalies: [{ depth_from_m: 10, depth_to_m: 11, anomaly_score: 98, why: 'fixture anomaly' }] });
  const [m] = await api.getMeasurements('TEST');
  assert.equal(m.depth_from_m, 10);
  assert.equal(m.depth_to_m, 11);
  assert.equal(m.mineral_1, null);
  assert.equal(m.confidence, 0);
  assert.equal(m.quality_flag, 'missing');
  assert.equal(m.is_anomaly, true);
  assert.equal(m.anomaly_score, 98);
});

test('valid dominance uses all samples as denominator and preserves absent-depth gaps', async () => {
  const rows = ['WHITE-MICA', 'WHITE-MICA', 'WHITE-MICA', 'CHLORITE', 'INVALID'].map((label, i) => sample(label, i));
  rows.push(sample('INVALID', 5, 12.2));
  const { api } = adapter(proposed, rows);
  const measurements = await api.getMeasurements('TEST');
  assert.equal(measurements.length, 2);
  assert.equal(measurements[0].confidence, 0.6);
  assert.equal(measurements[1].depth_from_m, 12);
  assert.equal(measurements[1].mineral_1, null);
});

test('sample mineral badges exclude INVALID while retaining available spectra and original real labels', async () => {
  const rows = [sample('WHITE-MICA', 0)];
  const exactSample = { sample_no: 0, sample_count: 1, md_m: 10, results: [
    { log_kind: 'scalar', status: 'available', source_log_name: 'Min1', value: { value_text: 'INVALID' } },
    { log_kind: 'scalar', status: 'available', source_log_name: 'Min2', value: { value_text: 'ASPECTRAL' } },
    { log_kind: 'scalar', status: 'available', source_log_name: 'Min3', value: { value_text: 'White Mica' } },
    { log_kind: 'spectral', status: 'available', region_code: 'VSWIR', spectra: [0.1, 0.2], wavelength: [500, 501], wavelength_unit: 'nm' }
  ] };
  const { api } = adapter(proposed, rows, { exactSample });
  const response = await api.getSpectralSample('TEST', 10);
  assert.deepEqual(JSON.parse(JSON.stringify(response.minerals)), [{ log_name: 'Min3', mineral: 'White Mica' }]);
  assert.equal(response.spectra.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(response.spectra[0].values)), [0.1, 0.2]);
  assert.equal(exactSample.results[0].value.value_text, 'INVALID');
});

test('actual 07THD003 response: all 188 metre intervals survive and INVALID disappears from mineral categories', async () => {
  const rows = read('07THD003-all-values.json');
  const options = { logs: read('07THD003-logs.json').items, revision: '87ff003a-7ec9-54b6-9927-d2a518e34aae', axis: '9c84fbf6-6513-5200-a71a-c303713a122c', selectedLog: 'cf2ee947-090f-50aa-b787-c234f64ac9c0', hole: '07THD003' };
  const before = await adapter(metricOnly, rows, options).api.getMeasurements(options.hole);
  const fixed = adapter(proposed, rows, options);
  const after = await fixed.api.getMeasurements(options.hole);
  assert.equal(rows.length, 54432);
  assert.equal(before.filter(m => m.mineral_1 === 'INVALID').length, 113);
  assert.equal(after.length, 188);
  assert.equal(after.filter(m => m.mineral_1 === 'INVALID').length, 0);
  assert.equal(after[0].depth_from_m, 64);
  assert.equal(after.at(-1).depth_to_m, 252);
  const map = await fixed.api.getMineralLogs(0.5);
  assert.equal(map.groups.includes('INVALID'), false);
  const b = before.findIndex(m => m.mineral_1 === 'INVALID' && m.confidence >= 0.5);
  const stats = list => ({ intervals: list.length, invalid_dominant: list.filter(m => m.mineral_1 === 'INVALID').length, invalid_above_threshold: list.filter(m => m.mineral_1 === 'INVALID' && m.confidence >= 0.5).length, low_agreement: list.filter(m => m.confidence < 0.5).length });
  const report = { source_commit: 'baa66348aa4e4572af96cefa41b964299725fe13', hole: options.hole, total_samples: rows.length, raw_INVALID_samples: rows.filter(r => r.value_text === 'INVALID').length,
    before: stats(before), after: stats(after), example: { before: before[b], after: after[b] }, disclaimer: 'Offline verification of a proposed patch; not deployed. Confidence means dominant-group share of all samples, not model probability.' };
  fs.writeFileSync(path.join(__dirname, 'verification-result.json'), JSON.stringify(report, null, 2));
});


