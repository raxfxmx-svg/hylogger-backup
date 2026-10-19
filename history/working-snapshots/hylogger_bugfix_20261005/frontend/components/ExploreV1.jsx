'use client';
import { useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { useCatalogue } from '@/lib/useCatalogue';
import DatasetPanel from './DatasetPanel';

const HoleMap = dynamic(() => import('./HoleMap'), {ssr:false});
export default function ExploreV1() {
  const {holes,loading,error} = useCatalogue();
  const [search,setSearch] = useState('');
  const [hovered,setHovered] = useState(null);
  const [selected,setSelected] = useState(null);
  const filtered = useMemo(()=>{
    const q=search.trim().toLowerCase();
    return holes.filter(h=>[h.hole_id,h.hole_name,h.project].some(v=>v?.toLowerCase().includes(q)));
  },[holes,search]);
  const hole=holes.find(h=>h.hole_id===selected);
  return <div className="columns">
    <aside className="sidebar catalogue-sidebar">
      <div className="search-row"><input type="search" aria-label="Search hole id or name" placeholder="Search hole id or name" value={search} onChange={e=>setSearch(e.target.value)} />
        <p className="hint">Choose a hole, then a dataset and log.</p>
      </div>
      <div className="hole-list">
        {loading && <p className="hint" role="status" style={{padding:12}}>Loading boreholes…</p>}
        {error && <p className="error" style={{margin:12}}>{error}</p>}
        {!loading&&!error&&!filtered.length&&<p className="empty">No holes match the search.</p>}
        {filtered.map(h=><button key={h.hole_id} className={`hole-row ${selected===h.hole_id?'selected':''}`} onMouseEnter={()=>setHovered(h.hole_id)} onFocus={()=>setHovered(h.hole_id)} onClick={()=>setSelected(h.hole_id)}>
          <span className="id">{h.hole_id}</span><span className="name">{h.project}</span>
          <span className="len">{h.borehole_length_m==null?'Length unavailable':`${h.borehole_length_m.toLocaleString(undefined,{maximumFractionDigits:5})} m reported`}</span>
          {h.latitude==null&&<span className="hint">Map location unavailable</span>}
        </button>)}
      </div>
    </aside>
    <div className="map-area">
      <HoleMap holes={filtered} selectedId={hovered||selected} onHover={setHovered} onSelect={setSelected} flyToId={selected} allow3d={false} />
      <div className="legend">{loading?'Loading boreholes…':error?'Data unavailable':`${filtered.length} holes · ${filtered.filter(h=>h.latitude!=null&&h.longitude!=null).length} mapped`}</div>
    </div>
    <aside className="detail dataset-detail"><DatasetPanel hole={hole} /></aside>
  </div>;
}
