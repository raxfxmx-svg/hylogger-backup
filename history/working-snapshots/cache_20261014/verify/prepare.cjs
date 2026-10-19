const fs = require('node:fs');
const path = require('node:path');
const fixtureRoot = path.resolve(__dirname, '../../live_diagnosis_20261008');
let test = fs.readFileSync(path.join(fixtureRoot, 'invalid_review/verify.cjs'), 'utf8');
test = test.replace('const root = path.dirname(__dirname);', `const root = ${JSON.stringify(fixtureRoot)};`);
test = test.replace("path.join(__dirname, 'proposal/frontend/lib/api.js')", "path.join(__dirname, '../frontend/lib/api.js')");
test = test.replace('    URLSearchParams,', '    URLSearchParams, TextEncoder, setTimeout, clearTimeout,');
test = test.replace('      let body;', '      if (options.failAnomalies && endpoint.endsWith("/anomalies")) return {ok:false,status:503};\n      let body;');
test = test.replace('  const runnable = source.replace', `  const cacheSource = fs.readFileSync(path.join(__dirname, '../frontend/lib/dataCache.js'), 'utf8').replace(/export /g, '');
  source = source.replace('import { cached, CATALOG_TTL } from "./dataCache";', '').replace('export { clearDataCache } from "./dataCache";', '');
  const prefix = source.includes('datasetOnce') ? cacheSource + '\\n' : '';
  const runnable = prefix + source.replace`);
test += `
test('adapter rejects failed anomalies and retries instead of caching unflagged intervals', async () => {
  const options = {failAnomalies:true};
  const {api,calls} = adapter(proposed, [sample('CHLORITE',0)], options);
  await assert.rejects(api.getMeasurements('TEST'), /503/);
  options.failAnomalies = false;
  options.anomalies = [{depth_from_m:10,depth_to_m:11,anomaly_score:99}];
  const result = await api.getMeasurements('TEST');
  assert.equal(result[0].is_anomaly,true);
  assert.equal(calls.filter(p => p.endsWith('/anomalies')).length,2);
  const before = calls.length;
  await api.getMeasurements('TEST');
  assert.equal(calls.length,before);
});
`;
fs.writeFileSync(path.join(__dirname, 'adapter.test.cjs'), test);
