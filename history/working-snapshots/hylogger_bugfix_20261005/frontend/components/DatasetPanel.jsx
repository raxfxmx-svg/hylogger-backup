'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/v1';
import { datasetKey, joinSampleValues } from '@/lib/v1-client.cjs';

const number = value => Number.isFinite(value) ? value.toLocaleString(undefined, {maximumFractionDigits:5}) : 'Unavailable';
const statusText = value => (value || 'unavailable').replaceAll('_', ' ');

// Key changes hide previous data immediately, including the render before effect cleanup.
function useRemote(key, load) {
  const [state, setState] = useState({key:null, data:null, error:null, loading:false});
  useEffect(() => {
    if (key == null) return;
    let active = true;
    setState({key,data:null,error:null,loading:true});
    Promise.resolve().then(load)
      .then(data => active && setState({key,data,error:null,loading:false}))
      .catch(error => active && setState({key,data:null,error:error.message,loading:false}));
    return () => { active = false; };
    // Every request argument is included in key; load captures that selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state.key === key ? state : {key,data:null,error:null,loading:key != null};
}

function RequestState({state, label='Loading data…'}) {
  return <>{state.loading && <p className="hint" role="status">{label}</p>}{state.error && <p className="error" role="alert">{state.error}</p>}</>;
}

export default function DatasetPanel({hole, depthRange}) {
  if (!hole) return <div className="empty">Select a hole to explore its datasets and samples.</div>;
  return <DatasetSelection key={hole.hole_id} hole={hole} depthRange={depthRange} />;
}

function DatasetSelection({hole, depthRange}) {
  const datasets = useRemote(hole.hole_id, () => api.datasets(hole.hole_id));
  const [choice, setChoice] = useState('');
  const rows = datasets.data || [];
  const selected = rows.find(d => datasetKey(d) === choice) || (rows.length === 1 ? rows[0] : null);
  return <section className="dataset-panel" aria-label={`Data for ${hole.hole_id}`}>
    <h2>{hole.hole_id}</h2>
    <p className="hint">{hole.project || hole.source_name}</p>
    <dl className="dataset-facts">
      <dt>Reported length</dt><dd>{number(hole.borehole_length_m)}{hole.borehole_length_m != null && ' m'}</dd>
      <dt>Collar</dt><dd>{number(hole.latitude)}, {number(hole.longitude)}</dd>
      <dt>Trajectory</dt><dd>{statusText(hole.trajectory_status)}{hole.orientation_missing_reason && ` (${statusText(hole.orientation_missing_reason)})`}</dd>
      <dt>Confidence</dt><dd>Not supplied by this data release</dd>
    </dl>
    <RequestState state={datasets} label="Loading datasets…" />
    {!datasets.loading && !datasets.error && !rows.length && <p className="hint">No datasets are available.</p>}
    {rows.length > 0 && <label className="dataset-field">Dataset and sample axis
      <select value={selected ? datasetKey(selected) : ''} onChange={e => setChoice(e.target.value)}>
        <option value="">Choose a dataset…</option>
        {rows.map(d => <option key={datasetKey(d)} value={datasetKey(d)}>
          {d.source_dataset_name || d.dataset_revision_id} · {number(d.sample_count)} samples · axis {d.axis_id?.slice(-8) || 'unavailable'}
        </option>)}
      </select>
    </label>}
    {selected?.axis_id && <DatasetContents key={datasetKey(selected)} dataset={selected} depthRange={depthRange} />}
    {selected && !selected.axis_id && <p className="hint">This dataset has no sample axis available.</p>}
  </section>;
}

function DatasetContents({dataset, depthRange}) {
  const {dataset_revision_id:revision, axis_id:axis} = dataset;
  const logs = useRemote(revision, () => api.logs(revision));
  const [logId, setLogId] = useState('');
  const [imageLogId, setImageLogId] = useState('');
  const allLogs = logs.data || [];
  const resultLogs = allLogs.filter(l => ['scalar','spectral','profile'].includes(l.log_kind) && (!l.axis_id || l.axis_id === axis));
  const imageLogs = allLogs.filter(l => l.log_kind === 'image');
  const log = resultLogs.find(l => l.log_id === logId);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [range, setRange] = useState({});
  const [validation, setValidation] = useState(null);
  const effectiveRange = depthRange || range;
  const rangeKey = JSON.stringify(effectiveRange);
  const [page, setPage] = useState({rangeKey, cursors:[-1]});
  const cursors = page.rangeKey === rangeKey ? page.cursors : [-1];
  const after = cursors.at(-1);
  const options = {axis_id:axis,...effectiveRange,after_sample:after,limit:100};
  const requestKey = `${revision}:${axis}:${rangeKey}:${after}`;
  const samples = useRemote(requestKey, () => api.samples(revision, options));
  const valuesKey = log?.log_kind === 'scalar' ? `${requestKey}:${logId}` : null;
  const values = useRemote(valuesKey, () => api.values(revision, logId, options));
  const [sampleSelection, setSampleSelection] = useState(null);
  const [numberInput, setNumberInput] = useState('');
  const selectedNo = sampleSelection?.requestKey === requestKey ? sampleSelection.number : null;
  const sampleRows = joinSampleValues(samples.data?.items || [], values.data?.items || []);

  function applyRange(event) {
    event.preventDefault();
    const next = {from_m:from.trim() === '' ? undefined : Number(from),to_m:to.trim() === '' ? undefined : Number(to)};
    if ((next.from_m != null && !Number.isFinite(next.from_m)) || (next.to_m != null && !Number.isFinite(next.to_m)) ||
        (next.from_m != null && next.to_m != null && next.from_m > next.to_m)) {
      setValidation('Enter a valid depth range.'); return;
    }
    setValidation(null); setRange(next); setSampleSelection(null); setPage({rangeKey:JSON.stringify(next),cursors:[-1]});
  }
  function chooseSample(n) { setValidation(null); setNumberInput(String(n)); setSampleSelection({requestKey,number:n}); }
  function jump(event) {
    event.preventDefault();
    const n = Number(numberInput);
    if (!numberInput.trim() || !Number.isSafeInteger(n) || n < 0 || n >= dataset.sample_count) {
      setValidation(`Enter a sample number from 0 to ${dataset.sample_count - 1}.`); return;
    }
    chooseSample(n);
  }

  return <>
    <p className="hint">Scanned depth: {number(dataset.depth_min_m)}–{number(dataset.depth_max_m)} m. Sample numbers start at 0; equal depths can represent different samples.</p>
    <RequestState state={logs} label="Loading logs…" />
    <label className="dataset-field">Result log
      <select value={logId} onChange={e => setLogId(e.target.value)} disabled={logs.loading}>
        <option value="">Images and sample information only</option>
        {resultLogs.map(l => <option key={`${l.log_id}:${l.axis_id}`} value={l.log_id}>
          {l.source_log_name} · {l.log_kind}{l.spectral_region ? ` · ${l.spectral_region}` : ''}{l.variant_code ? ` · ${l.variant_code}` : ''} · {l.log_id.slice(-6)}
        </option>)}
      </select>
    </label>
    {log && <p className="hint">{statusText(log.availability_status)} · {statusText(log.axis_binding_status)}{log.omission_reason && ` · ${statusText(log.omission_reason)}`}{log.unit ? ` · unit: ${log.unit}` : ' · unit not supplied'}</p>}
    <label className="dataset-field">Image log
      <select value={imageLogId} onChange={e => setImageLogId(e.target.value)}>
        <option value="">Resolve available image mapping</option>
        {imageLogs.map(l => <option key={l.log_id} value={l.log_id}>{l.source_log_name} · {l.log_id.slice(-6)}</option>)}
      </select>
    </label>
    {!depthRange && <form className="dataset-range" onSubmit={applyRange}>
      <label>From (m)<input type="number" step="any" value={from} onChange={e => setFrom(e.target.value)} /></label>
      <label>To (m)<input type="number" step="any" value={to} onChange={e => setTo(e.target.value)} /></label>
      <button className="action" type="submit">Apply</button>
    </form>}
    <form className="sample-jump" onSubmit={jump}>
      <label>Sample number<input type="number" min="0" max={dataset.sample_count - 1} step="1" value={numberInput} onChange={e => setNumberInput(e.target.value)} /></label>
      <button className="action" type="submit">View sample</button>
    </form>
    {validation && <p className="error" role="alert">{validation}</p>}
    {selectedNo != null && <ExactSample key={`${revision}:${axis}:${selectedNo}:${logId}:${imageLogId}`} revision={revision} axis={axis} sampleNo={selectedNo} log={log} imageLog={imageLogId} onImageLog={setImageLogId} />}
    <RequestState state={samples} label="Loading samples…" />
    <RequestState state={values} label="Loading selected log…" />
    {values.data?.status && values.data.status !== 'available' && <p className="hint">Log: {statusText(values.data.status)}</p>}
    {samples.data && <>
      <p className="hint">{sampleRows.length} samples on this page{valuesKey ? ' · values joined by sample number' : ''}.</p>
      <div className="sample-table-scroll"><table className="sample-table">
        <thead><tr><th>Sample</th><th>Depth (m)</th><th>{log?.log_kind === 'scalar' ? 'Value' : 'Inspect'}</th></tr></thead>
        <tbody>{sampleRows.map(row => <tr key={row.sample_no} className={row.sample_no === selectedNo ? 'selected' : ''}>
          <td><button className="sample-link" onClick={() => chooseSample(row.sample_no)}>{row.sample_no}</button></td>
          <td>{number(row.md_m)}</td><td>{log?.log_kind === 'scalar' ? valueLabel(row.result) : <button className="sample-link" onClick={() => chooseSample(row.sample_no)}>View</button>}</td>
        </tr>)}</tbody>
      </table></div>
      {!sampleRows.length && <p className="hint">No samples in this depth range.</p>}
      <div className="sample-pagination">
        <button className="action" disabled={cursors.length === 1} onClick={() => setPage({rangeKey,cursors:cursors.slice(0,-1)})}>Previous page</button>
        <span>Page {cursors.length}</span>
        <button className="action" disabled={samples.data.next_after_sample == null} onClick={() => setPage({rangeKey,cursors:[...cursors,samples.data.next_after_sample]})}>Next page</button>
      </div>
    </>}
    <DatasetAnnotations revision={revision} axis={axis} />
    <details className="dataset-provenance"><summary>Data identity</summary><dl>
      <dt>Release</dt><dd>{dataset.release_id}</dd><dt>Dataset</dt><dd>{dataset.dataset_id}</dd>
      <dt>Revision</dt><dd>{revision}</dd><dt>Axis</dt><dd>{axis}</dd>
    </dl></details>
  </>;
}

function valueLabel(result) {
  if (!result) return 'Not returned';
  if (result.status && result.status !== 'available') return statusText(result.status);
  return result.value_text ?? (Number.isFinite(result.value_numeric) ? number(result.value_numeric) : 'Source value missing');
}

function ExactSample({revision, axis, sampleNo, log, imageLog, onImageLog}) {
  const result = useRemote(`${revision}:${axis}:${sampleNo}:${log?.log_id || ''}:${imageLog}`,
    () => api.sample(revision, axis, sampleNo, log?.log_id, imageLog));
  const sample = result.data;
  return <section className="exact-sample" aria-label={`Sample ${sampleNo}`}>
    <h3>Sample {sampleNo}</h3><RequestState state={result} label="Loading sample and image…" />
    {sample && <>
      <p>Depth <strong>{number(sample.md_m)} m</strong></p>
      {sample.results?.map(r => <Result key={r.log_id} result={r} />)}
      <p className="hint">Image: {statusText(sample.image_status)}</p>
      {sample.image_status === 'selection_required' && <div className="sample-image-choices">
        <p className="hint">Multiple source image logs match this sample. Choose one.</p>
        {sample.images?.map(image => <button key={image.image_region_id} className="action" onClick={() => onImageLog(image.image_log_id)}>
          Image log {image.image_log_id?.slice(-8)} · {image.width_px} × {image.height_px}
        </button>)}
      </div>}
      {sample.image_status === 'available' && sample.images?.length === 1 && <SampleImage key={sample.images[0].image_asset_id} image={sample.images[0]} sampleNo={sampleNo} />}
    </>}
  </section>;
}

function SampleImage({image, sampleNo}) {
  const [failed, setFailed] = useState(false);
  const p = image.indicator?.p;
  return failed ? <p className="error">The sample image could not be loaded.</p> : <>
    <div className="sample-image">
      <img src={api.imageUrl(image.image_asset_id)} alt={`Core row containing sample ${sampleNo}`} onError={() => setFailed(true)} />
      {Number.isFinite(p) && p >= 0 && p <= 1 && <span className="sample-indicator" style={{left:`${p * 100}%`}} aria-label="Approximate sample position" />}
    </div>
    {Number.isFinite(p) && <p className="hint">Approximate position from sample order, not a measured mineral boundary.</p>}
  </>;
}

function Result({result}) {
  const profile = result.log_kind === 'profile' && Object.values(result.value || {}).find(v => Array.isArray(v));
  return <div className="sample-result"><h4>{result.source_log_name}</h4><p className="hint">{statusText(result.status)}</p>
    {result.log_kind === 'scalar' && <p className="sample-value">{valueLabel({...result.value,status:result.status})}{result.unit && ` ${result.unit}`}</p>}
    {result.log_kind === 'spectral' && result.status === 'available' && <SeriesPlot x={result.wavelength} y={result.spectra} label={`Wavelength (${result.wavelength_unit || 'source units'})`} />}
    {Array.isArray(profile) && <><SeriesPlot x={profile.map((_,i)=>i)} y={profile} label="Profile position index" /><p className="hint">Uncalibrated profile: physical geometry is not available.</p></>}
  </div>;
}

function SeriesPlot({x=[],y=[],label}) {
  const points = x.map((v,i)=>[v,y[i]]).filter(([a,b])=>Number.isFinite(a)&&Number.isFinite(b));
  if (!points.length) return <p className="hint">No finite values to plot.</p>;
  const minX=Math.min(...points.map(p=>p[0])), maxX=Math.max(...points.map(p=>p[0]));
  const minY=Math.min(...points.map(p=>p[1])), maxY=Math.max(...points.map(p=>p[1]));
  let drawing=false;
  const path=x.map((v,i)=>{
    if (!Number.isFinite(v)||!Number.isFinite(y[i])) {drawing=false;return '';}
    const command=drawing?'L':'M'; drawing=true;
    return `${command}${40+(v-minX)/(maxX-minX||1)*280},${160-(y[i]-minY)/(maxY-minY||1)*135}`;
  }).join(' ');
  return <figure className="sample-plot"><svg viewBox="0 0 350 205" role="img" aria-label={`${label}, ${points.length} available channels`}>
    <path d="M40 20V160H325" fill="none" stroke="var(--line)" />
    <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
    <text x="2" y="25">{maxY.toPrecision(3)}</text><text x="2" y="162">{minY.toPrecision(3)}</text>
    <text x="40" y="180">{number(minX)}</text><text x="320" y="180" textAnchor="end">{number(maxX)}</text>
    <text x="180" y="199" textAnchor="middle">{label}</text>
  </svg><figcaption className="hint">{points.length} available values; gaps remain unconnected. Original source scale.</figcaption></figure>;
}

function DatasetAnnotations({revision, axis}) {
  const [opened,setOpened]=useState(false);
  const [offset,setOffset]=useState(0);
  const anomalies=useRemote(opened ? `${revision}:${axis}:${offset}` : null,()=>api.anomalies(revision,axis,offset));
  const issues=useRemote(opened ? revision : null,()=>api.issues(revision));
  return <details className="dataset-annotations" onToggle={e=>setOpened(e.currentTarget.open)}><summary>Anomalies and data quality</summary>
    <RequestState state={anomalies} />
    {anomalies.data && <><p className="hint">Anomaly scores are batch percentiles (0–100), not probabilities. No returned intervals does not establish that a dataset is normal.</p>
      {!anomalies.data.items?.length && <p className="hint">No anomaly intervals returned for this release and axis.</p>}
      {anomalies.data.items?.map((a,i)=><p key={`${a.first_sample_no}:${i}`}>{number(a.depth_from_m)}–{number(a.depth_to_m)} m · {a.flag} · score {number(a.anomaly_score)}</p>)}
      <button className="action" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-100))}>Previous intervals</button>{' '}
      <button className="action" disabled={anomalies.data.next_offset==null} onClick={()=>setOffset(anomalies.data.next_offset)}>Next intervals</button>
    </>}
    <RequestState state={issues} />
    {issues.data && <p className="hint">{issues.data.items?.length ?? 0} source quality records returned.</p>}
    {issues.data?.items?.map((issue,i)=><p className="hint" key={issue.id||i}>{issue.issue_code || issue.code || issue.issue_type}: {issue.message || issue.description || issue.severity}</p>)}
  </details>;
}
