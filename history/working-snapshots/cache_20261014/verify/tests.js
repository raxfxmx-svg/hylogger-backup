const output = document.querySelector('#results');
output.textContent = '';
let passed = 0, serial = 0;
const assert = (ok, message) => { if (!ok) throw Error(message); };
const fresh = () => import(`/cache.js?test=${Date.now()}-${serial++}`);
const db = await new Promise((resolve, reject) => {
  const r = indexedDB.open('hylogger-data-v1', 1);
  r.onupgradeneeded = () => { r.result.createObjectStore('entries', {keyPath:'key'}); r.result.createObjectStore('metadata', {keyPath:'key'}); };
  r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error);
});
const entries = () => new Promise(resolve => { const r = db.transaction('entries').objectStore('entries').getAll(); r.onsuccess = () => resolve(r.result); });
const test = async (name, fn) => { try { await fn(); passed++; output.textContent += `PASS ${name}\n`; } catch(e) { output.textContent += `FAIL ${name}: ${e.stack}\n`; throw e; } };
let now = Date.now();
const realNow = Date.now;
Date.now = () => now;
try {
  let cache = await fresh();
  await cache.clearDataCache();
  await test('Concurrent calls share one loader and completed memory result', async () => {
    let calls = 0;
    const load = async () => { calls++; await new Promise(r => setTimeout(r, 5)); return [1,2]; };
    const result = await Promise.all([cache.cached('shared', load), cache.cached('shared', load)]);
    await cache.cached('shared', load);
    assert(calls === 1 && result.every(x => x.length === 2), 'Duplicate request');
  });
  await test('Fresh module restores committed IndexedDB data without API calls', async () => {
    cache = await fresh();
    const value = await cache.cached('shared', () => { throw Error('Should not load'); });
    assert(value[1] === 2, 'Persistent result missing');
  });
  await test('Reading cache does not extend TTL; expired data is fetched again', async () => {
    await cache.cached('ttl', () => 'old', {ttl:100});
    now += 90; cache = await fresh();
    assert(await cache.cached('ttl', () => 'wrong', {ttl:100}) === 'old', 'Early expiry');
    now += 11;
    assert(await cache.cached('ttl', () => 'new', {ttl:100}) === 'new', 'TTL was extended');
  });
  await test('Rejected loads are never saved and the next call retries', async () => {
    try { await cache.cached('failure', () => Promise.reject(Error('503'))); } catch {}
    assert(!(await entries()).some(x => x.key === 'failure'), 'Error saved');
    assert(await cache.cached('failure', () => 'recovered') === 'recovered', 'Failure retained');
  });
  await test('Memory-only raw samples do not persist across reloads', async () => {
    await cache.cached('raw', () => [1], {persist:false});
    cache = await fresh();
    assert((await cache.cached('raw', () => [2], {persist:false}))[0] === 2, 'Raw samples persisted');
    assert(!(await entries()).some(x => x.key === 'raw'), 'Raw record written');
  });
  await test('Clear removes saved results and blocks an old in-flight write', async () => {
    let release;
    const old = cache.cached('inflight', () => new Promise(r => { release = r; }));
    while (!release) await new Promise(r => setTimeout(r, 1));
    await cache.clearDataCache(); release('stale'); await old;
    assert((await entries()).length === 0, 'In-flight load repopulated storage');
    assert(await cache.cached('inflight', () => 'fresh') === 'fresh', 'Old memory survived');
  });
  await test('Oversized results still display but are not persisted', async () => {
    const big = 'x'.repeat(2*1024*1024);
    assert((await cache.cached('large', () => big)).length === big.length, 'Lost API result');
    assert(!(await entries()).some(x => x.key === 'large'), 'Oversized record saved');
  });
  await test('Persistent count is bounded and oldest entries are evicted', async () => {
    await cache.clearDataCache();
    for (let i=0; i<2051; i++) { now++; await cache.cached(`bounded:${i}`, () => i); }
    const rows = await entries();
    assert(rows.length === 2048 && !rows.some(x => x.key === 'bounded:0') && rows.some(x => x.key === 'bounded:2050'), 'Eviction failed');
  });
  await test('Storage permission failure falls back to the loader', async () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, 'indexedDB');
    Object.defineProperty(window, 'indexedDB', {configurable:true,value:{open(){throw Error('SecurityError');}}});
    try { const restricted = await fresh(); assert(await restricted.cached('blocked', () => 42) === 42, 'Storage blocked data'); }
    finally { Object.defineProperty(window, 'indexedDB', descriptor); }
  });
  await cache.clearDataCache();
  output.textContent += `\n${passed} / ${passed} passed using real browser IndexedDB.\n`;
} catch {} finally { Date.now = realNow; db.close(); }
