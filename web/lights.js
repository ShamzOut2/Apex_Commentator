"use strict";

// Starting lights: up only as a race is about to start. The red lights come
// on one by one (iRacing's start lights, the leader's run to the line on the
// lap to the green, or the Count down hotkey), stay lit, and go out at the
// green: "LIGHTS OUT", then it goes.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
let box = null;
let shownKey = "";

// The gantry the lights hang from: a lattice truss of steel tubes, ``w`` px wide.
function trussSvg(w) {
  const h = 70, bays = Math.max(4, Math.round(w / 64)), bay = w / bays;
  const lattice = [];
  for (let i = 0; i < bays; i++) {
    const x = i * bay;
    lattice.push(`<line x1="${x.toFixed(1)}" y1="14" x2="${(x + bay).toFixed(1)}" y2="56"/><line x1="${(x + bay).toFixed(1)}" y1="14" x2="${x.toFixed(1)}" y2="56"/>`);
    if (i) lattice.push(`<line x1="${x.toFixed(1)}" y1="14" x2="${x.toFixed(1)}" y2="56"/>`);
  }
  return `<svg class="lt-truss" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
    <defs><linearGradient id="lt-tube" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8d939c"/>
      <stop offset=".35" stop-color="#4a4e55"/><stop offset=".7" stop-color="#202226"/><stop offset="1" stop-color="#0d0e10"/></linearGradient></defs>
    <g class="back"><rect x="10" y="3" width="${w - 10}" height="8" rx="4" fill="url(#lt-tube)"/>
      <rect x="10" y="44" width="${w - 10}" height="8" rx="4" fill="url(#lt-tube)"/></g>
    <g class="lattice">${lattice.join("")}</g>
    <rect x="0" y="8" width="${w}" height="11" rx="5.5" fill="url(#lt-tube)"/>
    <rect x="0" y="51" width="${w}" height="11" rx="5.5" fill="url(#lt-tube)"/></svg>`;
}

// The LEDs of a lamp's face, in rings round its middle as on a real one
// (drawn once, used by every lamp).
function ledSymbol() {
  const dots = ['<circle cx="0" cy="0" r="1.9"/>'];
  for (let r = 6.2; r <= 41; r += 5.8) {
    const n = Math.floor((2 * Math.PI * r) / 6.1);
    for (let i = 0; i < n; i++) {
      const a = (i / n) * 2 * Math.PI + r;  // each ring turned a little, as they're set
      dots.push(`<circle cx="${(r * Math.cos(a)).toFixed(2)}" cy="${(r * Math.sin(a)).toFixed(2)}" r="1.9"/>`);
    }
  }
  return `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
    <symbol id="lt-leds" viewBox="-44 -44 88 88">${dots.join("")}</symbol></defs></svg>`;
}
stage.insertAdjacentHTML("beforeend", ledSymbol());

// One lamp: a bezel, the hood over its top, and a glass face of LEDs.
const LAMP = '<span class="lt-lamp"><span class="lt-face"><svg class="lt-dots" viewBox="0 0 88 88"><use href="#lt-leds" width="88" height="88"/></svg></span></span>';

function draw(l, cfg) {
  setPanels(cfg);
  setSize(cfg);
  const key = [cfg.place, l.lights, cfg.visible, cfg.show_text].join("|");
  if (!box || key !== shownKey) {
    leave();
    shownKey = key;
    // The housing: a column of two lamps for each light, 128 px apart, 30 px in from its edges.
    const boxW = l.lights * 128 - 18 + 60;
    const pods = Array.from({ length: l.lights }, () => `<div class="lt-pod">${LAMP}${LAMP}</div>`).join("");
    stage.insertAdjacentHTML("beforeend", `<div class="lights panel-in ${esc(cfg.place)} ${cfg.visible ? "" : "hidden-preview"}">
      <div class="lt-frame"><div class="lt-rig">
        ${trussSvg(boxW + 120)}
        <div class="lt-mounts" style="width:${boxW}px"><span></span><span></span></div>
        <div class="lt-box" style="width:${boxW}px"><div class="lt-row">${pods}</div>
          <i class="bolt tl"></i><i class="bolt tr"></i><i class="bolt bl"></i><i class="bolt br"></i></div>
        </div>${cfg.show_text ? '<div class="lt-text"></div>' : ""}
      </div></div>`);
    box = stage.lastElementChild;
    const el = box;
    setTimeout(() => el.classList.remove("panel-in"), 500);
  }
  box.querySelectorAll(".lt-pod").forEach((pod, i) => pod.classList.toggle("on", !l.out && i < l.lit));
  box.classList.toggle("out", !!l.out);
  const text = box.querySelector(".lt-text");
  if (text) text.textContent = l.out ? "Lights out" : l.lit >= l.lights ? "" : "Get ready";
}

function leave() {
  if (!box) return;
  const old = box;
  box = null;
  shownKey = "";
  old.classList.remove("panel-in");
  old.classList.add("panel-out");
  setTimeout(() => old.remove(), 520);
}

// The preview, with no start on: a count over and over (a light a second, held, then out).
function demo(cfg) {
  const n = cfg.lights || 5;
  const t = (Date.now() / 1000) % (n + 6);
  return t < n + 2 ? { lit: Math.min(n, Math.floor(t)), lights: n, out: false } : { lit: 0, lights: n, out: true };
}

let last = null;
function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.lights;
  if (!cfg) return;
  last = snap;
  const l = ov.lights;
  if (l && (cfg.visible || PREVIEW)) return draw(l, cfg);
  if (PREVIEW) return draw(demo(cfg), cfg);
  leave();
}

// The preview's count runs between snapshots too.
if (PREVIEW) setInterval(() => last && render(last), 100);
followSnapshots(render);
