const exports = {};
const maps = [];
class MockMap {
  constructor() {
    this.handlers = {};
    this.sources = {};
    this.states = {};
    this.moves = [];
    this.layouts = {};
    this.loaded = false;
    this.canvas = { style: {} };
    maps.push(this);
  }
  addControl() {}
  on(event, layer, callback) {
    (this.handlers[event] ||= []).push(callback || layer);
  }
  once(event, callback) {
    const wrapper = data => {
      this.handlers[event] = this.handlers[event].filter(handler => handler !== wrapper);
      callback(data);
    };
    this.on(event, wrapper);
  }
  emit(event, holeId) {
    if (event === 'load') this.loaded = true;
    for (const handler of [...(this.handlers[event] || [])]) {
      handler({ features: [{ properties: { hole_id: holeId } }] });
    }
  }
  isStyleLoaded() { return this.loaded; }
  addSource(name, options) {
    this.sources[name] = { data: options.data, setData(data) { this.data = data; } };
  }
  addLayer() {}
  getSource(name) { return this.sources[name]; }
  setFeatureState(feature, state) { this.states[feature.id] = state; }
  easeTo(options) { this.moves.push(options); }
  setLayoutProperty(layer, property, value) { this.layouts[layer] = value; }
  getCanvas() { return this.canvas; }
  remove() { this.removed = true; }
}
class MockOverlay { setProps(props) { this.props = props; } }
function require(name) {
  if (name === 'react') return React;
  if (name === 'maplibre-gl') return { Map: MockMap, NavigationControl: class {}, ScaleControl: class {} };
  if (name.endsWith('.css')) return {};
  if (name === 'deck.gl') return { MapLibreOverlay: MockOverlay, PathLayer: class { constructor(props) { this.props = props; } } };
  if (name === '@/config') return { MAP_START: { longitude: 119, latitude: -29, zoom: 4 }, MAP_STYLE: {}, MAP_3D_DEFAULT_EXAGGERATION: 15, MAP_3D_DEFAULT_CORE_WIDTH_M: 25 };
  if (name === '@/lib/desurvey') return { desurveyStraightLine: () => null };
  if (name === './CoreStripPanel') return { __esModule: true, default: () => null };
  throw new Error('Unexpected dependency: ' + name);
}
window.runRegression = async function (HoleMap) {
  const results = [];
  const flush = () => new Promise(resolve => setTimeout(resolve, 10));
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const equal = (actual, expected, message) => assert(JSON.stringify(actual) === JSON.stringify(expected), message + ': ' + JSON.stringify(actual));
  const holes = [
    { hole_id: 'A', longitude: 119, latitude: -29 },
    { hole_id: 'B', longitude: 120, latitude: -30 },
    { hole_id: 'C', longitude: 121, latitude: -31 },
  ];
  let root;
  const render = async props => {
    ReactDOM.flushSync(() => root.render(React.createElement(HoleMap, props)));
    await flush();
  };
  async function test(name, body) {
    root = ReactDOM.createRoot(document.getElementById('root'));
    try {
      await body();
      results.push({ name, passed: true });
    } catch (error) {
      results.push({ name, passed: false, error: error.message });
    } finally {
      ReactDOM.flushSync(() => root.unmount());
      await flush();
    }
  }
  await test('API completes before map load; latest data, highlight, controls synchronize', async () => {
    await render({ holes: [] });
    const map = maps.at(-1);
    await render({ holes, selectedId: 'A', selectedIdB: 'B', flyToId: null });
    document.querySelectorAll('button')[1].click();
    document.querySelector('input[type="checkbox"]').click();
    await flush();
    map.emit('load');
    await flush();
    equal(map.sources.holes.data.features.map(feature => feature.id), ['A', 'B', 'C'], 'Loaded marker IDs');
    equal(map.states.A, { selectedA: true, selectedB: false }, 'A is highlighted');
    equal(map.states.B, { selectedA: false, selectedB: true }, 'B is highlighted');
    equal(map.layouts, { satellite: 'none', light: 'visible' }, 'Pre-load basemap choice');
    assert(map.moves.some(move => move.pitch === 55), 'Pre-load 3D choice must tilt camera');
  });
  await test('map load before API response also receives markers', async () => {
    await render({ holes: [] });
    const map = maps.at(-1);
    map.emit('load');
    await flush();
    await render({ holes });
    equal(map.sources.holes.data.features.map(feature => feature.id), ['A', 'B', 'C'], 'Late marker IDs');
  });
  await test('Compare hover picks A then B and click uses current callback', async () => {
    let selection;
    function Compare() {
      const [a, setA] = React.useState('');
      const [b, setB] = React.useState('');
      selection = { a, b };
      const select = id => { if (!a) setA(id); else if (id !== a) setB(id); };
      return React.createElement(HoleMap, { holes, selectedId: a, selectedIdB: b, onHover: select, onSelect: select, flyToSelection: false });
    }
    ReactDOM.flushSync(() => root.render(React.createElement(Compare)));
    await flush();
    const map = maps.at(-1);
    map.emit('load');
    await flush();
    map.emit('mousemove', 'A');
    await flush();
    map.emit('mousemove', 'B');
    await flush();
    equal(selection, { a: 'A', b: 'B' }, 'A/B after two hovers');
    map.emit('click', 'C');
    await flush();
    equal(selection, { a: 'A', b: 'C' }, 'A/B after click');
  });
  await test('Explore initial hover does not move camera; explicit click does', async () => {
    await render({ holes, selectedId: 'A', flyToId: null });
    const map = maps.at(-1);
    map.emit('load');
    await flush();
    await render({ holes, selectedId: 'B', flyToId: null });
    assert(!map.moves.some(move => move.center), 'Hover must not move camera before a click');
    await render({ holes, selectedId: 'B', flyToId: 'A' });
    equal(map.moves.filter(move => move.center).map(move => move.center), [[119, -29]], 'Clicked hole camera target');
  });
  await test('StrictMode cleanup recreates a working map', async () => {
    const before = maps.length;
    ReactDOM.flushSync(() => root.render(React.createElement(React.StrictMode, null, React.createElement(HoleMap, { holes, selectedId: 'A' }))));
    await flush();
    assert(maps.length === before + 2, 'StrictMode should mount twice');
    assert(maps[before].removed, 'Discarded map should be removed');
    const map = maps.at(-1);
    map.emit('load');
    await flush();
    equal(map.sources.holes.data.features.map(feature => feature.id), ['A', 'B', 'C'], 'Remounted markers');
    assert(map.states.A.selectedA, 'Remounted selection');
  });
  window.testResults = results;
  document.body.appendChild(Object.assign(document.createElement('pre'), { textContent: JSON.stringify(results, null, 2) }));
};
