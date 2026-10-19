const fs = require('node:fs');
const path = require('node:path');
const frontend = path.resolve(__dirname, '../hylogger_bugfix_20261005/frontend');
const swc = require(path.join(frontend, 'node_modules/next/dist/build/swc'));
const script = value => '<script>' + value.replace(/<\/script/gi, '<\\/script') + '</script>';
const modules = ['CoreStripPanel', 'Hole3D', 'StripLog'].map(name => {
  const code = swc.transformSync(fs.readFileSync(path.join(frontend, 'components', name + '.jsx'), 'utf8'), {
    jsc: { parser: { syntax: 'ecmascript', jsx: true }, transform: { react: { runtime: 'classic' } }, target: 'es2020' }, module: { type: 'commonjs' }
  }).code;
  return `{ const exports = {}; ${code}; components.${name} = exports.default; }`;
}).join('\n');
const setup = `
const components = {}, calls = [], failures = [], results = [];
window.addEventListener('unhandledrejection', event => { failures.push(String(event.reason)); event.preventDefault(); });
const moduleDefault = value => ({__esModule:true, default:value});
function require(name) {
  if (name==='react') return React;
  if (name==='@/lib/api') return {getCoreStrip: holeId => new Promise((resolve,reject)=>calls.push({holeId,resolve,reject}))};
  if (name==='@/config') return {MEDIA_BASE:'', ANOMALY_COLOUR:'#ffffff', LOW_CONFIDENCE_COLOUR:'#444444', CONFIDENCE_THRESHOLD:0.5, mineralColour:()=> '#ffffff', toRgb:()=>[255,255,255]};
  if (name==='@luma.gl/engine') return {CylinderGeometry:class{}};
  if (name==='deck.gl') return {...moduleDefault(()=>React.createElement('div',null,'3D scene')), COORDINATE_SYSTEM:{CARTESIAN:0}, OrbitView:class{}, ScatterplotLayer:class{}, SimpleMeshLayer:class{}};
  throw new Error(name);
}
const root = ReactDOM.createRoot(document.getElementById('root'));
const pause=()=>new Promise(resolve=>setTimeout(resolve,40));
const render=async(name,props)=>{ReactDOM.flushSync(()=>root.render(React.createElement(components[name],props))); await pause();};
const assert=(value,message)=>{if(!value)throw new Error(message);};
const data=depth=>({depth_min_m:depth,depth_max_m:depth+1,sheets:[]});
const test=async(name,body)=>{try{await body();results.push({name,passed:true});}catch(e){results.push({name,passed:false,error:e.message});}ReactDOM.flushSync(()=>root.render(null));await pause();};
`;
const tests = `
(async()=>{
 await test('Core photo ignores a late response for the previous hole',async()=>{
  await render('CoreStripPanel',{holeId:'A'}); const a=calls.at(-1);
  await render('CoreStripPanel',{holeId:'B'}); const b=calls.at(-1);
  b.resolve(data(20));await pause();a.resolve(data(10));await pause();
  assert(document.body.innerText.includes('B · 20-21'),'Old hole photo replaced current hole');
 });
 await test('Core photo failure is visible and loading finishes',async()=>{
  await render('CoreStripPanel',{holeId:'C'});calls.at(-1).reject(Error('fixture outage'));await pause();
  assert(document.body.innerText.includes('Could not load core photo: fixture outage'),'Missing error');
  assert(!document.body.innerText.includes('Loading core photo'),'Loading stuck');
 });
 await test('3D photo request failure is caught while scene stays visible',async()=>{
  await render('Hole3D',{traces:[{hole_id:'D',latitude:-29,longitude:119,points:[]}],holes:[]});
  calls.at(-1).reject(Error('fixture outage'));await pause();
  assert(document.body.innerText.includes('Some core photos are unavailable'),'Missing photo error');
  assert(document.body.innerText.includes('3D scene'),'Lost scene');
  assert(failures.length===0,'Unhandled rejection');
 });
 await test('Missing confidence does not crash the mineral tooltip',async()=>{
  await render('StripLog',{measurements:[{depth_from_m:0,depth_to_m:10,mineral_1:'QUARTZ',quality_flag:'ok'}]});
  document.querySelectorAll('rect')[1].dispatchEvent(new MouseEvent('mouseover',{bubbles:true,clientX:1,clientY:1}));await pause();
  assert(document.body.innerText.includes('confidence unavailable'),'Tooltip missing safe confidence');
 });
 document.body.appendChild(Object.assign(document.createElement('pre'),{textContent:JSON.stringify(results,null,2)}));
})().catch(error=>{document.body.appendChild(Object.assign(document.createElement('pre'),{textContent:error.stack}));});
`;
fs.writeFileSync(path.join(__dirname,'media-regression.html'), '<!doctype html><meta charset="utf-8"><title>Media regression</title><div id="root"></div>' +
  script(fs.readFileSync(path.join(frontend,'node_modules/react/umd/react.development.js'),'utf8')) +
  script(fs.readFileSync(path.join(frontend,'node_modules/react-dom/umd/react-dom.development.js'),'utf8')) + script(setup+modules+tests));
