const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const base = 'https://api.example.com';
const calls = [];
const sandbox = { URLSearchParams, fetch: async (url, options) => {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(60000) });
  const u = new URL(url);
  calls.push({ path: u.pathname, axis: u.searchParams.get('axis_id'),
    logIds: u.searchParams.getAll('log_ids').length, status: response.status });
  return response;
} };
vm.createContext(sandbox);
const source = fs.readFileSync(path.join(__dirname, '../frontend/lib/api.js'), 'utf8')
  .replace('import { API_BASE } from "@/config";', `const API_BASE = ${JSON.stringify(base)};`)
  .replace(/export const /g, 'const ');
vm.runInContext(source + '\nthis.api = { context, groupSamples, getMeasurements, getSpectralSample, intervals };', sandbox);
async function main() {
  const results = [];
  for (const [hole, depth, expectedParts, expectedEnd] of [['12CADD001', 400, 2, 538], ['15EIS001', 900, 4, 1702]]) {
    const parts = await sandbox.api.context(hole);
    const ms = await sandbox.api.getMeasurements(hole);
    const samples = await sandbox.api.groupSamples(hole);
    const spectrum = await sandbox.api.getSpectralSample(hole, depth);
    const trays = await sandbox.api.intervals(hole, 'tray');
    const result = { hole, parts: parts.map((p) => ({ name: p.name, revision: p.revision, from: p.from,
      to: Number.isFinite(p.to) ? p.to : null, retainedSamples: samples.filter((s) => s.part === p.part).length })),
      intervals: ms.length, from: ms[0]?.depth_from_m, to: ms.at(-1)?.depth_to_m,
      lowConfidence: ms.filter((m) => m.confidence < 0.5).length,
      invalidMinerals: ms.filter((m) => m.mineral_1 === 'INVALID').length,
      trays: trays.length, trayParts: [...new Set(trays.map((t) => t.part))],
      spectrum: { depth: spectrum.md_m, dataset: spectrum.dataset_name, sample: spectrum.sample_no,
        minerals: spectrum.minerals.length, regions: spectrum.spectra.map((s) => ({ region: s.region, channels: s.values.length })) } };
    assert.equal(parts.length, expectedParts);
    assert.equal(result.from, 0);
    assert.equal(result.to, expectedEnd);
    assert.equal(result.invalidMinerals, 0);
    assert.equal(result.trayParts.length, expectedParts);
    assert.equal(spectrum.spectra.length, 2);
    assert.ok(Math.abs(spectrum.md_m - depth) < 0.1);
    results.push(result);
    console.log(JSON.stringify(result));
  }
  assert.ok(calls.every((c) => c.status === 200));
  assert.ok(calls.every((c) => c.logIds <= 16));
  const report = { checkedAt: new Date().toISOString(), results, calls };
  fs.writeFileSync(path.join(__dirname, 'live-adapter-result.json'), JSON.stringify(report, null, 2));
  console.log('PASS: live reads, all batches <=16, 2-part and 4-part coverage verified');
}
main().catch((error) => {
  fs.writeFileSync(path.join(__dirname, 'live-adapter-error.json'), JSON.stringify({ message: error.message, calls }, null, 2));
  console.error(error); process.exitCode = 1;
});
