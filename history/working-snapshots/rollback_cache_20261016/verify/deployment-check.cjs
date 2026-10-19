const fs = require('node:fs');
const path = require('node:path');
const site = 'https://app.example.com';
async function get(url) {
  const response = await fetch(url, {cache:'no-store',signal:AbortSignal.timeout(30000)});
  if (!response.ok) throw Error(`${response.status} ${url}`);
  return response.text();
}
(async()=>{
  const html = await get(site+'/?rollback-check='+Date.now());
  const scripts = [...new Set([...html.matchAll(/<script[^>]+src="([^"]+)"/g)].map(x=>x[1]))];
  const fetched = await Promise.all(scripts.map(async src=>({src,code:await get(new URL(src,site))})));
  const app = fetched.filter(s=>s.code.includes('mineral_group')||s.code.includes('Refresh data')||s.code.includes('hylogger-data-v1'));
  for(const [i,s] of app.entries()) fs.writeFileSync(path.join(__dirname,`live-app-${i}.js`),s.code);
  const all = fetched.map(s=>s.code).join('\n');
  const report = {checkedAt:new Date().toISOString(),scripts:scripts.length,appScripts:app.map(s=>s.src),persistentCachePresent:all.includes('hylogger-data-v1'),refreshDataControlPresent:all.includes('Refresh data'),mineralGroupPresent:all.includes('mineral_group'),invalidNormalizationPresent:all.includes('"ASPECTRAL","NULL","INVALID"'),confidencePresent:all.includes('confidence'),apiOrigins:[...new Set(all.match(/https:\/\/[a-z0-9.-]+\.on\.aws/g)||[])]};
  fs.writeFileSync(path.join(__dirname,'deployment-result.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
})().catch(e=>{console.error(e.message);process.exitCode=1;});
