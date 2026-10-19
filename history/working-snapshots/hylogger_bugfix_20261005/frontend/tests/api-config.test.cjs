const test = require("node:test");
const assert = require("node:assert/strict");
const { resolveApiBase, assertProductionApiBase } = require("../lib/api-config.cjs");

test("localhost is only the unconfigured development default", () => {
  assert.equal(resolveApiBase(undefined, "development"), "http://localhost:8000/api");
  assert.equal(resolveApiBase(undefined, "production"), "");
  assert.equal(resolveApiBase("   ", "production"), "");
});

test("configured API URLs are trimmed and trailing slashes removed", () => {
  assert.equal(resolveApiBase(" https://api.example.com/api/// ", "production"), "https://api.example.com/api");
  assert.equal(assertProductionApiBase("https://api.example.com/api/"), "https://api.example.com/api");
});

test("unconfigured production preserves an explicit disconnected state", () => {
  for (const value of [undefined, "", " "]) assert.equal(assertProductionApiBase(value), "");
});

test("production rejects a local, mixed-content or malformed API address", () => {
  for (const value of ["/api", "not a URL", "http://api.example.com/api",
    "https://localhost/api", "https://demo.localhost/api", "https://127.0.0.1/api",
    "https://127.1/api", "https://0.0.0.0/api", "https://[::1]/api", "https://[::]/api",
    "https://user:password@api.example.com/api", "https://api.example.com/api?key=bad",
    "https://api.example.com/api#fragment"]) {
    assert.throws(() => assertProductionApiBase(value), /NEXT_PUBLIC_API_BASE/);
  }
});
