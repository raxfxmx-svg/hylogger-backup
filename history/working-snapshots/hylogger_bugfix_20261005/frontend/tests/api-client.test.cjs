const test = require("node:test");
const assert = require("node:assert/strict");
const { createApiClient, requireArray, NOT_CONNECTED } = require("../lib/api-client.cjs");

test("missing configuration never sends a localhost or same-origin request", async () => {
  let calls = 0;
  const get = createApiClient("", async () => { calls++; });
  await assert.rejects(get("/holes/"), { message: NOT_CONNECTED });
  assert.equal(calls, 0);
});
test("success reads JSON from the configured base", async () => {
  const get = createApiClient("https://api.example.com/api", async (url, init) => {
    assert.equal(url, "https://api.example.com/api/holes/");
    assert.equal(init.cache, "no-store");
    assert.ok(init.signal instanceof AbortSignal);
    return Response.json([{ hole_id: "A" }]);
  });
  assert.deepEqual(await get("/holes/"), [{ hole_id: "A" }]);
});
test("only optional 404 responses become missing data", async () => {
  const get = createApiClient("https://api.example.com/api", async () => new Response("missing", { status: 404 }));
  assert.equal(await get("/optional/", { optional: true }), null);
  await assert.rejects(get("/holes/"), /does not provide/);
});
test("optional server failures remain visible", async () => {
  const get = createApiClient("https://api.example.com/api", async () => Response.json({ detail: "private backend detail" }, { status: 503 }));
  await assert.rejects(get("/optional/", { optional: true }), /unavailable \(503\)/);
});
test("HTML fallback responses and invalid JSON do not reach components", async () => {
  for (const response of [new Response("<html>page</html>", { headers: { "Content-Type": "text/html" } }),
    new Response("not json", { headers: { "Content-Type": "application/json" } })]) {
    const get = createApiClient("https://api.example.com/api", async () => response);
    await assert.rejects(get("/holes/"), /web page|invalid data/);
  }
});
test("network failure has a useful error", async () => {
  const get = createApiClient("https://api.example.com/api", async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(get("/holes/"), /Cannot reach/);
});
test("hanging requests time out and abort the fetch", async () => {
  const get = createApiClient("https://api.example.com/api", (_, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
  }), 5);
  await assert.rejects(get("/holes/"), /took too long/);
});
test("different list contracts fail clearly instead of crashing React", () => {
  assert.deepEqual(requireArray([]), []);
  for (const value of [null, { items: [] }, { detail: "error" }]) assert.throws(() => requireArray(value), /incompatible format/);
});
