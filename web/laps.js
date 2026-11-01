"use strict";

// Qualifying lap tracker: one big tracker for the car on camera, and small
// ones along the bottom for the other cars on a timed lap. The server times
// the sectors and decides who's shown (a finished lap stays up for a few
// seconds, then goes); this page only draws it and runs the lap clock.

const stage = $("#stage");
const box = $("#trackers");
box.innerHTML = '<div class="big-slot"></div><div class="small-slot"></div>';
const bigSlot = box.querySelector(".big-slot");
const smallSlot = box.querySelector(".small-slot");
const SMALL_MIN_W = 300;   // narrower than this and a tracker gets hard to read
const SMALL_MAX_W = 360;
// ?screen=1: full-screen live timing for every driver, to show on its own.
const SCREEN = new URLSearchParams(location.search).has("screen");
if (SCREEN) document.body.classList.add("screen");
fitStage(stage);

const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3", logo: null };
const shown = new Map();   // car_idx -> { el, kind, received, item }
let snap = null;

function fmtSector(t) {
  return t == null ? "" : t >= 60 ? fmtLap(t) : t.toFixed(3);
}

// A sector against what it was compared with: −0.324 (faster), +0.512 (slower).
const fmtGain = (d) => `${d < 0 ? "−" : d > 0 ? "+" : "±"}${Math.abs(d).toFixed(3)}`;

// A sector just done shows its difference first (sector_delta_s seconds, fading
// in and out), then its time.
const deltaFor = (s, cfg) => {
  const hold = cfg.sector_delta_s ?? 3;
  return hold > 0 && s.time != null && s.delta != null && s.age != null && s.age < hold ? hold : 0;
};

// An invalidated lap's colours (the lap tracker's settings).
function setInvalidColours(cfg) {
  const st = document.body.style;
  st.setProperty("--inv-text", cfg.invalid_text_color || "#ff4d4d");
  st.setProperty("--inv-sector", cfg.invalid_sector_color || "#5b616b");
  st.setProperty("--inv-line", cfg.invalid_line_color || "#ff4d4d");
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
    ${cfg.show_driver_number && item.driver_number ? `<span class="dn" style="border-color:${esc(cls.color)};color:${esc(cls.color)}">${esc(item.driver_number)}</span>` : ""}
    ${badge}`;
}

function build(kind) {
  const el = document.createElement("div");
  // Opens from the middle with a light sweep (laps.css); once in, moving it
  // (reordering) doesn't play that again.
  el.className = `tracker ${kind} entering`;
  setTimeout(() => el.classList.remove("entering"), 1300);
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
    s.innerHTML = '<i></i><span class="st tnum"></span>';
    sectorsEl.appendChild(s);
  }
  while (sectorsEl.children.length > sectors.length) sectorsEl.lastChild.remove();
  sectors.forEach((s, i) => {
    const node = sectorsEl.children[i];
    const bar = node.querySelector("i");
    bar.className = s.colour || "";
    node.dataset.c = s.colour || "";
    // A new lap empties the bars at once instead of sliding back.
    const width = `${Math.round(s.done * 1000) / 10}%`;
    if (s.done < parseFloat(bar.style.width || "0") - 1) bar.style.transition = "none";
    bar.style.width = width;
    if (bar.style.transition === "none") requestAnimationFrame(() => (bar.style.transition = ""));
    // An invalidated lap: the sector it happened in struck through, the rest greyed out.
    node.classList.toggle("struck", s.mark === "struck");
    node.classList.toggle("grey", s.mark === "grey");
    const st = node.querySelector(".st");
    const hold = deltaFor(s, cfg);
    if (hold) {
      const key = `${i}:${s.time}`;
      if (node.dataset.dk !== key) {  // a new sector time: its difference fades in and out
        node.dataset.dk = key;
        node.style.setProperty("--dd", `${hold}s`);
        node.style.setProperty("--dage", `-${s.age}s`);
        node.classList.remove("delta", "time-in");
        void node.offsetWidth;  // restart the animation
      }
      node.classList.add("delta");
      st.textContent = fmtGain(s.delta);
    } else {
      if (node.classList.contains("delta")) {  // then the time comes in
        node.classList.remove("delta");
        node.classList.add("time-in");
        setTimeout(() => node.classList.remove("time-in"), 500);
      }
      st.textContent = fmtSector(s.time);
    }
    node.classList.toggle("tight", !!s.time && st.scrollWidth > node.clientWidth - 6);
  });
  const lt = el.querySelector(".lt");
  const dl = el.querySelector(".dl");
  lt.classList.toggle("done", !!lap && lap.state === "finished");
  lt.classList.toggle("void", !!lap && lap.state === "finished" && !lap.valid);
  // A lap just finished lands: the time pops in, the tracker flashes purple
  // (the fastest) or green (a personal best).
  const landKey = lap && lap.state === "finished" ? `${lap.lap_time}:${lap.elapsed}` : "";
  if (landKey && entry.landKey !== landKey) {
    entry.landKey = landKey;
    if (lap.shown_for == null || lap.shown_for < 1.5) {
      el.classList.remove("landed", "land-purple", "land-green");
      void el.offsetWidth;
      el.classList.add("landed");
      if (lap.lap_colour) el.classList.add(`land-${lap.lap_colour}`);
      clearTimeout(entry.landTimer);
      entry.landTimer = setTimeout(() => el.classList.remove("landed", "land-purple", "land-green"), 2600);
    }
  }
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
  if (SCREEN) {
    setInvalidColours(ov.settings.laps);
    setBackground(ov.settings.laps, true);
    setSize(ov.settings.laps, true);
    return renderScreen(ov);
  }
  const cfg = ov.settings.laps;
  setPanels(cfg);
  setSize(cfg);
  setInvalidColours(cfg);
  const laps = ov.laps;
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const want = new Map();
  if (snap.connected && cfg.visible && laps.active) {
    if (laps.camera) want.set(laps.camera.car_idx, ["big", laps.camera]);
    for (const t of laps.trackers.slice(0, cfg.count)) want.set(t.car_idx, ["small", t]);
  }
  // As many small trackers to a row as fit at a readable width; the rest
  // wrap onto a row above.
  const smallCount = [...want.values()].filter(([k]) => k === "small").length;
  const room = 1840 - (want.size > smallCount ? 620 + 24 : 0);
  const perRow = Math.max(1, Math.min(smallCount, Math.floor((room + 12) / (SMALL_MIN_W + 12))));
  box.style.setProperty("--small-w", `${Math.min(SMALL_MAX_W, Math.floor((room - 12 * (perRow - 1)) / perRow))}px`);
  for (const [idx, entry] of shown) {
    const w = want.get(idx);
    if (!w || w[0] !== entry.kind) {
      shown.delete(idx);
      entry.el.classList.remove("entering", "landed", "land-purple", "land-green");
      entry.el.classList.add("gone");
      setTimeout(() => entry.el.remove(), 650);
    }
  }
  for (const [idx, [kind, item]] of want) {
    let entry = shown.get(idx);
    if (!entry) {
      entry = { el: build(kind), kind, top: "" };
      shown.set(idx, entry);
      (kind === "big" ? bigSlot : smallSlot).appendChild(entry.el);
    }
    update(entry, item, cfg, classes, laps.sectors);
  }
  // Keep the small ones in the server's order (moving a node replays its
  // entrance animation, so only when the order changed).
  const order = laps.trackers.slice(0, cfg.count).map((t) => shown.get(t.car_idx)).filter((e) => e && e.kind === "small");
  const current = [...smallSlot.children].filter((el) => !el.classList.contains("gone"));
  if (order.some((e, i) => current[i] !== e.el)) {
    // The trackers slide to their new places rather than jumping.
    const was = new Map(order.map((e) => [e.el, e.el.getBoundingClientRect()]));
    for (const e of order) smallSlot.appendChild(e.el);
    for (const [el, r] of was) {
      const now = el.getBoundingClientRect();
      const k = now.width / el.offsetWidth || 1;  // the screen's scaling
      const dx = (r.left - now.left) / k, dy = (r.top - now.top) / k;
      if (!dx && !dy) continue;
      el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], { duration: 450, easing: "cubic-bezier(.2, .8, .2, 1)" });
    }
  }
}

// -- full-screen live timing ---------------------------------------------------

let screenShown = "";
let screenAt = 0;
const screenClocks = new Map();  // car_idx -> running lap (elapsed at screenAt)

function screenRowHtml(item, cfg, cls, nsec, camIdx) {
  const lap = item.lap;
  const sectors = lap ? lap.sectors : Array.from({ length: nsec }, () => ({ time: null, colour: null, done: 0 }));
  let lapCell = "";
  if (!lap) lapCell = `<span class="state">${item.on_pit ? "IN PITS" : item.in_world ? "OUT LAP" : "—"}</span>`;
  else if (lap.state === "finished") {
    const d = lap.delta != null && lap.valid ? `<span class="${lap.delta <= 0 ? "faster" : "slower"}"> ${lap.delta > 0 ? "+" : "−"}${Math.abs(lap.delta).toFixed(3)}</span>` : "";
    lapCell = lap.valid ? `<span class="lapclock">${fmtLap(lap.lap_time)}</span>${d}` : '<span class="lapclock void">INVALID</span>';
  } else lapCell = `<span class="lapclock ${lap.valid ? "" : "invalid"}" data-clock="${item.car_idx}"></span>`;
  const team = item.team ? `${cfg.show_logo && item.team_logo ? `<img src="${esc(item.team_logo)}" alt="">` : ""}${esc(item.team)}` : "";
  return `<tr class="${item.car_idx === camIdx ? "cam" : ""}">
    <td class="stripe" style="background:${esc(cls.color)}"></td>
    <td class="p r">${item.pos ?? ""}</td>
    <td class="c"><span class="num" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">${esc(item.number)}</span></td>
    <td>${esc(formatName(item, cfg.name_format))}</td>
    <td class="team">${team}</td>
    ${sectors.map((sc) => `<td class="sec ${sc.mark || ""}"><div class="${sc.colour || ""}">${sc.colour ? "" : `<i style="width:${Math.round(sc.done * 100)}%"></i>`}<span>${sc.time == null ? "" : deltaFor(sc, cfg) ? fmtGain(sc.delta) : fmtSector(sc.time)}</span></div></td>`).join("")}
    <td class="r">${lapCell}</td>
    <td class="r lead">${fmtLap(item.best)}</td>
    <td class="r">${item.pos > 1 && item.gap != null ? `+${item.gap.toFixed(3)}` : ""}</td>
  </tr>`;
}

function renderScreen(ov) {
  const cfg = ov.settings.laps;
  const laps = ov.laps;
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const nsec = laps.sectors;
  const camIdx = snap.camera && snap.camera.car_idx;
  const rows = laps.all || [];
  const rowH = Math.max(26, Math.min(44, Math.floor(900 / Math.max(rows.length, 1))));
  const session = snap.session || {};
  const sub = [snap.league && snap.league.name, [session.track, session.track_config].filter(Boolean).join(" – ")].filter(Boolean).join(" · ");
  const secW = Math.max(64, Math.min(120, Math.floor(720 / Math.max(nsec, 1))));
  const widths = ["6px", "70px", "70px", "auto", "auto", ...Array(nsec).fill(`${secW}px`), "190px", "130px", "120px"];
  const body = !snap.connected ? '<div class="screen-empty">Waiting for iRacing…</div>'
    : !laps.active ? '<div class="screen-empty">Live lap timing shows during qualifying.</div>'
      : `<div class="screen-body"><div class="screen-col"><table class="screen-table">
        <colgroup>${widths.map((w) => `<col style="width:${w}">`).join("")}</colgroup>
        <thead><tr><th class="stripe"></th><th class="r">Pos</th><th class="c">#</th><th>Driver</th><th>Team</th>
          ${Array.from({ length: nsec }, (_, i) => `<th class="c">S${i + 1}</th>`).join("")}<th class="r">Lap</th><th class="r">Best</th><th class="r">Gap</th></tr></thead>
        <tbody>${rows.map((it) => screenRowHtml(it, cfg, classes.get(it.class_key) || DEFAULT_CLASS, nsec, camIdx)).join("")}</tbody>
      </table></div></div>`;
  const html = `<div class="screen-page" style="--row-h:${rowH}px;--row-font:${Math.round(rowH * 0.52)}px">
    <div class="screen-head"><span class="t1">${laps.active ? "QUALIFYING" : "LIVE TIMING"}</span><span class="t2">${esc(sub)}</span>
      <span class="t3">${snap.connected ? fmtClock(session.time) : ""}</span></div>${body}</div>`;
  screenAt = performance.now();
  screenClocks.clear();
  for (const it of rows) if (it.lap && it.lap.state === "running") screenClocks.set(String(it.car_idx), it.lap.elapsed);
  if (html !== screenShown) {
    screenShown = html;
    stage.innerHTML = html;
  }
}

// The lap clock runs here between snapshots.
function tick() {
  const now = performance.now();
  const speed = snap && snap.replay ? snap.replay.speed ?? 1 : 1;
  if (SCREEN) {
    for (const el of stage.querySelectorAll("[data-clock]")) {
      const elapsed = screenClocks.get(el.dataset.clock);
      el.textContent = elapsed == null ? "" : fmtLap(elapsed + ((now - screenAt) / 1000) * speed).replace(/(\.\d)\d\d$/, "$1");
    }
    return requestAnimationFrame(tick);
  }
  for (const entry of shown.values()) {
    const lap = entry.item && entry.item.lap;
    const lt = entry.el.querySelector(".lt");
    if (!lap) lt.textContent = "";
    else if (lap.state === "finished") lt.textContent = lap.valid ? fmtLap(lap.lap_time) : "INVALID";
    else lt.textContent = fmtLap(lap.elapsed + ((now - entry.received) / 1000) * speed).replace(/(\.\d)\d\d$/, "$1");
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

followSnapshots((s) => {
  snap = s;
  render();
});
