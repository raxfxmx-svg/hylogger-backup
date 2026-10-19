const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { part, fixture } = require('../frontend/test/api-fixture.cjs');
async function main() {
  const rows = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../live_diagnosis_20261008/07THD003-all-values.json'), 'utf8').replace(/^\uFEFF/, ''));
  const p = part('07THD003', 64, []);
  p.swir = rows;
  p.sample_count = rows.length;
  const { api } = fixture([p]);
  const ms = await api.getMeasurements('TEST');
  const result = { raw_samples: rows.length, raw_INVALID: rows.filter((s) => s.value_text === 'INVALID').length,
    intervals: ms.length, low_confidence: ms.filter((m) => m.confidence < 0.5).length,
    INVALID_minerals: ms.filter((m) => m.mineral_1 === 'INVALID').length,
    from: ms[0].depth_from_m, to: ms.at(-1).depth_to_m };
  assert.deepEqual(result, { raw_samples: 54432, raw_INVALID: 21403, intervals: 188,
    low_confidence: 150, INVALID_minerals: 0, from: 64, to: 252 });
  fs.writeFileSync(path.join(__dirname, 'real-fixture-result.json'), JSON.stringify(result, null, 2));
  console.log(result);
}
main().catch((e) => { console.error(e); process.exitCode = 1; });
