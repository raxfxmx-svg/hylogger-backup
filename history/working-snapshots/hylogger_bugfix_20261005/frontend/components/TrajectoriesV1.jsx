'use client';
import { useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useCatalogue } from '@/lib/useCatalogue';

const HoleMap=dynamic(()=>import('./HoleMap'),{ssr:false});
export default function TrajectoriesV1() {
  const {holes,loading,error}=useCatalogue();
  const [selected,setSelected]=useState(null);
  const hole=holes.find(h=>h.hole_id===selected);
  return <main className="page">
    <h1>Drillhole trajectories</h1>
    <p className="hint">The connected API supplies collar locations and trajectory availability, but does not supply survey stations for 3D reconstruction. The map below shows measured collar locations.</p>
    <p><Link href="/">Explore real sample depths, mineral logs and core images</Link></p>
    {loading&&<p role="status">Loading boreholes…</p>}{error&&<p className="error">{error}</p>}
    <label className="dataset-field">Hole<select value={selected||''} onChange={e=>setSelected(e.target.value)}><option value="">Choose a hole…</option>{holes.map(h=><option key={h.hole_id} value={h.hole_id}>{h.hole_id}</option>)}</select></label>
    {hole&&<p className="hint">{hole.hole_id}: {(hole.trajectory_status||'unavailable').replaceAll('_',' ')}{hole.orientation_missing_reason&&` — ${hole.orientation_missing_reason.replaceAll('_',' ')}`}. No synthetic dip, azimuth or core geometry is drawn.</p>}
    <div className="compare-map"><HoleMap holes={holes} selectedId={selected} flyToId={selected} onSelect={setSelected} allow3d={false} /></div>
  </main>;
}
