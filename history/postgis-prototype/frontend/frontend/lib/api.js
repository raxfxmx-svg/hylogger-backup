// Adapter between this frontend's original Django-shaped contract and the
// demo2 read-only FastAPI contract. Keeping the translation here lets the UI
// stay focused on presentation and keeps PostgreSQL access behind the API.

import { API_BASE } from "@/config";

const BASE = API_BASE.replace(/\/$/, "");

async function get(path) {
  const response = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(
      `${response.status} from ${path}. Is the demo2 API running on ${BASE}?`
    );
  }
  return response.json();
}

function assetUrl(path) {
  if (!path) return null;
  return new URL(path, new URL(BASE).origin).toString();
}

function normaliseHoleFeature(feature) {
  const [longitude, latitude] = feature.geometry.coordinates;
  return {
    hole_id: feature.properties.hole_id,
    hole_name: feature.properties.name || feature.properties.hole_id,
    latitude,
    longitude,
    borehole_length_m: feature.properties.borehole_length_m,
    release_id: feature.properties.release_id,
    operator: feature.properties.operator,
    drill_start_date: feature.properties.drill_start_date,
    anomaly_count: 0,
  };
}

function normaliseHoleDetail(hole) {
  const coordinates = hole.location?.coordinates || [null, null];
  const sectionCount = hole.datasets.reduce(
    (total, dataset) => total + dataset.section_count,
    0
  );
  return {
    ...hole,
    hole_name: hole.name || hole.hole_id,
    longitude: coordinates[0],
    latitude: coordinates[1],
    elevation_m: null,
    inclination_deg: hole.inclination_deg,
    azimuth_deg: hole.azimuth_deg,
    orientation_status: hole.orientation_status,
    measurement_count: sectionCount,
    anomaly_count: 0,
  };
}

function normaliseSection(section) {
  const mineral = section.mineral;
  return {
    ...section,
    sample_no: section.section_index,
    mineral_1: mineral?.primary_raw || null,
    mineral_1_pct: mineral?.primary_fraction ?? null,
    mineral_2: mineral?.secondary_raw || null,
    mineral_2_pct: mineral?.secondary_fraction ?? null,
    mineral_group: mineral?.display_group || null,
    mineral_colour: mineral?.display_color || null,
    confidence: mineral?.confidence ?? 0,
    quality_flag: mineral?.quality || "missing",
    is_anomaly: false,
    anomaly_score: 0,
    image_url: assetUrl(section.image?.url),
    image_quality: section.image?.quality || null,
  };
}

export async function getStats() {
  const data = await get("/health");
  return {
    holes: data.hole_count,
    measurements: data.section_count,
    images: data.section_image_count,
    anomalies: 0,
    database: data.database,
    postgis_version: data.postgis_version,
  };
}

export async function getHoles({ search = "", anomaliesOnly = false, limit = 1000 } = {}) {
  if (anomaliesOnly) return [];
  const data = await get(`/holes?limit=${Math.min(limit, 1000)}&offset=0`);
  const needle = search.trim().toLowerCase();
  return data.features
    .map(normaliseHoleFeature)
    .filter(
      (hole) =>
        !needle ||
        hole.hole_id.toLowerCase().includes(needle) ||
        hole.hole_name.toLowerCase().includes(needle)
    );
}

export async function getHole(holeId) {
  return normaliseHoleDetail(await get(`/holes/${encodeURIComponent(holeId)}`));
}

export async function getMeasurements(holeId) {
  const hole = await getHole(holeId);
  const dataset = hole.datasets[0];
  if (!dataset) return [];
  const data = await get(`/datasets/${encodeURIComponent(dataset.dataset_id)}/sections`);
  return data.sections.map(normaliseSection);
}

export const getAnomalies = async () => [];

export async function getNearby(holeId, km = 25) {
  const [origin, holes] = await Promise.all([getHole(holeId), getHoles({ limit: 1000 })]);
  return holes
    .filter((hole) => hole.hole_id !== holeId)
    .map((hole) => ({
      ...hole,
      distance_km: haversineKm(origin.latitude, origin.longitude, hole.latitude, hole.longitude),
    }))
    .filter((hole) => hole.distance_km <= km)
    .sort((a, b) => a.distance_km - b.distance_km);
}

export async function getDistance(a, b) {
  const [holeA, holeB] = await Promise.all([getHole(a), getHole(b)]);
  return {
    distance_km: haversineKm(
      holeA.latitude,
      holeA.longitude,
      holeB.latitude,
      holeB.longitude
    ),
    hole_a: holeA,
    hole_b: holeB,
    method: "client-side preview; production endpoint should use PostGIS",
  };
}

export async function getTrace(holeId) {
  const [hole, sections] = await Promise.all([getHole(holeId), getMeasurements(holeId)]);
  const points = sections.map((section) => ({
    depth_m: section.depth_from_m,
    east_m: 0,
    north_m: 0,
    tvd_m: section.depth_from_m,
    mineral: null,
    is_anomaly: false,
    anomaly_score: 0,
    depth_to_m: section.depth_to_m,
    image_url: section.image_url,
    image_quality: section.image_quality,
  }));

  if (sections.length) {
    const last = sections[sections.length - 1];
    points.push({
      depth_m: last.depth_to_m,
      east_m: 0,
      north_m: 0,
      tvd_m: last.depth_to_m,
      mineral: null,
      is_anomaly: false,
      anomaly_score: 0,
      depth_to_m: last.depth_to_m,
      image_url: null,
      image_quality: null,
    });
  }

  return {
    hole_id: hole.hole_id,
    latitude: hole.latitude,
    longitude: hole.longitude,
    trajectory_kind: "vertical_preview",
    points,
  };
}

function haversineKm(lat1, lon1, lat2, lon2) {
  if ([lat1, lon1, lat2, lon2].some((value) => value == null)) return Infinity;
  const radians = (degrees) => (degrees * Math.PI) / 180;
  const dLat = radians(lat2 - lat1);
  const dLon = radians(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(dLon / 2) ** 2;
  return 6371.0088 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
