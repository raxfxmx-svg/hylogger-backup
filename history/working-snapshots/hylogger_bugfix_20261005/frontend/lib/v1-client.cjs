const { createApiClient, requireArray } = require('./api-client.cjs');

const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const datasetKey = (d) => `${d.dataset_revision_id}:${d.axis_id}`;

function normaliseBoreholes(rows) {
  const byId = new Map();
  for (const row of requireArray(rows)) {
    if (!row || typeof row.hole_id !== 'string') throw new Error('Invalid borehole catalogue.');
    const coordinates = row.geometry?.type === 'Point' ? row.geometry.coordinates : [];
    const located = Array.isArray(coordinates) && finite(coordinates[0]) && finite(coordinates[1]) &&
      Math.abs(coordinates[0]) <= 180 && Math.abs(coordinates[1]) <= 90;
    const previous = byId.get(row.hole_id);
    if (!previous) {
      byId.set(row.hole_id, {
        ...row, hole_name: row.source_name || row.project || row.hole_id,
        longitude: located ? coordinates[0] : null, latitude: located ? coordinates[1] : null,
        borehole_length_m: finite(row.reported_length_m) ? row.reported_length_m : null,
        catalogue_rows: 1,
      });
    } else {
      previous.catalogue_rows++;
      // Different datasets can describe one hole. Do not pick an arbitrary collar.
      if (!located || previous.longitude !== coordinates[0] || previous.latitude !== coordinates[1]) {
        previous.longitude = previous.latitude = null;
        previous.location_status = 'conflicting_or_missing';
      }
      if (previous.borehole_length_m !== row.reported_length_m) previous.borehole_length_m = null;
    }
  }
  return [...byId.values()];
}

function pageQuery({ axis_id, from_m, to_m, after_sample = -1, limit = 100 }) {
  if (!axis_id) throw new Error('Select a sample axis first.');
  if (from_m != null && !finite(from_m) || to_m != null && !finite(to_m) ||
      from_m != null && to_m != null && from_m > to_m) throw new Error('Enter a valid depth range.');
  const query = new URLSearchParams({ axis_id, after_sample: String(after_sample), limit: String(limit) });
  if (from_m != null) query.set('from_m', from_m);
  if (to_m != null) query.set('to_m', to_m);
  return query.toString();
}

function joinSampleValues(samples, values) {
  const bySample = new Map(requireArray(values).map(v => [v.sample_no, v]));
  return requireArray(samples).map(s => ({ ...s, result: bySample.get(s.sample_no) ?? null }));
}

function createV1Client(base, fetcher) {
  // Accept an origin or the old /api base setting during migration.
  const origin = (base || '').replace(/\/+$/, '').replace(/\/api$/, '');
  // Aurora can need up to 60 seconds to resume from an idle state.
  const get = createApiClient(origin, fetcher, 90000);
  const enc = encodeURIComponent;
  const items = async (path) => requireArray((await get(path)).items);
  return {
    holes: async () => normaliseBoreholes(await items('/v1/boreholes')),
    datasets: (hole) => items(`/v1/boreholes/${enc(hole)}/datasets`),
    logs: (revision) => items(`/v1/datasets/${enc(revision)}/logs`),
    samples: (revision, options) => get(`/v1/datasets/${enc(revision)}/samples?${pageQuery(options)}`),
    values: (revision, log, options) => get(`/v1/datasets/${enc(revision)}/logs/${enc(log)}/values?${pageQuery(options)}`),
    sample: (revision, axis, number, log, imageLog) => {
      if (!Number.isSafeInteger(number) || number < 0) throw new Error('Enter a valid sample number.');
      const q = new URLSearchParams({ axis_id: axis, include_results: log ? 'true' : 'false' });
      if (log) q.set('log_ids', log);
      if (imageLog) q.set('image_log_id', imageLog);
      return get(`/v1/datasets/${enc(revision)}/samples/${number}?${q}`);
    },
    anomalies: (revision, axis, offset = 0) => get(`/v1/datasets/${enc(revision)}/anomalies?${new URLSearchParams({axis_id:axis, offset, limit:100})}`),
    issues: (revision) => get(`/v1/datasets/${enc(revision)}/issues`),
    imageUrl: (asset) => origin ? `${origin}/v1/image-assets/${enc(asset)}/content` : '',
  };
}

module.exports = { createV1Client, normaliseBoreholes, datasetKey, pageQuery, joinSampleValues };
