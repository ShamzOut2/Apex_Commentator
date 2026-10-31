"use strict";

// Grid walk: the starting grid two cars at a time, on a stretch of track
// running across the screen. Each car stands in its painted grid box (its
// picture from the thumbnails folder, else a drawing in its livery colours)
// with the driver's details beside it. The front car of the row is on the
// upper lane, further up the road; the second staggered behind it below,
// as on a real grid. Follows the walk the server keeps, so the control panel
// and any number of OBS sources stay in step.

const stage = $("#stage");
fitStage(stage);

let snap = null;
let shownKey = "";
let progress = null;
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3", logo: null };

const classFor = (classes, e) => classes.get(e.class_key) || DEFAULT_CLASS;

// Pole shows its lap time, everyone else the gap to their class pole.
function qualText(e) {
  if (e.qual_gap) return `+${e.qual_gap.toFixed(3)}`;
  if (e.qual_time) return fmtLap(e.qual_time);
  return "";
}

function carArt(e, cfg) {
  if (e.car_image) return `<img src="${esc(e.car_image)}" alt="" class="${cfg.flip_cars ? "flip" : ""}">`;
  return carSvg(e.car_design, e.number);  // no picture: a drawing in its livery colours
}

// One car in its grid box, and the driver's details beside it.
function slotHtml(e, i, cls, cfg, multiclass) {
  const lane = i === 0 ? "front" : "rear";
  const status = !e.in_session ? "NOT IN SESSION" : !e.in_world ? "NOT ON TRACK" : "";
  const qual = qualText(e);
  const badge = multiclass || cls.logo ? `<span class="gw-class">${classHeaderHtml(cls, "", rerender)}</span>` : "";
  return `<div class="gw-slot ${lane}">
    <div class="gw-box"><div class="gw-car">${carArt(e, cfg)}</div></div>
    <div class="gw-info" style="--cls:${esc(cls.color)}">
      <div class="gw-top">
        <span class="gw-pos"><small>P</small>${e.grid_pos}</span>
        ${multiclass ? `<span class="gw-cpos">P${e.class_pos} in class</span>` : ""}
        ${badge}
        ${e.make_logo ? `<img class="gw-make" src="${esc(e.make_logo)}" alt="${esc(e.make)}">` : ""}
      </div>
      <div class="gw-name"><span class="gw-num" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(e.number)}</span>
        <span class="gw-driver">${esc(e.name)}</span></div>
      ${e.nickname ? `<div class="gw-nick">“${esc(e.nickname)}”</div>` : ""}
      ${e.team ? `<div class="gw-team">${e.team_logo ? `<img src="${esc(e.team_logo)}" alt="">` : ""}<span>${esc(e.team)}</span></div>` : ""}
      <div class="gw-foot">${qual ? `<span class="gw-qual">${esc(qual)}</span>` : ""}${status ? `<span class="gw-status">${status}</span>` : ""}</div>
    </div>
  </div>`;
}

function walkHtml(g, pair, classes, cfg, multiclass) {
  const row = Math.floor(g.index / 2) + 1;
  const title = (snap.league && snap.league.name) || "Starting grid";
  const track = snap.session && snap.session.track;
  return `<div class="walk">
    <div class="gw-title"><span class="t1">${esc(title)}</span>${track ? `<span class="t2">${esc(track)}</span>` : ""}
      <span class="t3">STARTING GRID · ROW ${row}</span><div class="progress"><i id="progress"></i></div></div>
    <div class="gw-track"><div class="gw-edge top"></div><div class="gw-edge bottom"></div></div>
    ${pair.map((e, i) => slotHtml(e, i, classFor(classes, e), cfg, multiclass)).join("")}
  </div>`;
}

function rerender() {
  shownKey = "";
  render();
}

function render() {
  const g = snap && snap.gridwalk;
  if (!g) return;
  const cfg = (snap.overlays && snap.overlays.settings.gridwalk) || {};
  const entries = g.entries || [];
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const pair = entries.slice(g.index, g.index + 2);
  progress = { elapsed: g.elapsed, interval: g.interval, running: g.running && g.visible, at: performance.now() };
  const show = g.visible && pair.length > 0;
  setPanels(cfg);
  setSize(cfg, true, true);
  // Only rebuild when what's on screen changes, so the animations play once.
  const key = JSON.stringify([show, g.index, pair, pair.map((e) => classes.get(e.class_key) || null), cfg.flip_cars,
    snap.league && snap.league.name, snap.session && snap.session.track]);
  if (key === shownKey) return;
  shownKey = key;
  stage.classList.toggle("hidden", !show);
  if (!show) return;  // the last pair stays while it fades out
  const multiclass = new Set(entries.map((e) => e.class_key)).size > 1;
  stage.innerHTML = walkHtml(g, pair, classes, cfg, multiclass);
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
followSnapshots((s) => {
  snap = s;
  render();
});
