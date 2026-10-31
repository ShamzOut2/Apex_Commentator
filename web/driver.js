"use strict";

// "Who's this": a small board at the bottom centre naming the driver the
// camera is on. It slides in each time the camera moves to someone, or the
// same driver is picked again in the app (the last card slides away, and its
// timer goes with it), and stays up for the time set (hide_s), or for as long
// as they're on camera (stay).

const stage = $("#stage");
const slot = $("#slot");
fitStage(stage);
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3" };
const OUT_MS = 680;  // the leaving animation (driver.css .card.out)
let current = null;  // {key, el, at, html, hidden, timer, hideMs}

// The position box: overall (P3), in class (P1 and the class under it), or
// both (P3, and P1 GT3 under it).
function positionHtml(d, cfg, cls) {
  const which = cfg.position_shown || "overall";
  const name = cfg.pos_class_name !== false && cls.name ? esc(cls.name) : "";  // the class's name, unless turned off
  if (which === "class" && d.class_pos) return `<span class="p">P${d.class_pos}</span>${name ? `<span class="cp">${name}</span>` : ""}`;
  if (which === "both" && d.class_pos) return `<span class="p">P${d.pos}</span><span class="cp">P${d.class_pos}${name ? ` ${name}` : ""}</span>`;
  return `<span class="p">P${d.pos}</span>`;
}

function cardHtml(d, cfg, cls, multiclass) {
  // Their class colour (main or secondary, as set), or none: no background, white text.
  const color = paintFor(d, cls, cfg.class_colors);
  const pos = cfg.show_position && d.pos
    ? `<div class="pos" style="color:${color ? inkFor(color) : "#fff"}">${positionHtml(d, cfg, cls)}</div>` : "";
  const number = cfg.show_number && d.number
    ? (color ? `<span class="num" style="background:${esc(color)};color:${inkFor(color)}">${esc(d.number)}</span>` : `<span class="num plain">${esc(d.number)}</span>`) : "";
  // Under the driver's name: the team name, with the team logo before or
  // after it, and the car badge at the end of the card. Swapped ("end"):
  // the car badge takes the logo's place by the team name, and the team logo
  // goes to the end.
  const swapped = cfg.team_place === "end";
  const teamLogo = cfg.show_logo && d.team_logo ? `<img class="team-logo" src="${esc(d.team_logo)}" alt="">` : "";
  const badge = (small) => (cfg.show_make && d.make_logo
    ? `<span class="make ${small ? "small" : ""}"><img src="${esc(d.make_logo)}" alt="${esc(d.make)}"></span>` : "");
  const byName = swapped ? badge(true) : teamLogo;
  const teamName = cfg.show_team && d.team ? `<span class="team-name">${esc(d.team)}</span>` : "";
  const team = teamName || byName
    ? `<div class="team">${cfg.team_logo_side === "last" ? teamName + byName : byName + teamName}</div>` : "";
  const klass = cfg.show_class && multiclass && cls.name && paintFor(d, cls, "main") ? `<span class="klass" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(cls.name)}</span>` : "";
  const end = swapped ? (teamLogo ? `<span class="team-end">${teamLogo}</span>` : "") : badge(false);
  const under = team;
  return `${pos}<div class="who">${number}<div class="names"><div class="name">${esc(formatName(d, cfg.name_format))}${klass}</div>${under}</div></div>${end}`;
}

function render(snap) {
  const ov = snap.overlays;
  if (!ov || !ov.settings.driver) return;
  const cfg = ov.settings.driver;
  setPanels(cfg);
  setSize(cfg);
  const d = snap.connected && cfg.visible ? ov.driver : null;
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const multiclass = (snap.classes || []).length > 1;
  if (!d) return leave();
  const cls = classes.get(d.class_key) || DEFAULT_CLASS;
  const html = cardHtml(d, cfg, cls, multiclass);
  const key = `${d.car_idx}:${d.pick || 0}`;
  if (!current || current.key !== key) {
    // The camera moved to someone: they slide in, whoever was there slides away.
    leave();
    const el = document.createElement("div");
    el.className = "card in";
    el.style.setProperty("--cls", paintFor(d, cls, cfg.class_colors) || "transparent");
    el.innerHTML = html;
    slot.appendChild(el);
    // Once it's in, updates (a new position) just swap the numbers.
    setTimeout(() => el.classList.remove("in"), 1300);
    current = { key, el, at: performance.now(), html, hidden: false, timer: null, hideMs: null };
    schedule(cfg);
    return;
  }
  // Same driver: new numbers (position) without animating again.
  if (html !== current.html && !current.hidden) {
    current.el.innerHTML = html;
    current.html = html;
  }
  current.el.style.setProperty("--cls", paintFor(d, cls, cfg.class_colors) || "transparent");
  schedule(cfg);  // the time may have been changed while it's up
}

// Its own timer, so it goes on time even when nothing else changes (iRacing
// paused, say): hide_s after it came in, unless it stays while they're on camera.
function schedule(cfg) {
  const hideMs = cfg.stay || !(cfg.hide_s > 0) ? null : cfg.hide_s * 1000;
  if (!current || current.hidden || hideMs === current.hideMs) return;
  clearTimeout(current.timer);
  current.hideMs = hideMs;
  if (hideMs == null) return;
  const card = current;
  card.timer = setTimeout(() => {
    if (current !== card || card.hidden) return;
    card.hidden = true;
    slideOut(card.el);
  }, Math.max(0, card.at + hideMs - performance.now()));
}

function leave() {
  if (!current) return;
  clearTimeout(current.timer);
  if (!current.hidden) slideOut(current.el);
  else current.el.remove();
  current = null;
}

function slideOut(el) {
  el.classList.remove("in");
  el.classList.add("out");
  setTimeout(() => el.remove(), OUT_MS);
}

followSnapshots(render);
