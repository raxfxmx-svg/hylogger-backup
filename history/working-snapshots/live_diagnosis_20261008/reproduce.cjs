const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const read = name => JSON.parse(fs.readFileSync(path.join(__dirname, name), 'utf8').replace(/^\uFEFF/, ''));
const source = fs.readFileSync(path.join(__dirname, 'source/frontend/lib/api.js'), 'utf8');
const logs = read('07THD003-logs.json');
const values = read('07THD003-all-values.json');
const anomalies = read('07THD003-anomalies.json');
const revision = '87ff003a-7ec9-54b6-9927-d2a518e34aae';
const axis = '9c84fbf6-6513-5200-a71a-c303713a122c';
const dataset = { dataset_revision_id: revision, axis_id: axis, sample_count: 54432 };

async function replay(mode) {
  let code = source;
  if (mode !== 'original') {
    const target = 'l.metric_key === "mineral_name" && usable(l)';
    assert.equal(code.split(target).length, 2);
    code = code.replace(target, 'l.metric_key === "mineral_group" && usable(l)');
  }
  if (mode === 'metric_and_invalid') {
    code = code.replace('name === "ASPECTRAL" || name === "NULL"', 'name === "ASPECTRAL" || name === "NULL" || name === "INVALID"');
  }
  const calls = [];
  const context = {
    URLSearchParams,
    fetch: async url => {
      const u = new URL(url);
      calls.push(u.pathname);
      let payload;
      if (u.pathname === '/v1/boreholes/07THD003/datasets') payload = { items: [dataset] };
      else if (u.pathname === `/v1/datasets/${revision}/logs`) payload = logs;
      else if (u.pathname === `/v1/datasets/${revision}/anomalies`) payload = anomalies;
      else if (u.pathname === `/v1/datasets/${revision}/logs/cf2ee947-090f-50aa-b787-c234f64ac9c0/values`) {
        const after = Number(u.searchParams.get('after_sample'));
        const limit = Number(u.searchParams.get('limit'));
        const remaining = values.filter(row => row.sample_no > after);
        const items = remaining.slice(0, limit);
        payload = { items, next_after_sample: remaining.length > limit ? items.at(-1).sample_no : null };
      } else throw new Error(`Unexpected replay request: ${u.pathname}`);
      return { ok: true, json: async () => payload };
    }
  };
  vm.createContext(context);
  code = code.replace('import { API_BASE } from "@/config";', 'const API_BASE = "https://recorded-api.example";').replace(/export const /g, 'const ');
  vm.runInContext(code + '\nthis.replayApi = { getMeasurements, groupLog, groupName };', context);
  const selected = context.replayApi.groupLog(logs.items, 'SWIR');
  const measurements = await context.replayApi.getMeasurements('07THD003');
  const counts = {};
  for (const m of measurements) counts[m.mineral_1 ?? 'missing'] = (counts[m.mineral_1 ?? 'missing'] ?? 0) + 1;
  return { mode, selected_log: selected?.source_log_name ?? null, interval_count: measurements.length,
    depth_from_m: measurements[0]?.depth_from_m ?? null, depth_to_m: measurements.at(-1)?.depth_to_m ?? null,
    dominant_interval_counts: counts, invalid_high_confidence_intervals: measurements.filter(m => m.mineral_1 === 'INVALID' && m.confidence >= 0.5).length,
    scalar_page_requests: calls.filter(p => p.endsWith('/values')).length };
}

(async () => {
  const results = [];
  for (const mode of ['original', 'metric_only', 'metric_and_invalid']) results.push(await replay(mode));
  assert.equal(results[0].interval_count, 0);
  assert.equal(results[1].interval_count, 188);
  assert.equal(results[1].selected_log, 'Grp1 sTSAS');
  assert.equal(results[2].dominant_interval_counts.INVALID, undefined);
  const report = { source_commit: 'baa66348aa4e4572af96cefa41b964299725fe13', hole: '07THD003',
    scope: 'Offline replay of current frontend adapter using real captured API catalogue and all 54432 scalar rows. No deployed code or AWS settings modified.', results };
  fs.writeFileSync(path.join(__dirname, 'reproduction-result.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
