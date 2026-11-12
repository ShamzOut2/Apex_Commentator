"use strict";

// Live timing for spectators (see index.html and apex/spectate.py). Everything
// comes from this site's own /feed and /map.json: nothing else is loaded.

const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let data = null;            // the live timing now
let mapPoints = null;       // the track outline (lap fraction i / n -> [x, y], 0..1), or null: the round map
let mapId;                  // which outline that is
let mapVer = 0;             // bumped each time the outline changes (the track is drawn again)
const picks = [];           // the two drivers compared (car ids)
let classFilter = "all";
const motion = new Map();   // car id -> how it moves on the map (see noteMotion)

// Only the rows that changed are rebuilt, and moved where they now are:
// the rest of the list (logos and all) stays as it is.
function patch(parent, items) {
  const old = new Map(Array.from(parent.children, (el) => [el.dataset.key, el]));
  let prev = null;
  for (const [key, html] of items) {
    let el = old.get(key);
    if (!el || el._html !== html) {
      const t = document.createElement("template");
      t.innerHTML = html.trim();
      const fresh = t.content.firstElementChild;
      fresh.dataset.key = key;
      fresh._html = html;
      if (el) el.replaceWith(fresh);
      el = fresh;
    }
    old.delete(key);
    const at = prev ? prev.nextElementSibling : parent.firstElementChild;
    if (at !== el) parent.insertBefore(el, at);
    prev = el;
  }
  old.forEach((el) => el.remove());
}
const activeTab = () => document.querySelector(".panel.active")?.id;

// -- formatting --------------------------------------------------------------------

function fmtLap(t) {
  if (!t || t <= 0) return "";
  const m = Math.floor(t / 60);
  const s = (t - m * 60).toFixed(3);
  return m ? `${m}:${s.padStart(6, "0")}` : s;
}
const dec = () => (data && data.dec) || [1, 3];
const race = () => data && data.kind === "race";
const secs = (v) => Number(v).toFixed(race() ? dec()[0] : dec()[1]);
const signed = (d, places = 3) => `${d > 0 ? "+" : d < 0 ? "−" : "±"}${Math.abs(d).toFixed(places)}`;
function clock(t) {
  if (t == null) return "";
  t = Math.max(0, Math.round(t));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}
const classOf = (car) => (data.classes || []).find((c) => c.key === car.cls) || { color: "#8b93a3", name: "" };
const img = (token) => (token ? `img/${encodeURIComponent(token)}` : "");
function ink(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return "#111";
  const n = parseInt(m[1], 16);
  return ((n >> 16) * 299 + ((n >> 8) & 255) * 587 + (n & 255) * 114) / 1000 > 150 ? "#111" : "#fff";
}
// How the page looks and what it shows (the app's Live timing tab).
const look = () => (data && data.look) || {};
const shows = (k) => look()[k] !== false;
let accent = "#e10600";
function applyLook() {
  const want = /^#[0-9a-f]{6}$/i.test(look().accent || "") ? look().accent : "#e10600";
  if (want !== accent || !document.documentElement.style.getPropertyValue("--red")) {
    accent = want;
    document.documentElement.style.setProperty("--red", accent);
    document.documentElement.style.setProperty("--on-red", ink(accent));
  }
  const tracker = look().tracker !== false;
  const tab = document.querySelector('.tab[data-tab="tracker"]');
  if (tab.hidden === tracker) {
    tab.hidden = !tracker;
    if (!tracker && activeTab() === "tab-tracker") document.querySelector('.tab[data-tab="board"]').click();
  }
}
const tyre = (t) => (t === "wet" ? '<span class="tyre wet" title="Wet tyres">W</span>' : t === "dry" ? '<span class="tyre dry" title="Dry tyres">D</span>' : "");

// -- the header ------------------------------------------------------------------------

function renderHeader() {
  applyLook();
  $("#series").textContent = data.series || "Live timing";
  $("#session").textContent = [data.title, data.kind === "race" ? "" : ""].filter(Boolean).join(" · ") || "";
  const logo = $("#series-logo");
  if (data.logo) {
    logo.src = img(data.logo);
    logo.hidden = false;
  } else logo.hidden = true;
  $("#track").textContent = [data.track, data.config].filter(Boolean).join(" – ");
  const p = data.progress || {};
  let text = "";
  if (p.finished) text = "FINISHED";
  else if (p.mode === "laps" && p.laps_total) text = `LAP ${Math.max(p.lap || 0, 0)} / ${p.laps_total}`;
  else if (p.time_up) text = "LAST LAP";
  else if (p.time_remain != null) text = `${clock(p.time_remain)} LEFT`;
  else if (p.lap) text = `LAP ${p.lap}`;
  $("#progress").textContent = text;
  $("#flag").className = `flag ${data.flag || ""}`;
  document.title = `${data.series ? `${data.series} · ` : ""}${data.title || "Live timing"}`;
  // Classes: only with more than one.
  const classes = data.classes || [];
  const key = JSON.stringify([classes, classFilter]);
  if ($("#class-chips").dataset.key !== key) {
    $("#class-chips").dataset.key = key;
    $("#class-chips").innerHTML = classes.length < 2 ? "" : [`<button class="chip ${classFilter === "all" ? "on" : ""}" data-cls="all">All</button>`,
      ...classes.map((c) => `<button class="chip ${classFilter === c.key ? "on" : ""}" data-cls="${esc(c.key)}"><i style="background:${esc(c.color)}"></i>${esc(c.name)}</button>`)].join("");
  }
}

$("#class-chips").addEventListener("click", (e) => {
  const b = e.target.closest("[data-cls]");
  if (!b) return;
  classFilter = b.dataset.cls;
  render();
});

// -- the leaderboard ---------------------------------------------------------------------

const visible = () => (data.cars || []).filter((c) => classFilter === "all" || c.cls === classFilter);

function gapCell(car, first) {
  if (car.out && !car.fin) return '<span class="tag out">OUT</span>';
  if (!race()) {
    if (!car.best) return "";
    if (first) return `<span class="lead">${fmtLap(car.best)}</span>`;
    return `+${secs(car.best - first.best)}`;
  }
  if (first === car || car.pos === 1) return '<span class="lead">Leader</span>';
  if (car.down) return `+${car.down} L`;
  return car.gap != null ? `+${secs(car.gap)}` : "";
}

function sectorsHtml(car, n) {
  // The lap on now: sectors done (coloured), the rest still to come; just
  // after the line, the lap just done.
  const now = car.now && car.now.sectors.length ? car.now : null;
  const lap = now || car.sec;
  return Array.from({ length: n }, (_, i) => {
    const t = lap && lap.sectors[i];
    const col = lap && lap.colours && lap.colours[i];
    return `<td class="c wide"><span class="sec ${t ? col || "" : "run"}">${t ? t.toFixed(3) : "–"}</span></td>`;
  }).join("");
}

function renderBoard() {
  const cars = visible();
  const n = Math.max(1, (data.sectors || []).length);
  const first = race() ? cars[0] : cars.find((c) => c.best);
  // The columns switched on: [heading, the cell for a car].
  const cols = [
    ['<th class="r">Pos</th>', (c) => `<td class="pos">${(classFilter === "all" ? c.pos : c.cpos) ?? ""}</td>`],
    race() && shows("pos_change") && ["<th></th>", (c) => `<td class="chg-cell">${c.pc ? `<span class="chg ${c.pc > 0 ? "up" : "down"}">${c.pc > 0 ? "▲" : "▼"}${Math.abs(c.pc)}</span>` : ""}</td>`],
    shows("number") && ["<th>#</th>", (c) => {
      const color = classOf(c).color;
      return `<td><span class="num" style="background:${esc(color)};color:${ink(color)}">${esc(c.num)}</span></td>`;
    }],
    ["<th>Driver</th>", (c) => `<td><div class="driver ${shows("number") ? "" : "bar"}" style="--cls:${esc(classOf(c).color)}">${c.logo ? `<img src="${img(c.logo)}" alt="">` : ""}<div class="who"><span class="n">${esc(c.name)}</span>${c.team ? `<span class="t">${esc(c.team)}</span>` : ""}</div></div></td>`],
    ['<th class="r">Gap</th>', (c) => `<td class="r time">${gapCell(c, first)}</td>`],
    race() && shows("interval") && ['<th class="r wide">Int</th>', (c) => `<td class="r time muted wide">${c.out && !c.fin ? "" : c.int != null && c !== first ? `+${secs(c.int)}` : ""}</td>`],
    shows("last") && ['<th class="r wide">Last</th>', (c) => `<td class="r time muted wide">${fmtLap(c.last)}</td>`],
    shows("best") && ['<th class="r">Best</th>', (c) => `<td class="r time ${c.fl ? "fl" : ""}">${fmtLap(c.best)}</td>`],
    shows("sectors") && [Array.from({ length: n }, (_, i) => `<th class="c wide">S${i + 1}</th>`).join(""), (c) => sectorsHtml(c, n)],
    shows("tyre") && ['<th class="c">Tyre</th>', (c) => `<td class="c">${tyre(c.tyre)}</td>`],
    shows("laps") && ['<th class="r wide">Laps</th>', (c) => `<td class="r muted wide">${c.laps ?? ""}</td>`],
    shows("status") && ['<th class="c"></th>', (c) => `<td class="c">${c.fin ? '<span class="tag fin" title="Finished">F</span>' : c.pit ? '<span class="tag">PIT</span>' : ""}</td>`],
  ].filter(Boolean);
  const head = cols.map(([h]) => h).join("");
  if ($("#board-head").innerHTML !== head) $("#board-head").innerHTML = head;
  patch($("#board-rows"), cars.map((c) => [String(c.id),
    `<tr class="${picks.includes(c.id) ? "pick" : ""} ${c.out && !c.fin ? "out" : ""}" data-car="${c.id}">${cols.map(([, cell]) => cell(c)).join("")}</tr>`]));
  if ($("#board-empty").hidden !== cars.length > 0) $("#board-empty").hidden = cars.length > 0;
}

$("#board-rows").addEventListener("click", (e) => {
  const tr = e.target.closest("[data-car]");
  if (tr) pick(+tr.dataset.car);
});

// -- the driver tracker -------------------------------------------------------------------

function pick(id) {
  const i = picks.indexOf(id);
  if (i >= 0) picks.splice(i, 1);
  else {
    if (picks.length >= 2) picks.shift();
    picks.push(id);
  }
  try {
    localStorage.setItem("apex.live.picks", JSON.stringify(picks));
  } catch (e) { /* not kept */ }
  render();
}
try {
  const kept = JSON.parse(localStorage.getItem("apex.live.picks") || "[]");
  if (Array.isArray(kept)) picks.push(...kept.filter((x) => Number.isInteger(x)).slice(0, 2));
} catch (e) { /* none */ }

$("#pos-list").addEventListener("click", (e) => {
  const li = e.target.closest("[data-car]");
  if (li) pick(+li.dataset.car);
});
document.querySelector(".h2h-head").addEventListener("click", (e) => {
  const x = e.target.closest("[data-unpick]");
  if (x) pick(+x.dataset.unpick);
});

function renderPositions() {
  const cars = visible();
  const html = cars.map((c) => {
    const pos = classFilter === "all" ? c.pos : c.cpos;
    const mark = race() && c.pc ? `<span class="pn ${c.pc > 0 ? "up" : "down"}">${c.pc > 0 ? "↑" : "↓"}</span>` : `<span class="pn">${pos ?? ""}</span>`;
    return `<li class="${picks.includes(c.id) ? "pick" : ""} ${c.out && !c.fin ? "out" : ""}" data-car="${c.id}" title="${esc(c.name)}">${mark}<span class="bar" style="background:${esc(classOf(c).color)}"></span><span class="ab">${esc(c.abbr)}</span></li>`;
  });
  patch($("#pos-list"), cars.map((c, i) => [String(c.id), html[i]]));
}

function renderH2H() {
  const cars = new Map((data.cars || []).map((c) => [c.id, c]));
  const [a, b] = picks.map((id) => cars.get(id));
  document.querySelectorAll(".pick[data-slot]").forEach((el, i) => {
    const c = [a, b][i];
    el.classList.toggle("empty", !c);
    el.innerHTML = c ? `<span class="disc" style="border-color:${esc(classOf(c).color)}">${c.logo ? `<img src="${img(c.logo)}" alt="">` : esc(c.num)}</span>
      <span class="lbl"><b>${esc(c.abbr)}</b><span>P${c.pos ?? "–"} · #${esc(c.num)}</span></span><button class="x" data-unpick="${c.id}" title="Remove">×</button>`
      : `Driver ${i + 1}: pick one from the list`;
  });
  $("#h2h-hint").hidden = !!(a && b);
  if (!(a && b)) {
    $("#h2h-body").innerHTML = "";
    return;
  }
  // Each row: driver 1's figure, what it is, driver 2's (green: quicker than driver 1).
  const row = (label, x, y, fmt = fmtLap, big = false) => {
    const d = x && y ? y - x : null;
    const cls = d == null ? "" : d < 0 ? "faster" : d > 0 ? "slower" : "";
    return `<div class="h2h-row ${big ? "big" : ""}"><span class="a">${x ? fmt(x) : "–"}</span><span class="lab">${label}</span>
      <span class="b ${cls}">${y ? fmt(y) : "–"}${d != null ? `<small>${signed(d)}</small>` : ""}</span></div>`;
  };
  const rows = [];
  if (race()) {
    const gap = a.gap != null && b.gap != null && !a.down && !b.down ? Math.abs(b.gap - a.gap) : null;
    rows.push(`<div class="h2h-row big"><span class="a">P${a.pos ?? "–"}</span><span class="lab">Gap</span><span class="b">${gap != null ? secs(gap) : a.down !== b.down ? `${Math.abs((a.down || 0) - (b.down || 0))} L` : "–"}</span></div>`);
  }
  rows.push(row(race() ? "Last lap" : "Lap", a.last || a.best, b.last || b.best, fmtLap, true));
  const n = (data.sectors || []).length;
  for (let i = 0; i < n; i++) {
    const sa = a.sec && a.sec.sectors[i], sb = b.sec && b.sec.sectors[i];
    rows.push(row(`S${i + 1}`, sa, sb, (t) => t.toFixed(3)));
  }
  rows.push(row("Best", a.best, b.best));
  rows.push(`<div class="h2h-row"><span class="a">${tyre(a.tyre) || "–"}</span><span class="lab">Tyre</span><span class="b">${tyre(b.tyre) || "–"}</span></div>`);
  const html = rows.join("");
  if ($("#h2h-body").dataset.html !== html) {
    $("#h2h-body").dataset.html = html;
    $("#h2h-body").innerHTML = html;
  }
}

// -- the track map -----------------------------------------------------------------------

const canvas = $("#map");
const screen = canvas.getContext("2d");
let g = screen;

// The canvas size: kept up to date as it changes (not measured every frame,
// which made the browser lay the page out again each time).
let box = { w: 0, h: 0 };
new ResizeObserver(([e]) => {
  box = { w: e.contentRect.width, h: e.contentRect.height };
}).observe(canvas);
function fit() {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(box.w * dpr)), h = Math.max(1, Math.round(box.h * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  return dpr;
}

// The track (outline, sectors, the line) drawn once into a picture of its
// own, and again only when the size, the outline or the sectors change.
const trackPic = document.createElement("canvas");
let trackKey = "";
function track(w, h, pad, dpr) {
  const key = [w, h, dpr, mapId, mapVer, accent, (data.sectors || []).join()].join("|");
  if (key !== trackKey) {
    trackKey = key;
    trackPic.width = w;
    trackPic.height = h;
    const main = g;
    g = trackPic.getContext("2d");
    drawTrack(w, h, pad, dpr);
    g = main;
  }
  return trackPic;
}

// Where a lap fraction is on screen: on the outline (point i at i / n), else on a circle.
function locate(pct, w, h, pad) {
  if (mapPoints) {
    const size = Math.min(w, h) - pad * 2;
    const ox = (w - size) / 2, oy = (h - size) / 2;
    const n = mapPoints.length;
    const f = (((pct % 1) + 1) % 1) * n;
    const i = Math.floor(f) % n, j = (i + 1) % n, k = f - Math.floor(f);
    const p = mapPoints[i], q = mapPoints[j];
    return [ox + (p[0] + (q[0] - p[0]) * k) * size, oy + (p[1] + (q[1] - p[1]) * k) * size];
  }
  const r = Math.min(w, h) / 2 - pad;
  const a = -Math.PI / 2 + pct * Math.PI * 2;
  return [w / 2 + Math.cos(a) * r, h / 2 + Math.sin(a) * r];
}

function drawTrack(w, h, pad, dpr) {
  const steps = mapPoints ? mapPoints.length : 240;
  g.lineJoin = g.lineCap = "round";
  const path = () => {
    g.beginPath();
    for (let i = 0; i <= steps; i++) {
      const [x, y] = locate(i / steps, w, h, pad);
      if (i) g.lineTo(x, y);
      else g.moveTo(x, y);
    }
    g.closePath();
  };
  path();
  g.strokeStyle = "#0b0b10";
  g.lineWidth = 16 * dpr;
  g.stroke();
  path();
  g.strokeStyle = "#4a4c5e";
  g.lineWidth = 10 * dpr;
  g.stroke();
  path();
  g.strokeStyle = accent;
  g.globalAlpha = 0.85;
  g.lineWidth = 3 * dpr;
  g.setLineDash([14 * dpr, 6 * dpr]);
  g.stroke();
  g.setLineDash([]);
  g.globalAlpha = 1;
  // Sector ends: short lines across the track, labelled; the start / finish line chequered.
  const across = (pct, len) => {
    const [x1, y1] = locate(pct - 0.002, w, h, pad), [x2, y2] = locate(pct + 0.002, w, h, pad);
    const [x, y] = locate(pct, w, h, pad);
    const a = Math.atan2(y2 - y1, x2 - x1) + Math.PI / 2;
    return [x - Math.cos(a) * len, y - Math.sin(a) * len, x + Math.cos(a) * len, y + Math.sin(a) * len, x, y, a];
  };
  const starts = data.sectors || [];
  starts.slice(1).forEach((s, i) => {
    const [ax, ay, bx, by, x, y, a] = across(s, 12 * dpr);
    g.strokeStyle = "#ffb020";
    g.lineWidth = 3 * dpr;
    g.beginPath();
    g.moveTo(ax, ay);
    g.lineTo(bx, by);
    g.stroke();
    g.fillStyle = "rgba(255,255,255,.75)";
    g.font = `700 ${11 * dpr}px system-ui, sans-serif`;
    g.textAlign = "center";
    g.fillText(`SECTOR ${i + 2}`, x + Math.cos(a) * 28 * dpr, y + Math.sin(a) * 28 * dpr);
  });
  const [ax, ay, bx, by] = across(0, 12 * dpr);
  for (let k = 0; k < 6; k++) {
    g.strokeStyle = k % 2 ? "#111" : "#fff";
    g.lineWidth = 4 * dpr;
    g.beginPath();
    g.moveTo(ax + ((bx - ax) * k) / 6, ay + ((by - ay) * k) / 6);
    g.lineTo(ax + ((bx - ax) * (k + 1)) / 6, ay + ((by - ay) * (k + 1)) / 6);
    g.stroke();
  }
}

function pill(text, x, y, dpr, strong) {
  g.font = `${strong ? 900 : 700} ${(strong ? 17 : 13) * dpr}px system-ui, sans-serif`;
  const w = g.measureText(text).width + (strong ? 26 : 12) * dpr;
  const h = (strong ? 30 : 20) * dpr;
  const left = x + 10 * dpr, top = y - h - 8 * dpr;
  g.fillStyle = strong ? "#fff" : "rgba(21, 21, 30, .8)";
  g.beginPath();
  g.roundRect(left, top, w, h, h / 2);
  g.fill();
  if (strong) {
    g.fillStyle = accent;
    g.fillRect(left + 9 * dpr, top + 7 * dpr, 4 * dpr, h - 14 * dpr);
  }
  g.fillStyle = strong ? "#111" : "#fff";
  g.textAlign = "left";
  g.textBaseline = "middle";
  g.fillText(text, left + (strong ? 17 : 6) * dpr, top + h / 2 + dpr);
  g.textBaseline = "alphabetic";
}

// Smooth movement: the feed says where each car was a few times a second
// (and over the internet those updates arrive unevenly). Between them each
// car carries on at the speed it's been going, timed by the session clock
// the figures were taken at rather than when they got here, and the small
// misses are eased out rather than jumped.
const wrap = (d) => d - Math.round(d);
function noteMotion() {
  const clock = data.clock, now = performance.now();
  const seen = new Set();
  for (const c of data.cars || []) {
    if (c.pct == null || (c.out && !c.fin)) continue;
    seen.add(c.id);
    const m = motion.get(c.id);
    if (!m || clock == null || m.clock == null || clock < m.clock || clock - m.clock > 5) {
      motion.set(c.id, { pct: c.pct, clock, at: now, speed: 0, shown: m ? m.shown : c.pct });
      continue;
    }
    const dt = clock - m.clock;
    if (dt <= 0) continue;
    const d = wrap(c.pct - m.pct);
    // A big jump (to the pits, towed, a replay): no speed from it.
    const speed = d < -0.002 || d / dt > 0.15 ? 0 : Math.max(0, d / dt);
    m.speed = m.speed ? m.speed * 0.4 + speed * 0.6 : speed;
    if (Math.abs(wrap(c.pct - m.shown)) > 0.1) m.shown = c.pct;  // far off (to the pits, a replay): straight there
    Object.assign(m, { pct: c.pct, clock, at: now });
  }
  for (const id of motion.keys()) if (!seen.has(id)) motion.delete(id);
}

let lastFrame = performance.now();
function drawMap() {
  requestAnimationFrame(drawMap);
  const now = performance.now();
  const step = Math.min(100, now - lastFrame);
  lastFrame = now;
  if (!data || activeTab() !== "tab-tracker") return;
  const dpr = fit();
  const w = canvas.width, h = canvas.height;
  const pad = 60 * dpr;
  g.clearRect(0, 0, w, h);
  g.drawImage(track(w, h, pad, dpr), 0, 0);
  const cars = visible().filter((c) => motion.has(c.id));
  const order = cars.filter((c) => !picks.includes(c.id)).concat(cars.filter((c) => picks.includes(c.id)));
  const ease = 1 - Math.exp(-step / 120);
  for (const c of order) {
    const m = motion.get(c.id);
    // Where it should be now: on from the last figure, at most a second on.
    const ahead = m.pct + m.speed * Math.min(1, (now - m.at) / 1000);
    m.shown = (((m.shown + wrap(ahead - m.shown) * ease) % 1) + 1) % 1;
    const [x, y] = locate(m.shown, w, h, pad);
    const picked = picks.includes(c.id);
    const col = picked ? accent : classOf(c).color || "#fff";
    if (picked) {
      g.fillStyle = accent;
      g.globalAlpha = 0.35;
      g.beginPath();
      g.arc(x, y, 24 * dpr, 0, Math.PI * 2);
      g.fill();
      g.globalAlpha = 1;
    }
    g.fillStyle = col;
    g.strokeStyle = "#0b0b10";
    g.lineWidth = 2 * dpr;
    g.beginPath();
    g.arc(x, y, (picked ? 14 : 8) * dpr, 0, Math.PI * 2);
    g.fill();
    g.stroke();
    if (c.pit) {
      g.globalAlpha = 0.5;
    }
    // Its label: as picked in the app (the drivers picked here always have theirs).
    const label = picked ? c.abbr : { number: `#${c.num}`, name: c.name, none: "" }[look().label] ?? c.abbr;
    if (label) pill(label, x, y, dpr, picked);
    g.globalAlpha = 1;
  }
}
requestAnimationFrame(drawMap);

async function loadMap() {
  if (!data || data.map === mapId) return;
  mapId = data.map;
  if (!mapId) {
    mapPoints = null;
    mapVer++;
    return;
  }
  try {
    const m = await (await fetch("map.json", { cache: "no-store" })).json();
    mapPoints = m && Array.isArray(m.points) && m.points.length > 50 ? m.points : null;
    mapVer++;
  } catch (e) {
    mapPoints = null;
    mapVer++;
    mapId = undefined; // try again on the next update
  }
}

// -- tabs, the feed ---------------------------------------------------------------------

document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${t.dataset.tab}`));
  render();
  try {
    localStorage.setItem("apex.live.tab", t.dataset.tab);
  } catch (e) { /* not kept */ }
}));
try {
  const tab = localStorage.getItem("apex.live.tab");
  if (tab) document.querySelector(`.tab[data-tab="${tab}"]`)?.click();
} catch (e) { /* first tab */ }

// Only the tab on screen is brought up to date (the other when it's opened).
function render() {
  if (!data) return;
  renderHeader();
  if (activeTab() === "tab-board") renderBoard();
  else {
    renderPositions();
    renderH2H();
  }
  const note = mapPoints ? "" : "Track outline not available: cars shown round the lap";
  if ($("#map-note").textContent !== note) $("#map-note").textContent = note;
}

let heard = 0;
function connect() {
  const feed = new EventSource(/[?&]preview=1/.test(location.search) ? "feed?preview=1" : "feed");
  feed.onmessage = (m) => {
    heard = Date.now();
    data = JSON.parse(m.data);
    noteMotion();
    $("#offline").hidden = true;
    $(".live").classList.toggle("off", !data || !data.cars);
    loadMap();
    render();
  };
  feed.onerror = () => {
    $("#offline").hidden = false;
    $(".live").classList.add("off");
  };
}
connect();
