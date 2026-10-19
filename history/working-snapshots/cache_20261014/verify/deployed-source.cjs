const fs = require('node:fs/promises');
const path = require('node:path');
(async () => {
  const site = 'https://app.example.com';
  const html = await (await fetch(site, {cache:'no-store'})).text();
  const scripts = [...html.matchAll(/<script[^>]+src="([^"]+)"/g)].map(x => x[1]);
  for (const src of scripts) {
    const code = await (await fetch(new URL(src,site))).text();
    if (!code.includes('hylogger-data-v1')) continue;
    await fs.writeFile(path.join(__dirname, 'deployed-cache-bundle.js'), code);
    console.log(JSON.stringify({script:src,cacheModule:true,ttlCatalog:code.includes('3e5'),ttlData:code.includes('36e5'),maxBytes128MiB:code.includes('134217728'),maxEntries2048:code.includes('2048'),refreshButton:code.includes('Refresh data'),apiOrigins:[...new Set(code.match(/https:\/\/[a-z0-9.-]+\.on\.aws/g)||[])]}));
  }
})();
