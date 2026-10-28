"use strict";

// Standings timing tower. Race: running order with gap to the leader.
// Qualifying and practice: fastest clean lap, and nobody until they set one.

const stage = $("#stage");
const tower = $("#tower");
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

function rerender() {
  shown = "";
  render();
}

followSnapshots((snap) => {
  last = snap;
  render();
});
