"use strict";

// Pit strategy: a few cars (picked in the app, by number), each with its race
// so far along a lap scale, a tag at the lap of each pit stop, where it is now
// (PIT while it's in the pit lane, a chequered flag once it's finished), its
// stops and the laps in its current stint.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3" };
const STOP_GAP_PX = 46;  // stops closer than this on the scale share one tag ("L14 · 15")
let shownKey = "";
let shownHtml = "";

// Where a lap is along the scale (%).
const along = (lap, scale) => Math.min(100, Math.max(0, (lap / Math.max(1, scale)) * 100));

// The lap scale's marks: every 5, 10, 25 or 50 laps, to suit its length.
function ticks(scale) {
  const step = scale <= 30 ? 5 : scale <= 80 ? 10 : scale <= 200 ? 25 : 50;
  const out = [];
  for (let lap = 0; lap <= scale; lap += step) out.push(lap);
  return out;
}

// The columns: position, the car, the lap scale, stops, stint.
function columns(cfg) {
  return [cfg.show_position && "56px", "minmax(240px, 340px)", "1fr", cfg.show_stops && "64px", cfg.show_stint && "64px"].filter(Boolean);
}

// A penalty served in the pit lane: its tag's letters and what they stand for.
const PENALTY = { drive_through: ["DT", "Drive-through"], stop_go: ["SG", "Stop-and-go"] };

// Each visit to the pit lane that's over: a tag at its lap. Pit stops "L14";
// penalties served there "DT L20" / "SG L20", in the penalty colour (counted
// as stops or not: All overlays & boards). Close ones of a kind share a tag.
function stopsHtml(stops, scale, laneW) {
  const groups = [];
  for (const s of [...stops].filter((v) => v.kind).sort((a, b) => a.lap - b.lap)) {
    const last = groups[groups.length - 1];
    if (last && last.kind === s.kind && ((s.lap - last.laps[0]) / Math.max(1, scale)) * laneW < STOP_GAP_PX) last.laps.push(s.lap);
    else groups.push({ kind: s.kind, laps: [s.lap] });
  }
  // Left to right, a tag that would cover the one before it (a stop and a
  // penalty a lap apart) moves along just enough to sit beside it.
  let edge = -Infinity;  // the right-hand end of the last tag (px)
  return groups.map((g) => {
    const pen = PENALTY[g.kind];
    const text = `${pen ? `${pen[0]} ` : ""}L${g.laps.join(" · ")}`;
    const width = 20 + text.length * 8.5;  // about, at the standard size
    const at = (along(g.laps[0], scale) / 100) * laneW;
    const shift = Math.max(0, edge + 4 - (at - width / 2));
    edge = at + shift + width / 2;
    return `<span class="st-stop ${pen ? "pen" : ""}" style="left:calc(${along(g.laps[0], scale)}% + ${Math.round(shift)}px)"${pen ? ` title="${pen[1]}"` : ""}>${pen ? `<b>${pen[0]}</b> ` : ""}L${g.laps.join(" · ")}</span>`;
  }).join("");
}

function rowHtml(r, i, cfg, cls, scale, laneW) {
  const color = paintFor(r, cls, cfg.class_colors) || cls.color || "#8b93a3";
  const number = cfg.show_number && r.number
    ? `<span class="num" style="background:${esc(bgc(color))};color:${inkFor(color)}">${esc(r.number)}</span>` : "";
  const logo = !cfg.show_logo ? "" : teamLogoOf(r, cfg) ? `<img class="logo" src="${esc(teamLogoOf(r, cfg))}" alt="">` : '<span class="logo"></span>';
  const done = Math.min(r.done, scale);
  const now = r.in_pit ? '<span class="st-now pit">PIT</span>'
    : r.finished ? '<span class="st-now fin"></span>'
      : r.out ? '<span class="st-now out">OUT</span>' : '<span class="st-now"></span>';
  const cells = [];
  if (cfg.show_position) cells.push(`<span class="pos">${r.pos ? `P${r.pos}` : "–"}</span>`);
  cells.push(`<span class="who">${number}${logo}<span class="names"><span class="name">${nameHtml(r, cfg.name_format)}</span></span></span>`);
  cells.push(`<span class="st-lane" style="--run:${esc(color)}"><span class="st-line"></span>
    <span class="st-run" style="width:${along(done, scale)}%"></span>${stopsHtml(r.stops, scale, laneW)}
    <span class="st-at ${r.in_pit || r.out ? "over" : ""}" style="left:${along(done, scale)}%">${now}</span></span>`);
  if (cfg.show_stops) cells.push(`<span class="st-n">${r.stop_count}</span>`);
  if (cfg.show_stint) cells.push(`<span class="st-n stint">${r.stint ?? "–"}</span>`);
  return `<div class="bt-row panel-row ${r.in_pit ? "in-pit" : ""} ${r.out ? "gone" : ""}" style="--i:${i}" data-key="${r.car_idx}">${cells.join("")}</div>`;
}

function strategyHtml(d, cfg, classes) {
  const cols = columns(cfg);
  // The lap scale's room across (for telling which stops are too close to tag apart).
  const fixed = (cfg.show_position ? 56 : 0) + 340 + (cfg.show_stops ? 64 : 0) + (cfg.show_stint ? 64 : 0) + 12 * (cols.length - 1) + 32;
  const laneW = Math.max(200, cfg.panel_width - fixed);
  const title = cfg.title || "Pit strategy";
  const lap = d.laps_total ? `LAP ${Math.min(d.lap + 1, d.laps_total)} / ${d.laps_total}` : d.lap ? `LAP ${d.lap + 1}` : "";
  const scaleRow = `<div class="bt-cols st-cols">${cfg.show_position ? "<span></span>" : ""}<span></span>
    <span class="st-ticks">${ticks(d.scale).map((t) => `<i style="left:${along(t, d.scale)}%">${t}</i>`).join("")}</span>
    ${cfg.show_stops ? '<span class="r">Stops</span>' : ""}${cfg.show_stint ? '<span class="r">Stint</span>' : ""}</div>`;
  const rows = d.rows.map((r, i) => rowHtml(r, i, cfg, classes.get(r.class_key) || DEFAULT_CLASS, d.scale, laneW)).join("");
  const marks = ticks(d.scale);
  const tick = marks.length > 1 ? (marks[1] / d.scale) * 100 : 100;  // the faint lines down the lanes, at the marks
  return `<div class="bt-head">${esc(title)}${lap ? `<span class="st-lap tnum">${lap}</span>` : ""}</div>${scaleRow}${rows}
    <style>.strategy{--bt-cols:${cols.join(" ")};--tick:${tick.toFixed(3)}%}</style>`;
}

function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.strategy;
  if (!cfg) return;
  setPanels(cfg);
  setSize(cfg);
  const d = ov.strategy;
  const has = d && d.rows && d.rows.length;
  if (!has || !(cfg.visible || PREVIEW)) {
    leave();
    shownKey = "";
    if (PREVIEW && !stage.querySelector(".bt-hint")) {
      stage.insertAdjacentHTML("beforeend", '<div class="bt-hint">Pick the cars on the Widgets tab (it shows during a race)</div>');
    }
    return;
  }
  stage.querySelectorAll(".bt-hint").forEach((el) => el.remove());
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const html = strategyHtml(d, cfg, classes);
  // The same cars: what's changed is redrawn (places changing slide); other cars: in fresh.
  const key = [d.rows.map((r) => r.car_idx).sort().join(","), cfg.place, cfg.visible, cfg.panel_width].join("|");
  const cur = stage.querySelector(".strategy:not(.out)");
  if (key === shownKey && cur) {
    if (html !== shownHtml) {
      shownHtml = html;
      patchRows(cur, ".bt-row", html);
    }
    return;
  }
  leave();
  shownKey = key;
  shownHtml = html;
  stage.insertAdjacentHTML("beforeend", `<div class="battle strategy panel-in ${esc(cfg.place)} ${cfg.visible ? "" : "hidden-preview"}"
    style="width:${cfg.panel_width}px">${html}</div>`);
  const el = stage.lastElementChild;
  setTimeout(() => el.classList.remove("panel-in"), 1300);
}

function leave() {
  for (const old of stage.querySelectorAll(".strategy:not(.out)")) {
    old.classList.remove("panel-in");
    old.classList.add("out", "panel-out");
    setTimeout(() => old.remove(), 480);
  }
}

followSnapshots(render);
