/*
 * HyLogger 3D drill core visualisation frontend
 * No build step: native ES modules; three.js loads from a CDN via the index.html import map.
 * jsDelivr is the primary CDN; unpkg is the fallback listed in index.html.
 *
 * Texture orientation:
 *   - Strip JPGs are 2048 px wide; depth increases from left to right.
 *   - CylinderGeometry side UVs use V = 1 at the top and V = 0 at the bottom.
 *     With the default flipY=true, V = 1 maps to the top image row.
 *   - Rotate each strip 90 degrees clockwise on a canvas so its shallow left edge
 *     becomes the top row, matching the top of the cylinder section.
 */
'use strict';

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

window.__appStarted = true;

/* ---------------- Constants ---------------- */

var TEX_LEN = 512;             // Texture resolution along the section depth, in pixels
var TEX_CIRC = 64;             // Texture resolution around the section
var RADIAL_SEGMENTS = 48;      // Cylinder radial segments
var CORE_RADIUS = 0.8;         // One scene unit equals one metre; radius is enlarged for visibility
var MIN_SECTION_HEIGHT = 0.02; // Minimum displayed height for zero-length sections, in metres
var SAMPLES_PER_SECTION = 131; // Dataset-specific sample count used to estimate spectrum indices
var OVERLAY_ALPHA = 0.55;      // Mineral band opacity in overlay mode
var MAX_PALETTE_MINERALS = 20; // Maximum number of minerals assigned palette colours

// Tableau20 palette
var PALETTE = [
  '#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c',
  '#98df8a', '#d62728', '#ff9896', '#9467bd', '#c5b0d5',
  '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f',
  '#c7c7c7', '#bcbd22', '#dbdb8d', '#17becf', '#9edae5'
];
var NULL_COLOR = '#9e9e9e';  // Unassigned mineral (null)
var OTHER_COLOR = '#4b5563'; // Minerals outside the top 20 by thickness

/* ---------------- Global state ---------------- */

var state = {
  holes: [],           // List from /api/holes
  holeId: null,
  hole: null,          // Current hole entry from /api/holes
  meta: null,          // Current hole response from /meta
  sensor: 'vnir',
  mode: 'photo',       // photo | mineral | overlay
  intervals: [],       // Current sensor intervals, sorted by depth_from
  intervalCache: {},   // key: holeId + '|' + sensor
  sections: [],        // Flattened sections with image/texture caches and mesh references
  colorOf: null,       // function(mineral) -> CSS colour
  legendMinerals: [],  // Top 20 entries: {mineral, color, thickness}
  nullThickness: 0,
  otherThickness: 0,
  selected: null,      // {section, depth, interval}
  reviewed: {},        // Interval IDs reviewed in this session -> true
  depthMin: 0,
  depthMax: 0,
  loadToken: 0         // Invalidates pending loads when switching holes
};

/* three.js objects, initialised by setupSceneOnce */
var renderer = null;
var scene = null;
var camera = null;
var controls = null;
var coreGroup = null;
var ringMesh = null;       // Marker ring for the selected depth
var capMaterial = null;    // End-cap material shared by all sections
var raycaster = new THREE.Raycaster();

/* ---------------- DOM references and utilities ---------------- */

function $(id) { return document.getElementById(id); }

function esc(s) {
  return String(s).replace(/[&<>"']/g, function (ch) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
  });
}

function fmt(v, digits) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return Number(v).toFixed(digits === undefined ? 4 : digits);
}

function statusLabel(status) {
  if (status === 'confirmed') return 'Confirmed';
  if (status === 'doubtful') return 'Doubtful';
  return status || '—';
}

/** Fetch wrapper: throw an error with FastAPI details for non-2xx responses. */
function api(path, options) {
  return fetch(path, options).then(function (res) {
    if (!res.ok) {
      return res.text().then(function (text) {
        var detail = text;
        try {
          var body = JSON.parse(text);
          detail = body.detail || text;
        } catch (e) { /* Keep the original response text. */ }
        throw new Error('HTTP ' + res.status + ': ' + detail);
      });
    }
    return res.json();
  });
}

function showError(msg) {
  $('error-text').textContent = msg;
  $('error-banner').hidden = false;
}

function hideError() {
  $('error-banner').hidden = true;
}

function showLoading(text) {
  $('loading-text').textContent = text;
  $('loading-fill').style.width = '0%';
  $('loading').hidden = false;
}

function setLoadingProgress(done, total) {
  var pct = total > 0 ? Math.round((done / total) * 100) : 0;
  $('loading-fill').style.width = pct + '%';
  $('loading-text').textContent = 'Loading core strip images... ' + done + '/' + total;
}

function hideLoading() {
  $('loading').hidden = true;
}

/* ---------------- Initialisation ---------------- */

function init() {
  window.addEventListener('unhandledrejection', function (ev) {
    showError('Unhandled error: ' + (ev.reason && ev.reason.message ? ev.reason.message : ev.reason));
  });
  $('error-close').addEventListener('click', hideError);
  $('hole-select').addEventListener('change', function () {
    loadHole($('hole-select').value);
  });
  Array.prototype.forEach.call(document.querySelectorAll('#sensor-seg .seg-btn'), function (btn) {
    btn.addEventListener('click', function () { setSensor(btn.getAttribute('data-sensor')); });
  });
  Array.prototype.forEach.call(document.querySelectorAll('#mode-seg .seg-btn'), function (btn) {
    btn.addEventListener('click', function () { setMode(btn.getAttribute('data-mode')); });
  });
  $('chart').addEventListener('click', onChartClick);
  window.addEventListener('resize', onResize);

  return api('/api/holes').then(function (holes) {
    state.holes = holes;
    if (!holes.length) {
      showError('No boreholes found in the index database. Check data/index.sqlite.');
      return;
    }
    var sel = $('hole-select');
    sel.innerHTML = holes.map(function (h) {
      return '<option value="' + esc(h.hole_id) + '">' + esc(h.hole_id) + '</option>';
    }).join('');
    sel.value = holes[0].hole_id;
    return loadHole(holes[0].hole_id);
  }).catch(function (err) {
    showError('Cannot connect to the backend. Start it with: python -m uvicorn server.app:app --port 8000. ' + err.message);
  });
}

/* ---------------- Hole loading ---------------- */

function loadHole(holeId) {
  var token = ++state.loadToken;
  state.holeId = holeId;
  state.hole = null;
  state.meta = null;
  state.sections = [];
  state.intervals = [];
  state.selected = null;
  state.reviewed = {};
  hideError();
  showLoading('Loading borehole metadata...');
  renderDetailPlaceholder();

  for (var i = 0; i < state.holes.length; i++) {
    if (state.holes[i].hole_id === holeId) state.hole = state.holes[i];
  }

  return api('/api/holes/' + encodeURIComponent(holeId) + '/meta').then(function (meta) {
    if (token !== state.loadToken) return;
    state.meta = meta;
    state.depthMin = meta.depth_from;
    state.depthMax = meta.depth_to;

    // Switch to the first available sensor if the current sensor is unavailable.
    var sensors = meta.sensors && meta.sensors.length ? meta.sensors : ['vnir'];
    if (sensors.indexOf(state.sensor) < 0) state.sensor = sensors[0];
    updateSensorButtons(sensors);

    // Flatten the section list.
    var sections = [];
    meta.trays.forEach(function (tray) {
      (tray.sections || []).forEach(function (s) {
        sections.push({
          tray: tray.tray,
          trayLabel: tray.tray_label,
          section: s.section,
          row: s.row,
          depthFrom: s.depth_from,
          depthTo: s.depth_to,
          strip: s.strip,
          note: s.note || '',
          image: null,
          imageFailed: false,
          tex: {},      // mode -> THREE.CanvasTexture cache
          mesh: null,
          sideMat: null
        });
      });
    });
    sections.sort(function (a, b) { return a.section - b.section; });
    state.sections = sections;

    $('hole-info').textContent =
      fmt(meta.depth_from, 2) + '–' + fmt(meta.depth_to, 2) + ' m · ' +
      meta.trays.length + ' trays · ' + sections.length + ' sections';

    return loadIntervals(holeId, state.sensor, token);
  }).then(function () {
    if (token !== state.loadToken) return;
    computeMineralColors();
    setupSceneOnce();
    buildCore();
    updateModeButtons();
    buildLegend();
    drawChart();
    return preloadStripImages(token);
  }).then(function () {
    if (token !== state.loadToken) return;
    hideLoading();
  }).catch(function (err) {
    if (token !== state.loadToken) return;
    hideLoading();
    showError('Failed to load borehole ' + holeId + ': ' + err.message);
  });
}

function loadIntervals(holeId, sensor, token) {
  var key = holeId + '|' + sensor;
  if (state.intervalCache[key]) {
    state.intervals = state.intervalCache[key];
    return Promise.resolve();
  }
  return api('/api/holes/' + encodeURIComponent(holeId) + '/intervals?sensor=' + sensor).then(function (list) {
    if (token !== undefined && token !== state.loadToken) return;
    list.sort(function (a, b) { return a.depth_from - b.depth_from || a.id - b.id; });
    state.intervalCache[key] = list;
    state.intervals = list;
  });
}

/** Preload strip images and refresh each section when its active mode uses photos. */
function preloadStripImages(token) {
  var total = state.sections.length;
  var done = 0;
  var failed = 0;
  showLoading('Loading core strip images... 0/' + total);
  var jobs = state.sections.map(function (sec) {
    return new Promise(function (resolve) {
      var img = new Image();
      img.onload = function () {
        if (token !== state.loadToken) { resolve(); return; }
        sec.image = img;
        // Invalidate photo-dependent textures and rebuild them as needed.
        disposeSecTexture(sec, 'photo');
        disposeSecTexture(sec, 'overlay');
        if (state.mode === 'photo' || state.mode === 'overlay') applyMode(sec);
        done += 1;
        setLoadingProgress(done, total);
        resolve();
      };
      img.onerror = function () {
        sec.imageFailed = true;
        failed += 1;
        done += 1;
        setLoadingProgress(done, total);
        resolve();
      };
      img.src = '/api/holes/' + encodeURIComponent(state.holeId) + '/strip/' + encodeURIComponent(sec.strip);
    });
  });
  return Promise.all(jobs).then(function () {
    if (failed > 0) {
      showError(failed + ' strip images failed to load. Affected sections appear grey.');
    }
  });
}

/* ---------------- Toolbar interactions ---------------- */

function updateSensorButtons(sensors) {
  Array.prototype.forEach.call(document.querySelectorAll('#sensor-seg .seg-btn'), function (btn) {
    var s = btn.getAttribute('data-sensor');
    btn.disabled = sensors.indexOf(s) < 0;
    btn.classList.toggle('active', s === state.sensor);
  });
}

function updateModeButtons() {
  Array.prototype.forEach.call(document.querySelectorAll('#mode-seg .seg-btn'), function (btn) {
    btn.classList.toggle('active', btn.getAttribute('data-mode') === state.mode);
  });
}

function setSensor(sensor) {
  if (sensor === state.sensor) return;
  state.sensor = sensor;
  updateSensorButtons((state.meta && state.meta.sensors) || [sensor]);
  var token = state.loadToken;
  loadIntervals(state.holeId, sensor, token).then(function () {
    if (token !== state.loadToken) return;
    computeMineralColors();
    // Mineral and overlay textures depend on interval data; invalidate and rebuild them.
    state.sections.forEach(function (sec) {
      disposeSecTexture(sec, 'mineral');
      disposeSecTexture(sec, 'overlay');
    });
    if (state.mode !== 'photo') applyModeAll();
    buildLegend();
    // Keep the selected depth and find the interval for the current sensor.
    if (state.selected) {
      state.selected.interval = findIntervalByDepth(state.selected.depth);
      renderDetail();
      loadSpectrum(state.selected.section, state.selected.depth);
    }
    drawChart();
  }).catch(function (err) {
    showError('Failed to load intervals: ' + err.message);
  });
}

function setMode(mode) {
  if (mode === state.mode) return;
  state.mode = mode;
  updateModeButtons();
  applyModeAll();
}

/* ---------------- 3D scene ---------------- */

function setupSceneOnce() {
  if (renderer) return;
  var canvas = $('gl');
  renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x101317);

  camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);

  var hemi = new THREE.HemisphereLight(0xffffff, 0x30363d, 1.0);
  scene.add(hemi);
  var dir = new THREE.DirectionalLight(0xffffff, 1.2);
  dir.position.set(1, 0.6, 0.8);
  scene.add(dir);

  controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;

  capMaterial = new THREE.MeshStandardMaterial({ color: 0x8a919a, roughness: 0.9 });

  // Marker ring for the selected depth, initially hidden.
  ringMesh = new THREE.Mesh(
    new THREE.TorusGeometry(CORE_RADIUS * 1.18, 0.05, 8, 72),
    new THREE.MeshBasicMaterial({ color: 0xff8800 })
  );
  ringMesh.rotation.x = Math.PI / 2;
  ringMesh.visible = false;
  scene.add(ringMesh);

  // Treat small pointer movements as clicks and larger movements as rotation drags.
  var downX = 0;
  var downY = 0;
  canvas.addEventListener('pointerdown', function (e) {
    downX = e.clientX;
    downY = e.clientY;
  });
  canvas.addEventListener('pointerup', function (e) {
    if (Math.abs(e.clientX - downX) + Math.abs(e.clientY - downY) > 6) return;
    pickAt(e);
  });

  onResize();
  requestAnimationFrame(animate);
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

/** Rebuild the core as vertically stacked cylinders, with shallow depth at each top. */
function buildCore() {
  if (coreGroup) {
    scene.remove(coreGroup);
    disposeCore();
  }
  coreGroup = new THREE.Group();
  var depthMin = state.depthMin;

  state.sections.forEach(function (sec) {
    var span = sec.depthTo - sec.depthFrom;
    var h = Math.max(span, MIN_SECTION_HEIGHT);
    var mid = (sec.depthFrom + sec.depthTo) / 2;
    var geo = new THREE.CylinderGeometry(CORE_RADIUS, CORE_RADIUS, h, RADIAL_SEGMENTS, 1, false);
    // Material groups: 0 = textured side, 1 = top cap, 2 = bottom cap.
    var sideMat = new THREE.MeshStandardMaterial({
      color: 0xcccccc,
      roughness: 0.92,
      metalness: 0.0
    });
    var mesh = new THREE.Mesh(geo, [sideMat, capMaterial, capMaterial]);
    mesh.position.y = -(mid - depthMin);
    mesh.userData.section = sec;
    sec.mesh = mesh;
    sec.sideMat = sideMat;
    coreGroup.add(mesh);
    applyMode(sec);
  });

  scene.add(coreGroup);

  var spanAll = Math.max(state.depthMax - state.depthMin, 1);
  camera.position.set(spanAll * 0.32, -spanAll * 0.35, spanAll * 0.5);
  controls.target.set(0, -spanAll / 2, 0);
  controls.update();
  ringMesh.visible = false;
}

function disposeCore() {
  if (!coreGroup) return;
  state.sections.forEach(function (sec) {
    if (sec.mesh) sec.mesh.geometry.dispose();
    if (sec.sideMat) sec.sideMat.dispose();
    ['photo', 'mineral', 'overlay'].forEach(function (m) { disposeSecTexture(sec, m); });
    sec.mesh = null;
    sec.sideMat = null;
  });
}

function applyModeAll() {
  state.sections.forEach(function (sec) { applyMode(sec); });
}

function applyMode(sec) {
  if (!sec.sideMat) return;
  var tex = getSectionTexture(sec, state.mode);
  sec.sideMat.map = tex;
  sec.sideMat.color.set('#ffffff');
  sec.sideMat.needsUpdate = true;
}

function disposeSecTexture(sec, mode) {
  var t = sec.tex[mode];
  if (t) {
    t.dispose();
    delete sec.tex[mode];
  }
}

/* ---------------- Texture generation ---------------- */

function getSectionTexture(sec, mode) {
  if (sec.tex[mode]) return sec.tex[mode];
  var canvas;
  if (mode === 'photo') {
    canvas = makePhotoCanvas(sec);
  } else if (mode === 'mineral') {
    canvas = makeMineralCanvas(sec, false);
  } else {
    canvas = makeOverlayCanvas(sec);
  }
  var tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  sec.tex[mode] = tex;
  return tex;
}

/**
 * Draw the strip on a canvas rotated 90 degrees clockwise.
 * Canvas width follows the circumference (TEX_CIRC); height follows depth (TEX_LEN).
 * The shallow left edge becomes the top row and maps to the cylinder top.
 */
function makePhotoCanvas(sec) {
  var c = document.createElement('canvas');
  c.width = TEX_CIRC;
  c.height = TEX_LEN;
  var g = c.getContext('2d');
  if (sec.image) {
    g.translate(TEX_CIRC, 0);
    g.rotate(Math.PI / 2);
    g.drawImage(sec.image, 0, 0, TEX_LEN, TEX_CIRC);
  } else {
    g.fillStyle = '#777777';
    g.fillRect(0, 0, TEX_CIRC, TEX_LEN);
    if (sec.imageFailed) {
      g.fillStyle = '#dddddd';
      g.font = '20px sans-serif';
      g.save();
      g.translate(TEX_CIRC, 0);
      g.rotate(Math.PI / 2);
      g.fillText('Missing image', TEX_LEN / 2 - 40, TEX_CIRC / 2 + 7);
      g.restore();
    }
  }
  return c;
}

/** Draw mineral bands in the same rotated coordinate system as the photos. */
function drawMineralBands(g, sec) {
  var s0 = sec.depthFrom;
  var s1 = sec.depthTo;
  var span = s1 - s0;
  g.save();
  g.translate(TEX_CIRC, 0);
  g.rotate(Math.PI / 2);
  state.intervals.forEach(function (iv) {
    if (iv.depth_to < s0 || iv.depth_from > s1) return;
    var a = Math.max(iv.depth_from, s0);
    var b = Math.min(iv.depth_to, s1);
    var x0;
    var w;
    if (span > 0) {
      x0 = ((a - s0) / span) * TEX_LEN;
      w = Math.max(((b - a) / span) * TEX_LEN, 1);
    } else {
      x0 = 0;
      w = TEX_LEN; // Fill the entire texture for a zero-length section.
    }
    var color = state.colorOf(iv.mineral);
    if (iv.status === 'doubtful') {
      g.fillStyle = g.createPattern(getHatchCanvas(color), 'repeat');
    } else {
      g.fillStyle = color;
    }
    g.fillRect(x0, 0, w, TEX_CIRC);
  });
  g.restore();
}

function makeMineralCanvas(sec, transparentBg) {
  var c = document.createElement('canvas');
  c.width = TEX_CIRC;
  c.height = TEX_LEN;
  var g = c.getContext('2d');
  if (!transparentBg) {
    g.fillStyle = '#e5e5e5';
    g.fillRect(0, 0, TEX_CIRC, TEX_LEN);
  }
  drawMineralBands(g, sec);
  return c;
}

function makeOverlayCanvas(sec) {
  var photo = makePhotoCanvas(sec);
  var g = photo.getContext('2d');
  var bands = makeMineralCanvas(sec, true);
  g.globalAlpha = OVERLAY_ALPHA;
  g.drawImage(bands, 0, 0);
  g.globalAlpha = 1;
  return photo;
}

/* Cache 45-degree hatch patterns by colour for doubtful intervals. */
var hatchCache = {};
function getHatchCanvas(color) {
  if (hatchCache[color]) return hatchCache[color];
  var c = document.createElement('canvas');
  c.width = 8;
  c.height = 8;
  var g = c.getContext('2d');
  g.strokeStyle = color;
  g.lineWidth = 2.5;
  g.beginPath();
  g.moveTo(-2, 10);
  g.lineTo(10, -2);
  g.moveTo(-2, 2);
  g.lineTo(2, -2);
  g.moveTo(6, 10);
  g.lineTo(10, 6);
  g.stroke();
  hatchCache[color] = c;
  return c;
}

/* ---------------- Mineral colours and legend ---------------- */

function computeMineralColors() {
  var thickness = {};
  var nullT = 0;
  state.intervals.forEach(function (iv) {
    var t = Math.max(iv.depth_to - iv.depth_from, 0);
    if (iv.mineral === null || iv.mineral === undefined) {
      nullT += t;
    } else {
      thickness[iv.mineral] = (thickness[iv.mineral] || 0) + t;
    }
  });
  var names = Object.keys(thickness).sort(function (a, b) { return thickness[b] - thickness[a]; });
  var colorMap = {};
  state.legendMinerals = [];
  names.forEach(function (name, idx) {
    var color = idx < MAX_PALETTE_MINERALS ? PALETTE[idx] : OTHER_COLOR;
    colorMap[name] = color;
    if (idx < MAX_PALETTE_MINERALS) {
      state.legendMinerals.push({ mineral: name, color: color, thickness: thickness[name] });
    }
  });
  var otherT = 0;
  names.forEach(function (name, idx) {
    if (idx >= MAX_PALETTE_MINERALS) otherT += thickness[name];
  });
  state.otherThickness = otherT;
  state.nullThickness = nullT;
  state.colorOf = function (mineral) {
    if (mineral === null || mineral === undefined) return NULL_COLOR;
    return Object.prototype.hasOwnProperty.call(colorMap, mineral) ? colorMap[mineral] : OTHER_COLOR;
  };
}

function buildLegend() {
  var box = $('legend');
  var html = '<h3>Legend — ' + state.sensor.toUpperCase() + ' minerals by total thickness</h3>';
  state.legendMinerals.forEach(function (m) {
    html += '<div class="legend-row">' +
      '<span class="swatch" style="background:' + m.color + '"></span>' +
      '<span class="name">' + esc(m.mineral) + '</span>' +
      '<span class="thick">' + fmt(m.thickness, 2) + ' m</span></div>';
  });
  if (state.otherThickness > 0) {
    html += '<div class="legend-row">' +
      '<span class="swatch" style="background:' + OTHER_COLOR + '"></span>' +
      '<span class="name">Other minerals (outside the top 20)</span>' +
      '<span class="thick">' + fmt(state.otherThickness, 2) + ' m</span></div>';
  }
  if (state.nullThickness > 0) {
    html += '<div class="legend-row">' +
      '<span class="swatch" style="background:' + NULL_COLOR + '"></span>' +
      '<span class="name">Unassigned (mineral = null)</span>' +
      '<span class="thick">' + fmt(state.nullThickness, 2) + ' m</span></div>';
  }
  html += '<div class="legend-row"><span class="swatch swatch-hatch"></span>' +
    '<span class="name">45° hatching = doubtful; solid colour = confirmed</span></div>';
  box.innerHTML = html;
}

/* ---------------- 2D depth chart ---------------- */

function chartGeom() {
  var canvas = $('chart');
  var box = $('chart-box');
  var dpr = window.devicePixelRatio || 1;
  var w = box.clientWidth;
  var h = box.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  return { canvas: canvas, w: w, h: h, dpr: dpr };
}

function drawChart() {
  if (!state.meta) return;
  var gm = chartGeom();
  var g = gm.canvas.getContext('2d');
  g.setTransform(gm.dpr, 0, 0, gm.dpr, 0, 0);
  var W = gm.w;
  var H = gm.h;
  g.clearRect(0, 0, W, H);
  g.fillStyle = '#171b20';
  g.fillRect(0, 0, W, H);

  var depthMin = state.depthMin;
  var depthMax = state.depthMax;
  var span = Math.max(depthMax - depthMin, 1e-9);

  var padL = 46;
  var padT = 22;
  var padB = 10;
  var trackW = 46;
  var gap = 8;
  var padR = 10;
  var plotTop = padT;
  var plotBot = H - padB;
  var trackX0 = padL;
  var trackX1 = padL + trackW;
  var wtX0 = trackX1 + gap;
  var wtX1 = W - padR;
  var wtW = Math.max(wtX1 - wtX0, 10);

  function yOf(d) { return plotTop + ((d - depthMin) / span) * (plotBot - plotTop); }

  // Title
  g.fillStyle = '#9ca3af';
  g.font = '11px sans-serif';
  g.textAlign = 'left';
  g.fillText('Depth (m)', 4, 13);
  g.textAlign = 'right';
  g.fillText('wt1 (0–1)', W - padR, 13);

  // Depth grid lines and ticks
  var step = 10;
  var firstTick = Math.ceil(depthMin / step) * step;
  g.textAlign = 'right';
  g.strokeStyle = '#2a313b';
  g.lineWidth = 1;
  for (var d = firstTick; d <= depthMax; d += step) {
    var y = yOf(d);
    g.beginPath();
    g.moveTo(padL - 4, y);
    g.lineTo(W - padR, y);
    g.stroke();
    g.fillStyle = '#9ca3af';
    g.fillText(String(Math.round(d)), padL - 7, y + 3.5);
  }
  // Tray boundary ticks
  g.strokeStyle = '#4b5563';
  state.meta.trays.forEach(function (tray) {
    var y2 = yOf(tray.depth_from);
    g.beginPath();
    g.moveTo(trackX0 - 3, y2);
    g.lineTo(trackX0 + 2, y2);
    g.stroke();
  });

  // Mineral track background
  g.fillStyle = '#f5f5f5';
  g.fillRect(trackX0, plotTop, trackW, plotBot - plotTop);

  // Interval colour bands
  state.intervals.forEach(function (iv) {
    var y0 = yOf(Math.max(iv.depth_from, depthMin));
    var y1 = yOf(Math.min(iv.depth_to, depthMax));
    var hh = Math.max(y1 - y0, 1);
    var color = state.colorOf(iv.mineral);
    if (iv.status === 'doubtful') {
      g.fillStyle = g.createPattern(getHatchCanvas(color), 'repeat');
    } else {
      g.fillStyle = color;
    }
    g.fillRect(trackX0, y0, trackW, hh);
  });
  g.strokeStyle = '#6b7280';
  g.strokeRect(trackX0 + 0.5, plotTop + 0.5, trackW - 1, plotBot - plotTop - 1);

  // wt1 line on a fixed 0–1 scale, with gaps at null values
  g.strokeStyle = '#e5e7eb';
  g.lineWidth = 1;
  g.strokeRect(wtX0 + 0.5, plotTop + 0.5, wtW - 1, plotBot - plotTop - 1);
  g.strokeStyle = '#38bdf8';
  g.lineWidth = 1.2;
  g.beginPath();
  var pen = false;
  state.intervals.forEach(function (iv) {
    if (iv.wt1_avg === null || iv.wt1_avg === undefined) { pen = false; return; }
    var v = Math.min(Math.max(iv.wt1_avg, 0), 1);
    var x = wtX0 + v * wtW;
    var y = yOf((iv.depth_from + iv.depth_to) / 2);
    if (!pen) { g.moveTo(x, y); pen = true; } else { g.lineTo(x, y); }
  });
  g.stroke();

  // Selected interval outline
  if (state.selected && state.selected.interval) {
    var iv = state.selected.interval;
    var sy0 = yOf(Math.max(iv.depth_from, depthMin));
    var sy1 = yOf(Math.min(iv.depth_to, depthMax));
    g.strokeStyle = '#ff8800';
    g.lineWidth = 2;
    g.strokeRect(trackX0 + 1, sy0, trackW - 2, Math.max(sy1 - sy0, 2));
  }

  // Selected depth marker after a 3D or 2D click
  if (state.selected) {
    var my = yOf(state.selected.depth);
    g.strokeStyle = '#ff8800';
    g.lineWidth = 2;
    g.beginPath();
    g.moveTo(padL - 4, my);
    g.lineTo(W - padR, my);
    g.stroke();
    var label = fmt(state.selected.depth, 2) + ' m';
    g.font = '11px sans-serif';
    var tw = g.measureText(label).width;
    g.fillStyle = '#ff8800';
    g.fillRect(W - padR - tw - 8, my - 14, tw + 8, 13);
    g.fillStyle = '#111111';
    g.textAlign = 'left';
    g.fillText(label, W - padR - tw - 4, my - 3.5);
  }
}

function onChartClick(e) {
  if (!state.meta) return;
  var canvas = $('chart');
  var rect = canvas.getBoundingClientRect();
  var H = rect.height;
  var padT = 22;
  var padB = 10;
  var frac = (e.clientY - rect.top - padT) / (H - padT - padB);
  frac = Math.min(Math.max(frac, 0), 1);
  var depth = state.depthMin + frac * (state.depthMax - state.depthMin);
  selectDepth(depth, null);
}

/* ---------------- Selection and picking ---------------- */

function pickAt(e) {
  if (!coreGroup) return;
  var rect = renderer.domElement.getBoundingClientRect();
  var ndc = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1
  );
  raycaster.setFromCamera(ndc, camera);
  var hits = raycaster.intersectObjects(coreGroup.children, false);
  if (!hits.length) return;
  var hit = hits[0];
  var sec = hit.object.userData.section;
  // Convert the cylinder hit point back to depth: y = -(depth - depthMin).
  var depth = state.depthMin - hit.point.y;
  depth = Math.min(Math.max(depth, state.depthMin), state.depthMax);
  selectDepth(depth, sec);
}

function findSectionByDepth(depth) {
  var best = null;
  var bestDist = Infinity;
  state.sections.forEach(function (sec) {
    if (sec.depthFrom <= depth && depth <= sec.depthTo) {
      var c = (sec.depthFrom + sec.depthTo) / 2;
      var dc = Math.abs(depth - c);
      if (dc < bestDist) { bestDist = dc; best = sec; }
    }
  });
  if (best) return best;
  state.sections.forEach(function (sec) {
    var dist = depth < sec.depthFrom ? sec.depthFrom - depth
      : depth > sec.depthTo ? depth - sec.depthTo : 0;
    if (dist < bestDist) { bestDist = dist; best = sec; }
  });
  return best;
}

function findIntervalByDepth(depth) {
  var best = null;
  var bestDist = Infinity;
  state.intervals.forEach(function (iv) {
    var dist = depth < iv.depth_from ? iv.depth_from - depth
      : depth > iv.depth_to ? depth - iv.depth_to : 0;
    if (dist < bestDist) { bestDist = dist; best = iv; }
  });
  // Treat gaps greater than 0.1 m, such as tray seams, as having no interval.
  return bestDist <= 0.1 ? best : null;
}

function selectDepth(depth, sec) {
  if (!sec) sec = findSectionByDepth(depth);
  if (!sec) return;
  var iv = findIntervalByDepth(depth);
  state.selected = { section: sec, depth: depth, interval: iv };

  // Reset the old 3D selection and highlight the new section side with emissive colour.
  state.sections.forEach(function (s) {
    if (s.sideMat) s.sideMat.emissive.set('#000000');
  });
  if (sec.sideMat) sec.sideMat.emissive.set('#7a3c00');
  ringMesh.position.y = -(depth - state.depthMin);
  ringMesh.visible = true;

  renderDetail();
  loadSpectrum(sec, depth);
  drawChart();
}

/* ---------------- Details panel ---------------- */

function renderDetailPlaceholder() {
  $('detail').innerHTML = '<div class="placeholder">Click the 3D core or the depth chart to inspect intervals and spectra.</div>';
}

function renderDetail() {
  var sel = state.selected;
  var box = $('detail');
  if (!sel) { renderDetailPlaceholder(); return; }
  var sec = sel.section;
  var iv = sel.interval;

  var html = '<div class="detail-title">Section ' + sec.section +
    '<span class="badge" style="background:#262c35;color:#9ca3af">Tray ' + esc(sec.trayLabel) +
    ' · Row ' + sec.row + '</span></div>' +
    '<div class="detail-sub">Section depth ' + fmt(sec.depthFrom, 3) + '–' + fmt(sec.depthTo, 3) +
    ' m · Selected depth ' + fmt(sel.depth, 3) + ' m</div>';

  if (sec.note) {
    html += '<div class="detail-sub">Note: ' + esc(sec.note) + '</div>';
  }

  if (iv) {
    var reviewed = state.reviewed[iv.id];
    html += '<table class="kv-table">' +
      '<tr><td class="k">Interval ID</td><td>' + iv.id + '</td></tr>' +
      '<tr><td class="k">Depth range</td><td>' + fmt(iv.depth_from, 3) + '–' + fmt(iv.depth_to, 3) + ' m</td></tr>' +
      '<tr><td class="k">Mineral</td><td>' + (iv.mineral ? esc(iv.mineral) : '— (unassigned)') + '</td></tr>' +
      '<tr><td class="k">Mineral group</td><td>' + (iv.grp ? esc(iv.grp) : '—') + '</td></tr>' +
      '<tr><td class="k">wt1_avg</td><td>' + fmt(iv.wt1_avg) + '</td></tr>' +
      '<tr><td class="k">error_avg</td><td>' + fmt(iv.error_avg) + '</td></tr>' +
      '<tr><td class="k">nil_avg</td><td>' + fmt(iv.nil_avg) + '</td></tr>' +
      '<tr><td class="k">Samples</td><td>' + (iv.n_samples === null ? '—' : iv.n_samples) + '</td></tr>' +
      '<tr><td class="k">Status</td><td>' + statusLabel(iv.status) +
      ' <span class="badge badge-' + iv.status + '">' + iv.status + '</span>' +
      (reviewed ? ' <span class="badge badge-reviewed">Reviewed</span>' : '') + '</td></tr>' +
      '<tr><td class="k">Flags</td><td>' + (iv.flags ? esc(iv.flags) : '—') + '</td></tr>' +
      '</table>' +
      '<input type="text" id="note-input" placeholder="Review note (optional)">' +
      '<div class="detail-btns">' +
      '<button type="button" id="btn-confirm">Confirm</button>' +
      '<button type="button" id="btn-doubt">Doubtful</button>' +
      '<span id="save-msg"></span></div>';
  } else {
    html += '<div class="detail-sub">No interval within ±0.1 m of this depth; this may be a tray seam or an unscanned section.</div>';
  }

  html += '<div class="spectrum-title" id="spectrum-title">Loading spectrum...</div>' +
    '<canvas id="spectrum-canvas"></canvas>';
  box.innerHTML = html;

  if (iv) {
    $('btn-confirm').addEventListener('click', function () { postStatus('confirmed'); });
    $('btn-doubt').addEventListener('click', function () { postStatus('doubtful'); });
  }
}

/* ---------------- Spectra ---------------- */

function loadSpectrum(sec, depth) {
  var sel = state.selected;
  if (!sel) return;
  // Estimate the spectrum index using this dataset's fixed 131 samples per section.
  // Samples are numbered across the hole: section 1 uses 0–130; section 2 starts at 131.
  // Map relative depth to 0–130, ignoring small variations in sample spacing.
  var span = sec.depthTo - sec.depthFrom;
  var frac = span > 0 ? (depth - sec.depthFrom) / span : 0;
  frac = Math.min(Math.max(frac, 0), 1);
  var sample = (sec.section - 1) * SAMPLES_PER_SECTION + Math.round(frac * (SAMPLES_PER_SECTION - 1));

  var titleEl = $('spectrum-title');
  if (titleEl) {
    titleEl.textContent = state.sensor.toUpperCase() + ' spectrum · Sample #' + sample + ' (estimated from relative section depth)';
  }

  api('/api/holes/' + encodeURIComponent(state.holeId) + '/spectrum?sensor=' + state.sensor + '&sample=' + sample)
    .then(function (spec) {
      // The selected depth may have changed while the request was pending.
      if (state.selected !== sel) return;
      var canvas = $('spectrum-canvas');
      if (!canvas) return;
      drawSpectrum(canvas, spec);
    })
    .catch(function (err) {
      if (state.selected !== sel) return;
      var t = $('spectrum-title');
      if (t) t.textContent = 'Failed to load spectrum: ' + err.message;
    });
}

function drawSpectrum(canvas, spec) {
  var dpr = window.devicePixelRatio || 1;
  var w = canvas.clientWidth || 340;
  var h = canvas.clientHeight || 180;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  var g = canvas.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = '#11151a';
  g.fillRect(0, 0, w, h);

  var wl = spec.wavelengths_nm || [];
  var vals = spec.values || [];
  var pts = [];
  var vmin = Infinity;
  var vmax = -Infinity;
  for (var i = 0; i < wl.length && i < vals.length; i++) {
    if (vals[i] === null || vals[i] === undefined) continue;
    pts.push([wl[i], vals[i]]);
    if (vals[i] < vmin) vmin = vals[i];
    if (vals[i] > vmax) vmax = vals[i];
  }
  if (!pts.length) {
    g.fillStyle = '#9ca3af';
    g.font = '12px sans-serif';
    g.textAlign = 'center';
    g.fillText('All spectrum values are null for this sample', w / 2, h / 2);
    return;
  }
  var wlMin = wl[0];
  var wlMax = wl[wl.length - 1];
  if (vmax - vmin < 1e-12) vmax = vmin + 1e-12;

  var padL = 44;
  var padR = 8;
  var padT = 8;
  var padB = 20;
  function xOf(v) { return padL + ((v - wlMin) / (wlMax - wlMin)) * (w - padL - padR); }
  function yOf(v) { return padT + (1 - (v - vmin) / (vmax - vmin)) * (h - padT - padB); }

  g.strokeStyle = '#2a313b';
  g.lineWidth = 1;
  g.strokeRect(padL + 0.5, padT + 0.5, w - padL - padR - 1, h - padT - padB - 1);

  // Draw the line with gaps at null values.
  g.strokeStyle = '#4ade80';
  g.lineWidth = 1.2;
  g.beginPath();
  var pen = false;
  for (var j = 0; j < wl.length && j < vals.length; j++) {
    if (vals[j] === null || vals[j] === undefined) { pen = false; continue; }
    var x = xOf(wl[j]);
    var y = yOf(vals[j]);
    if (!pen) { g.moveTo(x, y); pen = true; } else { g.lineTo(x, y); }
  }
  g.stroke();

  g.fillStyle = '#9ca3af';
  g.font = '10.5px sans-serif';
  g.textAlign = 'left';
  g.fillText(fmt(vmax, 3), 4, padT + 9);
  g.fillText(fmt(vmin, 3), 4, h - padB);
  g.textAlign = 'center';
  g.fillText(fmt(wlMin, 0) + ' nm', padL + 14, h - 6);
  g.fillText(fmt(wlMax, 0) + ' nm', w - padR - 18, h - 6);
}

/* ---------------- Status review (POST) ---------------- */

function postStatus(newStatus) {
  var sel = state.selected;
  if (!sel || !sel.interval) return;
  var iv = sel.interval;
  var noteInput = $('note-input');
  var note = noteInput && noteInput.value.trim() ? noteInput.value.trim() : null;
  var btnC = $('btn-confirm');
  var btnD = $('btn-doubt');
  var msg = $('save-msg');
  if (btnC) btnC.disabled = true;
  if (btnD) btnD.disabled = true;
  if (msg) { msg.className = ''; msg.textContent = 'Saving...'; }

  api('/api/holes/' + encodeURIComponent(state.holeId) + '/intervals/' + iv.id + '/status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(note ? { status: newStatus, note: note } : { status: newStatus })
  }).then(function (updated) {
    // Update the local interval and its shared cache reference.
    iv.status = updated.status;
    state.reviewed[iv.id] = true;
    // Rebuild mineral and overlay textures for sections covered by this interval.
    state.sections.forEach(function (sec) {
      if (sec.depthTo < updated.depth_from || sec.depthFrom > updated.depth_to) return;
      disposeSecTexture(sec, 'mineral');
      disposeSecTexture(sec, 'overlay');
      if (state.mode === 'mineral' || state.mode === 'overlay') applyMode(sec);
    });
    renderDetail();
    var msg2 = $('save-msg');
    if (msg2) msg2.textContent = 'Saved: status → ' + statusLabel(updated.status) + ' (reviewed)';
    drawChart();
  }).catch(function (err) {
    var msg3 = $('save-msg');
    if (msg3) { msg3.className = 'err'; msg3.textContent = 'Failed to save: ' + err.message; }
    if (btnC) btnC.disabled = false;
    if (btnD) btnD.disabled = false;
  });
}

/* ---------------- Responsive sizing ---------------- */

function onResize() {
  var vp = $('viewport');
  if (renderer) {
    renderer.setSize(vp.clientWidth, vp.clientHeight);
    camera.aspect = vp.clientWidth / Math.max(vp.clientHeight, 1);
    camera.updateProjectionMatrix();
  }
  drawChart();
}

/* ---------------- Startup ---------------- */

init();
