"use strict";

// Standings timing tower. Race: running order with gap to the leader.
// Qualifying and practice: fastest clean lap, and nobody until they set one.
// The columns are the commentator's choice (Overlays tab).

const stage = $("#stage");
const tower = $("#tower");
// ?screen=1: a full-screen standings board (opaque, every driver) to show
// on its own, rather than a tower over the race.
const SCREEN = new URLSearchParams(location.search).has("screen");
if (SCREEN) document.body.classList.add("screen");
fitStage(stage);
let last = null;
let shown = "";
let fitMode = "";

const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3", logo: null };

// The new-fastest-lap flash (top middle) lives beside the tower / full screen, not inside them.
const screenRoot = document.createElement("div");
if (SCREEN) stage.appendChild(screenRoot);
const flashBox = document.createElement("div");
flashBox.className = "fl-flash";
stage.appendChild(flashBox);
let flashId = "";

// Who moved up or down, and who just took the fastest lap: a brief tint /
// pop that carries on across redraws (see ongoing() in common.js).
const MOVE_MS = 1600;
const POP_MS = 700;
const lastPlace = new Map();   // car -> position last drawn
const moves = new Map();       // car -> {up, at}
const holders = new Map();     // car -> when they took the fastest lap
const finishers = new Map();   // car -> when they took the chequered flag
const WAVE_MS = 1100;          // one wave of a finished driver's flag
let placeView = "";

function notePlaces(entries, classMode) {
  const view = `${SCREEN}:${classMode}`;
  const fresh = view !== placeView;  // switched view: nothing "moved"
  placeView = view;
  const now = performance.now();
  for (const e of entries) {
    const pos = classMode ? e.class_pos : e.pos;
    const was = lastPlace.get(e.car_idx);
    if (!fresh && was != null && pos != null && pos !== was) moves.set(e.car_idx, { up: pos < was, at: now });
    lastPlace.set(e.car_idx, pos);
    const holds = classMode ? e.class_fastest : e.fastest;
    if (holds && !holders.has(e.car_idx)) holders.set(e.car_idx, fresh ? -1e9 : now);
    if (!holds) holders.delete(e.car_idx);
    if (e.finished && !finishers.has(e.car_idx)) finishers.set(e.car_idx, fresh ? -1e9 : now);
    if (!e.finished) finishers.delete(e.car_idx);
  }
}

function moveOf(car) {
  const m = moves.get(car);
  const style = m && ongoing(m.at, MOVE_MS);
  if (!style) {
    moves.delete(car);
    return null;
  }
  return { cls: m.up ? "moved-up" : "moved-down", style };
}

// Race start: the header flashes green GO_FLASHES times as the race goes
// green, then stops (only if this page saw the start, not when opened later).
const GO_FLASH_MS = 550;
const GO_FLASHES = 5;
let goAt = -1e9;

// The chequered flag: from the moment it's out, the header is a waving
// black-and-white chequered flag (it flashes in, then keeps waving) until the
// session changes or the overlay is taken off (standings.css: .chequered).

// The header's flag animation, if one is running: green at the start,
// chequered at the finish (only if this page saw it happen).
function goFlash(ov) {
  const race = ov.session_kind === "race";
  const since = ov.since_green;
  if (race && since != null && since >= 0 && since * 1000 < GO_FLASH_MS * GO_FLASHES) {
    goAt = performance.now() - since * 1000;
  }
  // The header, its light sweep and its text all run off the same clock:
  // the time since the flag came out.
  const fin = ov.since_chequered;
  if (race && fin != null && fin >= 0) return ` chequered" style="--go-delay:-${Math.round(fin * 1000)}ms`;
  const style = ongoing(goAt, GO_FLASH_MS * GO_FLASHES);
  return style ? ` go" style="--go-delay:${style.split(":")[1]}` : "";
}

// The purple stopwatch by the fastest lap's holder: overall, or each class's in "by class".
function fastestIcon(e, cfg, classMode) {
  if (!cfg.show_fastest_icon || !(classMode ? e.class_fastest : e.fastest)) return "";
  const pop = ongoing(holders.get(e.car_idx) ?? -1e9, POP_MS);
  return `<span class="fl-icon ${pop ? "pop" : ""}" style="${pop || ""}" title="Fastest lap">${STOPWATCH}</span>`;
}

// A chequered flag by a driver who's finished the race: it pops in as they
// cross the line, then waves. Every flag waves in time, whatever the redraws
// (the wave runs off the page's clock).
function finishFlag(e, cfg) {
  if (cfg.finish_flag === false || !e.finished) return "";
  const pop = ongoing(finishers.get(e.car_idx) ?? -1e9, POP_MS * 1.3);
  const wave = `--wave-delay:-${Math.round(performance.now() % WAVE_MS)}ms`;
  return `<span class="fin-flag ${pop ? "pop" : ""}" style="${pop ? `${pop};` : ""}${wave}" title="Finished">${FINISH_FLAG}</span>`;
}

// On the tower the flags are a tab of their own sticking out of its right
// edge, level with each finisher's row: a rail beside the tower (kept across
// redraws), each tab sliding out from behind the tower as they finish.
const finRail = document.createElement("div");
finRail.className = "fin-rail";
const finTabs = new Map();  // car -> tab element

function placeFinishTabs(entries, cfg) {
  if (finRail.parentNode !== tower) tower.appendChild(finRail);
  const done = new Map(entries.filter((e) => cfg.finish_flag !== false && e.finished).map((e) => [String(e.car_idx), e]));
  const seen = new Set();
  for (const row of tower.querySelectorAll(".srow[data-key]")) {
    const key = row.dataset.key;
    const e = done.get(key);
    if (!e || seen.has(key)) continue;
    seen.add(key);
    // Its place in the tower as laid out (not mid-slide).
    let top = 0;
    for (let el = row; el && el !== tower; el = el.offsetParent) top += el.offsetTop;
    let tab = finTabs.get(key);
    if (!tab) {
      tab = document.createElement("div");
      const fresh = ongoing(finishers.get(e.car_idx) ?? -1e9, 1500);
      tab.className = `fin-tab ${fresh ? "in" : ""}`;
      tab.innerHTML = `<span class="fin-flag">${FINISH_FLAG}</span>`;
      finTabs.set(key, tab);
      finRail.appendChild(tab);
    }
    tab.style.top = `${top}px`;
    tab.style.height = `${row.offsetHeight}px`;
    tab.querySelector(".fin-flag").style.setProperty("--wave-delay", `-${Math.round(performance.now() % WAVE_MS)}ms`);
  }
  for (const [key, tab] of finTabs) {
    if (!seen.has(key)) {
      tab.remove();
      finTabs.delete(key);
    }
  }
}

function renderFlash(snap, ov) {
  const f = snap.connected ? ov.fastest_flash : null;
  const id = f ? f.id : "";
  if (id === flashId) return;
  flashId = id;
  const old = flashBox.firstElementChild;
  if (old) {
    old.classList.add("out");
    setTimeout(() => old.remove(), 450);
  }
  if (!f) return;
  const cls = f.scope === "class" && (snap.classes || []).find((c) => c.key === f.class_key);
  const pill = document.createElement("div");
  pill.className = "fl-pill";
  // "NEW FASTEST LAP" first, then who and the time (in the same spot, see standings.css).
  pill.innerHTML = `${STOPWATCH}<div class="fl-swap">
      <div class="fl-intro">New fastest lap${cls ? `<span>${esc(cls.name)}</span>` : ""}</div>
      <div class="fl-text">
        <div class="fl-cap">Fastest lap${cls ? ` · ${esc(cls.name)}` : ""}</div>
        <div class="fl-name">${esc(f.name)}</div>
        <div class="fl-time tnum">${fmtLap(f.lap_time)}</div>
      </div>
    </div>`;
  flashBox.appendChild(pill);
}

// Columns after the driver, as the commentator has chosen them:
// [setting, width, label, value(e, race, classMode)].
const COLUMNS = [
  ["show_pos_change", "46px", "+/−", (e, race) => {
    if (!race || !e.pos_change) return race ? '<span class="dim">–</span>' : "";
    return `<span class="${e.pos_change > 0 ? "up" : "down"}">${e.pos_change > 0 ? "▲" : "▼"}${Math.abs(e.pos_change)}</span>`;
  }, (race) => race],
  ["show_laps", "44px", "Laps", (e) => e.laps_completed ?? ""],
  ["show_pits", "40px", "Pit", (e) => e.pit_stops || ""],
  ["show_last_lap", "92px", "Last", (e) => fmtLap(e.last_lap)],
  ["show_best_lap", "92px", "Best", (e, race) => fmtLap(race ? e.best_lap : e.best)],
  ["show_gap", "92px", "Gap", (e, race, classMode, cfg) => {
    const gap = classMode ? e.class_gap : e.gap;
    const first = classMode ? e.class_pos === 1 : e.pos === 1;
    if (!race && e.best == null) return '<span class="dim">No time</span>';
    if (first) return `<span class="lead">${race ? leaderText(e, cfg) : fmtLap(e.best)}</span>`;
    const down = race && (classMode ? e.class_laps_down : e.laps_down);
    if (down) return `+${down} L`;
    return gap != null ? `+${race ? gap.toFixed(1) : gap.toFixed(3)}` : "";
  }],
  ["show_interval", "80px", "Int", (e, race, classMode, cfg, green) => {
    const interval = classMode ? e.class_interval : e.interval;
    const first = classMode ? e.class_pos === 1 : e.pos === 1;
    if (first) return race ? leaderInterval(e, cfg) : "";
    if (interval == null) return "";
    const text = `+${race ? interval.toFixed(1) : interval.toFixed(3)}`;
    // Racing within close_s of the car ahead: red until they're past or it opens up.
    const close = race && green && cfg.close_s > 0 && interval <= cfg.close_s && e.in_world && !e.on_pit;
    return close ? `<span class="close">${text}</span>` : text;
  }],
];

// In the order picked (cfg.column_order: "gap,interval,...", by the setting without "show_").
function columnsFor(cfg, race) {
  const order = String(cfg.column_order || "").split(",");
  const rank = (c) => {
    const i = order.indexOf(c[0].replace(/^show_/, ""));
    return i < 0 ? 99 : i;
  };
  return COLUMNS.filter(([key, , , , when]) => cfg[key] && (!when || when(race))).sort((a, b) => rank(a) - rank(b));
}

// The extra drivers under the top of the order. "rotate": the rest of the field
// cfg.rows_last at a time, the next set every rows_extra_s seconds and then
// round again (by the clock, so every copy of the overlay is on the same set);
// "last": the last ones.
function extraDrivers(entries, cfg) {
  const n = cfg.rows_last;
  if (!n || entries.length <= cfg.rows + n) return [];
  if (cfg.rows_extra_mode === "last") return entries.slice(-n);
  const rest = entries.slice(cfg.rows);
  const sets = Math.ceil(rest.length / n);
  const set = Math.floor(Date.now() / 1000 / cfg.rows_extra_s) % sets;
  // Always n drivers: a last set that's short is filled from the start of the rest again.
  return Array.from({ length: n }, (_, k) => rest[(set * n + k) % rest.length]);
}

// What the race leader (each class's, by class) shows where the gap would be:
// "Leader", or the lap they're on.
function leaderText(e, cfg, setting = cfg.leader_cell) {
  return setting === "lap" && e.lap ? `Lap ${e.lap}` : "Leader";
}

// The same for the interval column (interval_leader): nothing, "Leader" or their lap.
function leaderInterval(e, cfg) {
  return cfg.interval_leader === "blank" ? "" : `<span class="lead">${leaderText(e, cfg, cfg.interval_leader)}</span>`;
}

// The bar's class colour: the car number's (class_colors), unless it has its own.
const stripeWhich = (cfg) => (cfg.stripe_colors === "main" || cfg.stripe_colors === "secondary" ? cfg.stripe_colors : cfg.class_colors);
// By class: the classes shown, in the order picked (every class, in the
// league's order, when none are picked).
function towerClassKeys(cfg, snap) {
  const picked = String(cfg.class_keys || cfg.class_key || "").split(",").filter(Boolean);
  return picked.length ? picked : (snap.classes || []).map((c) => c.key);
}

// The coloured bar's colour: the class picked for it (by class and overall
// alike), or the team's colour when "Team colour" is picked (the class
// colour for a driver whose team has none). "" = no bar.
function stripeColor(e, cls, cfg) {
  if (!cfg.show_stripe) return "";
  const paint = paintFor(e, cls, stripeWhich(cfg));
  return cfg.stripe_colors === "team" ? e.team_color || paint || "" : paint || "";
}

// The car number: on a background in the driver's class colour, or just the number (Overlays tab).
function numberChip(e, cls, cfg) {
  const color = paintFor(e, cls, cfg.class_colors);
  return cfg.color_number && color
    ? `<span class="num" style="background:${esc(color)};color:${inkFor(color)}">${esc(e.number)}</span>`
    : `<span class="num plain">${esc(e.number)}</span>`;
}

// The row's columns, in order: [part, width, fits its contents]. Position,
// stripe, number and team logo are the same size whatever the width; the
// driver's name takes the room left; the team name (its own column, when
// it's not under the driver's name) and the columns picked fit what's in them.
// The team logo goes before the driver or after the team (team_logo_side).
function rowSpec(cfg, cols) {
  const spec = [["pos", "40px", false], ["stripe", "6px", false]];
  if (cfg.show_number) spec.push(["number", "50px", false]);
  const logoW = `${Math.round(34 * Math.min(1.5, (cfg.logo_scale || 100) / 100))}px`;  // the logo column grows with the logos
  if (cfg.logo_col && !cfg.logo_last) spec.push(["logo", logoW, false]);
  // The driver name column: set by hand (name_width px; longer names end in
  // "…"), or 0: it takes the room left / fits the names.
  spec.push(cfg.name_width > 0 ? ["name", `${cfg.name_width}px`, false] : ["name", "minmax(60px, 1fr)", true]);
  if (cfg.team_col) spec.push(["team", "minmax(60px, .6fr)", true]);
  if (cfg.logo_col && cfg.logo_last) spec.push(["logo", logoW, false]);
  return spec.concat(cols.map((c) => [c[0], c[1], true]));
}

// A width set by hand: the name takes what the other columns leave.
function gridFor(cfg, cols) {
  return rowSpec(cfg, cols).map((c) => c[1]).join(" ");
}

// Automatic width: each column (name included) as wide as its widest entry
// plus a little room, and the tower as wide as that. It grows straight away
// when something needs more room, but only narrows once there's clearly
// spare, so changing numbers don't make it twitch.
const fit = { key: "", widths: [] };
const ROW_GAP = 8;     // .srow column gap
const ROW_PAD = 12;    // .srow padding-right
const MIN_TOWER = 300; // the narrowest the tower goes
const HEAD_PAD = 6 + 14 * 2 + 4;  // the header's accent bar and padding

// How wide a cell's contents are, whatever the size of the cell itself (a
// cell's own width would follow the column it's in).
function contentWidth(el) {
  const range = document.createRange();
  range.selectNodeContents(el);
  return range.getBoundingClientRect().width;
}

function autoFit(cfg, cols) {
  const spec = rowSpec(cfg, cols);
  const rows = [...tower.querySelectorAll(".srow:not(.skip)")];
  if (!rows.length) return;
  // On-screen px back to the tower's own (it may be zoomed, and the stage scaled).
  const scale = rows[0].getBoundingClientRect().width / (rows[0].offsetWidth || 1) || 1;
  const need = spec.map(() => 0);
  for (const row of rows) {
    spec.forEach(([part, , fits], i) => {
      const cell = row.children[i];
      if (!fits || !cell) return;
      // The name cell holds the name line and the team line: the wider one.
      const parts = part === "name" && cell.children.length ? [...cell.children] : [cell];
      need[i] = Math.max(need[i], ...parts.map((el) => contentWidth(el) / scale));
    });
  }
  const key = JSON.stringify(spec.map((c) => c[0]));
  if (key !== fit.key) {
    fit.key = key;
    fit.widths = [];
  }
  // With a background per column the cells carry their own padding (standings.css), and the last one more.
  const colBg = document.body.classList.contains("col-bg");
  fit.widths = spec.map(([part, width, fits], i) => {
    if (!fits) return parseFloat(width);
    const pad = colBg ? (i === spec.length - 1 ? 16 : 8) : 0;
    const want = Math.ceil(Math.max(part === "name" ? 60 : 24, need[i] + (part === "name" ? 12 : 4) + pad));
    const was = fit.widths[i];
    return was && want <= was && want > was - 14 ? was : want;
  });
  // The name column takes any spare room (when the header needs more width than the columns).
  tower.style.setProperty("--grid", fit.widths.map((w, i) => (spec[i][0] === "name" && spec[i][2] ? `minmax(${w}px, 1fr)` : `${w}px`)).join(" "));
  const total = fit.widths.reduce((n, w) => n + w, 0) + (colBg ? 0 : ROW_GAP * (spec.length - 1) + ROW_PAD);
  // Room for the header too: the session name and laps / time left side by
  // side, unless the name may wrap onto two lines.
  const h1 = tower.querySelector(".tower-head .h1");
  const head = h1 && !cfg.title_wrap
    ? [...h1.children].reduce((n, el) => n + contentWidth(el) / scale, 0) + 10 * (h1.children.length - 1) + HEAD_PAD : 0;
  tower.style.width = `${Math.max(MIN_TOWER, Math.ceil(total), Math.ceil(head))}px`;
}

function rowHtml(e, cfg, cols, cls, race, classMode, multiclass, camIdx, green) {
  const pos = classMode ? e.class_pos : e.pos;
  const pit = cfg.show_pit_status && e.on_pit ? '<span class="pitb">PIT</span>' : "";
  const move = moveOf(e.car_idx);
  // The cells in the order rowSpec gives: the team logo and the team name are columns of their own.
  const cell = {
    pos: () => `<span class="p tnum" data-opcol="pos">${pos}</span>`,
    stripe: () => `<span class="stripe" style="${stripeColor(e, cls, cfg) ? `background:${esc(stripeColor(e, cls, cfg))}` : ""}"></span>`,
    number: () => `<span data-opcol="number">${numberChip(e, cls, cfg)}</span>`,
    logo: () => `<span class="lg" data-opcol="logo">${e.team_logo ? `<img class="team-logo" src="${esc(e.team_logo)}" alt="">` : ""}</span>`,
    name: () => `<span class="who" data-opcol="name"><span class="n">${esc(formatName(e, cfg.name_format))}${fastestIcon(e, cfg, classMode)}${pit}</span>${cfg.team_under && e.team ? `<span class="tm">${esc(e.team)}</span>` : ""}</span>`,
    team: () => `<span class="tmc" data-opcol="team">${esc(e.team || "")}</span>`,
  };
  return `<div class="srow ${e.car_idx === camIdx ? "cam" : ""} ${move ? move.cls : ""}" data-key="${e.car_idx}" style="${move ? move.style : ""}">
    ${rowSpec(cfg, []).map(([k]) => cell[k]()).join("")}
    ${cols.map((c) => `<span class="c tnum" data-opcol="${c[0].replace(/^show_/, "")}">${c[3](e, race, classMode, cfg, green)}</span>`).join("")}
  </div>`;
}

// "LAP 5 / 20", "12:34 LEFT", "FINAL LAP", "FINISHED": whatever the
// session is limited by (or what the commentator picked).
function progressText(ov) {
  const left = ov.settings.standings.time_left_word ? " LEFT" : "";
  const pr = ov.progress;
  if (!pr || pr.mode === "none") return "";
  if (pr.finished) return "FINISHED";
  if (pr.mode === "laps") {
    if (!pr.lap) return pr.laps_total ? `${pr.laps_total} LAPS` : "";
    if (pr.laps_total && pr.lap >= pr.laps_total) return "FINAL LAP";
    return `LAP ${pr.lap}${pr.laps_total ? ` / ${pr.laps_total}` : ""}`;
  }
  // The clock has run out: the last lap, until the chequered flag.
  if (pr.time_up) return "LAST LAP";
  if (pr.time_remain == null) return "";
  return `${fmtClock(pr.time_remain)}${left}`;
}

// The accent colour (header time / lap, the tower header's bar, the full
// screen's header line): orange, one picked, or by session (accent setting).
function setAccent(cfg, ov) {
  const kind = ov.session_kind === "race" ? "race" : ov.session_kind === "qualify" ? "qualify" : "practice";
  const color = cfg.accent === "color" ? cfg.accent_color : cfg.accent === "session" ? cfg[`accent_${kind}`] : "";
  if (color) document.body.style.setProperty("--head-accent", color);
  else document.body.style.removeProperty("--head-accent");
}

// The sponsor bar under the tower's header: one logo, several taking turns.
// It's one element kept from redraw to redraw (placeSponsor), so the logo
// only changes, with a fade, when it's the next one's turn.
function sponsorLogo(snap, cfg) {
  if (!cfg.sponsor_bar) return null;
  const all = (snap.league && snap.league.sponsors) || [];
  const ids = cfg.sponsor_bar_ids && cfg.sponsor_bar_ids !== "none" ? new Set(cfg.sponsor_bar_ids.split(",")) : null;
  const logos = cfg.sponsor_bar_ids === "none" ? [] : all.filter((l) => !ids || ids.has(l.id));
  if (!logos.length) return null;
  return logos[Math.floor(Date.now() / 1000 / cfg.sponsor_bar_s) % logos.length];
}

const sponsorBar = document.createElement("div");
sponsorBar.className = "tower-sponsor";
let sponsorShown = "";
function placeSponsor(logo, cfg) {
  const slot = tower.querySelector(".tower-sponsor-slot");
  if (slot) slot.replaceWith(sponsorBar);
  if (!logo) return;
  sponsorBar.style.setProperty("--sb-h", `${cfg.sponsor_bar_size}px`);
  if (logo.url === sponsorShown) return;
  const first = !sponsorShown;
  sponsorShown = logo.url;
  const img = document.createElement("img");
  img.src = logo.url;
  img.alt = logo.name || "";
  sponsorBar.replaceChildren(img);
  if (!first) img.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 500, easing: "ease" });
}

function headRowHtml(cfg, cols) {
  if (!cols.length || !cfg.show_col_labels) return "";
  return `<div class="srow shead">${rowSpec(cfg, []).map(() => "<span></span>").join("")}
    ${cols.map((c) => `<span class="c">${c[2]}</span>`).join("")}</div>`;
}

function render() {
  const snap = last;
  const ov = snap && snap.overlays;
  if (!ov) return;
  renderFlash(snap, ov);
  setColumnOpacity(ov.settings.standings);
  setAccent(ov.settings.standings, ov);
  if (SCREEN) {
    setBackground(ov.settings.standings, true);
    setSize(ov.settings.standings, true);
    return renderScreen(snap, ov);
  }
  const entries = ov.standings;
  // No logo column when no team has a logo.
  const cfg = { ...ov.settings.standings };
  if (cfg.mode === "class") {
    // By class: its own most drivers and extra drivers (a class each).
    cfg.rows = cfg.rows_class;
    cfg.rows_last = cfg.rows_last_class;
  }
  // Team logo and team name, each a column of its own (the name can sit under the driver's instead).
  cfg.logo_col = cfg.show_logo && entries.some((e) => e.team_logo);
  cfg.logo_last = cfg.team_logo_side === "last";
  cfg.team_under = cfg.show_team && cfg.team_name_place !== "column";
  cfg.team_col = cfg.show_team && cfg.team_name_place === "column" && entries.some((e) => e.team);
  const race = ov.session_kind === "race";
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const multiclass = new Set(entries.map((e) => e.class_key)).size > 1;
  const classMode = cfg.mode === "class";
  const camIdx = snap.camera && snap.camera.car_idx;
  const cols = columnsFor(cfg, race);
  const grid = gridFor(cfg, cols);
  notePlaces(entries, classMode);
  const rows = (list, cls) => list.map((e) => rowHtml(e, cfg, cols, cls || classes.get(e.class_key) || DEFAULT_CLASS,
    race, classMode, multiclass, camIdx, ov.green)).join("");
  let body;
  if (classMode) {
    const keys = towerClassKeys(cfg, snap);
    // Each class: its top drivers, then (if asked) a few more of the rest of
    // the class after a small gap, as overall does for the whole field.
    const dim = cfg.rows_extra_opacity < 100 ? ` style="opacity:${cfg.rows_extra_opacity / 100}"` : "";
    body = keys.map((k) => {
      const all = entries.filter((e) => e.class_key === k);
      if (!all.length) return "";
      const tail = extraDrivers(all, cfg);
      const list = tail.length ? all.slice(0, cfg.rows) : all.slice(0, cfg.rows + cfg.rows_last);
      const cls = classes.get(k) || DEFAULT_CLASS;
      return `<div class="block">${classHeaderHtml(cls, "", rerender)}${rows(list, cls)}${tail.length
        ? `<div class="srow skip"><span></span><span class="dots">• • •</span></div><div class="extra"${dim}>${rows(tail, cls)}</div>` : ""}</div>`;
    }).join("");
  } else {
    // More drivers than rows: the top of the order, then (if asked) a few more
    // after a small gap: the rest of the field a set at a time, or the last ones.
    const tail = extraDrivers(entries, cfg);
    const top = tail.length ? entries.slice(0, cfg.rows) : entries.slice(0, cfg.rows + cfg.rows_last);
    const dim = cfg.rows_extra_opacity < 100 ? ` style="opacity:${cfg.rows_extra_opacity / 100}"` : "";
    body = entries.length
      ? `<div class="block">${rows(top)}${tail.length ? `<div class="srow skip"><span></span><span class="dots">• • •</span></div><div class="extra"${dim}>${rows(tail)}</div>` : ""}</div>` : "";
  }
  const session = snap.session || {};
  const title = sessionTitle(snap, ov);
  const sub = headerSub(snap, cfg, false);
  const progress = progressText(ov);
  const sponsor = sponsorLogo(snap, cfg);
  // Hidden until someone qualifies for a row, unless "reveal" is on: then
  // the header shows from the start and drivers join as they cross the line.
  const visible = snap.connected && cfg.visible && (entries.length > 0 || cfg.reveal);
  // The header (with the column labels) is one panel; the drivers follow it,
  // joined on (overall) or as a separate panel per class, evenly spaced.
  const html = `<div class="head-box ${body ? "" : "alone"}"><div class="tower-head${goFlash(ov)}"><div class="head-text">
      <div class="h1"><span class="t1">${esc(title)}</span>${progress ? `<span class="t3 tnum">${esc(progress)}</span>` : ""}</div>
      ${sub ? `<div class="t2">${esc(sub)}</div>` : ""}
    </div></div>${sponsor ? '<div class="tower-sponsor-slot"></div>' : ""}${body ? headRowHtml(cfg, cols) : ""}</div>${body}`;
  tower.classList.toggle("by-class", classMode);
  tower.classList.toggle("wrap-title", !!cfg.title_wrap);
  tower.classList.toggle("hidden", !visible);
  setPanels(cfg);
  setSize(cfg);
  // Width: set by hand, or (0) fitted to what's in the columns.
  const auto = !cfg.width;
  const mode = JSON.stringify([auto, cfg.width, grid, cfg.title_wrap]);
  if (!auto) {
    tower.style.width = `${Math.max(MIN_TOWER, cfg.width)}px`;
    tower.style.setProperty("--grid", grid);
  }
  if (visible && (html !== shown || mode !== fitMode)) {
    shown = html;
    fitMode = mode;
    flipRows(tower, ".srow[data-key]", () => {
      tower.innerHTML = html;
      tower.appendChild(finRail);
      placeSponsor(sponsor, cfg);
      if (auto) autoFit(cfg, cols);
    });
  }
  placeSponsor(sponsor, cfg);
  placeFinishTabs(visible ? entries : [], cfg);
}

// -- full-screen board --------------------------------------------------------

const ROW_BUDGET = 850;  // px of the 1080 stage left for table rows under the header and column labels

// The header's session name: the one set for races / qualifying / practice
// (Overlays tab), else RACE, QUALIFYING or iRacing's name for the session.
function sessionTitle(snap, ov) {
  const session = snap.session || {};
  const cfg = ov.settings.standings;
  // A heat event's race: its league round's name (as set in the rounds), else the
  // name set for heats / the consolation / the feature, else iRacing's.
  if (session.round_title) return session.round_title;
  if (["heat", "consolation", "feature"].includes(session.kind)) {
    const named = String(cfg[`title_${session.kind}`] || "").trim();
    const number = (String(session.name || "").match(/\d+/) || [""])[0];
    if (named) return number && !/\d/.test(named) ? `${named} ${number}` : named;
    return String(session.name || session.kind).toUpperCase();
  }
  const own = { race: cfg.title_race, qualify: cfg.title_qualify }[ov.session_kind] ?? cfg.title_practice;
  if (own && own.trim()) return own.trim();
  return ov.session_kind === "race" ? "RACE" : ov.session_kind === "qualify" ? "QUALIFYING"
    : String(session.name || "PRACTICE").toUpperCase();
}

// The line under it: the series (the active league's name) and the track, each if wanted.
function headerSub(snap, cfg, withLayout) {
  const session = snap.session || {};
  const track = withLayout ? [session.track, session.track_config].filter(Boolean).join(" – ") : session.track;
  return [cfg.show_series && snap.league && snap.league.name, cfg.show_track && track].filter(Boolean).join(" · ");
}

function sessionClock(snap, ov) {
  const session = snap.session || {};
  if (ov.session_kind === "race") {
    const lead = Math.max(0, ...ov.standings.map((e) => e.lap || 0));
    const total = parseInt(session.laps, 10);
    return lead ? `LAP ${lead}${total ? ` / ${total}` : ""}` : String(session.state || "").toUpperCase();
  }
  return fmtClock(session.time);
}

function screenRow(e, cfg, cls, race, classMode, multiclass, camIdx, compact) {
  const pos = classMode ? e.class_pos : e.pos;
  const gap = classMode ? e.class_gap : e.gap;
  const interval = classMode ? e.class_interval : e.interval;
  const first = pos === 1;
  const change = race && e.pos_change ? `<span class="${e.pos_change > 0 ? "up" : "down"}">${e.pos_change > 0 ? "▲" : "▼"}${Math.abs(e.pos_change)}</span>` : "";
  // The team logo and the team name: columns of their own, in the order picked.
  const teamCells = screenTeamParts(cfg, compact).map((p) => (p === "logo"
    ? `<td class="lg c" data-opcol="logo">${e.team_logo ? `<img src="${esc(e.team_logo)}" alt="">` : ""}</td>`
    : `<td class="team" data-opcol="team">${esc(e.team || "")}</td>`)).join("");
  const cells = [
    `<td class="stripe" style="${stripeColor(e, cls, cfg) ? `background:${esc(stripeColor(e, cls, cfg))}` : "background:none"}"></td>`,
    `<td class="p r" data-opcol="pos">${pos}</td>`,
    race ? `<td class="c" data-opcol="pos_change">${change}</td>` : "",
    `<td class="c" data-opcol="number">${numberChip(e, cls, cfg)}</td>`,
    `<td data-opcol="name">${esc(formatName(e, cfg.name_format))}${fastestIcon(e, cfg, classMode)}${finishFlag(e, cfg)}${!e.in_world ? '<span class="pit">OUT</span>' : e.on_pit ? '<span class="pit">PIT</span>' : ""}</td>`,
    teamCells,
  ];
  const down = classMode ? e.class_laps_down : e.laps_down;
  const cell = {
    laps: () => `<td class="r muted">${(race ? e.laps_completed : e.lap) ?? ""}</td>`,
    gap: () => (race
      ? `<td class="r ${first ? "lead" : ""}">${first ? leaderText(e, cfg) : down ? `+${down} L` : gap != null ? `+${gap.toFixed(1)}` : ""}</td>`
      : `<td class="r">${first ? "" : gap != null ? `+${gap.toFixed(3)}` : ""}</td>`),
    interval: () => (first && race && cfg.interval_leader !== "blank"
      ? `<td class="r lead">${leaderText(e, cfg, cfg.interval_leader)}</td>`
      : `<td class="r muted">${!first && interval != null ? `+${interval.toFixed(race ? 1 : 3)}` : ""}</td>`),
    last_lap: () => `<td class="r muted">${fmtLap(e.last_lap)}</td>`,
    best_lap: () => (race ? `<td class="r">${fmtLap(e.best_lap)}</td>` : `<td class="r lead">${fmtLap(e.best)}</td>`),
    pits: () => `<td class="r muted">${e.pit_stops || ""}</td>`,
  };
  cells.push(...screenColumns(cfg, race, compact).map((k) => cell[k]().replace("<td", `<td data-opcol="${k}"`)));
  const moved = moveOf(e.car_idx);
  return `<tr class="${e.car_idx === camIdx ? "cam" : ""} ${moved ? moved.cls : ""}" data-key="${e.car_idx}" style="${moved ? moved.style : ""}">${cells.join("")}</tr>`;
}

// The full screen's columns after the driver and team, in the order picked
// (cfg.screen_column_order; "" = the usual order, which differs between races
// and qualifying). Last lap and pit stops are race only; split into narrow
// columns, the least needed go.
const SCREEN_LABELS = { laps: "Laps", gap: "Gap", interval: "Int", last_lap: "Last", best_lap: "Best", pits: "Pits" };

function screenColumns(cfg, race, compact) {
  const order = cfg.screen_column_order ? cfg.screen_column_order.split(",")
    : race ? ["laps", "gap", "interval", "last_lap", "best_lap", "pits"] : ["best_lap", "gap", "interval", "laps"];
  const keep = race ? (k) => !compact || (k !== "last_lap" && k !== "pits") : (k) => k !== "last_lap" && k !== "pits" && (!compact || k !== "laps");
  return order.filter((k) => SCREEN_LABELS[k] && keep(k));
}

// The full screen's team columns, in order: the logo (also when two tables
// share the screen) and the name (not then), each if switched on.
function screenTeamParts(cfg, compact) {
  const parts = [cfg.show_logo ? "logo" : null, cfg.show_team && !compact ? "team" : null].filter(Boolean);
  return cfg.team_logo_side === "last" ? parts.reverse() : parts;
}

function screenHead(cfg, race, compact) {
  const cols = [["", "stripe"], ["Pos", "r"], race ? ["", "c"] : null, ["#", "c"], ["Driver", ""],
    ...screenTeamParts(cfg, compact).map((p) => (p === "logo" ? ["", "lg"] : ["Team", ""]))];
  cols.push(...screenColumns(cfg, race, compact).map((k) => [SCREEN_LABELS[k], "r"]));
  const widths = { "": "", Pos: "70px", "#": "70px", Laps: "70px", Pits: "60px", Gap: "120px", Int: "110px", Last: "130px", Best: "130px" };
  return `<colgroup>${cols.filter(Boolean).map(([l, c]) => `<col style="width:${c === "stripe" ? "6px" : c === "lg" ? "64px" : c === "c" && !l ? "78px" : widths[l] || "auto"}">`).join("")}</colgroup>
    <thead><tr>${cols.filter(Boolean).map(([l, c]) => `<th class="${c === "stripe" ? "stripe" : c}">${l}</th>`).join("")}</tr></thead>`;
}

// A class header row spans exactly the table's columns: spanning more makes
// the browser share the width out with columns that aren't there.
function spanFor(cfg, race, compact) {
  return (screenHead(cfg, race, compact).match(/<col /g) || []).length;
}

function renderScreen(snap, ov) {
  const cfg = ov.settings.standings;
  const race = ov.session_kind === "race";
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const entries = ov.standings;
  const multiclass = new Set(entries.map((e) => e.class_key)).size > 1;
  const classMode = cfg.mode === "class";
  const camIdx = snap.camera && snap.camera.car_idx;
  notePlaces(entries, classMode);
  // Lines: class headers and drivers, in order.
  const lines = [];
  if (classMode) {
    const keys = towerClassKeys(cfg, snap);
    for (const k of keys) {
      const rows = entries.filter((e) => e.class_key === k);
      if (!rows.length) continue;
      lines.push({ head: classes.get(k) || DEFAULT_CLASS, n: rows.length });
      for (const e of rows) lines.push({ e });
    }
  } else {
    for (const e of entries) lines.push({ e });
  }
  // Up to 26 lines a column; more drivers than that go into two (or three)
  // narrower columns.
  const perCol = 26;
  const ncols = Math.min(3, Math.max(1, Math.ceil(lines.length / perCol)));
  const rowsPerCol = Math.ceil(lines.length / ncols);
  const compact = ncols > 1;
  const cols = [];
  for (let c = 0; c < ncols; c++) cols.push(lines.slice(c * rowsPerCol, (c + 1) * rowsPerCol));
  // Class header rows are a fixed 54px (their gap included, see overlay.css):
  // driver rows share what's left.
  const fill = (col) => col.reduce((n, l) => n + (l.head ? 0 : 1), 0);
  const heads = (col) => col.length - fill(col);
  const tallest = cols.reduce((a, col) => (fill(col) + heads(col) * 2 > fill(a) + heads(a) * 2 ? col : a), cols[0] || []);
  const rowH = Math.max(26, Math.min(44, Math.floor((ROW_BUDGET - heads(tallest) * 54) / Math.max(fill(tallest), 1))));
  const body = !snap.connected ? '<div class="screen-empty">Waiting for iRacing…</div>'
    : !entries.length ? `<div class="screen-empty">${race ? "Waiting for the race" : "No lap times yet"}</div>`
      : `<div class="screen-body">${cols.map((col) => `<div class="screen-col"><table class="screen-table ${cfg.show_col_labels ? "" : "no-labels"}">${screenHead(cfg, race, compact)}<tbody>${col.map((l) => l.head
        ? `<tr class="classrow"><td colspan="${spanFor(cfg, race, compact)}">${classHeaderHtml(l.head, `${l.n} cars`, rerender)}</td></tr>`
        : screenRow(l.e, cfg, classes.get(l.e.class_key) || DEFAULT_CLASS, race, classMode, multiclass, camIdx, compact)).join("")}</tbody></table></div>`).join("")}</div>`;
  const session = snap.session || {};
  const sub = headerSub(snap, cfg, true);
  const html = `<div class="screen-page" style="--row-h:${rowH}px;--row-font:${Math.round(rowH * 0.55)}px">
    <div class="screen-head${goFlash(ov)}"><div class="head-text"><span class="t1">${esc(snap.connected ? sessionTitle(snap, ov) : "STANDINGS")}</span><span class="t2">${esc(sub)}</span>
      <span class="t3">${snap.connected ? esc(progressText(ov) || sessionClock(snap, ov)) : ""}</span></div></div>
    ${body}</div>`;
  if (html !== shown) {
    shown = html;
    flipRows(screenRoot, "tr[data-key]", () => { screenRoot.innerHTML = html; });
  }
}

function rerender() {
  shown = "";
  render();
}

followSnapshots((snap) => {
  last = snap;
  render();
});
