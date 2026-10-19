const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const row = (sample_no, depth_m, value_text = 'CHLORITE') =>
  ({ sample_no, depth_m, value_text, value_raw: value_text, status: 'available' });
const log = (log_id, extra = {}) => ({ log_id, source_log_name: log_id,
  availability_status: 'payload_present', axis_binding_status: 'verified', ...extra });
const group = (region = 'SWIR') => log(region, { source_log_name: `Grp1 ${region}`,
  output_region: region, log_kind: 'scalar', metric_key: 'mineral_group' });
const spectralLogs = () => [
  ...Array.from({ length: 16 }, (_, i) => log(`min${i}`, { log_kind: 'scalar', metric_key: 'mineral_name' })),
  ...['VSWIR', 'TIR'].map((region) => log(`spectrum${region}`, { log_kind: 'spectral', region_code: region })),
];
function part(revision, start, depths, mineral = 'CHLORITE') {
  return {
    dataset_revision_id: revision, axis_id: `axis-${revision}`, source_dataset_name: revision,
    sample_count: depths.length, depth_min_m: start, depth_max_m: Math.max(...depths),
    logs: [group(), group('TIR'), ...spectralLogs()],
    swir: depths.map((d, i) => row(i, d, mineral)),
    tir: depths.map((d, i) => row(i, d, `${mineral}-TIR`)),
    intervals: [{ ordinal: 0, sample_no_from: 0, sample_no_to: depths.length - 1 }],
    anomalies: [],
  };
}
function fixture(parts, options = {}) {
  const calls = [];
  let spectralFailures = options.spectralFailures || 0;
  async function request(input) {
    const url = new URL(input, 'http://localhost:8000');
    calls.push(url);
    const p = url.pathname;
    if (p === '/v1/boreholes') return { items: options.holes || [{ hole_id: 'TEST', project: 'Splice regression fixture',
      geometry: { coordinates: [116.5, -31] }, reported_length_m: 20, scan_from_m: 0, scan_to_m: 20 }] };
    if (p === '/v1/boreholes/nearby') {
      if (options.failNearby) throw Object.assign(new Error('fixture nearby failure'), { status: 503 });
      return { items: [] };
    }
    if (p === '/v1/boreholes/TEST/datasets') return { items: parts.map(({ logs, swir, tir, intervals, anomalies, ...meta }) => meta) };
    const match = p.match(/^\/v1\/datasets\/([^/]+)\/(.*)$/);
    if (!match) throw new Error(`Unexpected URL ${url}`);
    const part = parts.find((part) => part.dataset_revision_id === match[1]);
    if (!part) throw new Error(`Unexpected revision ${url}`);
    const tail = match[2];
    if (tail === 'logs') return { items: part.logs };
    if (url.searchParams.get('axis_id') !== part.axis_id) throw new Error(`Wrong axis ${url}`);
    if (tail === 'anomalies' || tail === 'intervals') {
      if (tail === 'intervals' && options.failTrays && url.searchParams.get('kind') === 'tray') {
        throw Object.assign(new Error('fixture tray failure'), { status: 503 });
      }
      const data = part[tail];
      const offset = Number(url.searchParams.get('offset'));
      const size = options.pageSize || Number(url.searchParams.get('limit'));
      const items = data.slice(offset, offset + size);
      return { items, next_offset: offset + size < data.length ? offset + size : null };
    }
    if (tail.startsWith('logs/')) {
      const id = tail.split('/')[1];
      const data = id === 'SWIR' ? part.swir : id === 'TIR' ? part.tir : null;
      if (!data) throw new Error(`Unexpected log ${url}`);
      const after = Number(url.searchParams.get('after_sample'));
      const size = options.pageSize || Number(url.searchParams.get('limit'));
      const rest = data.filter((s) => s.sample_no > after);
      const items = rest.slice(0, size);
      return { items, next_after_sample: rest.length > size ? items.at(-1).sample_no : null };
    }
    if (tail.startsWith('samples/')) {
      const no = Number(tail.split('/')[1]);
      const ids = url.searchParams.getAll('log_ids');
      if (ids.length > 16) throw Object.assign(new Error('At most 16 log IDs'), { status: 422 });
      const photosOnly = url.searchParams.get('include_results') === 'false';
      if (!photosOnly && spectralFailures-- > 0) throw Object.assign(new Error('fixture spectral failure'), { status: 503 });
      const results = photosOnly ? [] : ids.map((id) => {
        const entry = part.logs.find((l) => l.log_id === id);
        return { ...entry, status: 'available', value: { value_text: id === 'min0' ? 'INVALID' : `MINERAL-${id}` },
          spectra: entry.log_kind === 'spectral' ? [0.2, 0.8, 0.4] : null,
          wavelength: [500, 501, 502], wavelength_unit: 'nm' };
      });
      return { sample_no: no, sample_count: part.sample_count, md_m: part.swir[no]?.depth_m,
        results, images: [{ status: 'available', image_asset_id: `photo-${part.dataset_revision_id}`,
          width_px: 400, height_px: 25, source_depth_direction: part.direction || 'left_to_right' }] };
    }
    throw new Error(`Unexpected URL ${url}`);
  }
  async function fetch(input) {
    try { const body = await request(input); return { ok: true, status: 200, json: async () => body }; }
    catch (error) { if (!error.status) throw error; return { ok: false, status: error.status }; }
  }
  const source = fs.readFileSync(path.join(__dirname, '../lib/api.js'), 'utf8')
    .replace('import { API_BASE } from "@/config";', 'const API_BASE = "http://localhost:8000";')
    .replace(/export const /g, 'const ');
  const sandbox = { URLSearchParams, fetch };
  vm.createContext(sandbox);
  vm.runInContext(source + '\nthis.api = { getHoles, getHole, getMeasurements, getMineralLogs, getStats, getTrays, getCoreStrip, getSpectralSample, groupName, groupSamples, holeAnomalies, intervals };', sandbox);
  return { api: sandbox.api, calls, request };
}
module.exports = { row, log, group, part, fixture };
