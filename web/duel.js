"use strict";

// On-track battle: the car on camera and the cars just ahead and behind it,
// within the gap picked in the app ("Battle for P3"). With "auto" it comes up
// by itself when there's a battle and goes when it breaks up; otherwise it's
// shown and hidden by hand.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3" };
let shownKey = "";
let shownHtml = "";

function rowHtml(r, i, cfg, cls) {
  const color = paintFor(r, cls, "main") || cls.color;
  const number = cfg.show_number && r.number
    ? `<span class="num" style="${color ? `background:${esc(bgc(color))};color:${inkFor(color)}` : `background:${bgc("rgba(255,255,255,.14)")}`}">${esc(r.number)}</span>` : "";
  const logo = !cfg.show_logo ? "" : r.team_logo ? `<img class="logo" src="${esc(r.team_logo)}" alt="">` : '<span class="logo"></span>';
  const cells = [`<span class="pos">P${r.pos ?? "–"}</span>`,
    `<span class="who">${number}${logo}<span class="names"><span class="name">${esc(formatName(r, cfg.name_format))}</span>
      ${cfg.show_team && r.team ? `<span class="team">${esc(r.team)}</span>` : ""}</span></span>`];
  // The gap: to the car ahead of it, or to the driver on camera (− ahead of them, + behind).
  const toCam = cfg.gap_shown === "camera";
  const gap = toCam ? (r.cam ? null : r.to_cam) : (i ? r.interval : null);
  if (cfg.show_interval) cells.push(`<span class="int">${gap != null ? `${gap < 0 ? "−" : "+"}${secs(Math.abs(gap))}` : ""}</span>`);
  const close = gap != null && Math.abs(gap) <= cfg.gap_s;
  return `<div class="bt-row panel-row ${r.cam ? "cam" : ""} ${close ? "close" : ""}" style="--i:${i}" data-key="${r.car_idx}">${cells.join("")}</div>`;
}

function duelHtml(d, cfg, cls) {
  const grid = ["64px", "minmax(220px, 1fr)", cfg.show_interval && "80px"].filter(Boolean).join(" ");
  const title = cfg.title || `Battle for P${d.pos}`;
  const chip = d.multiclass && cls.name
    ? `<span class="chip" style="background:${esc(bgc(cls.color))};color:${inkFor(cls.color)}">${esc(cls.name)}</span>` : "";
  return `<div class="bt-head">${esc(title)} ${chip}</div>
    ${d.rows.map((r, i) => rowHtml(r, i, cfg, cls)).join("")}
    <style>.duel{--bt-cols:${grid}}</style>`;
}

function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.duel;
  if (!cfg) return;
  setPanels(cfg);
  setSize(cfg);
  const d = ov.duel;
  const has = d && d.rows && d.rows.length > 1;
  // Auto: up while there's a battle (and it's switched on); by hand: whenever it's on.
  const on = has && ((cfg.visible && (!cfg.auto || d.active)) || PREVIEW);
  if (!on) {
    leave();
    shownKey = "";
    if (PREVIEW && !stage.querySelector(".bt-hint")) {
      stage.insertAdjacentHTML("beforeend", '<div class="bt-hint">No battle around the car on camera right now (it shows during a race, cars within the gap set)</div>');
    }
    return;
  }
  stage.querySelectorAll(".bt-hint").forEach((el) => el.remove());
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const cls = classes.get(d.rows[0].class_key) || DEFAULT_CLASS;
  const html = duelHtml(d, cfg, cls);
  // The same cars: new gaps just swap in (places changing slide); new cars: in fresh.
  const key = [d.rows.map((r) => r.car_idx).sort().join(","), cfg.place, cfg.visible].join("|");
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
  stage.insertAdjacentHTML("beforeend", `<div class="battle duel panel-in ${esc(cfg.place)} ${cfg.visible ? "" : "hidden-preview"}" style="--grp:${esc(cls.color || "var(--accent)")}">${html}</div>`);
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
