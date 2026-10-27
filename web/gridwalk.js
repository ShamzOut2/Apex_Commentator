"use strict";

// Grid walk broadcast graphic. Follows the walk state the server keeps, so the
// control panel and any number of OBS sources stay in step.

const stage = $("#stage");
if (new URLSearchParams(location.search).has("preview")) document.body.classList.add("preview");

function fit() {
  const s = Math.min(innerWidth / 1920, innerHeight / 1080);
  stage.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
}
addEventListener("resize", fit);
fit();

let snap = null;
let shownKey = "";
let progress = null;

const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3", logo: null };

function classFor(classes, e) {
  return classes.get(e.class_key) || DEFAULT_CLASS;
}

function card(e, cls, { side = "left", second = false, mirror = false, multiclass = false, style = "" } = {}) {
  const ink = inkFor(cls.color);
  const car = e.car_image
    ? `<img src="${esc(e.car_image)}" alt="">`
    : carSvg(e.car_design, e.number, { mirror });
  const helmet = e.helmet_image ? `<img src="${esc(e.helmet_image)}" alt="">` : helmetSvg(e.helmet_design);
  const status = !e.in_session ? "NOT IN SESSION" : !e.in_world ? "NOT ON TRACK" : "";
  const badge = cls.logo || multiclass ? classHeaderHtml(cls, "", rerender) : "";
  return `<div class="card ${side} ${second ? "second" : ""}" style="${style}">
    <div class="stripe" style="background:${esc(cls.color)}"></div>
    <div class="pos"><small>P</small>${e.grid_pos}</div>
    ${multiclass ? `<div class="class-pos">P${e.class_pos} in class</div>` : ""}
    <div class="tags">${badge}<div class="number" style="background:${esc(cls.color)};color:${ink}">#${esc(e.number)}</div></div>
    ${status ? `<div class="status">${status}</div>` : ""}
    <div class="car">${car}</div>
    <div class="helmet">${helmet}</div>
    <div class="who">
      <div class="name">${esc(e.name)}</div>
      ${e.nickname ? `<div class="nick">“${esc(e.nickname)}”</div>` : ""}
      ${e.team ? `<div class="team">${e.team_logo ? `<img src="${esc(e.team_logo)}" alt="">` : ""}<span>${esc(e.team)}</span></div>` : ""}
    </div>
  </div>`;
}

function titleBar(g, pair) {
  const row = Math.floor(g.index / 2) + 1;
  const sub = [snap.league && snap.league.name, snap.session && snap.session.track].filter(Boolean).join(" · ");
  const range = pair.length > 1 ? `P${pair[0].grid_pos} – P${pair[1].grid_pos}` : `P${pair[0].grid_pos}`;
  return `<div class="walk-title">
    <span class="t1">STARTING GRID</span><span class="t2">${esc(sub)}</span>
    <span class="row">ROW ${row} · ${range}</span>
    <div class="progress"><i id="progress"></i></div>
  </div>`;
}

// Drawing of the whole grid with the current pair lit up, plus the two
// cards sitting in their (staggered) grid boxes.
function gridHtml(g, entries, pair, classes, multiclass) {
  const rows = Math.ceil(entries.length / 2);
  const top = 40;
  const usable = 860 - 8 - top - 50;
  const rowH = Math.min(70, usable / Math.max(rows, 1));
  const slotH = Math.max(14, rowH * 0.78);
  const slots = entries.map((e, i) => {
    const col = i % 2;
    const y = top + Math.floor(i / 2) * rowH + (col ? rowH / 2 : 0);
    const current = i === g.index || i === g.index + 1;
    const cls = classFor(classes, e);
    const style = `left:${col ? 196 : 24}px;top:${y}px;height:${slotH}px;font-size:${Math.min(22, slotH * 0.6)}px;` +
      (current ? `background:${cls.color};color:${inkFor(cls.color)}` : "");
    return `<div class="slot ${current ? "current" : i < g.index ? "done" : ""}" style="${style}"><span>P${e.grid_pos}</span><b>#${esc(e.number)}</b></div>`;
  }).join("");
  const cards = pair.map((e, i) => {
    const box = i === 0 ? "left:40px;top:30px" : "left:700px;top:382px";
    return `<div class="box" style="${box};width:660px;height:440px"><span class="slot-no">${e.grid_pos}</span></div>` +
      card(e, classFor(classes, e), {
        second: i === 1, multiclass, style: i === 0 ? "left:50px;top:40px" : "left:710px;top:392px",
      });
  }).join("");
  return `<div class="walk grid">
    ${titleBar(g, pair)}
    <div class="grid-map"><div class="flagline"></div>${slots}<div class="label">GRID</div></div>
    <div class="tarmac">${cards}</div>
  </div>`;
}

function h2hHtml(g, pair, classes, multiclass) {
  const [a, b] = pair;
  const row = Math.floor(g.index / 2) + 1;
  return `<div class="walk h2h">
    ${titleBar(g, pair)}
    ${card(a, classFor(classes, a), { side: "left", multiclass })}
    ${b ? `<div class="vs"><span>ROW</span><b>${row}</b></div>` : ""}
    ${b ? card(b, classFor(classes, b), { side: "right", second: true, mirror: true, multiclass }) : ""}
  </div>`;
}

// --- style: grid on track --------------------------------------------------
// Two cars standing in painted grid boxes on an angled stretch of road, like
// a TV grid walk. Everything on the road is placed with one affine map from
// road coordinates (u along the road, v across it from the far edge) to the
// 1920x1080 stage, so boxes, numbers and cars share the same plane.

const ROAD = { o: [0, 196], a: [1920, 278], b: [-300, 440] };
const roadPt = (u, v) => [ROAD.o[0] + u * ROAD.a[0] + v * ROAD.b[0], ROAD.o[1] + u * ROAD.a[1] + v * ROAD.b[1]];
const pts = (...uv) => uv.map(([u, v]) => roadPt(u, v).map((n) => n.toFixed(1)).join(",")).join(" ");

// Painted text lies on the road: x follows the road, y leans with it.
function roadTextMatrix(x, y) {
  const al = Math.hypot(...ROAD.a);
  const ax = ROAD.a[0] / al, ay = ROAD.a[1] / al;
  const bl = Math.hypot(...ROAD.b);
  let lx = ROAD.b[0] / bl * 0.45, ly = ROAD.b[1] / bl * 0.45 + 0.55;
  const ll = Math.hypot(lx, ly);
  lx /= ll; ly /= ll;
  return `matrix(${ax.toFixed(4)} ${ay.toFixed(4)} ${lx.toFixed(4)} ${ly.toFixed(4)} ${x.toFixed(1)} ${y.toFixed(1)})`;
}

// Front of each grid box: the car ahead sits higher up the road, nearer the far edge.
const TRACK_SLOTS = [{ u: 0.8, v0: 0.08, v1: 0.42 }, { u: 0.53, v0: 0.52, v1: 0.86 }];
const BOX_LEN = 0.13;

// Pole shows its lap time, everyone else the gap to their class pole.
function fmtQual(e) {
  if (e.qual_gap) return `+${e.qual_gap.toFixed(3)}`;
  if (e.qual_time) return fmtLap(e.qual_time);
  return "";
}

function trackHtml(g, pair, classes, multiclass) {
  const title = (snap.league && snap.league.name) || "Starting grid";
  const row = Math.floor(g.index / 2) + 1;
  const boxes = pair.map((e, i) => {
    const { u, v0, v1 } = TRACK_SLOTS[i];
    const [nx, ny] = roadPt(u + 0.024, (v0 + v1) / 2 + 0.03);
    const qual = fmtQual(e);
    return `<polyline points="${pts([u, v0], [u, v1], [u - BOX_LEN, v1])}" fill="none" stroke="#f4f4f4" stroke-width="11" stroke-linejoin="miter"/>
      <g transform="${roadTextMatrix(nx, ny)}" fill="#f4f4f4" font-weight="900" font-style="italic">
        <text x="0" y="0" font-size="112">${e.grid_pos}</text>
        ${qual ? `<text x="6" y="62" font-size="48" font-weight="700">${esc(qual)}</text>` : ""}
      </g>`;
  }).join("");
  const cars = pair.map((e, i) => {
    const { u, v0, v1 } = TRACK_SLOTS[i];
    // The drawn car's nose is ~215px right of its centre: line it up with the box front.
    const [x, y] = roadPt(u - 0.122, (v0 + v1) / 2);
    const art = e.car_image ? `<img src="${esc(e.car_image)}" alt="">` : car34Svg(e.car_design, e.number);
    return `<div class="track-car ${i ? "second" : ""}" style="left:${(x - 330).toFixed(0)}px;top:${(y - 245).toFixed(0)}px">${art}</div>`;
  }).join("");
  const label = (e, i) => {
    const cls = classFor(classes, e);
    const badge = multiclass || cls.logo ? `<span class="track-class">${classHeaderHtml(cls, "", rerender)}</span>` : "";
    return `<div class="track-label ${i ? "rear" : "front"}">
      <div class="track-name"><span class="track-num" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(e.number)}</span>
        <span>${esc(e.name)}</span>${badge}</div>
      ${e.nickname ? `<div class="track-nick">“${esc(e.nickname)}”</div>` : ""}
      ${e.team ? `<div class="track-team">${esc(e.team)}</div>` : ""}
      ${!e.in_session ? '<div class="track-status">NOT IN SESSION</div>' : !e.in_world ? '<div class="track-status">NOT ON TRACK</div>' : ""}
    </div>
    ${e.team_logo ? `<img class="track-logo ${i ? "rear" : "front"}" src="${esc(e.team_logo)}" alt="">` : ""}`;
  };
  return `<div class="walk track">
    <svg class="track-road" viewBox="0 0 1920 1080" width="1920" height="1080" xmlns="http://www.w3.org/2000/svg">
      <polygon points="${pts([-0.3, 0], [1.3, 0], [1.3, 1], [-0.3, 1])}" fill="#3f4247"/>
      <polyline points="${pts([-0.3, 0.025], [1.3, 0.025])}" stroke="#f4f4f4" stroke-width="13" fill="none"/>
      <polyline points="${pts([-0.3, 0.975], [1.3, 0.975])}" stroke="#f4f4f4" stroke-width="13" fill="none"/>
      ${boxes}
    </svg>
    ${cars}
    ${pair.map(label).join("")}
    <div class="track-title"><span>${esc(title)}</span><b>ROW ${row}</b><div class="progress"><i id="progress"></i></div></div>
  </div>`;
}

function rerender() {
  shownKey = "";
  render();
}

function render() {
  const g = snap && snap.gridwalk;
  if (!g) return;
  const entries = g.entries || [];
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const pair = entries.slice(g.index, g.index + 2);
  progress = { elapsed: g.elapsed, interval: g.interval, running: g.running && g.visible, at: performance.now() };
  const show = g.visible && pair.length > 0;
  // Only rebuild when what is on screen changes, so animations play once.
  const key = JSON.stringify([show, g.style, g.index, pair, pair.map((e) => classes.get(e.class_key) || null),
    entries.length, snap.league, snap.session && snap.session.track]);
  if (key === shownKey) return;
  shownKey = key;
  stage.classList.toggle("hidden", !show);
  if (!show) return;  // keep the last pair in place while it fades out
  const multiclass = new Set(entries.map((e) => e.class_key)).size > 1;
  stage.innerHTML = g.style === "h2h" ? h2hHtml(g, pair, classes, multiclass)
    : g.style === "grid" ? gridHtml(g, entries, pair, classes, multiclass)
      : trackHtml(g, pair, classes, multiclass);
}

function tickProgress() {
  const bar = document.getElementById("progress");
  if (bar && progress) {
    const extra = progress.running ? (performance.now() - progress.at) / 1000 : 0;
    bar.style.width = `${Math.min(100, ((progress.elapsed + extra) / progress.interval) * 100)}%`;
  }
  requestAnimationFrame(tickProgress);
}
requestAnimationFrame(tickProgress);

stage.classList.add("hidden");
const stream = new EventSource("/api/stream");
let version = null;
stream.onmessage = (msg) => {
  snap = JSON.parse(msg.data);
  // After an app update, reload so OBS picks up the new graphics.
  if (version && snap.version && snap.version !== version) return location.reload();
  version = version || snap.version;
  render();
};
