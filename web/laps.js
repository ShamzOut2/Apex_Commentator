"use strict";

// Qualifying lap tracker: one big tracker for the car on camera, and small
// ones along the bottom for the other cars on a timed lap. The server times
// the sectors and decides who's shown (a finished lap stays up for a few
// seconds, then goes); this page only draws it and runs the lap clock.

const stage = $("#stage");
const box = $("#trackers");
fitStage(stage);

const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3", logo: null };
const shown = new Map();   // car_idx -> { el, kind, received, item }
let snap = null;

function fmtSector(t) {
  return t == null ? "" : t >= 60 ? fmtLap(t) : t.toFixed(3);
}

function topHtml(item, cfg, cls, kind) {
  const lap = item.lap;
  // Small trackers use the team's short name when it has one.
  const teamName = kind === "small" && item.team_short ? item.team_short : item.team;
  const team = cfg.show_team && teamName ? `<span class="tm">${esc(teamName)}</span>` : "";
  let badge = "";
  if (!lap) badge = `<span class="badge info">${item.on_pit ? "IN PITS" : item.in_world ? "OUT LAP" : "NOT ON TRACK"}</span>`;
  else if (!lap.valid) badge = '<span class="badge">INVALID</span>';
  return `<span class="pos tnum">${item.pos ? `P${item.pos}` : ""}</span>
    ${cfg.show_number ? `<span class="num" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">#${esc(item.number)}</span>` : ""}
    ${cfg.show_logo && item.team_logo ? `<img class="team-logo" src="${esc(item.team_logo)}" alt="">` : ""}
    <span class="who"><span class="n">${esc(formatName(item, cfg.name_format))}</span>${team}</span>
    ${cfg.show_driver_number && item.driver_number ? `<span class="dn">${esc(item.driver_number)}</span>` : ""}
    ${badge}`;
}

function build(kind) {
  const el = document.createElement("div");
  el.className = `tracker ${kind}`;
  el.innerHTML = '<div class="tk-top"></div><div class="tk-body"><div class="sectors"></div><div class="timebox"><span class="lt tnum"></span><span class="dl tnum"></span><span class="pv tnum"></span></div></div>';
  return el;
}

function update(entry, item, cfg, classes, nsec) {
  const { el } = entry;
  const cls = classes.get(item.class_key) || DEFAULT_CLASS;
  const lap = item.lap;
  el.style.setProperty("--cls", cls.color);
  el.classList.toggle("invalid", !!lap && !lap.valid);
  const top = topHtml(item, cfg, cls, entry.kind);
  if (entry.top !== top) {
    entry.top = top;
    el.querySelector(".tk-top").innerHTML = top;
  }
  const sectorsEl = el.querySelector(".sectors");
  const sectors = lap ? lap.sectors : Array.from({ length: nsec }, () => ({ time: null, colour: null, done: 0 }));
  while (sectorsEl.children.length < sectors.length) {
    const s = document.createElement("div");
    s.className = "sector";
    s.innerHTML = '<div class="bar"><i></i></div><span class="st tnum"></span>';
    sectorsEl.appendChild(s);
  }
  while (sectorsEl.children.length > sectors.length) sectorsEl.lastChild.remove();
  sectors.forEach((s, i) => {
    const node = sectorsEl.children[i];
    const bar = node.querySelector("i");
    bar.className = s.colour || "";
    // A new lap empties the bars at once instead of sliding back.
    const width = `${Math.round(s.done * 1000) / 10}%`;
    if (s.done < parseFloat(bar.style.width || "0") - 1) bar.style.transition = "none";
    bar.style.width = width;
    if (bar.style.transition === "none") requestAnimationFrame(() => (bar.style.transition = ""));
    node.querySelector(".st").textContent = fmtSector(s.time);
  });
  const lt = el.querySelector(".lt");
  const dl = el.querySelector(".dl");
  lt.classList.toggle("done", !!lap && lap.state === "finished");
  if (lap && lap.state === "finished" && lap.delta != null && lap.valid) {
    dl.textContent = `${lap.delta > 0 ? "+" : lap.delta < 0 ? "−" : "±"}${Math.abs(lap.delta).toFixed(3)}`;
    dl.className = `dl tnum ${lap.delta <= 0 ? "faster" : "slower"}`;
  } else {
    dl.textContent = "";
    dl.className = "dl tnum";
  }
  const prev = lap ? lap.previous : null;
  el.querySelector(".pv").textContent = prev ? `PB ${fmtLap(prev)}` : "";
  entry.item = item;
  entry.received = performance.now();
}

function render() {
  const ov = snap && snap.overlays;
  if (!ov) return;
  const cfg = ov.settings.laps;
  const laps = ov.laps;
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const want = new Map();
  if (snap.connected && cfg.visible && laps.active) {
    if (laps.camera) want.set(laps.camera.car_idx, ["big", laps.camera]);
    for (const t of laps.trackers.slice(0, cfg.count)) want.set(t.car_idx, ["small", t]);
  }
  const smallCount = [...want.values()].filter(([k]) => k === "small").length;
  const room = 1840 - (want.size > smallCount ? 624 : 0);
  box.style.setProperty("--small-w", `${Math.min(300, Math.floor((room - 12 * Math.max(0, smallCount - 1)) / Math.max(1, smallCount)))}px`);
  for (const [idx, entry] of shown) {
    const w = want.get(idx);
    if (!w || w[0] !== entry.kind) {
      shown.delete(idx);
      entry.el.classList.add("gone");
      setTimeout(() => entry.el.remove(), 350);
    }
  }
  for (const [idx, [kind, item]] of want) {
    let entry = shown.get(idx);
    if (!entry) {
      entry = { el: build(kind), kind, top: "" };
      shown.set(idx, entry);
      box.appendChild(entry.el);
    }
    update(entry, item, cfg, classes, laps.sectors);
  }
  // Keep the small ones in the server's order (moving a node replays its
  // entrance animation, so only when the order changed).
  const order = laps.trackers.slice(0, cfg.count).map((t) => shown.get(t.car_idx)).filter((e) => e && e.kind === "small");
  const current = [...box.children].filter((el) => el.classList.contains("small") && !el.classList.contains("gone"));
  if (order.some((e, i) => current[i] !== e.el)) for (const e of order) box.appendChild(e.el);
}

// The lap clock runs here between snapshots.
function tick() {
  const now = performance.now();
  const speed = snap && snap.replay ? snap.replay.speed ?? 1 : 1;
  for (const entry of shown.values()) {
    const lap = entry.item && entry.item.lap;
    const lt = entry.el.querySelector(".lt");
    if (!lap) lt.textContent = "";
    else if (lap.state === "finished") lt.textContent = fmtLap(lap.lap_time);
    else lt.textContent = fmtLap(lap.elapsed + ((now - entry.received) / 1000) * speed).replace(/(\.\d)\d\d$/, "$1");
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

followSnapshots((s) => {
  snap = s;
  render();
});
