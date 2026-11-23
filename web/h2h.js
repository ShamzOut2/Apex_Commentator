"use strict";

// Head to head: two drivers picked in the app side by side: their seasons
// (championship place, points, wins, podiums, best finish, how often each
// finished ahead of the other) and, in a session, today's places and laps.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3" };
let shownKey = "";
let shownHtml = "";

const fmtPts = (v) => (v == null ? "–" : Number.isInteger(v) ? String(v) : v.toFixed(1));

function sideHtml(e, cfg, classes, side) {
  const cls = classes.get(e.class_key) || DEFAULT_CLASS;
  const color = paintFor(e, cls, "main") || cls.color;
  const number = cfg.show_number && e.number
    ? `<span class="num" style="background:${esc(bgc(color))};color:${inkFor(color)}">${esc(e.number)}</span>` : "";
  const logo = cfg.show_logo && teamLogoOf(e, cfg) ? `<img class="logo" src="${esc(teamLogoOf(e, cfg))}" alt="">` : "";
  return `<div class="hh-who ${side}">${side === "a" ? number + logo : ""}<span class="name">${nameHtml(e, cfg.name_format)}</span>${side === "b" ? logo + number : ""}</div>`;
}

// A row: the left driver's value, what it is, the right driver's; the better one lit.
function line(label, a, b, better = null) {
  const win = better === "a" ? ["best", ""] : better === "b" ? ["", "best"] : ["", ""];
  return `<div class="hh-row"><span class="v ${win[0]}">${a}</span><span class="lbl">${label}</span><span class="v ${win[1]}">${b}</span></div>`;
}
const lower = (x, y) => (x == null || y == null || x === y ? null : x < y ? "a" : "b");
const higher = (x, y) => (x == null || y == null || x === y ? null : x > y ? "a" : "b");

function h2hHtml(d, cfg, classes) {
  const [a, b] = d.drivers;
  const rows = [];
  const sa = a.season, sb = b.season;
  if (cfg.show_season && (sa || sb)) {
    rows.push(`<div class="hh-sec">${esc(d.championship || "Season")}</div>`);
    rows.push(line("Championship", sa && sa.pos ? `P${sa.pos}` : "–", sb && sb.pos ? `P${sb.pos}` : "–", lower(sa && sa.pos, sb && sb.pos)));
    rows.push(line("Points", fmtPts(sa && sa.points), fmtPts(sb && sb.points), higher(sa && sa.points, sb && sb.points)));
    rows.push(line("Wins", sa ? sa.wins : "–", sb ? sb.wins : "–", higher(sa && sa.wins, sb && sb.wins)));
    rows.push(line("Podiums", sa ? sa.podiums : "–", sb ? sb.podiums : "–", higher(sa && sa.podiums, sb && sb.podiums)));
    rows.push(line("Best finish", sa && sa.best ? `P${sa.best}` : "–", sb && sb.best ? `P${sb.best}` : "–", lower(sa && sa.best, sb && sb.best)));
    if (d.ahead) rows.push(line("Finished ahead", d.ahead[0], d.ahead[1], higher(d.ahead[0], d.ahead[1])));
  }
  const ta = a.today, tb = b.today;
  if (cfg.show_today && (ta || tb)) {
    rows.push('<div class="hh-sec">Today</div>');
    rows.push(line("Position", ta && ta.pos ? `P${ta.pos}` : "–", tb && tb.pos ? `P${tb.pos}` : "–", lower(ta && ta.pos, tb && tb.pos)));
    rows.push(line("Best lap", ta && ta.best_lap ? fmtLap(ta.best_lap) : "–", tb && tb.best_lap ? fmtLap(tb.best_lap) : "–", lower(ta && ta.best_lap, tb && tb.best_lap)));
    rows.push(line("Last lap", ta && ta.last_lap ? fmtLap(ta.last_lap) : "–", tb && tb.last_lap ? fmtLap(tb.last_lap) : "–", lower(ta && ta.last_lap, tb && tb.last_lap)));
    if (d.gap != null) rows.push(`<div class="hh-gap">Gap between them <b>${secs(Math.abs(d.gap))} s</b></div>`);
  }
  return `<div class="bt-head">${esc(cfg.title || "Head to head")}</div>
    <div class="hh-names">${sideHtml(a, cfg, classes, "a")}<span class="hh-vs">vs</span>${sideHtml(b, cfg, classes, "b")}</div>
    ${rows.join("")}`;
}

function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.h2h;
  if (!cfg) return;
  setPanels(cfg);
  setSize(cfg);
  const d = ov.h2h;
  const on = snap.connected && d && d.drivers && d.drivers.length === 2 && (cfg.visible || PREVIEW);
  if (!on) {
    leave();
    shownKey = "";
    if (PREVIEW && !stage.querySelector(".bt-hint")) {
      stage.insertAdjacentHTML("beforeend", '<div class="bt-hint">Pick the two drivers on the Widgets tab (Head to head)</div>');
    }
    return;
  }
  stage.querySelectorAll(".bt-hint").forEach((el) => el.remove());
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const html = h2hHtml(d, cfg, classes);
  const key = [d.drivers.map((x) => x.driver).join(","), cfg.place, cfg.visible].join("|");
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
  stage.insertAdjacentHTML("beforeend", `<div class="battle h2h panel-in ${esc(cfg.place)} ${cfg.visible ? "" : "hidden-preview"}" style="--grp:${esc(d.color || "var(--accent)")}">${html}</div>`);
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
