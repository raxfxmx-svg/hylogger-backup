'use client';
import { useState } from 'react';
import dynamic from 'next/dynamic';
import { useCatalogue } from '@/lib/useCatalogue';
import DatasetPanel from './DatasetPanel';

const HoleMap=dynamic(()=>import('./HoleMap'),{ssr:false});
function distance(a,b) {
  if (![a?.latitude,a?.longitude,b?.latitude,b?.longitude].every(Number.isFinite)) return null;
  const rad=Math.PI/180, dLat=(b.latitude-a.latitude)*rad, dLon=(b.longitude-a.longitude)*rad;
  const h=Math.sin(dLat/2)**2+Math.cos(a.latitude*rad)*Math.cos(b.latitude*rad)*Math.sin(dLon/2)**2;
  return 6371.0088*2*Math.asin(Math.sqrt(Math.min(1,h)));
}
export default function CompareV1() {
  const {holes,loading,error}=useCatalogue();
  const [a,setA]=useState(''),[b,setB]=useState(''),[slot,setSlot]=useState('A');
  const [from,setFrom]=useState(''),[to,setTo]=useState(''),[range,setRange]=useState({}),[rangeError,setRangeError]=useState(null);
  const holeA=holes.find(h=>h.hole_id===a),holeB=holes.find(h=>h.hole_id===b),km=distance(holeA,holeB);
  function apply(e) {
    e.preventDefault();
    const next={from_m:from.trim()===''?undefined:Number(from),to_m:to.trim()===''?undefined:Number(to)};
    if (Object.values(next).some(n=>n!=null&&!Number.isFinite(n)) || (next.from_m!=null&&next.to_m!=null&&next.from_m>next.to_m)) {
      setRangeError('Enter a valid depth range.');return;
    }
    setRangeError(null);setRange(next);
  }
  return <main className="page">
    <h1>Compare datasets</h1><p className="hint">Choose two holes, or compare different datasets from one hole. Select each result log explicitly; original values and missing data are preserved.</p>
    {loading&&<p role="status">Loading boreholes…</p>}{error&&<p className="error">{error}</p>}
    <div className="compare-pickers">
      {[['A',a,setA],['B',b,setB]].map(([name,value,set])=><label key={name}>Hole {name}<select value={value} onChange={e=>set(e.target.value)}><option value="">Select hole {name}…</option>{holes.map(h=><option key={h.hole_id} value={h.hole_id}>{h.hole_id}</option>)}</select></label>)}
      <button className="action" onClick={()=>{setA(b);setB(a);}} disabled={!a&&!b}>Swap</button>
      <button className="action" onClick={()=>{setA('');setB('');setSlot('A');}} disabled={!a&&!b}>Reset</button>
    </div>
    <p className="hint">Click the map to select hole {slot}. <button className="sample-link" onClick={()=>setSlot(slot==='A'?'B':'A')}>Select {slot==='A'?'B':'A'} instead</button></p>
    <div className="compare-map"><HoleMap holes={holes} selectedId={a} selectedIdB={b} flyToSelection={false} allow3d={false} onSelect={id=>{if(slot==='A'){setA(id);setSlot('B');}else setB(id);}} /></div>
    {km!=null&&<p className="hint">Collar separation: {km.toFixed(2)} km (great-circle estimate; not a downhole distance).</p>}
    <form className="dataset-range" onSubmit={apply}><label>Shared depth from (m)<input type="number" step="any" value={from} onChange={e=>setFrom(e.target.value)} /></label><label>To (m)<input type="number" step="any" value={to} onChange={e=>setTo(e.target.value)} /></label><button className="action">Apply to both</button></form>
    {rangeError&&<p className="error">{rangeError}</p>}
    <div className="dataset-compare-grid"><div><h2>Selection A</h2><DatasetPanel hole={holeA} depthRange={range} /></div><div><h2>Selection B</h2><DatasetPanel hole={holeB} depthRange={range} /></div></div>
  </main>;
}
