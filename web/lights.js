"use strict";

// Starting lights: up only as a race is about to start. The red lights come
// on one by one (iRacing's start lights, the leader's run to the line on the
// lap to the green, or the Count down hotkey), stay lit, and go out at the
// green: "LIGHTS OUT", then it goes.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
let box = null;
let shownKey = "";

function draw(l, cfg) {
  setPanels(cfg);
  setSize(cfg);
  const key = [cfg.place, l.lights, cfg.visible].join("|");
  if (!box || key !== shownKey) {
    leave();
    shownKey = key;
    const pods = Array.from({ length: l.lights }, () => '<div class="lt-pod"><span class="lt-lamp"></span><span class="lt-lamp"></span></div>').join("");
    stage.insertAdjacentHTML("beforeend", `<div class="lights panel-in ${esc(cfg.place)} ${cfg.visible ? "" : "hidden-preview"}">
      <div class="lt-row">${pods}</div>${cfg.show_text ? '<div class="lt-text"></div>' : ""}</div>`);
    box = stage.lastElementChild;
    const el = box;
    setTimeout(() => el.classList.remove("panel-in"), 500);
  }
  box.querySelectorAll(".lt-pod").forEach((pod, i) => pod.classList.toggle("on", !l.out && i < l.lit));
  box.classList.toggle("out", !!l.out);
  const text = box.querySelector(".lt-text");
  if (text) text.textContent = l.out ? "Lights out" : l.lit >= l.lights ? "" : "Get ready";
}

function leave() {
  if (!box) return;
  const old = box;
  box = null;
  shownKey = "";
  old.classList.remove("panel-in");
  old.classList.add("panel-out");
  setTimeout(() => old.remove(), 520);
}

// The preview, with no start on: a count over and over (a light a second, held, then out).
function demo(cfg) {
  const n = cfg.lights || 5;
  const t = (Date.now() / 1000) % (n + 6);
  return t < n + 2 ? { lit: Math.min(n, Math.floor(t)), lights: n, out: false } : { lit: 0, lights: n, out: true };
}

let last = null;
function render(snap) {
  const ov = snap.overlays;
  const cfg = ov && ov.settings && ov.settings.lights;
  if (!cfg) return;
  last = snap;
  const l = ov.lights;
  if (l && (cfg.visible || PREVIEW)) return draw(l, cfg);
  if (PREVIEW) return draw(demo(cfg), cfg);
  leave();
}

// The preview's count runs between snapshots too.
if (PREVIEW) setInterval(() => last && render(last), 100);
followSnapshots(render);
