from pathlib import Path
import json

workspace = Path(r"C:\path\to\project")
fixture = workspace / "hylogger-visualisation/data/fixtures/05KCD001"
output_dir = workspace / "hylogger-visualisation/prototype"
output_dir.mkdir(parents=True, exist_ok=True)

hole = json.loads((fixture / "hole.json").read_text(encoding="utf-8"))
log = json.loads((fixture / "mineral-log.json").read_text(encoding="utf-8"))
intervals = [
    {
        "f": x["depth_from_m"],
        "t": x["depth_to_m"],
        "s": x["sensor"],
        "m": x["dominant_mineral"],
        "w": x["dominant_weight"],
        "i": x["invalid_weight"],
        "c": x["confidence"],
        "q": x["quality_flags"],
    }
    for x in log["intervals"]
]

template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>05KCD001 Simple Visualisation</title>
  <link href="https://unpkg.com/maplibre-gl@5.6.2/dist/maplibre-gl.css" rel="stylesheet">
  <style>
    :root{font-family:Inter,"Microsoft YaHei",sans-serif;color:#172033;background:#f4f6f8}
    *{box-sizing:border-box} body{margin:0} header{padding:18px 24px;background:#123b4a;color:white}
    h1{font-size:22px;margin:0 0 5px} header p{margin:0;color:#cbe0e7;font-size:13px}
    main{max-width:1180px;margin:auto;padding:18px;display:grid;gap:16px}
    .top{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr);gap:16px}
    .panel{background:white;border:1px solid #dbe2e7;border-radius:10px;overflow:hidden}
    .panel-title{font-weight:700;padding:12px 15px;border-bottom:1px solid #e5eaee}
    #map{height:360px}.facts{padding:10px 15px;display:grid;grid-template-columns:1fr 1fr;gap:0 14px}
    .fact{border-bottom:1px solid #edf0f2;padding:9px 0}.fact span{display:block;color:#667382;font-size:12px}
    .fact strong{font-size:14px}.note{margin:12px 15px;padding:10px 12px;background:#fff7df;border-left:4px solid #c68b00;font-size:13px}
    .log-wrap{padding:14px;display:grid;grid-template-columns:76px 68px 68px minmax(220px,1fr);gap:10px;align-items:start}
    .track-title{text-align:center;font-weight:700;font-size:13px;height:26px}
    .axis,.track{height:568px;position:relative;border:1px solid #cfd8de;background:#f8fafb}
    .tick{position:absolute;right:5px;transform:translateY(-50%);font-size:11px;color:#586575}
    .tick-line{position:absolute;left:0;right:0;border-top:1px solid #d9e0e5}
    .segment{position:absolute;left:0;right:0;min-height:2px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,.55)}
    .segment.low{background:#aab1b7!important;background-image:repeating-linear-gradient(135deg,transparent 0 4px,rgba(255,255,255,.5) 4px 7px)!important}
    .segment.medium{opacity:.68}.segment:hover{outline:2px solid #172033;z-index:3}
    .detail{padding:12px 14px;border:1px solid #dbe2e7;background:#fafcfd;min-height:150px}
    .detail h3{margin:0 0 10px;font-size:15px}.detail dl{display:grid;grid-template-columns:105px 1fr;margin:0;font-size:13px}
    .detail dt,.detail dd{padding:4px 0;margin:0}.detail dt{color:#667382}
    .legend{display:flex;flex-wrap:wrap;gap:8px 14px;padding:0 14px 14px}
    .legend-item{font-size:12px;display:flex;align-items:center;gap:5px}.swatch{width:13px;height:13px;border:1px solid #aeb7bd}
    .footer-note{padding:0 14px 16px;color:#5b6875;font-size:12px}
    @media(max-width:760px){.top{grid-template-columns:1fr}.log-wrap{grid-template-columns:54px 58px 58px 1fr;padding:8px;gap:5px}.facts{grid-template-columns:1fr}}
  </style>
</head>
<body>
<header><h1>HyLogger Borehole 05KCD001</h1><p>Standard data from row 29 · Map location and dominant-mineral depth tracks</p></header>
<main>
  <section class="top">
    <div class="panel"><div class="panel-title">Borehole location</div><div id="map"></div></div>
    <div class="panel">
      <div class="panel-title">Borehole information</div>
      <div class="facts" id="facts"></div>
      <div class="note">Spectral weights are neither mineral mass percentages nor gold grades.</div>
    </div>
  </section>
  <section class="panel">
    <div class="panel-title">Mineral tracks by depth</div>
    <div class="log-wrap">
      <div><div class="track-title">Depth (m)</div><div class="axis" id="axis"></div></div>
      <div><div class="track-title">SWIR</div><div class="track" id="swir"></div></div>
      <div><div class="track-title">TIR</div><div class="track" id="tir"></div></div>
      <div>
        <div class="track-title">Selected interval</div>
        <div class="detail" id="detail"><h3>Hover over a track</h3><p>Depth, dominant mineral, weight and confidence appear here.</p></div>
      </div>
    </div>
    <div class="legend" id="legend"></div>
    <div class="footer-note">Grey hatching indicates low confidence, not absent rock or minerals. Tracks use System automatic interpretations. The first and last one-metre bins differ by half a metre from the catalogue interval of 59.5–201.5 m.</div>
  </section>
</main>
<script src="https://unpkg.com/maplibre-gl@5.6.2/dist/maplibre-gl.js"></script>
<script>
const hole=__HOLE_JSON__;
const intervals=__INTERVALS_JSON__;
const colors={"Silica":"#ef9ebc","Chlorite":"#2fb350","White-Mica":"#f0da2e","Carbonate":"#2869d8","Sulphate":"#84732b","Smectite":"#c9b89e","Kaolin":"#ede7c8","K-Feldspar":"#e9822c","Plagioclase":"#a94635","Other-AlOH":"#9b79a8","Amphibole":"#d03cab","Dark-Mica":"#6c5739","Epidote":"#19b9b0","Pyroxene":"#6e4b8f","Garnet":"#9c3153","Misc-Silicate":"#777f87"};
document.getElementById("facts").innerHTML=[
 ["Borehole",hole.hole_name],["Unique ID",hole.unique_well_id],["Project",hole.project],["Commodity",hole.commodity],
 ["Total depth",hole.total_depth_m+" m"],["Scanned interval",hole.scanned_from_m+"–"+hole.scanned_to_m+" m"],
 ["Dip",hole.initial_dip_deg+"°"],["Azimuth",hole.initial_azimuth_deg+"°"],
 ["Longitude",hole.longitude],["Latitude",hole.latitude],["Datum",hole.datum],["Processing level","Level "+hole.process_level]
].map(x=>'<div class="fact"><span>'+x[0]+'</span><strong>'+x[1]+'</strong></div>').join("");

const map=new maplibregl.Map({container:"map",style:"https://demotiles.maplibre.org/style.json",center:[hole.longitude,hole.latitude],zoom:7});
new maplibregl.Marker({color:"#d94832"}).setLngLat([hole.longitude,hole.latitude]).setPopup(new maplibregl.Popup().setHTML("<strong>"+hole.hole_name+"</strong><br>"+hole.project+"<br>Depth "+hole.total_depth_m+" m")).addTo(map);
map.addControl(new maplibregl.NavigationControl(),"top-right");

const minDepth=59,maxDepth=202,total=maxDepth-minDepth;
const pct=d=>(d-minDepth)/total*100;
const axis=document.getElementById("axis");
[60,80,100,120,140,160,180,200].forEach(d=>{
 axis.insertAdjacentHTML("beforeend",'<div class="tick-line" style="top:'+pct(d)+'%"></div><div class="tick" style="top:'+pct(d)+'%">'+d+'</div>');
});
function show(x){
 const flags=x.q.length?x.q.join(", "):"None";
 document.getElementById("detail").innerHTML='<h3>'+x.f+'–'+x.t+' m · '+x.s+'</h3><dl>'+
 '<dt>Dominant mineral</dt><dd><strong>'+x.m+'</strong></dd>'+
 '<dt>Relative weight</dt><dd>'+((x.w??0)*100).toFixed(1)+'%</dd>'+
 '<dt>Invalid weight</dt><dd>'+(x.i==null?"None":(x.i*100).toFixed(1)+"%")+'</dd>'+
 '<dt>Confidence</dt><dd>'+x.c+'</dd>'+
 '<dt>Quality flags</dt><dd>'+flags+'</dd></dl>';
}
intervals.forEach(x=>{
 const el=document.createElement("div");
 el.className="segment "+x.c;
 el.style.top=pct(x.f)+"%";el.style.height=Math.max(.7,pct(x.t)-pct(x.f))+"%";
 el.style.background=colors[x.m]||"#82909a";
 el.setAttribute("aria-label",x.f+" to "+x.t+" metres "+x.s+" "+x.m+" "+x.c);
 el.addEventListener("mouseenter",()=>show(x));el.addEventListener("click",()=>show(x));
 document.getElementById(x.s.toLowerCase()).appendChild(el);
});
const used=[...new Set(intervals.map(x=>x.m))].sort();
document.getElementById("legend").innerHTML=used.map(m=>'<span class="legend-item"><i class="swatch" style="background:'+(colors[m]||"#82909a")+'"></i>'+m+'</span>').join("")+
'<span class="legend-item"><i class="swatch" style="background:#aab1b7"></i>Low confidence</span>';
show(intervals.find(x=>x.s==="SWIR"&&x.f===100)||intervals[0]);
</script>
</body>
</html>"""

html = template.replace(
    "__HOLE_JSON__", json.dumps(hole, ensure_ascii=False, separators=(",", ":"))
).replace(
    "__INTERVALS_JSON__", json.dumps(intervals, ensure_ascii=False, separators=(",", ":"))
)
(output_dir / "05kcd001.html").write_text(html, encoding="utf-8")
(output_dir / 'OPENING_INSTRUCTIONS.txt').write_text(
    'Double-click 05kcd001.html to open it.\n'
    'The map basemap requires internet access; embedded mineral tracks work offline.\n'
    'This single-borehole visual prototype is intended for later migration to Next.js with Django/PostGIS.\n',
    encoding="utf-8",
)
print(output_dir / "05kcd001.html")
