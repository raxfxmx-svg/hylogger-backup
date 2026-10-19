const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const frontend = path.join(root, 'frontend');
const localRequire = createRequire(path.join(frontend, 'package.json'));
const bundle = JSON.parse(fs.readFileSync(path.join(frontend, 'data/anomalies.json'), 'utf8'));
const expected = { '05KCD001': 2, '07THD002': 10, '07THD003': 6 };
const holeIds = [...Object.keys(expected), 'CONTROL'];
const plain = value => JSON.parse(JSON.stringify(value));
const read = file => fs.readFileSync(path.join(frontend, file), 'utf8');

function runtime({ baseline = false, live = {}, fail = [], samples = true } = {}) {
  const calls = [];
  const sandbox = { URLSearchParams, TextEncoder, setTimeout, clearTimeout, bundledAnomalies: bundle,
    fetch: async input => {
      const url = new URL(input); calls.push(url);
      let value;
      if (url.pathname === '/v1/boreholes') {
        value = { items: holeIds.map(hole_id => ({ hole_id, project: '', scan_from_m: 0, scan_to_m: 600,
          reported_length_m: 600, geometry: { coordinates: [120, -25] } })) };
      } else if (url.pathname.endsWith('/datasets')) {
        const hole = url.pathname.split('/')[3];
        value = { items: [{ dataset_revision_id: hole, axis_id: `axis-${hole}`, sample_count: 100 }] };
      } else {
        const [, hole, tail] = url.pathname.match(/^\/v1\/datasets\/([^/]+)\/(.+)$/) || [];
        if (tail === 'logs') value = { items: [{ log_id: 'group', source_log_name: 'Grp1 sTSAS',
          log_kind: 'scalar', metric_key: 'mineral_group', availability_status: 'payload_present', axis_binding_status: 'verified' }] };
        else if (tail === 'anomalies') {
          if (fail.includes(hole)) return { ok: false, status: 503 };
          value = { items: live[hole] || [], next_offset: null };
        } else if (tail === 'logs/group/values') {
          const depths = bundle.items.filter(a => a.hole_id === hole).map(a => a.depth_from_m);
          if (!depths.length) depths.push(20);
          value = { items: samples ? depths.flatMap((d, i) => ['CHLORITE', 'INVALID'].map((v, j) => ({
            sample_no: i * 2 + j, depth_m: d + .1 + j * .1, value_text: v, value_raw: v, status: 'available',
          }))) : [], next_after_sample: null };
        } else throw Error(`Unexpected request: ${url}`);
      }
      return { ok: true, status: 200, json: async () => value };
    },
  };
  vm.createContext(sandbox);
  const cache = read('lib/dataCache.js').replace(/export (const|function|async function) /g, '$1 ');
  const source = fs.readFileSync(path.join(baseline ? path.join(root, 'baseline/frontend') : frontend, 'lib/api.js'), 'utf8')
    .replace('import { API_BASE } from "@/config";', 'const API_BASE = "https://fixture.test";')
    .replace('import bundledAnomalies from "@/data/anomalies.json";', '')
    .replace('import { cached, CATALOG_TTL } from "./dataCache";', '')
    .replace('export { clearDataCache } from "./dataCache";', '')
    .replace(/export const /g, 'const ');
  vm.runInContext(cache + '\n' + source + '\nthis.api = {getAnomalies,getMeasurements,getHole,getHoles,getStats,getMineralLogs};', sandbox);
  return { api: sandbox.api, calls };
}

async function compileComponent(file, modules = {}, extra = '') {
  const swc = localRequire('next/dist/build/swc');
  const { code } = await swc.transform(read(file) + extra, {
    jsc: { parser: { syntax: 'ecmascript', jsx: true }, target: 'es2020', transform: { react: { runtime: 'automatic' } } },
    module: { type: 'commonjs' },
  });
  const exports = {};
  vm.runInNewContext(code, { exports, require: id => id in modules ? modules[id] : localRequire(id) });
  return exports;
}

(async () => {
  const result = { baseline: '0c4e96173f7f7bc4bde0164353d62ed985e75e18', holes: {}, checks: [] };
  const { api } = runtime();
  const base = runtime({ baseline: true }).api;
  for (const [hole, count] of Object.entries(expected)) {
    const anomalies = plain(await api.getAnomalies(hole));
    assert.equal(anomalies.length, count);
    assert.deepEqual(anomalies.map(a => a.anomaly_score), bundle.items.filter(a => a.hole_id === hole).map(a => a.anomaly_score));
    const data = await api.getHole(hole);
    assert.equal(data.anomaly_count, count);
    const unaffected = rows => plain(rows).map(({ is_anomaly, anomaly_score, score_reliability, why, ...m }) => m);
    assert.deepEqual(unaffected(await api.getMeasurements(hole)), unaffected(await base.getMeasurements(hole)));
    result.holes[hole] = { count, scores: anomalies.map(a => a.anomaly_score) };
  }
  assert.equal((await api.getStats()).anomalies, 18);
  assert.deepEqual(plain((await api.getHoles({ anomaliesOnly: true })).map(h => h.hole_id)), Object.keys(expected));
  result.checks.push('18 unchanged source scores; counts and filter agree; mineral calculations match current baseline');
  const duplicate = { ...bundle.items[0], anomaly_score: 99.12, score_reliability: 'medium', why: 'API result' };
  const merged = await runtime({ live: { '05KCD001': [duplicate, duplicate] } }).api.getAnomalies('05KCD001');
  assert.equal(merged.length, 2); assert.equal(merged[0].anomaly_score, 99.12);
  result.checks.push('API priority and duplicate removal');
  const unavailable = runtime({ fail: ['05KCD001', 'CONTROL'] }).api;
  assert.equal((await unavailable.getAnomalies('05KCD001')).length, 2);
  await assert.rejects(unavailable.getAnomalies('CONTROL'), /503/);
  result.checks.push('Supplied intervals remain available; unrelated holes retain error behaviour');
  const empty = runtime({ samples: false }).api;
  assert.equal((await empty.getMeasurements('07THD003')).length, 0);
  assert.equal((await empty.getStats()).anomalies, 18);
  result.checks.push('No mineral rows required to count anomaly intervals');
  const React = localRequire('react');
  const { renderToStaticMarkup } = localRequire('react-dom/server');
  const config = { ANOMALY_COLOUR: '#ffb347', CONFIDENCE_THRESHOLD: .5, LOW_CONFIDENCE_COLOUR: '#39424c',
    MINERAL_COLOURS: {}, mineralColour: () => '#22c55e', toRgb: () => [255, 179, 71] };
  const StripLog = (await compileComponent('components/StripLog.jsx', { '@/config': config })).default;
  const preview = [];
  let svgMarks = 0;
  for (const hole of Object.keys(expected)) {
    const anomalies = plain(await api.getAnomalies(hole));
    const svg = renderToStaticMarkup(React.createElement(StripLog, { measurements: [], anomalies }));
    assert.equal((svg.match(/aria-label="Anomaly /g) || []).length, expected[hole]);
    for (const a of anomalies) assert.ok(svg.includes(`score ${a.anomaly_score.toFixed(2)}`));
    svgMarks += expected[hole];
    const holeData = { ...plain(await api.getHole(hole)), has_full_spectrum: false };
    const states = [holeData, plain(await api.getMeasurements(hole)), [], [], null, null]; let cursor = 0;
    const Detail = (await compileComponent('components/HoleDetail.jsx', {
      react: { ...React, useState: () => [states[cursor++], () => {}], useEffect: () => {} },
      '@/config': config, '@/lib/api': {}, '@/lib/format': { distinctName: () => '' },
      'next/link': 'a', './StripLog': StripLog, './CoreTrays': () => null,
    })).default;
    const html = renderToStaticMarkup(React.createElement(Detail, { holeId: hole }));
    assert.ok(html.includes(`Unusual intervals (${expected[hole]})`));
    for (const a of anomalies) assert.ok(html.includes(`<td>${a.anomaly_score.toFixed(2)}</td>`));
    assert.ok(!/\u5386\u53f2|historical/i.test(html));
    preview.push(html);
  }
  result.checks.push(`${svgMarks} independently rendered 2D marks and all scores in detail tables; no historical labels`);
  class Layer { constructor(props) { this.props = props; } }
  const three = await compileComponent('components/Hole3D.jsx', {
    '@/lib/api': {}, '@/config': config, '@/lib/coreMesh': { segmentTransform: () => [] },
    'deck.gl': { COORDINATE_SYSTEM: {}, LineLayer: Layer, OrbitView: Layer, ScatterplotLayer: Layer, SimpleMeshLayer: Layer, TextLayer: Layer },
  }, '\nexport { describe, buildLayers };');
  const state = Object.fromEntries(Object.keys(expected).map(hole => [hole, { measurements: [], strip: {},
    anomalies: bundle.items.filter(a => a.hole_id === hole) }]));
  let marks3D = 0;
  for (const hole of Object.keys(expected)) {
    const scene = three.describe([hole], state);
    const layers = three.buildLayers(scene, [0, 600], 300, 600, 0, false, new Map(), () => {});
    const marks = layers.find(layer => layer.props.id === 'unusual').props.data;
    assert.equal(marks.length, expected[hole]);
    assert.ok(marks.every(mark => /score \d+\.\d{2}/.test(mark.label)));
    marks3D += marks.length;
  }
  result.checks.push(`${marks3D} 3D marks, each with its score, independent of mineral rows`);
  fs.writeFileSync(path.join(__dirname, 'display-check-result.json'), JSON.stringify(result, null, 2));
  fs.writeFileSync(path.join(__dirname, 'preview.html'), '<!doctype html><html><meta charset="utf-8"><title>Anomaly display preview</title><style>' + read('app/globals.css') + '\nbody{padding:24px;display:flex;gap:24px;align-items:flex-start}.detail{position:static;overflow:visible;width:350px;max-height:none}th{text-align:left}</style>' + preview.join('') + '</html>');
  console.log(JSON.stringify(result, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
