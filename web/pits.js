"use strict";

// Pit stops: a card for each car in the pit lane (or just the car on camera),
// with its time since it crossed the pit lane entry line and its time in its
// pit box, ticking; after the exit line it shows the final times for a few
// seconds. The clocks are the app's (the sim's session time); between
// updates they run on here, at the replay's speed.

const stage = $("#stage");
const stack = $("#stack");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3" };
let stops = [];       // the latest stops, with when they arrived (performance.now())
let speed = 1;
let shownKey = "";

const fmt = (s) => (s == null ? "—" : s >= 60 ? `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}` : s.toFixed(1));
const keyOf = (s) => `${s.car_idx}:${s.entry}`;

function cardHtml(s, cfg, cls) {
  const color = paintFor(s, cls, cfg.class_colors);
  const number = cfg.show_number && s.number
    ? (color ? `<span class="num" style="background:${esc(color)};color:${inkFor(color)}">${esc(s.number)}</span>` : `<span class="num plain">${esc(s.number)}</span>`) : "";
  const logo = cfg.show_logo && s.team_logo ? `<img class="logo" src="${esc(s.team_logo)}" alt="">` : "";
  return `<div class="pit-who">${cfg.show_position && s.pos ? `<span class="pos">P${s.pos}</span>` : ""}${number}
      <span class="names"><span class="name">${esc(formatName(s, cfg.name_format))}</span>${cfg.show_team && s.team ? `<span class="team">${esc(s.team)}</span>` : ""}</span>
      ${logo}<span class="pit-tag ${s.out ? "out" : ""}" data-tag>${s.out ? "OUT" : s.in_box ? "STOPPED" : "PIT LANE"}</span></div>
    <div class="pit-times">
      <div class="pit-time lane" data-t="lane"><span class="lbl">PIT LANE</span><span class="val"></span></div>
      <div class="pit-time box" data-t="box"><span class="lbl">IN BOX</span><span class="val"></span></div>
    </div>`;
}

function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.pits;
  if (!cfg) return;
  setPanels(cfg);
  setSize(cfg);
  const p = ov.pits || { stops: [], speed: 1 };
  const at = performance.now();
  speed = p.speed ?? 1;
  stops = snap.connected && cfg.visible ? p.stops.map((s) => ({ ...s, at })) : [];
  stack.className = `pits ${cfg.place}`;
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  stage.querySelectorAll(".pit-hint").forEach((el) => el.remove());
  if (PREVIEW && !stops.length) stage.insertAdjacentHTML("beforeend", '<div class="pit-hint">A card shows here when a car comes into the pit lane</div>');
  // Cards: new ones slide in, finished ones slide out, the rest just update.
  const want = new Map(stops.map((s) => [keyOf(s), s]));
  for (const el of stack.querySelectorAll(".pit-card:not(.leaving)")) {
    if (!want.has(el.dataset.key)) {
      el.classList.add("leaving");
      setTimeout(() => el.remove(), 380);
    }
  }
  for (const s of stops) {
    const cls = classes.get(s.class_key) || DEFAULT_CLASS;
    const html = cardHtml(s, cfg, cls);
    let el = stack.querySelector(`.pit-card[data-key="${keyOf(s)}"]:not(.leaving)`);
    if (!el) {
      el = document.createElement("div");
      el.className = "pit-card";
      el.dataset.key = keyOf(s);
      stack.appendChild(el);
    }
    el.style.setProperty("--cls", paintFor(s, cls, cfg.class_colors) || "transparent");
    if (el.dataset.html !== html) {
      el.dataset.html = html;
      el.innerHTML = html;
    }
  }
  // In the stops' order (the car on camera first).
  const key = stops.map(keyOf).join(",");
  if (key !== shownKey) {
    shownKey = key;
    for (const s of stops) {
      const el = stack.querySelector(`.pit-card[data-key="${keyOf(s)}"]:not(.leaving)`);
      if (el) stack.appendChild(el);
    }
  }
  tick();
}

// The clocks, every frame: the last times sent, plus the time since (at the replay's speed).
function tick() {
  const now = performance.now();
  for (const s of stops) {
    const el = stack.querySelector(`.pit-card[data-key="${keyOf(s)}"]:not(.leaving)`);
    if (!el) continue;
    const since = Math.max(0, (now - s.at) / 1000) * speed;
    const lane = s.lane_s + (s.out ? 0 : since);
    const box = s.box_s == null ? null : s.box_s + (s.in_box ? since : 0);
    const laneEl = el.querySelector('[data-t="lane"]');
    const boxEl = el.querySelector('[data-t="box"]');
    laneEl.querySelector(".val").textContent = fmt(lane);
    boxEl.querySelector(".val").textContent = fmt(box);
    laneEl.classList.toggle("live", !s.out);
    laneEl.classList.toggle("done", s.out);
    boxEl.classList.toggle("live", s.in_box);
    boxEl.classList.toggle("done", !s.in_box && box != null);
  }
}

(function loop() {
  tick();
  requestAnimationFrame(loop);
}());

followSnapshots(render);
