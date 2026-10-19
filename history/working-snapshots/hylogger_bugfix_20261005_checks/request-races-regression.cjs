const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const assert = require('node:assert/strict');
const { chromium } = require('C:/Users/USER/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

const repo = path.resolve(__dirname, '../hylogger_bugfix_20261005');
const frontend = path.join(repo, 'frontend');
const swc = require(path.join(frontend, 'node_modules/next/dist/build/swc'));
const sources = {
  Explore: 'frontend/app/page.js',
  Compare: 'frontend/app/compare/page.js',
  Viewer: 'frontend/app/viewer3d/page.js',
  Detail: 'frontend/components/HoleDetail.jsx',
};
const script = value => '<script>' + value.replace(/<\/script/gi, '<\\/script') + '</script>';

function createHarness(revision) {
  const compiled = Object.fromEntries(Object.entries(sources).map(([name, file]) => {
    const source = revision === 'original'
      ? execFileSync('git', ['show', `HEAD:${file}`], { cwd: repo, encoding: 'utf8' })
      : fs.readFileSync(path.join(repo, file), 'utf8');
    return [name, swc.transformSync(source, {
      jsc: { parser: { syntax: 'ecmascript', jsx: true }, transform: { react: { runtime: 'classic' } }, target: 'es2020' },
      module: { type: 'commonjs' },
    }).code];
  }));
  const setup = `
    const h = React.createElement;
    window.calls = [];
    window.unhandled = [];
    addEventListener('unhandledrejection', event => {
      window.unhandled.push(String(event.reason?.message || event.reason));
      event.preventDefault();
    });
    window.holes = ['A', 'B', 'C'].map((id, index) => ({
      hole_id: id, hole_name: 'Hole ' + id, borehole_length_m: 100,
      latitude: -29.2 + index, longitude: 119.5 + index,
      measurement_count: 1, anomaly_count: 0,
    }));
    const measurement = [{ depth_from_m: 0, depth_to_m: 10, mineral_1: 'QUARTZ', confidence: 0.9 }];
    window.deferred = [];
    const api = Object.fromEntries(['getHoles', 'getHole', 'getMeasurements', 'getTrays', 'getNearby', 'getSpectralSample', 'getDistance', 'getTrace'].map(name => [name, (...args) => {
      if (window.deferred.includes(name)) return new Promise((resolve, reject) => {
        window.calls.push({ name, args, resolve, reject, settled: false });
      });
      const defaults = {
        getHoles: window.holes,
        getHole: window.holes.find(hole => hole.hole_id === args[0]),
        getMeasurements: measurement, getTrays: [], getNearby: [], getSpectralSample: null,
        getTrace: { hole_id: args[0], points: [] },
      };
      return Promise.resolve(defaults[name]);
    }]));
    window.resolveCall = (name, arg, value, error = false) => {
      const call = window.calls.find(call => call.name === name && !call.settled &&
        (arg === null || JSON.stringify(call.args).includes(arg)));
      if (!call) throw Error('No pending ' + name + ' ' + arg);
      call.settled = true;
      error ? call.reject(Error(value)) : call.resolve(value);
    };
    function MapOr3D(props) {
      if ('traces' in props) return h('output', { id: 'traces' }, props.traces.map(t => t.hole_id).join(','));
      return h('div', null, props.holes.map(hole => h('button', {
        key: hole.hole_id, 'data-map-hole': hole.hole_id,
        onClick: () => (props.onSelect || props.onHover)?.(hole.hole_id),
      }, 'Map ' + hole.hole_id)));
    }
    function StripLog(props) {
      return h('output', { 'data-log-label': props.label || 'detail' }, props.measurements.map(m => m.depth_to_m).join(','));
    }
    const empty = () => null;
    const defaultModule = value => ({ __esModule: true, default: value });
    function require(name) {
      if (name === 'react') return React;
      if (name === 'next/dynamic') return defaultModule(() => MapOr3D);
      if (name === 'next/navigation') return { useSearchParams: () => new URLSearchParams('a=A&b=B') };
      if (name === 'next/link') return defaultModule(props => h('a', props));
      if (name === '@/lib/api') return api;
      if (name === '@/lib/format') return { distinctName: hole => hole?.hole_name || '' };
      if (name === '@/config') return { DEFAULT_VERTICAL_EXAGGERATION: 25, MINERAL_COLOURS: {}, ANOMALY_COLOUR: 'orange', LOW_CONFIDENCE_COLOUR: 'grey' };
      if (name.endsWith('StripLog')) return defaultModule(StripLog);
      return defaultModule(empty);
    }
    window.components = {};
    const root = ReactDOM.createRoot(document.getElementById('root'));
    window.mount = (name, defer, props) => {
      window.deferred = defer;
      root.render(h(window.components[name], props || {}));
    };
  `;
  const modules = Object.entries(compiled).map(([name, code]) => `{
    const exports = {}; ${code}\n window.components[${JSON.stringify(name)}] = exports.default;
  }`).join('\n');
  const html = '<!doctype html><html><head><meta charset="utf-8"><title>Request lifecycle regression</title></head><body><div id="root"></div>' +
    script(fs.readFileSync(path.join(frontend, 'node_modules/react/umd/react.development.js'), 'utf8')) +
    script(fs.readFileSync(path.join(frontend, 'node_modules/react-dom/umd/react-dom.development.js'), 'utf8')) +
    script(setup + modules) + '</body></html>';
  const file = path.join(__dirname, `request-races-${revision}.html`);
  fs.writeFileSync(file, html);
  return file;
}

async function pending(page, name, count = 1) {
  await page.waitForFunction(({name, count}) => window.calls.filter(call => call.name === name).length >= count, {name, count});
}
async function settle(page, name, arg, value, error = false) {
  await page.evaluate(({name, arg, value, error}) => window.resolveCall(name, arg, value, error), {name, arg, value, error});
  await page.waitForTimeout(60);
}
const hole = id => ({ hole_id: id, hole_name: 'Hole ' + id, borehole_length_m: 100 });
const results = [];

async function runCase(browser, file, revision, name, task) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  try {
    await page.goto('file:///' + file.replace(/\\/g, '/'));
    const observation = await task(page, revision === 'original');
    assert.deepEqual(pageErrors, [], 'No unexpected page errors');
    results.push({ revision, test: name, passed: true, observation });
    console.log(JSON.stringify(results.at(-1)));
  } catch (error) {
    results.push({ revision, test: name, passed: false, error: error.stack });
    console.error(JSON.stringify(results.at(-1)));
  } finally {
    await context.close();
  }
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const revision of ['original', 'working']) {
      const file = createHarness(revision);
      await runCase(browser, file, revision, 'search-old-response', async (page, original) => {
        await page.evaluate(() => mount('Explore', ['getHoles']));
        await pending(page, 'getHoles');
        await settle(page, 'getHoles', null, [hole('INITIAL')]);
        await page.locator('input[type=search]').fill('old');
        await pending(page, 'getHoles', 2);
        await page.locator('input[type=search]').fill('new');
        await pending(page, 'getHoles', 3);
        await settle(page, 'getHoles', 'new', [hole('NEW')]);
        await settle(page, 'getHoles', 'old', [hole('OLD')]);
        const ids = await page.locator('.hole-list .id').allTextContents();
        assert.deepEqual(ids, [original ? 'OLD' : 'NEW']);
        assert.equal(await page.locator('input[type=search]').inputValue(), 'new');
        return { query: 'new', displayed: ids };
      });
      await runCase(browser, file, revision, 'compare-reset-late-distance', async (page, original) => {
        await page.evaluate(() => mount('Compare', ['getMeasurements', 'getDistance']));
        await pending(page, 'getDistance');
        await page.getByRole('button', {name:'Reset', exact:true}).click();
        await settle(page, 'getDistance', null, {distance_km: 42, hole_a: {hole_id:'A'}, hole_b: {hole_id:'B'}});
        await settle(page, 'getMeasurements', 'A', [{depth_to_m:10}]);
        await settle(page, 'getMeasurements', 'B', [{depth_to_m:20}]);
        const distanceVisible = await page.locator('.distance-readout').count();
        assert.equal(distanceVisible, original ? 1 : 0);
        assert.equal(await page.getByRole('button', {name:'Reset', exact:true}).isDisabled(), true);
        return { selectionReset: true, staleDistanceVisible: Boolean(distanceVisible) };
      });
      await runCase(browser, file, revision, 'compare-swap-late-logs', async (page, original) => {
        await page.evaluate(() => mount('Compare', ['getMeasurements', 'getDistance']));
        await pending(page, 'getMeasurements', 2);
        await page.getByRole('button', {name:'Swap', exact:true}).click();
        await pending(page, 'getMeasurements', 4);
        await page.evaluate(() => {
          for (const call of calls.filter(c => c.name === 'getMeasurements').slice(2)) {
            call.settled = true;
            call.resolve([{depth_to_m: call.args[0] === 'A' ? 10 : 20}]);
          }
        });
        await page.waitForTimeout(60);
        await settle(page, 'getMeasurements', 'A', [{depth_to_m:10}]);
        await settle(page, 'getMeasurements', 'B', [{depth_to_m:20}]);
        const first = await page.locator('[data-log-label]').first().textContent();
        const label = await page.locator('[data-log-label]').first().getAttribute('data-log-label');
        assert.ok(label.startsWith('B'));
        assert.equal(first, original ? '10' : '20');
        return { firstLogLabel: label, displayedDepth: first, correctDepth: '20' };
      });
      await runCase(browser, file, revision, 'spectral-rejection', async (page, original) => {
        await page.evaluate(() => mount('Detail', ['getSpectralSample'], {holeId:'A'}));
        await pending(page, 'getSpectralSample');
        await settle(page, 'getSpectralSample', 'A', '503 spectral service unavailable', true);
        const unhandled = await page.evaluate(() => window.unhandled);
        const errorVisible = await page.getByText('Could not load spectral data:', {exact:false}).count();
        const loadingVisible = await page.getByText('Checking NVCL for a real spectrum here', {exact:false}).count();
        assert.equal(unhandled.length, original ? 1 : 0);
        assert.equal(errorVisible, original ? 0 : 1);
        assert.equal(loadingVisible, original ? 1 : 0);
        assert.equal(await page.getByText('Mineral log', {exact:true}).count(), 1);
        return { unhandled, spectralLoadingStuck: Boolean(loadingVisible), errorVisible: Boolean(errorVisible), mineralLogRetained: true };
      });
      await runCase(browser, file, revision, 'viewer-clear-late-trace', async (page, original) => {
        await page.evaluate(() => mount('Viewer', ['getTrace']));
        await pending(page, 'getTrace');
        await page.locator('.hole-list .hole-row').filter({has:page.locator('.id', {hasText:/^A$/})}).click();
        await settle(page, 'getTrace', 'A', {hole_id:'A', points:[]});
        assert.equal(await page.locator('.hole-list .selected').count(), 0);
        const traces = await page.locator('#traces').textContent();
        assert.equal(traces, original ? 'A' : '');
        return { selectedHoles: [], displayedTraceIds: traces };
      });
      await runCase(browser, file, revision, 'viewer-neighbours-rejection', async (page, original) => {
        await page.evaluate(() => mount('Viewer', ['getNearby']));
        await page.waitForSelector('.hole-list .selected');
        await page.getByRole('button', {name:'Add 5 nearest holes', exact:true}).click();
        await pending(page, 'getNearby');
        await settle(page, 'getNearby', 'A', '503 nearby service unavailable', true);
        const unhandled = await page.evaluate(() => window.unhandled);
        const errorVisible = await page.getByText('Could not add nearest holes:', {exact:false}).count();
        assert.equal(unhandled.length, original ? 1 : 0);
        assert.equal(errorVisible, original ? 0 : 1);
        assert.equal(await page.getByRole('button', {name:'Add 5 nearest holes', exact:true}).isEnabled(), true);
        return { unhandled, errorVisible: Boolean(errorVisible), retryEnabled: true };
      });
      await runCase(browser, file, revision, 'viewer-neighbours-after-selection-cleared', async (page, original) => {
        await page.evaluate(() => mount('Viewer', ['getNearby']));
        await page.waitForSelector('.hole-list .selected');
        await page.getByRole('button', {name:'Add 5 nearest holes', exact:true}).click();
        await pending(page, 'getNearby');
        await page.locator('.hole-list .selected').click();
        await settle(page, 'getNearby', 'A', [hole('B')]);
        const selected = await page.locator('.hole-list .selected .id').allTextContents();
        assert.deepEqual(selected, original ? ['B'] : []);
        return { userClearedSelection: true, selectedAfterLateResponse: selected };
      });
    }
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(__dirname, 'request-races-results.json'), JSON.stringify(results, null, 2));
  }
  if (results.some(result => !result.passed)) process.exitCode = 1;
})().catch(error => {console.error(error); process.exitCode = 1;});
