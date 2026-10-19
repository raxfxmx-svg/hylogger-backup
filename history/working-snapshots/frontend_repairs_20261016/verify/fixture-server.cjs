const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { part, fixture } = require('../frontend/test/api-fixture.cjs');
const a = part('main', 0, [0, 0.1, 0.2, 0.3, 1, 1.1, 3], 'CHLORITE');
a.swir[0].value_text = 'INVALID';
a.swir[1].value_text = 'INVALID';
a.swir[2].value_text = 'INVALID';
a.direction = 'right_to_left';
const b = part('wedge', 2, [2, 3, 5], 'WHITE-MICA');
const { request, calls } = fixture([a, b], { spectralFailures: Number(process.env.FIXTURE_FAILURES ?? 1), failNearby: true, failTrays: true });
const alternate = fixture([part('other', 10, [10, 11, 12], 'QUARTZ')]);
http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Cache-Control', 'no-store');
  try {
    if (req.url.startsWith('/v1/image-assets/')) {
      res.setHeader('Content-Type', 'image/svg+xml');
      res.end('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="25"><rect width="200" height="25" fill="#cf5240"/><rect x="200" width="200" height="25" fill="#3599cc"/></svg>');
    } else {
      let data;
      if (req.url === '/v1/boreholes') {
        data = await request(req.url);
        data.items.push({ ...data.items[0], hole_id: 'OTHER', project: 'Switch regression fixture' });
      } else if (req.url.includes('/datasets/other/') || req.url.includes('/boreholes/OTHER/datasets')) {
        data = await alternate.request(req.url.replace('/boreholes/OTHER/datasets', '/boreholes/TEST/datasets'));
      } else data = await request(req.url);
      if (req.url.includes('/datasets/main/samples/') && !req.url.includes('include_results=false')) {
        await new Promise((resolve) => setTimeout(resolve, Number(process.env.FIXTURE_DELAY_MS || 0)));
      }
      res.end(JSON.stringify(data));
    }
  } catch (error) {
    res.statusCode = error.status || 500;
    res.end(JSON.stringify({ detail: error.message }));
  }
  fs.writeFileSync(path.join(__dirname, 'browser-requests.json'), JSON.stringify(calls.map((u) => u.href), null, 2));
}).listen(8000, '127.0.0.1', () => console.log('Read-only fixture API at http://localhost:8000 (first spectrum fails intentionally)'));
