const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
// Exercise the canvas crop operation with a recorded drawing context. A
// reversed photo must crop its opposite end before rotating it into depth.
function crop(row) {
  const source = fs.readFileSync(path.join(__dirname, '../components/Hole3D.jsx'), 'utf8');
  const start = source.indexOf('function uprightRow(');
  const end = source.indexOf('\nfunction intervalColour(', start);
  const calls = [];
  const ctx = Object.fromEntries(['translate', 'rotate', 'scale', 'drawImage'].map((method) =>
    [method, (...args) => calls.push([method, ...args])]));
  const canvas = { getContext: () => ctx };
  const sandbox = { document: { createElement: () => canvas } };
  vm.createContext(sandbox);
  vm.runInContext(source.slice(start, end) + '\nthis.crop = uprightRow;', sandbox);
  sandbox.crop({ naturalWidth: 400, naturalHeight: 25 }, row);
  return { canvas, calls, draw: calls.find((c) => c[0] === 'drawImage').slice(2) };
}
test('normal and reversed photos crop to the same depth window without stretching', () => {
  const normal = crop({ crop_from: 0.25, crop_to: 0.5, flip: false });
  const reverse = crop({ crop_from: 0.25, crop_to: 0.5, flip: true });
  assert.deepEqual(normal.draw, [100, 0, 100, 25, 0, 0, 100, 25]);
  assert.deepEqual(reverse.draw, [200, 0, 100, 25, 0, 0, 100, 25]);
  assert.equal(normal.canvas.height, 100);
  assert.equal(reverse.canvas.height, 100);
  assert.equal(reverse.canvas.width, 25);
  assert.ok(reverse.calls.some((c) => c[0] === 'scale' && c[1] === -1));
});
test('legacy full photos without splice crop metadata retain their whole width', () => {
  assert.deepEqual(crop({}).draw, [0, 0, 400, 25, 0, 0, 400, 25]);
});
