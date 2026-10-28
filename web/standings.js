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

const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3", logo: null };

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
  ["show_gap", "92px", "Gap", (e, race, classMode) => {
    const gap = classMode ? e.class_gap : e.gap;
    const first = classMode ? e.class_pos === 1 : e.pos === 1;
    if (!race && e.best == null) return '<span class="dim">No time</span>';
    if (first) return `<span class="lead">${race ? "Leader" : fmtLap(e.best)}</span>`;
    return gap != null ? `+${race ? gap.toFixed(1) : gap.toFixed(3)}` : "";
  }],
  ["show_interval", "80px", "Int", (e, race, classMode) => {
    const interval = classMode ? e.class_interval : e.interval;
    const first = classMode ? e.class_pos === 1 : e.pos === 1;
    return !first && interval != null ? `+${race ? interval.toFixed(1) : interval.toFixed(3)}` : "";
  }],
];

function columnsFor(cfg, race) {
  return COLUMNS.filter(([key, , , , when]) => cfg[key] && (!when || when(race)));
}

function gridFor(cfg, cols) {
  return ["40px", "6px", cfg.show_number ? "50px" : null, cfg.show_logo ? "30px" : null, "minmax(150px, 1fr)",
    ...cols.map((c) => c[1])].filter(Boolean).join(" ");
}

function rowHtml(e, cfg, cols, cls, race, classMode, multiclass, camIdx) {
  const pos = classMode ? e.class_pos : e.pos;
  const team = cfg.show_team && e.team ? `<span class="tm">${esc(e.team)}</span>` : "";
  const pill = !classMode && multiclass && cfg.show_class_pos
    ? `<span class="cp" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(cls.name)} ${e.class_pos}</span>` : "";
  const pit = cfg.show_pit_status && e.on_pit ? '<span class="pitb">PIT</span>' : "";
  return `<div class="srow ${e.car_idx === camIdx ? "cam" : ""}">
    <span class="p tnum">${pos}</span>
    <span class="stripe" style="background:${esc((classMode || !multiclass) && e.team_color ? e.team_color : cls.color)}"></span>
    ${cfg.show_number ? `<span><span class="num" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(e.number)}</span></span>` : ""}
    ${cfg.show_logo ? `<span>${e.team_logo ? `<img class="team-logo" src="${esc(e.team_logo)}" alt="">` : ""}</span>` : ""}
    <span class="who"><span class="n">${pill}${esc(formatName(e, cfg.name_format))}${pit}</span>${team}</span>
    ${cols.map((c) => `<span class="c tnum">${c[3](e, race, classMode)}</span>`).join("")}
  </div>`;
}

// "LAP 5 / 20", "12:34 LEFT", "FINAL LAP", "FINISHED": whatever the
// session is limited by (or what the commentator picked).
function progressText(ov) {
  const pr = ov.progress;
  if (!pr || pr.mode === "none") return "";
  if (pr.finished) return "FINISHED";
  if (pr.mode === "laps") {
    if (!pr.lap) return pr.laps_total ? `${pr.laps_total} LAPS` : "";
    if (pr.laps_total && pr.lap >= pr.laps_total) return "FINAL LAP";
    return `LAP ${pr.lap}${pr.laps_total ? ` / ${pr.laps_total}` : ""}`;
  }
  if (pr.time_remain == null) return "";
  return `${fmtClock(pr.time_remain)} LEFT`;
}

function headRowHtml(cfg, cols) {
  if (!cols.length) return "";
  return `<div class="srow shead" style="grid-template-columns:${gridFor(cfg, cols)}">
    <span></span><span></span>${cfg.show_number ? "<span></span>" : ""}${cfg.show_logo ? "<span></span>" : ""}<span></span>
    ${cols.map((c) => `<span class="c">${c[2]}</span>`).join("")}</div>`;
}

function render() {
  const snap = last;
  const ov = snap && snap.overlays;
  if (!ov) return;
  if (SCREEN) return renderScreen(snap, ov);
  const cfg = ov.settings.standings;
  const race = ov.session_kind === "race";
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const entries = ov.standings;
  const multiclass = new Set(entries.map((e) => e.class_key)).size > 1;
  const classMode = cfg.mode === "class";
  const camIdx = snap.camera && snap.camera.car_idx;
  const cols = columnsFor(cfg, race);
  const grid = gridFor(cfg, cols);
  const rows = (list, cls) => list.map((e) => rowHtml(e, cfg, cols, cls || classes.get(e.class_key) || DEFAULT_CLASS,
    race, classMode, multiclass, camIdx)).join("");
  let body;
  if (classMode) {
    const keys = cfg.class_key ? [cfg.class_key] : (snap.classes || []).map((c) => c.key);
    body = keys.map((k) => {
      const list = entries.filter((e) => e.class_key === k).slice(0, cfg.rows);
      if (!list.length) return "";
      const cls = classes.get(k) || DEFAULT_CLASS;
      return `<div class="block">${classHeaderHtml(cls, "", rerender)}${rows(list, cls)}</div>`;
    }).join("");
  } else {
    body = entries.length ? `<div class="block">${rows(entries.slice(0, cfg.rows))}</div>` : "";
  }
  const session = snap.session || {};
  const title = race ? "RACE" : ov.session_kind === "qualify" ? "QUALIFYING" : String(session.name || "PRACTICE").toUpperCase();
  const sub = [snap.league && snap.league.name, session.track].filter(Boolean).join(" · ");
  const progress = progressText(ov);
  // Hidden until someone qualifies for a row, unless "reveal" is on: then
  // the header shows from the start and drivers join as they cross the line.
  const visible = snap.connected && cfg.visible && (entries.length > 0 || cfg.reveal);
  const width = 430 + cols.reduce((n, c) => n + parseInt(c[1], 10) + 8, 0) - (cols.length ? 60 : 0);
  const html = `<div class="tower-head ${body ? "" : "alone"}">
      <div class="h1"><span class="t1">${esc(title)}</span>${progress ? `<span class="t3 tnum">${esc(progress)}</span>` : ""}</div>
      ${sub ? `<div class="t2">${esc(sub)}</div>` : ""}
    </div>${body ? headRowHtml(cfg, cols) : ""}${body}`;
  tower.classList.toggle("hidden", !visible);
  tower.style.width = `${width}px`;
  tower.style.setProperty("--grid", grid);
  if (visible && html !== shown) {
    shown = html;
    tower.innerHTML = html;
  }
}

// -- full-screen board --------------------------------------------------------

const ROW_BUDGET = 900;  // px of the 1080 stage for table rows

function sessionTitle(snap, ov) {
  const session = snap.session || {};
  return ov.session_kind === "race" ? "RACE" : ov.session_kind === "qualify" ? "QUALIFYING"
    : String(session.name || "PRACTICE").toUpperCase();
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
  const pill = !classMode && multiclass ? `<span class="cpill" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(cls.name)} ${e.class_pos}</span>` : "";
  const team = e.team ? `${cfg.show_logo && e.team_logo ? `<img src="${esc(e.team_logo)}" alt="">` : ""}${esc(e.team)}` : "";
  const cells = [
    `<td class="stripe" style="background:${esc(classMode && e.team_color ? e.team_color : cls.color)}"></td>`,
    `<td class="p r">${pos}</td>`,
    race ? `<td class="c">${change}</td>` : "",
    `<td class="c"><span class="num" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(e.number)}</span></td>`,
    `<td>${pill}${esc(formatName(e, cfg.name_format))}${!e.in_world ? '<span class="pit">OUT</span>' : e.on_pit ? '<span class="pit">PIT</span>' : ""}</td>`,
    compact ? "" : `<td class="team">${team}</td>`,
  ];
  if (race) {
    cells.push(
      `<td class="r muted">${e.lap ?? ""}</td>`,
      `<td class="r ${first ? "lead" : ""}">${first ? "Leader" : gap != null ? `+${gap.toFixed(1)}` : ""}</td>`,
      `<td class="r muted">${!first && interval != null ? `+${interval.toFixed(1)}` : ""}</td>`,
      compact ? "" : `<td class="r muted">${fmtLap(e.last_lap)}</td>`,
      `<td class="r">${fmtLap(e.best_lap)}</td>`,
      compact ? "" : `<td class="r muted">${e.pit_stops || ""}</td>`,
    );
  } else {
    cells.push(
      `<td class="r lead">${fmtLap(e.best)}</td>`,
      `<td class="r">${first ? "" : gap != null ? `+${gap.toFixed(3)}` : ""}</td>`,
      `<td class="r muted">${!first && interval != null ? `+${interval.toFixed(3)}` : ""}</td>`,
      compact ? "" : `<td class="r muted">${e.lap ?? ""}</td>`,
    );
  }
  return `<tr class="${e.car_idx === camIdx ? "cam" : ""}">${cells.join("")}</tr>`;
}

function screenHead(race, compact) {
  const cols = [["", "stripe"], ["Pos", "r"], race ? ["", "c"] : null, ["#", "c"], ["Driver", ""], compact ? null : ["Team", ""]];
  if (race) cols.push(["Laps", "r"], ["Gap", "r"], ["Int", "r"], compact ? null : ["Last", "r"], ["Best", "r"], compact ? null : ["Pits", "r"]);
  else cols.push(["Best", "r"], ["Gap", "r"], ["Int", "r"], compact ? null : ["Laps", "r"]);
  const widths = { "": "", Pos: "70px", "#": "70px", Laps: "70px", Pits: "60px", Gap: "120px", Int: "110px", Last: "130px", Best: "130px" };
  return `<colgroup>${cols.filter(Boolean).map(([l, c]) => `<col style="width:${c === "stripe" ? "6px" : c === "c" && !l ? "60px" : widths[l] || "auto"}">`).join("")}</colgroup>
    <thead><tr>${cols.filter(Boolean).map(([l, c]) => `<th class="${c === "stripe" ? "stripe" : c}">${l}</th>`).join("")}</tr></thead>`;
}

function renderScreen(snap, ov) {
  const cfg = ov.settings.standings;
  const race = ov.session_kind === "race";
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const entries = ov.standings;
  const multiclass = new Set(entries.map((e) => e.class_key)).size > 1;
  const classMode = cfg.mode === "class";
  const camIdx = snap.camera && snap.camera.car_idx;
  // Lines: class headers and drivers, in order.
  const lines = [];
  if (classMode) {
    const keys = cfg.class_key ? [cfg.class_key] : (snap.classes || []).map((c) => c.key);
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
  const rowH = Math.max(26, Math.min(44, Math.floor(ROW_BUDGET / Math.max(rowsPerCol, 1))));
  const compact = ncols > 1;
  const cols = [];
  for (let c = 0; c < ncols; c++) cols.push(lines.slice(c * rowsPerCol, (c + 1) * rowsPerCol));
  const body = !snap.connected ? '<div class="screen-empty">Waiting for iRacing…</div>'
    : !entries.length ? `<div class="screen-empty">${race ? "Waiting for the race" : "No lap times yet"}</div>`
      : `<div class="screen-body">${cols.map((col) => `<div class="screen-col"><table class="screen-table">${screenHead(race, compact)}<tbody>${col.map((l) => l.head
        ? `<tr class="classrow"><td colspan="20">${classHeaderHtml(l.head, `${l.n} cars`, rerender)}</td></tr>`
        : screenRow(l.e, cfg, classes.get(l.e.class_key) || DEFAULT_CLASS, race, classMode, multiclass, camIdx, compact)).join("")}</tbody></table></div>`).join("")}</div>`;
  const session = snap.session || {};
  const sub = [snap.league && snap.league.name, [session.track, session.track_config].filter(Boolean).join(" – ")].filter(Boolean).join(" · ");
  const html = `<div class="screen-page" style="--row-h:${rowH}px;--row-font:${Math.round(rowH * 0.55)}px">
    <div class="screen-head"><span class="t1">${esc(snap.connected ? sessionTitle(snap, ov) : "STANDINGS")}</span><span class="t2">${esc(sub)}</span>
      <span class="t3">${snap.connected ? esc(progressText(ov) || sessionClock(snap, ov)) : ""}</span></div>
    ${body}</div>`;
  if (html !== shown) {
    shown = html;
    stage.innerHTML = html;
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
