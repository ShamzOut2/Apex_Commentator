"use strict";

// A driver's season: the driver on camera (or one picked in the app), their
// championship place and points, the points to the leader, wins, podiums,
// best finish and their last few results. It comes up for each new driver
// (and each time it's asked for again) and goes after the time set.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3" };
let shownKey = "";
let shownHtml = "";
let hideTimer = null;
let hiddenKey = "";  // shown for its time and gone: not again until the driver (or the pick) changes

const fmtPts = (v) => (v == null ? "–" : Number.isInteger(v) ? String(v) : v.toFixed(1));

function seasonHtml(d, cfg, cls) {
  const color = paintFor(d, cls, "main") || cls.color;
  const number = cfg.show_number && d.number
    ? `<span class="num" style="background:${esc(bgc(color))};color:${inkFor(color)}">${esc(d.number)}</span>` : "";
  const logo = cfg.show_logo && teamLogoOf(d, cfg) ? `<img class="logo" src="${esc(teamLogoOf(d, cfg))}" alt="">` : "";
  const s = d.season;
  const stat = (label, value) => `<div class="ss-stat"><span class="lbl">${label}</span><b>${value}</b></div>`;
  const stats = [];
  if (s) {
    // A championship the league doesn't score (overall in a class league, say): its finishes only.
    if (d.scored !== false) {
      stats.push(stat("Championship", s.pos ? `P${s.pos}` : "–"));
      if (cfg.show_points) stats.push(stat("Points", fmtPts(s.points)));
      if (cfg.show_behind && s.pos > 1 && s.behind) stats.push(stat("To the leader", `−${fmtPts(s.behind)}`));
    }
    if (cfg.show_wins) stats.push(stat("Wins", String(s.wins)));
    if (cfg.show_podiums) stats.push(stat("Podiums", String(s.podiums)));
    if (cfg.show_best) stats.push(stat("Best finish", s.best ? `P${s.best}` : "–"));
  }
  const form = s && cfg.show_form && cfg.form > 0 && s.form.length
    ? `<div class="ss-form"><span class="lbl">Last ${s.form.length === 1 ? "race" : `${s.form.length} races`}</span>${s.form.map((f) =>
      `<span class="ss-res ${f === "P1" ? "win" : /^P[23]$/.test(f) ? "podium" : /^P/.test(f) ? "" : "out"}">${esc(f)}</span>`).join("")}</div>` : "";
  const notes = cfg.show_notes && d.notes ? `<div class="ss-notes">${esc(d.notes)}</div>` : "";
  const empty = !s ? '<div class="ss-none">No championship results for them yet</div>' : "";
  return `<div class="ss-top">${number}${logo}<div class="ss-names"><span class="name">${nameHtml(d, cfg.name_format)}</span>
      ${cfg.show_team && d.team ? `<span class="team">${esc(d.team)}</span>` : ""}</div>
      ${d.championship ? `<span class="ss-champ">${esc(d.championship)}${d.scored === false ? " finishes" : ""}</span>` : ""}</div>
    ${stats.length ? `<div class="ss-stats">${stats.join("")}</div>` : ""}${form}${notes}${empty}`;
}

function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.season;
  if (!cfg) return;
  setPanels(cfg);
  setSize(cfg);
  const d = ov.season;
  const on = snap.connected && d && (cfg.visible || PREVIEW);
  if (!on) {
    leave();
    shownKey = hiddenKey = "";
    if (PREVIEW && !stage.querySelector(".bt-hint")) {
      stage.insertAdjacentHTML("beforeend", '<div class="bt-hint">Nothing to show yet: the driver on camera\'s season (with a league active)</div>');
    }
    return;
  }
  stage.querySelectorAll(".bt-hint").forEach((el) => el.remove());
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const cls = classes.get(d.class_key) || DEFAULT_CLASS;
  const html = seasonHtml(d, cfg, cls);
  const key = [d.car_idx, d.pick, cfg.place, cfg.visible].join("|");
  if (key === hiddenKey && !PREVIEW) return;  // its time's up: until another driver
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
  stage.insertAdjacentHTML("beforeend", `<div class="battle season panel-in ${esc(cfg.place)} ${cfg.visible ? "" : "hidden-preview"}" style="--grp:${esc(paintFor(d, cls, "main") || cls.color || "var(--accent)")}">${html}</div>`);
  const el = stage.lastElementChild;
  setTimeout(() => el.classList.remove("panel-in"), 1300);
  clearTimeout(hideTimer);
  if (cfg.hide_s > 0 && !PREVIEW) {
    hideTimer = setTimeout(() => {
      hiddenKey = key;
      shownKey = "";
      leave();
    }, cfg.hide_s * 1000);
  }
}

function leave() {
  for (const old of stage.querySelectorAll(".battle:not(.out)")) {
    old.classList.remove("panel-in");
    old.classList.add("out", "panel-out");
    setTimeout(() => old.remove(), 480);
  }
}

followSnapshots(render);
