"use strict";

// Track map: the track's outline (as on the live timing website: a lap
// recorded by Apex Overlays, iRacing's own map, or the shared library) with
// a dot for every car where it is, in its main or secondary class colour.
// The outline comes once from /api/trackmap; each snapshot says where the
// cars are, and between them they carry on at their own speed.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
let cfg = null;
let data = null;            // the snapshot's trackmap: {map, cam, cars, clock}
let points = null;          // the outline: lap fraction i / n -> [x, y] (0..1)
let mapId;                  // which one that is
let box = null;             // the widget's element
const motion = new Map();   // car -> {pct, clock, at, speed, shown}
let pixels = 420;           // the canvases' size (px)

async function loadMap(id) {
  mapId = id;
  if (!id) {
    points = null;
    return;
  }
  try {
    const m = await (await fetch("/api/trackmap", { cache: "no-store" })).json();
    points = m && m.id === id && Array.isArray(m.points) && m.points.length > 50 ? m.points : null;
    if (!points) mapId = undefined;  // not there yet: asked again next time
  } catch (e) {
    points = null;
    mapId = undefined;
  }
  trackKey = "";
}

// Where a lap fraction is on the canvas.
function locate(pct, size, pad) {
  const n = points.length;
  const f = (((pct % 1) + 1) % 1) * n;
  const i = Math.floor(f) % n, j = (i + 1) % n, k = f - Math.floor(f);
  const p = points[i], q = points[j];
  const s = size - pad * 2;
  return [pad + (p[0] + (q[0] - p[0]) * k) * s, pad + (p[1] + (q[1] - p[1]) * k) * s];
}

// The outline, drawn once into a picture of its own (again when it or its look changes).
const trackPic = document.createElement("canvas");
let trackKey = "";
function track(size, pad, k) {
  const key = [size, mapId, cfg.track_color, cfg.track_width, cfg.start_line].join("|");
  if (key === trackKey) return trackPic;
  trackKey = key;
  trackPic.width = trackPic.height = size;
  const g = trackPic.getContext("2d");
  g.clearRect(0, 0, size, size);
  g.lineJoin = g.lineCap = "round";
  const path = () => {
    g.beginPath();
    for (let i = 0; i <= points.length; i++) {
      const [x, y] = locate(i / points.length, size, pad);
      if (i) g.lineTo(x, y);
      else g.moveTo(x, y);
    }
    g.closePath();
  };
  const w = (cfg.track_width / 100) * k;
  // A dark edge so it reads over any picture, then the track itself.
  path();
  g.strokeStyle = "rgba(0, 0, 0, .55)";
  g.lineWidth = 11 * w;
  g.stroke();
  path();
  g.strokeStyle = cfg.track_color || "#ffffff";
  g.lineWidth = 6 * w;
  g.stroke();
  if (cfg.start_line) {
    const [x1, y1] = locate(-0.003, size, pad), [x2, y2] = locate(0.003, size, pad), [x, y] = locate(0, size, pad);
    const a = Math.atan2(y2 - y1, x2 - x1) + Math.PI / 2;
    const len = 10 * w;
    for (let s = 0; s < 4; s++) {
      g.strokeStyle = s % 2 ? "#111" : "#fff";
      g.lineWidth = 4 * w;
      g.beginPath();
      g.moveTo(x - Math.cos(a) * len + (Math.cos(a) * 2 * len * s) / 4, y - Math.sin(a) * len + (Math.sin(a) * 2 * len * s) / 4);
      g.lineTo(x - Math.cos(a) * len + (Math.cos(a) * 2 * len * (s + 1)) / 4, y - Math.sin(a) * len + (Math.sin(a) * 2 * len * (s + 1)) / 4);
      g.stroke();
    }
  }
  return trackPic;
}

// Smooth movement: each car carries on at the speed it's been going between
// snapshots (timed by the session clock), small misses eased out.
const wrap = (d) => d - Math.round(d);
function noteMotion() {
  const clock = data.clock, now = performance.now();
  const seen = new Set();
  for (const c of data.cars) {
    seen.add(c.id);
    const m = motion.get(c.id);
    if (!m || clock == null || m.clock == null || clock < m.clock || clock - m.clock > 5) {
      motion.set(c.id, { pct: c.pct, clock, at: now, speed: 0, shown: m ? m.shown : c.pct });
      continue;
    }
    const dt = clock - m.clock;
    if (dt <= 0) continue;
    const d = wrap(c.pct - m.pct);
    const speed = d < -0.002 || d / dt > 0.15 ? 0 : Math.max(0, d / dt);
    m.speed = m.speed ? m.speed * 0.4 + speed * 0.6 : speed;
    if (Math.abs(wrap(c.pct - m.shown)) > 0.1) m.shown = c.pct;
    Object.assign(m, { pct: c.pct, clock, at: now });
  }
  for (const id of motion.keys()) if (!seen.has(id)) motion.delete(id);
}

// The cars are drawn 30 times a second at most (smooth enough for dots
// going round a map, and half the work of every frame), and not at all while
// none has moved. The outline is a picture of its own underneath, drawn only
// when it changes. Both are as many pixels as the map takes on screen (up to
// twice its size), no more.
const FRAME_MS = 1000 / 30;
let lastFrame = performance.now();
let lastDrawn = "";
function draw() {
  if (!box || !points || !data) return false;  // nothing to draw: it starts again with the next snapshot
  const now = performance.now();
  const step = Math.min(100, now - lastFrame);
  lastFrame = now;
  const canvas = box.querySelector("canvas.tm-cars");
  const size = pixels;
  if (canvas.width !== size) {
    canvas.width = canvas.height = size;
    lastDrawn = "";
  }
  const k = size / 420;
  const pad = 22 * k * Math.max(1, cfg.dot_size / 100);
  const under = box.querySelector("canvas.tm-track");
  const pic = track(size, pad, k);
  if (under.dataset.key !== trackKey) {
    under.width = under.height = size;
    under.getContext("2d").drawImage(pic, 0, 0);
    under.dataset.key = trackKey;
  }
  const ease = 1 - Math.exp(-step / 120);
  // The car on camera last (on top).
  const cars = [...data.cars].sort((a, b) => (a.id === data.cam) - (b.id === data.cam));
  const dots = [];
  for (const c of cars) {
    const m = motion.get(c.id);
    if (!m) continue;
    const ahead = m.pct + m.speed * Math.min(1, (now - m.at) / 1000);
    m.shown = (((m.shown + wrap(ahead - m.shown) * ease) % 1) + 1) % 1;
    const [x, y] = locate(m.shown, size, pad);
    const cam = cfg.camera && c.id === data.cam;
    const label = cfg.labels === "number" ? String(c.num || "") : cfg.labels === "position" ? String(c.pos || "") : "";
    const r = (label ? 11 : 7) * k * (cfg.dot_size / 100) * (cam ? 1.35 : 1);
    const color = (cfg.colors === "secondary" ? c.second : c.main) || "#ffffff";
    dots.push({ x, y, cam, label, r, color, pit: c.pit });
  }
  const drawn = JSON.stringify([size, trackKey, dots.map((d) => [Math.round(d.x * 2), Math.round(d.y * 2), d.cam, d.label, d.color, d.pit])]);
  if (drawn === lastDrawn) return true;  // nothing's moved
  lastDrawn = drawn;
  const g = canvas.getContext("2d");
  g.clearRect(0, 0, size, size);
  for (const { x, y, cam, label, r, color, pit } of dots) {
    g.globalAlpha = pit ? 0.55 : 1;
    if (cam) {
      g.beginPath();
      g.arc(x, y, r + 5 * k, 0, Math.PI * 2);
      g.fillStyle = "#ffffff";
      g.fill();
    }
    g.beginPath();
    g.arc(x, y, r, 0, Math.PI * 2);
    g.fillStyle = color;
    g.fill();
    g.lineWidth = 2 * k;
    g.strokeStyle = "rgba(0, 0, 0, .7)";
    g.stroke();
    if (label) {
      g.fillStyle = inkFor(color);
      g.font = `900 ${Math.round(r * (label.length > 2 ? 0.85 : 1.05))}px system-ui, sans-serif`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(label, x, y + k);
    }
    g.globalAlpha = 1;
  }
  return true;
}
const runDraw = frameLoop(draw, FRAME_MS);

function render(snap) {
  const ov = snap.overlays;
  cfg = ov && ov.settings && ov.settings.trackmap;
  if (!cfg) return;
  setSize(cfg);
  data = ov.trackmap || null;
  if (data) {
    noteMotion();
    if (data.map !== mapId) loadMap(data.map);
  }
  const on = (cfg.visible || PREVIEW) && data && data.map;
  const hint = stage.querySelector(".tm-hint");
  if (PREVIEW && !(data && data.map)) {
    if (!hint) stage.insertAdjacentHTML("beforeend", '<div class="tm-hint">No track outline for this track yet (it shows once one is found)</div>');
  } else if (hint) hint.remove();
  if (!on) {
    if (box) {
      const old = box;
      old.classList.add("out");
      setTimeout(() => old.remove(), 480);
      box = null;
    }
    return;
  }
  if (!box) {
    stage.insertAdjacentHTML("beforeend", '<div class="tmap"><canvas class="tm-track"></canvas><canvas class="tm-cars"></canvas></div>');
    box = stage.lastElementChild;
    lastDrawn = "";  // a new canvas: the cars drawn on it whether or not they've moved
  }
  runDraw();
  box.className = `tmap ${cfg.place} ${cfg.visible ? "" : "hidden-preview"}`;
  box.style.setProperty("--map-size", `${cfg.map_size}px`);
  // As many pixels as it takes on screen (the page may be scaled to fit, or
  // on a high-resolution display), between its own size and twice that.
  const onScreen = box.getBoundingClientRect().width * (devicePixelRatio || 1);
  pixels = Math.round(Math.min(cfg.map_size * 2, Math.max(cfg.map_size, onScreen || cfg.map_size)));
}

followSnapshots(render);
