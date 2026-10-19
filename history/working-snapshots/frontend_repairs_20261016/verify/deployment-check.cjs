const fs = require('node:fs');
const path = require('node:path');
const site = 'https://app.example.com';
async function get(url) {
  const response = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw Error(`${response.status} ${url}`);
  return response.text();
}
async function main() {
  const html = await get(site + '/?verify-repair=' + Date.now());
  const scripts = [...new Set([...html.matchAll(/<script[^>]+src="([^"]+)"/g)].map((m) => m[1]))];
  const bundles = await Promise.all(scripts.map(async (src) => ({ src, code: await get(new URL(src, site)) })));
  const code = bundles.map((b) => b.code).join('\n');
  const report = { checkedAt: new Date().toISOString(), site, scripts,
    features: {
      multiDatasetSplice: code.includes('their splice order cannot be determined'),
      mergedCatalogDepths: /Math\.min\([^)]*\.logged_from_m,[^)]*\.scan_from_m\)/.test(code) && /Math\.max\([^)]*\.logged_to_m,[^)]*\.scan_to_m\)/.test(code),
      spectralRetry: code.includes('Retry spectrum'),
      batchLimit16: /\+=16\b/.test(code),
      confidenceExplained: code.includes('sample agreement') && code.includes('Invalid and unclassified samples stay in the total'),
      photoCropping: code.includes('crop_from') && code.includes('crop_to'),
      mineralGroupFix: code.includes('mineral_group'),
      invalidNormalization: code.includes('"ASPECTRAL","NULL","INVALID"'),
      persistentCacheAbsent: !code.includes('hylogger-data-v1') && !code.includes('Refresh data'),
    },
    apiOrigins: [...new Set(code.match(/https:\/\/[a-z0-9.-]+\.on\.aws/g) || [])],
  };
  report.allFeaturesPresent = Object.values(report.features).every(Boolean);
  fs.writeFileSync(path.join(__dirname, 'deployment-result.json'), JSON.stringify(report, null, 2));
  for (const [i, bundle] of bundles.filter((b) => b.code.includes('mineral_group')).entries()) {
    fs.writeFileSync(path.join(__dirname, `deployed-app-${i}.js`), bundle.code);
  }
  console.log(JSON.stringify(report, null, 2));
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
