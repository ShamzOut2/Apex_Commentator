"use strict";

// Catching: two cars on track, the gap between them now and lap by lap (a
// small graph), how fast it's closing or growing and, closing, the laps
// until it's gone. The driver on camera and the car ahead (or behind, or the
// nearer of the two), or two cars picked in the app.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3" };
let shownKey = "";
let shownHtml = "";

function carHtml(e, cfg, classes, label) {
  const cls = classes.get(e.class_key) || DEFAULT_CLASS;
  const color = paintFor(e, cls, "main") || cls.color;
  const number = cfg.show_number && e.number
    ? `<span class="num" style="background:${esc(bgc(color))};color:${inkFor(color)}">${esc(e.number)}</span>` : "";
  const logo = cfg.show_logo && teamLogoOf(e, cfg) ? `<img class="logo" src="${esc(teamLogoOf(e, cfg))}" alt="">` : "";
  return `<div class="ct-car"><span class="pos">P${e.pos ?? "–"}</span><span class="who">${number}${logo}
    <span class="name">${nameHtml(e, cfg.name_format)}</span></span><span class="ct-tag">${label}</span></div>`;
}

// The gap lap by lap: 0 (caught) along the bottom, the latest on the right.
function graphHtml(d) {
  const pts = d.gaps.map((g) => [g.lap, g.gap]);
  if (d.gap != null && pts.length) pts.push([pts[pts.length - 1][0] + 0.5, d.gap]);  // now, just past the last line
  if (d.gaps.length < 2) return "";  // a trend needs two laps at the line
  const W = 360, H = 86, P = 8;
  const top = Math.max(0.5, ...pts.map((p) => p[1])) * 1.15;
  const lo = pts[0][0], hi = pts[pts.length - 1][0];
  const x = (lap) => P + (W - 2 * P) * (hi > lo ? (lap - lo) / (hi - lo) : 0);
  const y = (gap) => H - P - (H - 2 * P) * Math.max(0, Math.min(1, gap / top));
  const line = pts.map(([l, g]) => `${x(l).toFixed(1)},${y(g).toFixed(1)}`).join(" ");
  const dots = d.gaps.map((g) => `<circle cx="${x(g.lap).toFixed(1)}" cy="${y(g.gap).toFixed(1)}" r="3.5"/>`).join("");
  const last = pts[pts.length - 1];
  return `<svg class="ct-graph ${d.trend || ""}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <line class="ct-zero" x1="${P}" y1="${H - P}" x2="${W - P}" y2="${H - P}"/>
    <polyline points="${line}"/>${dots}<circle class="now" cx="${x(last[0]).toFixed(1)}" cy="${y(last[1]).toFixed(1)}" r="5"/></svg>
    <div class="ct-laps"><span>Lap ${d.gaps[0].lap}</span><span>now</span></div>`;
}

function catchingHtml(d, cfg, classes) {
  const title = cfg.title || (d.trend === "closing" ? "Catching" : d.trend === "pulling" ? "Pulling away" : "The gap");
  const rate = d.rate == null ? "" : d.trend === "steady" ? "Steady"
    : `${d.rate < 0 ? "−" : "+"}${Math.abs(d.rate).toFixed(2)} s a lap`;
  const gap = d.lapped ? "A lap apart" : d.gap != null ? `${secs(d.gap)} s` : "–";
  const laps = d.catch_laps != null ? Math.max(1, Math.round(d.catch_laps)) : null;
  const catchText = laps != null ? `On them in about ${laps} lap${laps === 1 ? "" : "s"}` : "";
  return `<div class="bt-head">${esc(title)}</div>
    ${carHtml(d.ahead, cfg, classes, "Ahead")}${carHtml(d.behind, cfg, classes, "Behind")}
    <div class="ct-now"><div class="ct-gap"><span class="lbl">Gap</span><b>${esc(gap)}</b></div>
      ${cfg.show_rate && rate ? `<div class="ct-rate ${d.trend || ""}"><span class="lbl">Trend (${d.gaps.length} laps)</span><b>${esc(rate)}</b></div>` : ""}</div>
    ${cfg.show_catch && catchText ? `<div class="ct-catch">${esc(catchText)}</div>` : ""}
    ${cfg.show_graph ? graphHtml(d) : ""}`;
}

function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.catching;
  if (!cfg) return;
  setPanels(cfg);
  setSize(cfg);
  const d = ov.catching;
  const on = snap.connected && d && (cfg.visible || PREVIEW);
  if (!on) {
    leave();
    shownKey = "";
    if (PREVIEW && !stage.querySelector(".bt-hint")) {
      stage.insertAdjacentHTML("beforeend", '<div class="bt-hint">Nothing to show yet: it shows two cars in a race (the driver on camera and the car ahead, or two you pick)</div>');
    }
    return;
  }
  stage.querySelectorAll(".bt-hint").forEach((el) => el.remove());
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const html = catchingHtml(d, cfg, classes);
  const key = [d.ahead.car_idx, d.behind.car_idx, cfg.place, cfg.visible].join("|");
  const cur = stage.querySelector(".battle:not(.out)");
  if (key === shownKey && cur) {
    if (html !== shownHtml) {
      shownHtml = html;
      cur.innerHTML = html;
    }
    return;
  }
  leave();
  shownKey = key;
  shownHtml = html;
  const cls = classes.get(d.behind.class_key) || DEFAULT_CLASS;
  stage.insertAdjacentHTML("beforeend", `<div class="battle catching panel-in ${esc(cfg.place)} ${cfg.visible ? "" : "hidden-preview"}" style="--grp:${esc(cls.color || "var(--accent)")}">${html}</div>`);
  const el = stage.lastElementChild;
  setTimeout(() => el.classList.remove("panel-in"), 1300);
}

function leave() {
  for (const old of stage.querySelectorAll(".battle:not(.out)")) {
    old.classList.remove("panel-in");
    old.classList.add("out", "panel-out");
    setTimeout(() => old.remove(), 480);
  }
}

followSnapshots(render);
