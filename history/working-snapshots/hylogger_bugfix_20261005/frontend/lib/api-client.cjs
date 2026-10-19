const NOT_CONNECTED = "The data service is not connected yet. Please contact the site owner.";

function createApiClient(base, fetcher = globalThis.fetch, timeoutMs = 30000) {
  return async function get(path, { optional = false } = {}) {
    if (!base) throw new Error(NOT_CONNECTED);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetcher(`${base}${path}`, { cache: "no-store", signal: controller.signal });
      if (optional && response.status === 404) return null;
      if (!response.ok) {
        if (response.status === 404) throw new Error("This data service does not provide the requested feature. Please contact the site owner.");
        if (response.status === 401 || response.status === 403) throw new Error("Access to the data service was denied.");
        throw new Error(`The data service is temporarily unavailable (${response.status}). Please try again.`);
      }
      const type = response.headers.get("content-type") || "";
      if (!type.includes("application/json") && !type.includes("+json")) {
        throw new Error("The data service returned a web page instead of data. Please contact the site owner.");
      }
      try { return await response.json(); }
      catch { throw new Error("The data service returned invalid data. Please try again."); }
    } catch (error) {
      if (controller.signal.aborted) throw new Error("The data service took too long to respond. Please try again.");
      if (error instanceof TypeError) throw new Error("Cannot reach the data service. Please check your connection and try again.");
      throw error;
    } finally { clearTimeout(timer); }
  };
}

function requireArray(value) {
  if (!Array.isArray(value)) throw new Error("The data service uses an incompatible format. Please contact the site owner.");
  return value;
}
module.exports = { createApiClient, requireArray, NOT_CONNECTED };
