const fs = require('node:fs');
const path = require('node:path');
const base = 'https://api.example.com';
const usable = l => l.availability_status === 'payload_present' && l.axis_binding_status === 'verified';
async function get(route) {
  const r = await fetch(base + route, {signal: AbortSignal.timeout(25000)});
  return {status:r.status,body:await r.json()};
}
async function main() {
  const hole = '12CADD001';
  const datasets = await get(`/v1/boreholes/${hole}/datasets`);
  if (datasets.status !== 200) throw Error(JSON.stringify(datasets));
  const d = datasets.body.items.filter(d=>d.axis_id).sort((a,b)=>b.sample_count-a.sample_count)[0];
  const logs = await get(`/v1/datasets/${d.dataset_revision_id}/logs`);
  if (logs.status !== 200) throw Error(JSON.stringify(logs));
  const group = logs.body.items.find(l=>usable(l)&&l.log_kind==='scalar'&&l.metric_key==='mineral_group'&&/^grp\s*1/i.test(l.source_log_name)&&!(/TIR/i.test(l.output_region||'')||/TSAT/i.test(l.source_log_name)));
  const values = await get(`/v1/datasets/${d.dataset_revision_id}/logs/${group.log_id}/values?axis_id=${d.axis_id}&after_sample=-1&limit=1`);
  if (values.status !== 200 || !values.body.items.length) throw Error(JSON.stringify(values));
  const sampleNo = values.body.items[0].sample_no;
  const chosen = logs.body.items.filter(l=>usable(l)&&(l.log_kind==='spectral'||l.log_kind==='scalar'&&l.metric_key==='mineral_name'));
  const requestSample = list => {
    const query = new URLSearchParams({axis_id:d.axis_id});
    list.forEach(l=>query.append('log_ids',l.log_id));
    return get(`/v1/datasets/${d.dataset_revision_id}/samples/${sampleNo}?${query}`);
  };
  const before = await requestSample(chosen);
  const capped = [...chosen].sort((a,b)=>(a.log_kind==='spectral'?0:1)-(b.log_kind==='spectral'?0:1)).slice(0,16);
  const after = await requestSample(capped);
  const report = { checkedAt:new Date().toISOString(),hole,datasetCount:datasets.body.items.length,revision:d.dataset_revision_id,axis:d.axis_id,sampleNo,currentRequest:{logCount:chosen.length,status:before.status,detail:before.status===200?undefined:before.body.detail},cappedRequest:{logCount:capped.length,status:after.status,spectra:after.body.results?.filter(r=>r.log_kind==='spectral').map(r=>({region:r.region_code,channels:r.spectra?.length,status:r.status}))},note:'Read-only API requests; no deployed code or backend data changed.' };
  fs.writeFileSync(path.join(__dirname,'live-spectral-result.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
