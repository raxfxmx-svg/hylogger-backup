const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const baseline = path.resolve(root, '../rollback_cache_20261016');
const changed = ['lib/api.js', 'components/HoleDetail.jsx', 'components/StripLog.jsx',
  'components/CoreStripPanel.jsx', 'components/Hole3D.jsx', 'package.json'];
const added = ['test/api-fixture.cjs', 'test/api.test.cjs', 'test/photo.test.cjs'];
const source = (folder, file) => fs.readFileSync(path.join(folder, 'frontend', file), 'utf8');
const before = source(baseline, 'lib/api.js');
const after = source(root, 'lib/api.js');
const slice = (s, start, end) => s.slice(s.indexOf(start), s.indexOf(end, s.indexOf(start)));
for (const [start, end] of [
  ['export const getHoles =', 'export const getHole ='],
  ['export const getMineralLogs =', '// ------------------------------------------------------- where holes are'],
  ['const cache = new Map();', '// ---------------------------------------------------------------- holes'],
  ['async function pool(', '// One promise per key'],
]) assert.equal(slice(after, start, end), slice(before, start, end));
assert.ok(after.includes('holeAnomalies(holeId).catch(() => [])'));
assert.ok(after.includes('l.metric_key === "mineral_group"'));
assert.ok(after.includes('["ASPECTRAL", "NULL", "INVALID"].includes(name)'));
assert.equal(fs.existsSync(path.join(root, 'frontend/lib/dataCache.js')), false);
const tree = JSON.parse(fs.readFileSync(path.join(root, 'reference/base-tree.json'), 'utf8'));
for (const file of changed) {
  const b = Buffer.from(source(baseline, file));
  const sha = crypto.createHash('sha1').update(`blob ${b.length}\0`).update(b).digest('hex');
  assert.equal(sha, tree.find((item) => item.path === `frontend/${file}`).sha, `Base file mismatch: ${file}`);
}
let patch = '';
for (const file of changed) {
  const r = spawnSync('git', ['-c', 'core.autocrlf=false', '-c', 'core.quotepath=false', 'diff', '--no-index', '--no-color', '--',
    path.join(baseline, 'frontend', file), path.join(root, 'frontend', file)], { encoding: 'utf8' });
  assert.equal(r.status, 1, r.stderr);
  patch += r.stdout.replace(/^diff --git .*$/m, `diff --git a/frontend/${file} b/frontend/${file}`)
    .replace(/^--- .*$/m, `--- a/frontend/${file}`).replace(/^\+\+\+ .*$/m, `+++ b/frontend/${file}`);
}
for (const file of added) {
  const content = source(root, file).replace(/\r\n/g, '\n');
  const lines = content.replace(/\n$/, '').split('\n');
  patch += `diff --git a/frontend/${file} b/frontend/${file}\nnew file mode 100644\n--- /dev/null\n+++ b/frontend/${file}\n@@ -0,0 +1,${lines.length} @@\n` + lines.map((line) => '+' + line).join('\n') + '\n';
}
const destination = path.join(root, 'frontend-repairs.patch');
fs.writeFileSync(destination, patch);
const check = spawnSync('git', ['apply', '--check', destination], { cwd: baseline, encoding: 'utf8' });
assert.equal(check.status, 0, check.stderr);
const report = { base_commit: 'aacb5df1085e0ad1b4b8f1fef21b928ba91c5a6c', checkedAt: new Date().toISOString(),
  changed: changed.map((p) => 'frontend/' + p), added: added.map((p) => 'frontend/' + p),
  global_concurrency_and_failure_handling_unchanged: true, persistent_cache_absent: true,
  mineral_group_and_INVALID_fixes_preserved: true, patch_apply_check: 'passed',
  patch_sha256: crypto.createHash('sha256').update(patch).digest('hex') };
fs.writeFileSync(path.join(__dirname, 'scope-and-patch-result.json'), JSON.stringify(report, null, 2));
console.log(report);
