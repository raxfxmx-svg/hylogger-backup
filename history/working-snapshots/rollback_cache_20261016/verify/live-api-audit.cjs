const fs = require('node:fs');
const path = require('node:path');
const base = 'https://api.example.com';
const prior = JSON.parse(fs.readFileSync(path.join(__dirname,'../../confidence_audit_20261016/live-spectral-result.json'),'utf8'));
async function read(label,route) {
  const started=Date.now(); console.log('Request: '+label);
  try {
    const r=await fetch(base+route,{signal:AbortSignal.timeout(60000)});
    const body=await r.json();
    const out={label,status:r.status,elapsedMs:Date.now()-started,body};
    console.log(JSON.stringify(out)); return out;
  } catch(e) { const out={label,error:e.message,elapsedMs:Date.now()-started};console.log(JSON.stringify(out));return out; }
}
(async()=>{
 const ids=prior.currentRequest.detail[0].input;
 const q=new URLSearchParams({axis_id:prior.axis});ids.forEach(id=>q.append('log_ids',id));
 const results=await Promise.all([
   read('18-log spectral validation',`/v1/datasets/${prior.revision}/samples/${prior.sampleNo}?${q}`),
   read('15EIS001 datasets','/v1/boreholes/15EIS001/datasets'),
   read('12CADD001 datasets','/v1/boreholes/12CADD001/datasets')
 ]);
 fs.writeFileSync(path.join(__dirname,'live-api-result.json'),JSON.stringify({checkedAt:new Date().toISOString(),results},null,2));
})();
