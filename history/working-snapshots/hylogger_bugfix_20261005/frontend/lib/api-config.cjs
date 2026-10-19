const LOCAL_API_BASE = "http://localhost:8000/api";

function resolveApiBase(value, environment) {
  return (value?.trim() || (environment === "development" ? LOCAL_API_BASE : ""))
    .replace(/\/+$/, "");
}

function assertProductionApiBase(value) {
  const base = resolveApiBase(value, "production");
  const help = "Set NEXT_PUBLIC_API_BASE to the public HTTPS API base URL (including /api) before building the frontend.";
  // Preserve a disconnected state so the UI can explain missing configuration.
  if (!base) return "";

  let url;
  try {
    url = new URL(base);
  } catch {
    throw new Error(`NEXT_PUBLIC_API_BASE must be an absolute URL. ${help}`);
  }
  const host = url.hostname.toLowerCase();
  if (host === "localhost" || host.endsWith(".localhost") || host.startsWith("127.") ||
      ["0.0.0.0", "[::]", "[::1]"].includes(host)) {
    throw new Error(`NEXT_PUBLIC_API_BASE points to a local computer. ${help}`);
  }
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
    throw new Error(`NEXT_PUBLIC_API_BASE must be an HTTPS base URL without credentials, a query, or a fragment. ${help}`);
  }
  return base;
}

module.exports = { resolveApiBase, assertProductionApiBase };
