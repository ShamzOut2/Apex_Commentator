"use strict";

// Championship battle: a few drivers picked in the app (Overlays tab), in one
// championship. Their place and points (during a race, as if it finished
// now), the points this race gives them, places gained or lost, and the
// points between them.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
let shownKey = "";
let shownHtml = "";

const pts = (x) => (x == null ? "" : Number.isInteger(x) ? String(x) : x.toFixed(1));

function rowHtml(r, i, b, cfg, cols) {
  const live = b.live;
  const change = live && cfg.show_change && r.pos_before ? r.pos_before - r.pos : 0;
  const gap = cfg.gap_to === "ahead" ? r.gap_ahead : r.gap_first;
  const cells = [`<span class="pos">${r.pos ? `P${r.pos}` : "–"}</span>`];
  if (cols.change) cells.push(`<span class="chg ${change > 0 ? "up" : change < 0 ? "down" : ""}">${change > 0 ? `▲${change}` : change < 0 ? `▼${-change}` : ""}</span>`);
  const number = cfg.show_number && r.number
    ? `<span class="num" style="${r.class_color ? `background:${esc(r.class_color)};color:${inkFor(r.class_color)}` : "background:rgba(255,255,255,.14)"}">${esc(r.number)}</span>` : "";
  // An empty space where a driver has no team logo, so the names line up.
  const logo = !cfg.show_logo ? "" : r.team_logo ? `<img class="logo" src="${esc(r.team_logo)}" alt="">` : '<span class="logo"></span>';
  cells.push(`<span class="who">${number}${logo}<span class="names"><span class="name">${esc(formatName(r, cfg.name_format))}</span>
    ${cfg.show_team && r.team ? `<span class="team">${esc(r.team)}</span>` : ""}</span></span>`);
  if (cols.race) cells.push(`<span class="race ${r.race_points ? "" : "zero"}">${r.race_points ? `+${pts(r.race_points)}` : "0"}</span>`);
  cells.push(`<span class="pts">${pts(r.points)}</span>`);
  cells.push(`<span class="gap">${i === 0 || gap == null ? "" : gap > 0 ? `−${pts(gap)}` : gap < 0 ? `+${pts(-gap)}` : "="}</span>`);
  return `<div class="bt-row panel-row ${i === 0 ? "first" : ""}" style="--i:${i}" data-key="${esc(r.driver)}">${cells.join("")}</div>`;
}

function battleHtml(b, cfg) {
  const cols = { change: b.live && cfg.show_change, race: b.live && cfg.show_race_points };
  const grid = ["64px", cols.change && "34px", "minmax(200px, 1fr)", cols.race && "64px", "70px", "70px"].filter(Boolean).join(" ");
  const labels = [["", ""], cols.change && ["", ""], ["Driver", ""], cols.race && ["Race", "r"], ["Pts", "r"],
    [cfg.gap_to === "ahead" ? "Ahead" : "Gap", "r"]].filter(Boolean)
    .map(([l, cls]) => `<span class="${cls}">${esc(l)}</span>`).join("");
  const title = cfg.title || "Championship";
  const chip = `<span class="chip" style="${b.color ? `background:${esc(b.color)};color:${inkFor(b.color)}` : "background:rgba(255,255,255,.14)"}">${esc(b.name)}</span>`;
  return `<div class="bt-head">${esc(title)} ${chip}${b.live ? '<span class="live">If it ended now</span>' : ""}</div>
    ${b.rows.length ? `<div class="bt-cols">${labels}</div>${b.rows.map((r, i) => rowHtml(r, i, b, cfg, cols)).join("")}`
      : '<div class="bt-empty">None of the drivers picked are in this championship.</div>'}
    <style>.battle{--bt-cols:${grid}}</style>`;
}

function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.battle;
  if (!cfg) return;
  setPanels(cfg);
  setSize(cfg);
  const b = ov.battle;
  const on = b && (cfg.visible || PREVIEW);
  if (!on) {
    leave();
    shownKey = "";
    if (PREVIEW && !stage.querySelector(".bt-hint")) {
      stage.insertAdjacentHTML("beforeend", '<div class="bt-hint">Pick drivers for the battle in the app\'s Overlays tab (it shows once the championship has standings)</div>');
    }
    return;
  }
  stage.querySelectorAll(".bt-hint").forEach((el) => el.remove());
  const html = battleHtml(b, cfg);
  // A new set of drivers (or championship) comes in fresh; new numbers just swap in.
  const key = [b.group, b.rows.map((r) => r.driver).sort().join(","), cfg.place, cfg.visible].join("|");
  const cur = stage.querySelector(".battle:not(.out)");
  if (key === shownKey && cur) {
    if (html !== shownHtml) {
      shownHtml = html;
      flipRows(cur, ".bt-row", () => { cur.innerHTML = html; });
    }
    return;
  }
  leave();
  shownKey = key;
  shownHtml = html;
  stage.insertAdjacentHTML("beforeend", `<div class="battle panel-in ${esc(cfg.place)} ${cfg.visible ? "" : "hidden-preview"}" style="--grp:${esc(b.color || "var(--accent)")}">${html}</div>`);
  // Once it's in, new numbers just swap in (no animating again).
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
