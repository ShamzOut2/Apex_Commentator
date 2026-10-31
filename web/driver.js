"use strict";

// "Who's this": a small board at the bottom centre naming the driver the
// camera is on. It slides in each time the camera moves to someone (the last
// one slides away), and with "hide after" set, goes again after that long.

const stage = $("#stage");
const slot = $("#slot");
fitStage(stage);
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3" };
const OUT_MS = 400;
let current = null;  // {key, el, at, html, hidden}

function cardHtml(d, cfg, cls, multiclass) {
  const pos = cfg.show_position && d.pos
    ? `<div class="pos" style="color:${inkFor(cls.color)}"><span class="p">P${d.pos}</span>${multiclass && d.class_pos ? `<span class="cp">P${d.class_pos} ${esc(cls.name)}</span>` : ""}</div>` : "";
  const number = cfg.show_number && d.number
    ? `<span class="num" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(d.number)}</span>` : "";
  const team = cfg.show_team && d.team
    ? `<div class="team">${cfg.show_logo && d.team_logo ? `<img src="${esc(d.team_logo)}" alt="">` : ""}${esc(d.team)}</div>` : "";
  const klass = cfg.show_class && multiclass && cls.name ? `<span class="klass" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(cls.name)}</span>` : "";
  const make = cfg.show_make && d.make_logo ? `<span class="make"><img src="${esc(d.make_logo)}" alt="${esc(d.make)}"></span>` : "";
  return `${pos}<div class="who">${number}<div class="names"><div class="name">${esc(formatName(d, cfg.name_format))}${klass}</div>${team}</div></div>${make}`;
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
  const key = String(d.car_idx);
  if (!current || current.key !== key) {
    // The camera moved to someone: they slide in, whoever was there slides away.
    leave();
    const el = document.createElement("div");
    el.className = "card in";
    el.style.setProperty("--cls", cls.color);
    el.innerHTML = html;
    slot.appendChild(el);
    // Once it's in, updates (a new position) just swap the numbers.
    setTimeout(() => el.classList.remove("in"), 1300);
    current = { key, el, at: performance.now(), html, hidden: false };
    return;
  }
  // Same driver: new numbers (position) without animating again.
  if (html !== current.html && !current.hidden) {
    current.el.innerHTML = html;
    current.html = html;
  }
  current.el.style.setProperty("--cls", cls.color);
  // "Hide after": gone again once it's been up that long (back when the camera moves).
  if (cfg.hide_s > 0 && !current.hidden && performance.now() - current.at > cfg.hide_s * 1000) {
    current.hidden = true;
    slideOut(current.el);
  }
}

function leave() {
  if (!current) return;
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
