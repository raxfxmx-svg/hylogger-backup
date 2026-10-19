const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const root = path.dirname(__dirname);
http.createServer((req, res) => {
  const p = new URL(req.url, 'http://localhost').pathname;
  const names = { '/': 'verify/index.html', '/tests.js': 'verify/tests.js', '/cache.js': 'frontend/lib/dataCache.js' };
  if (!names[p]) { res.writeHead(404); return res.end(); }
  res.setHeader('Content-Type', p === '/' ? 'text/html; charset=utf-8' : 'text/javascript; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(fs.readFileSync(path.join(root, names[p])));
}).listen(4179, '127.0.0.1', () => console.log('Cache tests: http://127.0.0.1:4179'));
