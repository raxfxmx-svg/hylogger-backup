// Offline review reference, not integrated into the application.
// A production integration must also route Lambda image requests here,
// add cancellation/interaction priority, and render explicit error states.
function createJsonClient(fetchImpl, {
  concurrency = 4,
  retries = 2,
  sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
  random = Math.random,
  now = Date.now,
} = {}) {
  const queue = [];
  let active = 0;
  function drain() {
    while (active < concurrency && queue.length) {
      const { task, resolve, reject } = queue.shift();
      active++;
      const release = () => { active--; drain(); };
      Promise.resolve().then(task).then(
        value => { release(); resolve(value); },
        error => { release(); reject(error); },
      );
    }
  }
  const run = task => new Promise((resolve, reject) => {
    queue.push({ task, resolve, reject });
    drain();
  });
  async function get(url) {
    for (let attempt = 0; ; attempt++) {
      try {
        return await run(async () => {
          const response = await fetchImpl(url, { cache: 'no-store' });
          if (!response.ok) {
            const error = new Error(`HTTP ${response.status}`);
            error.status = response.status;
            const value = response.headers?.get('Retry-After');
            const seconds = value && /^\d+(\.\d+)?$/.test(value.trim()) ? Number(value) : NaN;
            error.retryAfterMs = !value ? 0 : Number.isFinite(seconds) ? seconds * 1000 : Math.max(0, Date.parse(value) - now()) || 0;
            // Do not leave an error response body occupying a connection.
            await response.body?.cancel();
            throw error;
          }
          // Keep the slot while the response body is received and decoded.
          return await response.json();
        });
      } catch (error) {
        if (attempt >= retries || ![429, 502, 503, 504].includes(error.status)) throw error;
        // A longer server backoff should be presented to the user, not ignored.
        if (error.retryAfterMs > 30000) throw error;
        const jittered = 500 * 2 ** attempt * (0.5 + random());
        await sleep(Math.max(error.retryAfterMs, jittered));
        // Backoff happens outside the concurrency slot.
      }
    }
  }
  return { get };
}
module.exports = { createJsonClient };
