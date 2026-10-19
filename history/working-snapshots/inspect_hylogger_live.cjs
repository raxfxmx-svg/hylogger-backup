const { chromium } = require('C:/Users/USER/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage();
  const errors = [];
  const failures = [];
  const requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('requestfailed', r => failures.push({url: r.url(), error: r.failure()?.errorText}));
  page.on('request', r => { if (r.url().includes('/api/') || r.url().includes('/v1/')) requests.push(r.url()); });
  await page.goto('https://app.example.com/', { waitUntil: 'networkidle', timeout: 45000 });
  await page.screenshot({ path: 'C:/path/to/project/_codex_work/hylogger_live_20261005.png', fullPage: true });
  console.log(JSON.stringify({errors, failures, requests, text: await page.locator('body').innerText()}, null, 2));
  await browser.close();
})().catch(e => { console.error(e); process.exitCode = 1; });
