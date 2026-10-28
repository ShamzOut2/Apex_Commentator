"use strict";

// Standings timing tower. Race: running order with gap to the leader.
// Qualifying and practice: fastest clean lap, and nobody until they set one.

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

function timeText(e, race, classMode) {
  const gap = classMode ? e.class_gap : e.gap;
  const first = classMode ? e.class_pos === 1 : e.pos === 1;
  if (race) return first ? ["Leader", true] : [gap != null ? `+${gap.toFixed(1)}` : "", false];
  return first ? [fmtLap(e.best), true] : [gap != null ? `+${gap.toFixed(3)}` : "", false];
}

function rowHtml(e, cfg, cls, race, classMode, multiclass, camIdx) {
  const [t, lead] = cfg.show_gap ? timeText(e, race, classMode) : ["", false];
  const pos = classMode ? e.class_pos : e.pos;
  const change = race && e.pos_change ? (e.pos_change > 0 ? "up" : "down") : "";
  const team = cfg.show_team && e.team ? `<span class="tm">${esc(e.team)}</span>` : "";
  return `<div class="srow ${e.car_idx === camIdx ? "cam" : ""} ${e.on_pit ? "pit" : ""} ${change}">
    <span class="p tnum">${pos}</span>
    <span class="stripe" style="background:${esc((classMode || !multiclass) && e.team_color ? e.team_color : cls.color)}"></span>
    <span>${cfg.show_number ? `<span class="num" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(e.number)}</span>` : ""}</span>
    <span>${cfg.show_logo && e.team_logo ? `<img class="team-logo" src="${esc(e.team_logo)}" alt="">` : ""}</span>
    <span class="who"><span class="n">${esc(formatName(e, cfg.name_format))}</span>${team}</span>
    <span class="t tnum ${lead ? "lead" : ""}">${!classMode && multiclass ? `<span class="cp">P${e.class_pos}</span>` : ""}${esc(t)}</span>
  </div>`;
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
  let body;
  if (classMode) {
    const keys = cfg.class_key ? [cfg.class_key] : (snap.classes || []).map((c) => c.key);
    body = keys.map((k) => {
      const rows = entries.filter((e) => e.class_key === k).slice(0, cfg.rows);
      if (!rows.length) return "";
      const cls = classes.get(k) || DEFAULT_CLASS;
      return `<div class="block">${classHeaderHtml(cls, "", rerender)}${rows.map((e) => rowHtml(e, cfg, cls, race, true, multiclass, camIdx)).join("")}</div>`;
    }).join("");
  } else {
    body = `<div class="block">${entries.slice(0, cfg.rows).map((e) => rowHtml(e, cfg, classes.get(e.class_key) || DEFAULT_CLASS, race, false, multiclass, camIdx)).join("")}</div>`;
  }
  const session = snap.session || {};
  const title = race ? "RACE" : ov.session_kind === "qualify" ? "QUALIFYING" : String(session.name || "PRACTICE").toUpperCase();
  const sub = [snap.league && snap.league.name, session.track].filter(Boolean).join(" · ");
  // Blank until someone has a time (qualifying), or when hidden.
  const visible = snap.connected && cfg.visible && entries.length > 0;
  const html = `<div class="tower-head"><span class="t1">${esc(title)}</span><span class="t2">${esc(sub)}</span></div>${body}`;
  tower.classList.toggle("hidden", !visible);
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
      <span class="t3">${snap.connected ? esc(sessionClock(snap, ov)) : ""}</span></div>
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
