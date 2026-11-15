"use strict";

// Flags: nothing on screen until a sector goes yellow (the hotkeys, or by
// itself with Auto). Then a waving yellow flag: "Sector 1", "Sectors 1 & 2"
// or "All Sectors", a strip of the sectors with the yellow ones lit, and the
// track's outline with them marked. A green "Track Clear" as the last clears.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
let box = null;
let shownKey = "";
let points = null;   // the track outline: lap fraction i / n -> [x, y] (0..1)
let mapId;

async function loadMap(id) {
  mapId = id;
  points = null;
  if (!id) return;
  try {
    const m = await (await fetch("/api/trackmap", { cache: "no-store" })).json();
    points = m && m.id === id && Array.isArray(m.points) && m.points.length > 50 ? m.points : null;
    if (!points) mapId = undefined;
  } catch (e) {
    mapId = undefined;
  }
  shownKey = "";
}

const CLOTH = (wave) => `M14 10 C 40 ${wave ? 2 : 16}, 62 ${wave ? 18 : 4}, 92 10 L 92 58 C 62 ${wave ? 66 : 52}, 40 ${wave ? 50 : 64}, 14 58 Z`;
const FLAG_SVG = `<svg class="fl-cloth" viewBox="0 0 96 92" aria-hidden="true">
  <rect x="8" y="6" width="6" height="84" rx="3" fill="#c9ced8"/>
  <path class="cloth" d="${CLOTH(false)}"><animate attributeName="d" dur="1.1s" repeatCount="indefinite"
    values="${CLOTH(false)};${CLOTH(true)};${CLOTH(false)}"/></path>
  <path d="${CLOTH(false)}" fill="url(#fl-shade)"><animate attributeName="d" dur="1.1s" repeatCount="indefinite"
    values="${CLOTH(false)};${CLOTH(true)};${CLOTH(false)}"/></path>
  <defs><linearGradient id="fl-shade" x1="0" x2="1"><stop offset="0" stop-color="#000" stop-opacity=".18"/>
    <stop offset=".35" stop-color="#fff" stop-opacity=".18"/><stop offset=".7" stop-color="#000" stop-opacity=".2"/>
    <stop offset="1" stop-color="#fff" stop-opacity=".12"/></linearGradient></defs></svg>`;

// The outline from one lap fraction to another, as SVG points (150 px box).
function line(from, to) {
  const n = points.length, out = [];
  const a = Math.floor(from * n), b = Math.ceil(to * n);
  for (let i = a; i <= b; i++) {
    const p = points[((i % n) + n) % n];
    out.push(`${(12 + p[0] * 126).toFixed(1)},${(12 + p[1] * 126).toFixed(1)}`);
  }
  return out.join(" ");
}

function mapSvg(f) {
  if (!points) return "";
  const starts = f.starts || [];
  const hot = f.sectors.map((s) => {
    const from = starts[s - 1] ?? 0, to = starts[s] ?? 1;
    const mid = points[Math.floor(((from + to) / 2) * points.length) % points.length];
    return `<polyline class="hot" points="${line(from, to)}"/>
      <text class="num" x="${(12 + mid[0] * 126).toFixed(1)}" y="${(12 + mid[1] * 126).toFixed(1)}" text-anchor="middle" dominant-baseline="central">${s}</text>`;
  }).join("");
  return `<svg class="fl-map" viewBox="0 0 150 150" aria-hidden="true"><polyline class="base" points="${line(0, 1)}"/>${hot}</svg>`;
}

function draw(f, cfg) {
  setPanels(cfg);
  setSize(cfg);
  if (f.map !== mapId && cfg.show_map) loadMap(f.map);
  const strip = Array.from({ length: f.count }, (_, i) => `<span class="${f.sectors.includes(i + 1) ? "on" : ""}">S${i + 1}</span>`).join("");
  const inner = `${FLAG_SVG}<div class="fl-main"><div class="fl-kind">${f.clear ? "Green flag" : "Yellow flag"}</div>
    <div class="fl-text">${esc(f.text)}</div><div class="fl-strip">${strip}</div></div>${cfg.show_map ? mapSvg(f) : ""}`;
  const key = [cfg.place, cfg.visible, f.clear, f.text, f.count, cfg.show_map, !!points].join("|");
  if (box && key === shownKey) return;
  const fresh = !box || box.classList.contains("clear") !== !!f.clear;
  shownKey = key;
  if (!fresh) {
    box.className = `flag ${esc(cfg.place)} ${f.clear ? "clear" : ""} ${cfg.visible ? "" : "hidden-preview"}`;
    box.innerHTML = inner;
    return;
  }
  leave(true);
  stage.insertAdjacentHTML("beforeend", `<div class="flag panel-in ${esc(cfg.place)} ${f.clear ? "clear" : ""} ${cfg.visible ? "" : "hidden-preview"}">${inner}</div>`);
  box = stage.lastElementChild;
  const el = box;
  setTimeout(() => el.classList.remove("panel-in"), 550);
}

function leave(keepKey) {
  if (!box) return;
  const old = box;
  box = null;
  if (!keepKey) shownKey = "";
  old.classList.remove("panel-in");
  old.classList.add("panel-out");
  setTimeout(() => old.remove(), 480);
}

function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.flags;
  if (!cfg) return;
  const f = ov.flags;
  if (f && (cfg.visible || PREVIEW)) {
    stage.querySelectorAll(".fl-hint").forEach((el) => el.remove());
    return draw(f, cfg);
  }
  leave();
  if (PREVIEW && !stage.querySelector(".fl-hint")) {
    stage.insertAdjacentHTML("beforeend", '<div class="fl-hint">No yellow flags right now (press a sector\'s hotkey, or turn Auto on)</div>');
  }
}

followSnapshots(render);
