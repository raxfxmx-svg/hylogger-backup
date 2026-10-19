// The UI's hole-based API contract. See DEPLOYMENT.md for ETL4 /v1 integration.
import { API_BASE } from "@/config";
import { createApiClient, requireArray } from "./api-client.cjs";

const get = createApiClient(API_BASE);
const id = encodeURIComponent;
const list = async (path) => requireArray(await get(path));

export const getStats = () => get("/stats/");
export const getHoles = ({ search = "", anomaliesOnly = false, limit = 3000 } = {}) => {
  const query = new URLSearchParams({ limit: String(limit) });
  if (search) query.set("search", search);
  if (anomaliesOnly) query.set("anomalies_only", "1");
  return list(`/holes/?${query}`);
};
export const getHole = (holeId) => get(`/holes/${id(holeId)}/`);
export const getMeasurements = (holeId) => list(`/holes/${id(holeId)}/measurements/`);
export const getTrays = (holeId) => list(`/holes/${id(holeId)}/trays/`);
export const getAnomalies = (holeId) => list(`/holes/${id(holeId)}/anomalies/`);
export const getTrace = (holeId, stepM = 5) => get(`/holes/${id(holeId)}/trace/?${new URLSearchParams({ step_m: String(stepM) })}`);
export const getNearby = (holeId, km = 25) => list(`/holes/${id(holeId)}/nearby/?${new URLSearchParams({ km: String(km) })}`);
export const getDistance = (a, b) => get(`/distance/?${new URLSearchParams({ a, b })}`);

// Only optional resources interpret 404 as no data. Network/server failures
// remain visible instead of being mislabeled as an unavailable spectrum/photo.
export const getSpectralSample = (holeId, depthM) => {
  const query = depthM != null ? `?${new URLSearchParams({ depth_m: String(depthM) })}` : "";
  return get(`/holes/${id(holeId)}/spectral-sample/${query}`, { optional: true });
};
export const getCoreStrip = (holeId) => get(`/holes/${id(holeId)}/core-strip/`, { optional: true });
