"use strict";

// ---------------------------------------------------------------------------
// control panel helpers (shared ones live in common.js)
// ---------------------------------------------------------------------------

let toastTimer;
function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show" + (isError ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = "toast"), isError ? 4000 : 1600);
}

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

async function cmd(action, params = {}, okMsg) {
  try {
    const r = await api("/api/cmd", { method: "POST", body: { action, params } });
    if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg);
    return r;
  } catch (e) {
    toast(e.message, true);
  }
}

// ---------------------------------------------------------------------------
// state
// ---------------------------------------------------------------------------

const ui = {
  snap: null,
  logFilter: "all",
  classFilter: "all",
  selectedEvent: null,   // race log line picked for a replay
  editing: null,         // league profile being edited
  activeLeague: null,
  library: [],           // built-in class logos
  libraryLoaded: false,
};

// Per-PC preferences for the timing screen.
const SETTINGS_KEY = "apex.timing";
const settings = Object.assign(
  { battleGap: 0.15, battleColor: "#ff3b6b", rewind: 10, logPreroll: 10, hotkeys: null },
  (() => {
    try {
      return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {};
    } catch (e) {
      return {};
    }
  })(),
);

function saveSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch (e) { /* storage unavailable */ }
}

// ---------------------------------------------------------------------------
// live data stream
// ---------------------------------------------------------------------------

function connectStream() {
  liveStream((snap) => {
    ui.snap = snap;
    // After an update the server restarts on the new version: load its UI.
    if (ui.version && ui.snap.version && ui.snap.version !== ui.version) return location.reload();
    ui.version = ui.version || ui.snap.version;
    $(".brand").title = `Apex Commentator v${ui.snap.version}`;
    render();
  }, () => {
    $("#status-dot").classList.remove("on");
    $("#session-line").textContent = "Overlay server not reachable, retrying…";
  });
}

// ---------------------------------------------------------------------------
// rendering
// ---------------------------------------------------------------------------

function render() {
  const s = ui.snap;
  $("#status-dot").classList.toggle("on", !!s.connected);
  const league = s.league;
  const lb = $("#league-badge");
  lb.textContent = league ? league.name : "No league";
  lb.classList.toggle("muted", !league);
  renderGridwalk(s);
  renderHome(s);
  renderPhotoboothFolder(s.photobooth);
  renderUpdates(s.update);
  renderResultsAuto(s.results_auto);
  renderOverlaySettings(s);
  renderChampLive(s);
  renderBoards(s);
  renderDesktop(s);

  if (!s.connected) {
    $("#session-line").textContent = s.source === "iracing" ? "Waiting for iRacing…" : "Not connected";
    $("#replay-badge").textContent = "—";
    $("#replay-badge").className = "badge";
    $("#standings-rows").innerHTML = "";
    rowEls.clear();
    $("#standings-empty").hidden = false;
    $("#log-status").textContent = "";
    return;
  }

  const ses = s.session;
  const track = [ses.track, ses.track_config].filter(Boolean).join(" – ");
  $("#session-line").innerHTML =
    `<b>${esc(track)}</b> · ${esc(ses.type || ses.name)} · ${esc(ses.state)} · ${fmtClock(ses.time)}` +
    (s.source === "mock" ? " · <i>mock data</i>" : "");

  const rb = $("#replay-badge");
  if (s.replay.live) {
    rb.textContent = "LIVE";
    rb.className = "badge live";
  } else {
    rb.textContent = `REPLAY ${fmtClock(s.replay.session_time)}`;
    rb.className = "badge replay";
  }
  $("#btn-live").classList.toggle("on-air", !!s.replay.live);

  renderCamButtons(s.camera);
  renderPhotobooth(s);
  renderStandings(s);
  renderLog(s);
}

// -- pages ----------------------------------------------------------------------

const PAGE_KEY = "apex.page";
// ?popout=timing: one page in a window of its own (the Pop out buttons), without the tabs.
const POPOUT = new URLSearchParams(location.search).get("popout");

// A nickname that's just the name without its "(P)" class tag says nothing new.
function sameButClassTag(name, nickname) {
  return String(name || "").replace(/^\s*\([^()]*\)\s*/, "").trim().toLowerCase() === String(nickname || "").trim().toLowerCase();
}

function showPage(name) {
  if (!document.getElementById(`tab-${name}`)) name = "home";
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
  // The timing screen fills the window; the other pages scroll.
  $("#main").classList.toggle("fixed", name === "timing");
  if (name === "league") loadLeagues();
  if (name === "teams" || name === "championship") renderLeaguePickers();
  if (POPOUT) return;  // a pop-out doesn't change which page the main window opens on
  try {
    localStorage.setItem(PAGE_KEY, name);
  } catch (e) { /* storage unavailable */ }
}

function renderHome(s) {
  $("#home-version").textContent = s.version ? `v${s.version}` : "";
  const ses = s.session;
  $("#home-session").textContent = s.connected
    ? `${[ses.track, ses.track_config].filter(Boolean).join(" – ")} · ${ses.type || ses.name} · ${ses.state}` +
      (s.source === "mock" ? " (demo mode)" : "")
    : (s.source === "iracing" ? "Waiting for iRacing: join or spectate a session." : "Not connected.");
  const drivers = (s.drivers || []).length;
  const battles = s.connected ? findBattles(s, s.drivers || []).size : 0;
  $("#tile-timing").textContent = s.connected
    ? `${drivers} drivers · ${(s.events || []).length} logged${battles ? ` · ${battles} in battles` : ""}`
    : "Offline";
  const league = s.league;
  $("#tile-teams").textContent = league ? `${league.teams} teams in ${league.name}` : "No league active";
  const g = s.gridwalk || {};
  $("#tile-gridwalk").textContent = g.visible ? (g.running ? "● On air" : "❚❚ On air, paused") : `${(g.entries || []).length} on the grid`;
  $("#tile-league").textContent = s.league ? `Active: ${s.league.name}` : "No league active";
}

// -- camera bar -----------------------------------------------------------------

let camKey = "";
const RESERVED_KEYS = new Set(["l", "r", "arrowup", "arrowdown"]);

// Camera group name -> key. Until set by hand, 1-9 go to the first nine cameras.
function hotkeys(groups) {
  if (settings.hotkeys) return settings.hotkeys;
  const map = {};
  groups.slice(0, 9).forEach((g, i) => { map[g.name] = String(i + 1); });
  return map;
}

function keyLabel(k) {
  return { arrowup: "↑", arrowdown: "↓", " ": "Space" }[k] || (k.length === 1 ? k.toUpperCase() : k);
}

function renderCamButtons(cam) {
  const keys = hotkeys(cam.groups);
  const key = JSON.stringify([cam.groups, keys]);
  if (key !== camKey) {
    camKey = key;
    $("#cam-buttons").innerHTML = cam.groups.map((g) => `<button class="btn cam" data-group="${g.num}">
        ${esc(g.name)}${keys[g.name] ? `<kbd>${esc(keyLabel(keys[g.name]))}</kbd>` : ""}</button>`).join("");
  }
  document.querySelectorAll("#cam-buttons .cam").forEach((b) => b.classList.toggle("active", +b.dataset.group === cam.group));
}

// -- standings ------------------------------------------------------------------

// Rows are reconciled cell by cell rather than rebuilt, so a row under the
// mouse is not replaced mid-click by the 4 Hz updates.
const rowEls = new Map();   // key -> <tr>

function patchRow(key, className, cells, attrs = {}) {
  let tr = rowEls.get(key);
  if (!tr) {
    tr = document.createElement("tr");
    rowEls.set(key, tr);
  }
  if (tr.className !== className) tr.className = className;
  for (const [k, v] of Object.entries(attrs)) if (tr.getAttribute(k) !== v) tr.setAttribute(k, v);
  while (tr.children.length > cells.length) tr.lastChild.remove();
  cells.forEach(([html, cls = "", colspan], i) => {
    let td = tr.children[i];
    if (!td) td = tr.appendChild(document.createElement("td"));
    if (td.className !== cls) td.className = cls;
    if (colspan) td.colSpan = colspan;
    if (td._html !== html) {
      td.innerHTML = html;
      td._html = html;
    }
  });
  return tr;
}

function isRace(s) {
  return (s.session.type || "").toLowerCase() === "race";
}

// Rows in the current view (all classes, or one), with gaps worked out for it.
function standingsView(s) {
  const rows = (s.drivers || []).filter((r) => ui.classFilter === "all" || r.class_key === ui.classFilter);
  const race = isRace(s);
  const fastest = Math.min(...rows.map((r) => r.best_lap || Infinity));
  const leaderGap = rows.length ? rows[0].gap : null;
  let prev = null;
  return rows.map((r) => {
    let gap = null, int = null;
    if (race && r.gap != null && leaderGap != null) {
      gap = r.gap - leaderGap;
      if (prev && prev.gap != null) int = Math.max(0, r.gap - prev.gap);
    }
    const down = race ? (ui.classFilter === "all" ? r.laps_down : r.class_laps_down) || 0 : 0;
    const v = { r, gap, int, down, fastestLap: isFinite(fastest) && r.best_lap === fastest, fastest };
    prev = r;
    return v;
  });
}

// car_idx of everyone within the battle gap of the car ahead (and that car).
function findBattles(s, rows) {
  const out = new Set();
  if (!isRace(s) || s.session.state !== "Racing") return out;
  const view = rows === s.drivers ? standingsView(s) : rows;
  view.forEach((v, i) => {
    const ahead = view[i - 1];
    const fighting = (x) => x.r.in_world && !x.r.on_pit;
    if (ahead && v.int != null && v.int >= 0 && v.int <= settings.battleGap && fighting(v) && fighting(ahead)) {
      out.add(v.r.car_idx);
      out.add(ahead.r.car_idx);
    }
  });
  return out;
}

const FLAG_LABELS = {
  green: "Green", yellow: "Yellow", blue: "Blue", white: "White", checkered: "Chequered",
  black: "Black", meatball: "Meatball", warning: "Warning", dq: "DQ",
};

function changeCell(n) {
  if (n == null) return "";
  if (n === 0) return '<span class="chg same">–</span>';
  return n > 0 ? `<span class="chg up">▲${n}</span>` : `<span class="chg down">▼${-n}</span>`;
}

let classChipsKey = "";

function renderClassFilter(s) {
  const classes = s.classes || [];
  const key = JSON.stringify(classes.map((c) => [c.key, c.name, c.color]));
  if (key === classChipsKey) return;
  classChipsKey = key;
  if (ui.classFilter !== "all" && !classes.some((c) => c.key === ui.classFilter)) ui.classFilter = "all";
  $("#class-filter").innerHTML = classes.length > 1
    ? [`<button class="chip ${ui.classFilter === "all" ? "active" : ""}" data-class="all">All classes</button>`,
      ...classes.map((c) => `<button class="chip ${ui.classFilter === c.key ? "active" : ""}" data-class="${esc(c.key)}">
        <span class="swatch" style="background:${esc(c.color)}"></span>${esc(c.name)}</button>`)].join("")
    : "";
}

function renderStandings(s) {
  renderClassFilter(s);
  document.documentElement.style.setProperty("--battle", settings.battleColor);
  const view = standingsView(s);
  $("#standings-empty").hidden = view.length > 0;
  const race = isRace(s);
  const battles = findBattles(s, view);
  const classByKey = new Map((s.classes || []).map((c) => [c.key, c]));
  const inClass = ui.classFilter !== "all";
  const firstRow = view.length ? view[0].r : null;
  const ordered = view.map((v) => {
    const r = v.r;
    const cls = classByKey.get(r.class_key) || {};
    const color = cls.color || r.class_color || "var(--muted)";
    const lg = r.league;
    const team = (lg && lg.team) || r.team;
    let gap = "", int = "";
    if (race) {
      gap = v.gap == null ? "" : v.r === firstRow ? "Leader" : v.down ? `+${v.down} L` : fmtDelta(v.gap);
      int = v.int == null ? "" : fmtDelta(v.int);
    } else if (r.best_lap && isFinite(v.fastest)) {
      gap = v.fastestLap ? "Fastest" : fmtDelta(r.best_lap - v.fastest);
    }
    const status = !r.in_world ? '<span class="tag out">OUT</span>'
      : r.on_pit ? '<span class="tag pit">PIT</span>'
      : r.surface === "off_track" ? '<span class="tag off">OFF</span>' : "";
    const watching = s.camera.car_idx === r.car_idx;
    // Penalties have their own column; the flag column is for racing flags.
    const flag = r.flag && !["green", "black", "dq", "meatball", "warning"].includes(r.flag)
      ? `<span class="flag flag-${r.flag}">${FLAG_LABELS[r.flag] || r.flag}</span>` : "";
    const className = [watching && "watching", !r.in_world && "gone", battles.has(r.car_idx) && "battle"].filter(Boolean).join(" ");
    return patchRow(`d${r.car_idx}`, className, [
      [String(r.pos ?? ""), "pos"],
      [r.class_pos ? `<span class="cls-pos" style="border-color:${esc(color)}">${r.class_pos}</span>` : ""],
      [changeCell(inClass ? r.class_pos_change : r.pos_change), "c-chg"],
      [`<span class="num" style="border-left-color:${esc(color)}">${esc(r.number)}</span>`],
      [`<span class="name">${esc(r.name)}</span>${lg && lg.nickname && !sameButClassTag(r.name, lg.nickname) ? `<span class="nick">“${esc(lg.nickname)}”</span>` : ""}` +
        `${team ? `<span class="sub">${esc(team)}</span>` : ""} ${status}`, "driver-cell"],
      [String(r.lap ?? "")],
      [gap, "c-time"],
      [int, "c-time"],
      [fmtLap(r.last_lap), "c-time col-wide"],
      [fmtLap(r.best_lap), `c-time col-wide ${v.fastestLap ? "best" : ""}`],
      [r.pit_stops ? String(r.pit_stops) : "", "col-wide"],
      [flag],
      [(r.penalties || []).map((p) => `<span class="pen">⚑ ${esc(p)}</span>`).join(" ")],
      [r.incidents == null ? "" : r.incidents + "x"],
    ], { "data-car": String(r.car_idx), title: `Click to watch ${r.name}` });
  });
  const body = $("#standings-rows");
  const keep = new Set(ordered);
  for (const [key, tr] of rowEls) {
    if (!keep.has(tr)) {
      tr.remove();
      rowEls.delete(key);
    }
  }
  // Drivers changing places slide past each other.
  flipRows(body, "tr[data-car]", () => {
    ordered.forEach((tr, i) => {
      if (body.children[i] !== tr) body.insertBefore(tr, body.children[i] || null);
    });
  }, 350, (el) => el.dataset.car);
}

// -- race log -------------------------------------------------------------------

const LOG_LABELS = {
  overtake: "PASS", offtrack: "OFF", slowdown: "SLOW", spin: "SPIN", contact: "CONTACT", incident: "INC", pit_in: "PIT", pit_out: "PIT",
  position: "LOST", penalty: "PEN", fastest_lap: "FAST",
};
const LOG_GROUPS = {
  incident: ["contact", "offtrack", "slowdown", "spin", "incident"], pit: ["pit_in", "pit_out"],
};
const PREROLL_CHOICES = [5, 10, 15, 20, 25, 30];

function car(num, name) {
  return `<span class="num">${esc(num)}</span> ${esc(name)}`;
}

function eventText(ev) {
  const who = car(ev.car_number, ev.driver);
  const pts = ev.incidents ? ` <b>${ev.incidents}x</b>` : "";
  switch (ev.type) {
    case "overtake":
      return `${who} passes ${car(ev.other_car_number, ev.other_driver)}${ev.position ? ` for <b>P${ev.position}</b>` : ""}`;
    case "offtrack":
      return `${who} ${ev.spin ? "spins off track" : "off track"}${pts}`;
    case "slowdown":
      return `${who} slows ${ev.from_kph}→${ev.speed_kph} km/h${pts}`;
    case "contact": {
      const theirs = ev.other_incidents ? ` <b>${ev.other_incidents}x</b>` : "";
      return `${who}${pts} and ${car(ev.other_car_number, ev.other_driver)}${theirs} make contact`;
    }
    case "spin":
      return `${who} spins (${ev.from_kph}→${ev.speed_kph} km/h)${pts}`;
    case "pit_in":
      return `${who} pits${ev.position ? ` from P${ev.position}` : ""}`;
    case "pit_out": {
      const lost = ev.position && ev.from_position ? ev.position - ev.from_position : 0;
      return `${who} rejoins <b>P${ev.position ?? "?"}</b>${lost > 0 ? ` (lost ${lost})` : ""} · ${ev.duration}s in the pits`;
    }
    case "position":
      return `${who} loses <b>${ev.position - ev.from_position}</b> place${ev.position - ev.from_position === 1 ? "" : "s"} after going off (P${ev.from_position} → P${ev.position})`;
    case "penalty":
      return `${who}: <b>${esc(ev.penalty)}</b>`;
    case "fastest_lap":
      return `${who} fastest lap${ev.car_class ? ` in ${esc(ev.car_class)}` : ""}: <b>${fmtLap(ev.lap_time)}</b>`;
    default:
      return `${who} incident${pts}`;
  }
}

function logStatus(s) {
  return {
    live: "● Logging live",
    replay: "● Logging the replay being played",
    paused: "❚❚ Logging paused: you're watching something already logged. It resumes past that point (Go live).",
    waiting: "Waiting for the session to start…",
  }[s.detection] || "";
}

let logKey = "";

function renderLog(s) {
  const all = s.events || [];
  $("#log-status").textContent = logStatus(s);
  $("#log-status").className = `log-status ${s.detection || ""}`;
  const types = LOG_GROUPS[ui.logFilter] || (ui.logFilter === "all" ? null : [ui.logFilter]);
  const shown = all.filter((e) => !types || types.includes(e.type))
    .sort((a, b) => b.session_num - a.session_num || b.session_time - a.session_time || b.id - a.id);
  $("#log-empty").hidden = shown.length > 0;
  const key = JSON.stringify([shown, ui.selectedEvent, settings.logPreroll]);
  if (key === logKey) return;
  logKey = key;
  $("#race-log").innerHTML = shown.map((ev) => {
    const selected = ev.id === ui.selectedEvent;
    const cls = ev.incidents ? "kind has-points" : `kind ${ev.spin ? "spin" : ev.type}`;
    return `<li class="${selected ? "selected" : ""}" data-event="${ev.id}">
      <div class="log-line">
        <span class="when">L${ev.lap} · ${fmtClock(ev.session_time)}</span>
        <span class="${cls}">${ev.spin ? "SPIN" : LOG_LABELS[ev.type] || ev.type}</span>
        <span class="what">${eventText(ev)}</span>
      </div>
      ${selected ? `<div class="log-actions">
        <span class="label">Replay from</span>
        ${PREROLL_CHOICES.map((p) => `<button class="chip ${p === settings.logPreroll ? "active" : ""}" data-preroll="${p}"
            title="Replay from ${p} seconds before">−${p}s</button>`).join("")}
        <button class="btn icon" data-watch="${ev.car_idx}" title="Watch ${esc(ev.driver)} live">👁</button>
      </div>` : ""}
    </li>`;
  }).join("");
}

// ---------------------------------------------------------------------------
// grid walk
// ---------------------------------------------------------------------------

let gwRowsKey = "";

function renderGridwalk(s) {
  const g = s.gridwalk;
  if (!g) return;
  const entries = g.entries || [];
  const classes = new Map((s.classes || []).map((c) => [c.key, c]));
  $("#gridwalk-badge").textContent = g.visible ? (g.running ? "● on air" : "❚❚ on air") : "";
  $("#gw-toggle").textContent = g.running ? "❚❚ Pause" : "▶ Resume";
  for (const [id, value, prop] of [["#gw-interval", g.interval, "value"], ["#gw-style", g.style, "value"],
    ["#gw-loop", g.loop, "checked"], ["#gw-absent", g.include_absent, "checked"]]) {
    const el = $(id);
    if (document.activeElement !== el) el[prop] = value;
  }
  const sources = {
    qualifying: "Grid order from qualifying.", "qualifying session": "Grid order from the qualifying session.",
    "current positions": "Grid order from current positions (no qualifying results yet).",
    "car number": "No qualifying results yet: ordered by car number.", manual: "Grid order set by hand.",
  };
  $("#gw-source").textContent = entries.length ? sources[g.source] || "" : "";
  $("#gw-reset-order").hidden = !g.manual_order;
  $("#gw-empty").hidden = entries.length > 0;
  // Rebuild rows only when they change, so buttons aren't replaced mid-click.
  const key = JSON.stringify([g.index, g.visible, entries.map((e) => [e.key, e.number, e.name, e.nickname, e.team,
    e.in_session, e.in_world, (classes.get(e.class_key) || {}).color])]);
  if (key === gwRowsKey) return;
  gwRowsKey = key;
  $("#gw-rows").innerHTML = entries.map((e, i) => {
    const onScreen = g.visible && (i === g.index || i === g.index + 1);
    const color = (classes.get(e.class_key) || {}).color || "var(--muted)";
    const status = !e.in_session ? '<span class="tag out">NOT IN SESSION</span>'
      : !e.in_world ? '<span class="tag out">NOT ON TRACK</span>' : "";
    return `<tr class="${onScreen ? "on-screen" : ""}">
      <td class="pos">P${e.grid_pos}</td>
      <td><span class="num" style="border-left-color:${esc(color)}">${esc(e.number)}</span></td>
      <td><span class="name">${esc(e.name)}</span>${e.nickname ? `<span class="nick">“${esc(e.nickname)}”</span>` : ""}</td>
      <td class="sub">${esc(e.team)}</td>
      <td>${status}</td>
      <td><div class="actions">
        <button class="btn" data-gw-goto="${i}" title="Show this driver's pair now">Show</button>
        <button class="btn icon" data-pb-car="${e.car_idx ?? ""}" ${e.in_world ? "" : "disabled"} title="${e.in_world ? "Take this car's photo in iRacing" : "Only cars loaded onto the track can be photographed"}">📷</button>
        <button class="btn icon" data-gw-move="${esc(e.key)}" data-dir="-1" ${i ? "" : "disabled"} title="Move up the grid">↑</button>
        <button class="btn icon" data-gw-move="${esc(e.key)}" data-dir="1" ${i < entries.length - 1 ? "" : "disabled"} title="Move down the grid">↓</button>
      </div></td>
    </tr>`;
  }).join("");
}

$("#tab-gridwalk").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const g = ui.snap && ui.snap.gridwalk;
  if (btn.dataset.gw) {
    const action = {
      start: "gridwalk_start", prev: "gridwalk_prev", next: "gridwalk_next", hide: "gridwalk_hide",
      toggle: g && g.running ? "gridwalk_pause" : "gridwalk_resume",
    }[btn.dataset.gw];
    return cmd(action, {});
  }
  if (btn.dataset.gwGoto != null) return cmd("gridwalk_goto", { index: +btn.dataset.gwGoto });
  if (btn.dataset.pbCar) return startPhotobooth(+btn.dataset.pbCar);
  if (btn.dataset.gwMove) return cmd("gridwalk_move", { key: btn.dataset.gwMove, direction: +btn.dataset.dir });
  if (btn.id === "gw-reset-order") return cmd("gridwalk_reset_order", {}, "Grid order reset");
  if (btn.id === "gw-copy") {
    navigator.clipboard.writeText($("#gw-url").textContent).then(() => toast("Copied"), () => toast("Copy failed", true));
  }
});

$("#gw-interval").addEventListener("change", (e) => cmd("gridwalk_settings", { interval: +e.target.value }));
$("#gw-style").addEventListener("change", (e) => cmd("gridwalk_settings", { style: e.target.value }));
$("#gw-loop").addEventListener("change", (e) => cmd("gridwalk_settings", { loop: e.target.checked }));
$("#gw-absent").addEventListener("change", (e) => cmd("gridwalk_settings", { include_absent: e.target.checked }));
$("#gw-url").textContent = `${location.origin}/gridwalk.html`;

// ---------------------------------------------------------------------------
// photo booth
// ---------------------------------------------------------------------------

const PB_CAMERA_KEY = "apex.photoboothCamera";
let pbGroupsKey = "";
let pbResultsKey = "";

function renderPhotoboothFolder(pb) {
  if (!pb) return;
  const input = $("#pb-folder");
  if (document.activeElement !== input) input.value = pb.screenshots_custom ? pb.screenshots_dir : "";
  input.placeholder = pb.screenshots_custom ? "iRacing's own folder" : pb.screenshots_dir;
  $("#pb-folder-reset").hidden = !pb.screenshots_custom;
}

async function setPhotoboothFolder(folder) {
  try {
    const r = await api("/api/cmd", { method: "POST", body: { action: "photobooth_folder", params: { folder } } });
    toast(`Screenshots folder: ${r.folder}`);
  } catch (err) {
    toast(err.message, true);
  }
}
$("#pb-folder-save").addEventListener("click", () => setPhotoboothFolder($("#pb-folder").value.trim()));
$("#pb-folder").addEventListener("keydown", (e) => {
  if (e.key === "Enter") setPhotoboothFolder(e.target.value.trim());
});
$("#pb-folder-reset").addEventListener("click", () => setPhotoboothFolder(""));

function renderPhotobooth(s) {
  const pb = s.photobooth;
  if (!pb) return;
  // Camera choice: the groups iRacing offers, remembering the last pick.
  const groups = s.camera.groups || [];
  const key = groups.map((g) => g.num + g.name).join("|");
  const sel = $("#pb-camera");
  if (key !== pbGroupsKey) {
    pbGroupsKey = key;
    let saved = null;
    try {
      saved = localStorage.getItem(PB_CAMERA_KEY);
    } catch (e) { /* storage unavailable */ }
    // A camera looking at the car from the front-side suits the grid walk best.
    const preferred = ["Rear Chase", "Chase", "TV1"].map((n) => groups.find((g) => g.name === n)).find(Boolean);
    sel.innerHTML = groups.map((g) => `<option value="${g.num}">${esc(g.name)}</option>`).join("");
    const pick = groups.find((g) => g.name === saved) || preferred;
    if (pick) sel.value = String(pick.num);
  }
  const busy = ["downloading", "capturing", "processing"].includes(pb.state);
  $("#pb-start").disabled = busy;
  $("#pb-cancel").hidden = !busy;
  $("#pb-cutout").disabled = busy || !pb.cutout_available;
  if (!pb.cutout_available) $("#pb-cutout").checked = false;
  // Automatic photos: on or off is kept by the app, so every window agrees.
  const auto = pb.auto || {};
  if (document.activeElement !== $("#pb-auto")) $("#pb-auto").checked = !!auto.on;
  const autoText = auto.error ? `Automatic photos stopped: ${auto.error}`
    : !auto.on ? "" : auto.paused ? `Automatic photos: ${auto.paused}.`
      : auto.waiting ? `Automatic photos: ${auto.waiting} car${auto.waiting === 1 ? "" : "s"} just loaded in, photographing in a few seconds…`
        : `Automatic photos: on${auto.camera ? ` (${auto.camera} camera)` : ""}, waiting for drivers without a photo.`;
  $("#pb-auto-status").textContent = autoText;
  $("#pb-auto-status").hidden = !autoText;
  $("#pb-auto-status").classList.toggle("error-text", !!auto.error);
  const dl = pb.model_download || {};
  const pct = dl.total ? Math.round((dl.done / dl.total) * 100) : 0;
  const n = pb.total;
  const status = {
    idle: pb.model_ready || !pb.cutout_available ? "" : "The cut-out model downloads the first time you use it (about 170 MB).",
    downloading: `Downloading the cut-out model (first time only): ${pct}%…`,
    capturing: `Photographing ${pb.current || ""} (${pb.captured + 1}/${n})… leave iRacing's camera alone.`,
    processing: `${pb.use_cutout ? "Cutting out" : "Saving"} ${pb.current || ""} (${pb.processed + 1}/${n})…`,
    done: `Done: ${pb.results.filter((r) => r.state === "saved").length} of ${n} photos saved to the league.`,
    cancelled: `Cancelled: ${pb.results.filter((r) => r.state === "saved").length} photos saved.`,
    error: pb.error || "Something went wrong.",
  }[pb.state] || "";
  const el = $("#pb-status");
  el.textContent = status;
  el.classList.toggle("error-text", pb.state === "error");
  const resultsKey = JSON.stringify(pb.results);
  if (resultsKey === pbResultsKey) return;
  pbResultsKey = resultsKey;
  $("#pb-results").innerHTML = pb.results.map((r) => `<figure class="pb-shot ${r.state}" title="${esc(r.error || r.state)}">
      <div class="pb-img">${r.image ? `<img src="${esc(r.image)}" alt="">` : `<span>${esc(r.state === "failed" ? "✕" : "…")}</span>`}</div>
      <figcaption><span class="num">${esc(r.number)}</span> ${esc(r.name)}</figcaption>
    </figure>`).join("");
}

function startPhotobooth(carIdx) {
  const params = { group: +$("#pb-camera").value || undefined, cutout: $("#pb-cutout").checked };
  if (carIdx != null) params.car_idx = carIdx;
  else params.missing_only = $("#pb-missing").checked;
  return cmd("photobooth_start", params, (r) => `Photographing ${r.cars} car${r.cars === 1 ? "" : "s"}…`);
}

$("#pb-start").addEventListener("click", () => startPhotobooth(null));
$("#pb-cancel").addEventListener("click", () => cmd("photobooth_cancel", {}, "Cancelling…"));
$("#pb-camera").addEventListener("change", (e) => {
  try {
    localStorage.setItem(PB_CAMERA_KEY, e.target.selectedOptions[0].textContent);
  } catch (err) { /* storage unavailable */ }
  if ($("#pb-auto").checked) setAutoPhotos(true);  // automatic photos use the new camera
});

// Automatic photos, with the camera and cut-out picked here.
function setAutoPhotos(on) {
  return cmd("photobooth_auto", { enabled: on, group: +$("#pb-camera").value || undefined, cutout: $("#pb-cutout").checked },
    on ? "Automatic photos on: each driver without a photo is photographed as their car loads in" : "Automatic photos off");
}
$("#pb-auto").addEventListener("change", (e) => setAutoPhotos(e.target.checked));
$("#pb-cutout").addEventListener("change", () => {
  if ($("#pb-auto").checked) setAutoPhotos(true);
});
const PB_MISSING_KEY = "apex.pbMissing";
try {
  $("#pb-missing").checked = localStorage.getItem(PB_MISSING_KEY) === "1";
} catch (e) { /* storage unavailable */ }
$("#pb-missing").addEventListener("change", (e) => {
  try {
    localStorage.setItem(PB_MISSING_KEY, e.target.checked ? "1" : "");
  } catch (err) { /* storage unavailable */ }
});

// ---------------------------------------------------------------------------
// interactions
// ---------------------------------------------------------------------------

function replayEvent(id, preroll) {
  return cmd("replay_event", { event_id: id, preroll }, (r) => `Replaying ${r.replaying} from ${preroll}s before`);
}

document.addEventListener("click", (e) => {
  const tab = e.target.closest(".tab, [data-goto]");
  if (tab && tab.dataset.champGoto) champ.view = tab.dataset.champGoto;
  if (tab) return showPage(tab.dataset.tab || tab.dataset.goto);

  const filter = e.target.closest("#log-filter .chip");
  if (filter) {
    ui.logFilter = filter.dataset.filter;
    document.querySelectorAll("#log-filter .chip").forEach((c) => c.classList.toggle("active", c === filter));
    if (ui.snap && ui.snap.connected) renderLog(ui.snap);
    return;
  }

  const classChip = e.target.closest("#class-filter .chip");
  if (classChip) {
    ui.classFilter = classChip.dataset.class;
    classChipsKey = "";
    if (ui.snap && ui.snap.connected) renderStandings(ui.snap);
    return;
  }

  const camBtn = e.target.closest("#cam-buttons .cam");
  if (camBtn) return cmd("camera_group", { group: +camBtn.dataset.group });

  // Race log: pick a line, then how far back the replay starts.
  const preroll = e.target.closest("[data-preroll]");
  if (preroll) {
    settings.logPreroll = +preroll.dataset.preroll;
    saveSettings();
    return replayEvent(ui.selectedEvent, settings.logPreroll);
  }
  const watchBtn = e.target.closest("[data-watch]");
  if (watchBtn) return cmd("watch", { car_idx: +watchBtn.dataset.watch });
  const logLine = e.target.closest("#race-log li");
  if (logLine) {
    const id = +logLine.dataset.event;
    ui.selectedEvent = ui.selectedEvent === id ? null : id;
    if (ui.snap && ui.snap.connected) renderLog(ui.snap);
    return;
  }

  // Standings: click a driver to put the camera on them.
  const row = e.target.closest("#standings-rows tr[data-car]");
  if (row) return cmd("watch", { car_idx: +row.dataset.car });

  const btn = e.target.closest("button[data-cmd]");
  if (btn) {
    const { cmd: action, ...rest } = btn.dataset;
    const params = {};
    for (const [k, v] of Object.entries(rest)) params[k] = isNaN(v) ? v : +v;
    if (action === "clear_events" && !confirm("Clear the race log?")) return;
    return cmd(action, params);
  }
});

// -- media bar ---------------------------------------------------------------------

function showRewind() {
  $("#rewind-secs").textContent = `${settings.rewind}s`;
}

function changeRewind(by) {
  settings.rewind = Math.min(120, Math.max(5, settings.rewind + by));
  saveSettings();
  showRewind();
}

function rewind() {
  return cmd("replay_seconds", { seconds: settings.rewind });
}

$("#rewind-less").addEventListener("click", () => changeRewind(-5));
$("#rewind-more").addEventListener("click", () => changeRewind(5));
$("#btn-rewind").addEventListener("click", rewind);
$("#btn-live").addEventListener("click", () => cmd("live", {}, "Back to live"));
showRewind();

// -- battle settings -----------------------------------------------------------------

$("#battle-gap").value = settings.battleGap;
$("#battle-color").value = settings.battleColor;
$("#battle-gap").addEventListener("change", (e) => {
  const v = parseFloat(e.target.value);
  if (v > 0) settings.battleGap = Math.round(v * 100) / 100;
  e.target.value = settings.battleGap;
  saveSettings();
});
$("#battle-color").addEventListener("input", (e) => {
  settings.battleColor = e.target.value;
  document.documentElement.style.setProperty("--battle", settings.battleColor);
  saveSettings();
});

// -- camera hotkeys --------------------------------------------------------------------

let hotkeyTarget = null;   // camera group name waiting for a key

function renderHotkeyList() {
  const groups = (ui.snap && ui.snap.camera && ui.snap.camera.groups) || [];
  const keys = hotkeys(groups);
  $("#hotkey-list").innerHTML = groups.length ? groups.map((g) => `<button class="btn hk ${hotkeyTarget === g.name ? "primary" : ""}"
      data-hk="${esc(g.name)}">${esc(g.name)} <kbd>${keys[g.name] ? esc(keyLabel(keys[g.name])) : "–"}</kbd></button>`).join("")
    : '<p class="hint">Cameras appear once iRacing is connected.</p>';
  $("#hotkey-prompt").textContent = hotkeyTarget ? `Press a key for ${hotkeyTarget}…` : "";
}

$("#btn-hotkeys").addEventListener("click", () => {
  hotkeyTarget = null;
  renderHotkeyList();
  $("#hotkey-modal").hidden = false;
});
$("#hotkey-list").addEventListener("click", (e) => {
  const b = e.target.closest("[data-hk]");
  if (!b) return;
  hotkeyTarget = b.dataset.hk;
  renderHotkeyList();
});
$("#hotkey-done").addEventListener("click", () => {
  hotkeyTarget = null;
  $("#hotkey-modal").hidden = true;
  camKey = "";
  if (ui.snap && ui.snap.connected) renderCamButtons(ui.snap.camera);
});
$("#hotkey-reset").addEventListener("click", () => {
  settings.hotkeys = null;
  saveSettings();
  renderHotkeyList();
});

function captureHotkey(e) {
  const key = e.key.toLowerCase();
  if (key === "escape") {
    hotkeyTarget = null;
  } else {
    const groups = ui.snap.camera.groups;
    const map = { ...hotkeys(groups) };
    if (key === "backspace" || key === "delete") {
      delete map[hotkeyTarget];
    } else if (RESERVED_KEYS.has(key)) {
      $("#hotkey-prompt").textContent = `${keyLabel(key)} is taken. Pick another key for ${hotkeyTarget}.`;
      return;
    } else {
      // A key belongs to one camera.
      for (const [name, k] of Object.entries(map)) if (k === key) delete map[name];
      map[hotkeyTarget] = key;
    }
    settings.hotkeys = map;
    saveSettings();
    hotkeyTarget = null;
  }
  renderHotkeyList();
}

document.addEventListener("keydown", (e) => {
  if (!$("#hotkey-modal").hidden && hotkeyTarget) {
    e.preventDefault();
    return captureHotkey(e);
  }
  if (e.target.closest("input, select, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
  if (!$("#hotkey-modal").hidden || !$("#update-modal").hidden) return;
  const key = e.key.toLowerCase();
  const groups = (ui.snap && ui.snap.camera && ui.snap.camera.groups) || [];
  const camName = Object.entries(hotkeys(groups)).find(([, k]) => k === key);
  const cam = camName && groups.find((g) => g.name === camName[0]);
  const keys = {
    l: () => cmd("live", {}, "Back to live"),
    r: rewind,
    arrowup: () => cmd("step_car", { direction: -1 }),
    arrowdown: () => cmd("step_car", { direction: 1 }),
  };
  const fn = cam ? () => cmd("camera_group", { group: cam.num }) : keys[key];
  if (fn) {
    e.preventDefault();
    fn();
  }
});

// ---------------------------------------------------------------------------
// championship: rules, rounds and results, penalties and standings for the
// League builder's league (ui.editing.championship). Standings are worked out
// by the app from the saved league; the live table comes with each snapshot.
// ---------------------------------------------------------------------------

const champ = { view: "standings", standings: null, bonuses: [], defaults: null, dirty: false, open: new Set() };
const STATUS_NAMES = [["finished", "Finished"], ["dnf", "DNF"], ["dsq", "DSQ"], ["dns", "DNS"]];

function champData() {
  const p = ui.editing;
  if (!p.championship) p.championship = JSON.parse(JSON.stringify(champ.defaults || { rules: {}, rounds: [], penalties: [], live_round: "" }));
  return p.championship;
}

async function loadChampStandings() {
  if (!ui.editing || !ui.editing.id) return;
  const id = ui.editing.id;
  try {
    const r = await api(`/api/leagues/${encodeURIComponent(id)}/championship`);
    if (!ui.editing || ui.editing.id !== id) return;
    champ.bonuses = r.bonuses;
    champ.defaults = r.championship;
    if (!ui.editing.championship) ui.editing.championship = r.championship;
    champ.standings = r.standings;
    renderChampionship();
  } catch (err) {
    toast(err.message, true);
  }
}

function markChampDirty() {
  champ.dirty = true;
  $("#champ-dirty").hidden = false;
}

function newId() {
  return Math.random().toString(36).slice(2, 12);
}

function parseLapTime(text) {
  const m = String(text || "").trim().match(/^(?:(\d+):)?(\d+(?:\.\d+)?)$/);
  return m ? (+(m[1] || 0)) * 60 + +m[2] : null;
}

function rosterOptions(selected, fallbackName) {
  const drivers = ui.editing.drivers || [];
  const keys = new Set(drivers.map(driverKey));
  const extra = selected && !keys.has(selected) ? `<option value="${esc(selected)}" selected>${esc(fallbackName || selected)}</option>` : "";
  return `<option value="">Pick a driver…</option>${extra}` + drivers.map((d) => {
    const k = driverKey(d);
    return `<option value="${esc(k)}" ${k === selected ? "selected" : ""}>${d.car_number ? `#${esc(d.car_number)} ` : ""}${esc(d.name || "Unnamed")}</option>`;
  }).join("");
}

function champClassName(id) {
  const cls = (ui.editing.classes || []).find((c) => c.id === id);
  return cls ? cls.name : String(id || "").replace(/^iracing:/, "") || "Overall";
}

function renderChampionship() {
  const has = !!ui.editing;
  $("#champ-empty").hidden = has;
  document.querySelectorAll(".champ-view").forEach((v) => (v.hidden = !has || v.dataset.view !== champ.view));
  document.querySelectorAll("[data-champ-view]").forEach((b) => b.classList.toggle("active", b.dataset.champView === champ.view));
  $("#champ-dirty").hidden = !champ.dirty;
  if (!has) return;
  champData();
  if (champ.view === "standings") renderChampStandings();
  if (champ.view === "rounds") renderChampRounds();
  if (champ.view === "penalties") renderChampPenalties();
  if (champ.view === "rules") renderChampRules();
  if (ui.snap) renderChampLive(ui.snap);
}

// -- standings ----------------------------------------------------------------

function fmtPts(v) {
  return v == null ? "" : Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function renderChampStandings() {
  const st = champ.standings;
  const box = $("#champ-standings");
  if (!st) {
    box.innerHTML = '<p class="hint">Loading…</p>';
    return;
  }
  const rounds = st.rounds.filter((r) => r.scored);
  if (!st.groups.length) {
    box.innerHTML = '<p class="hint">No results yet. Add rounds and their results under <b>Rounds &amp; results</b>.</p>';
    return;
  }
  const head = rounds.map((r, i) => `<th class="c-rd" title="${esc([r.name, r.track, r.date].filter(Boolean).join(" · "))}${r.multiplier !== 1 ? ` (×${r.multiplier})` : ""}">R${i + 1}</th>`).join("");
  const anyLicence = st.groups.some((g) => g.drivers.some((d) => d.licence_points));
  const anyPen = st.groups.some((g) => g.drivers.some((d) => d.penalty_points));
  // Class and overall championships: each table says which points it adds up.
  const rules = (ui.editing && champData().rules) || {};
  const both = rules.scoring === "both" || rules.scoring === "sum";
  const teamPen = st.teams.some((t) => t.penalty_points);
  const teamBasis = both ? ` <span class="hint">${(rules.team_points || "overall") === "class" ? "Drivers' class points" : "Drivers' overall points"}</span>` : "";
  const help = rules.scoring === "both"
    ? "Class and overall are separate championships: each driver scores in their class (on class positions) and overall (on overall positions), and each table adds up its own points. Bonuses and penalties apply in both."
    : rules.scoring === "sum" ? "Each driver's points are their class points plus their overall points, added up; each table ranks those totals. Bonuses count once."
      : "";
  const anySecondary = st.groups.some((g) => g.secondary);
  box.innerHTML = (help ? `<p class="hint">${help}</p>` : "") + st.groups.map((g) => `<div class="champ-group">
      ${g.key || st.groups.length > 1 ? `<div class="champ-group-head" style="--cls:${esc(g.color || "#8b93a3")}">${esc(g.name)}${g.secondary ? ' <span class="badge">SECONDARY CLASS</span>' : ""}${both || anySecondary ? ` <span class="hint">${esc(g.basis)}</span>` : ""}</div>` : ""}
      <div class="table-scroll"><table class="grid champ-table standings-table">
        <thead><tr><th class="c-num">Pos</th><th>Driver</th><th>Team</th>${head}${anyPen ? '<th class="c-num" title="Penalty points taken off">Pen</th>' : ""}${anyLicence ? '<th class="c-num" title="Licence points">Lic</th>' : ""}<th class="c-num">Points</th><th class="c-num">Gap</th></tr></thead>
        <tbody>${g.drivers.map((d) => `<tr>
          <td class="c-num"><b>${d.pos}</b></td>
          <td>${d.car_number ? `<span class="sub">#${esc(d.car_number)}</span> ` : ""}${esc(d.name)}</td>
          <td class="sub">${esc(d.team)}</td>
          ${rounds.map((r) => {
            const s = d.rounds.find((x) => x.round === r.id);
            const res = s && s.result;
            const title = res ? `${res.short ? "Too little of the race covered: DNF, no points. " : ""}${res.rank ? `P${res.rank}` : res.status.toUpperCase()}${Object.keys(res.bonus).length ? ` · bonus: ${Object.entries(res.bonus).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(", ")}` : ""}` : "Didn't take part";
            return `<td class="c-rd ${s && s.dropped ? "dropped" : ""} ${res && res.rank === 1 ? "win" : ""}" title="${esc(title)}${s && s.dropped ? " (dropped)" : ""}">${!res ? "–" : res.status === "dsq" ? "DSQ" : res.status === "dns" ? "DNS" : res.short ? "DNF" : fmtPts(s.points)}</td>`;
          }).join("")}
          ${anyPen ? `<td class="c-num bad">${d.penalty_points ? `−${fmtPts(d.penalty_points)}` : ""}</td>` : ""}
          ${anyLicence ? `<td class="c-num">${d.licence_points || ""}</td>` : ""}
          <td class="c-num"><b>${fmtPts(d.points)}</b></td>
          <td class="c-num sub">${d.behind ? `−${fmtPts(d.behind)}` : ""}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>`).join("") + (st.teams.length ? `<div class="champ-group">
      <div class="champ-group-head">Teams${teamBasis}</div>
      <div class="table-scroll"><table class="grid champ-table"><thead><tr><th class="c-num">Pos</th><th>Team</th><th>Drivers</th>${head}<th class="c-num">Wins</th>${teamPen ? '<th class="c-num" title="Penalty points taken off">Pen</th>' : ""}<th class="c-num">Points</th><th class="c-num">Gap</th></tr></thead>
      <tbody>${st.teams.map((t) => `<tr><td class="c-num"><b>${t.pos}</b></td><td>${esc(t.team)}</td>
        <td class="sub">${t.drivers.map((d) => `${esc(d.name)} (${fmtPts(d.points)})`).join(", ")}</td>
        ${rounds.map((r) => { const x = t.rounds.find((y) => y.round === r.id); return `<td class="c-rd">${x && x.points != null ? fmtPts(x.points) : "–"}</td>`; }).join("")}
        <td class="c-num sub">${t.wins || ""}</td>
        ${teamPen ? `<td class="c-num bad">${t.penalty_points ? `−${fmtPts(t.penalty_points)}` : ""}</td>` : ""}
        <td class="c-num"><b>${fmtPts(t.points)}</b></td><td class="c-num sub">${t.behind ? `−${fmtPts(t.behind)}` : ""}</td></tr>`).join("")}</tbody></table></div>
    </div>` : "");
}

let champLiveKey = "";

function renderChampLive(s) {
  const box = $("#champ-live");
  const c = s.championship;
  const show = c && c.live && ui.editing && s.league && s.league.id === ui.editing.id && champ.view === "standings";
  $("#tile-championship").textContent = c && c.live ? `Live: ${c.round}` : s.league ? `${s.league.name}` : "No league active";
  if (!show) {
    box.hidden = true;
    champLiveKey = "";
    return;
  }
  const key = JSON.stringify(c);
  if (key === champLiveKey) return;
  champLiveKey = key;
  box.hidden = false;
  box.innerHTML = `<h3>Live: ${esc(c.round)} <span class="hint">if the race finished now (from the race order, before stewards)</span></h3>` +
    c.groups.map((g) => `<div class="champ-group">
      ${c.groups.length > 1 || g.key ? `<div class="champ-group-head" style="--cls:${esc(g.color || "#8b93a3")}">${esc(g.name)}</div>` : ""}
      <table class="grid champ-table"><thead><tr><th class="c-num">Pos</th><th></th><th>Driver</th><th class="c-num">In race</th><th class="c-num">Race pts</th><th class="c-num">Before</th><th class="c-num">Live</th><th class="c-num">Gap</th></tr></thead>
      <tbody>${g.drivers.map((d) => {
        const move = d.pos_before ? d.pos_before - d.pos : null;
        return `<tr>
          <td class="c-num"><b>${d.pos}</b></td>
          <td class="c-num ${move > 0 ? "good" : move < 0 ? "bad" : "sub"}">${move ? (move > 0 ? `▲${move}` : `▼${-move}`) : d.pos_before ? "–" : "new"}</td>
          <td>${d.car_number ? `<span class="sub">#${esc(d.car_number)}</span> ` : ""}${esc(d.name)}</td>
          <td class="c-num sub">${d.race_rank ? `P${d.race_rank}` : ""}</td>
          <td class="c-num good">${d.race_points ? `+${fmtPts(d.race_points)}` : ""}</td>
          <td class="c-num sub">${fmtPts(d.points_before)}</td>
          <td class="c-num"><b>${fmtPts(d.points)}</b></td>
          <td class="c-num sub">${d.behind ? `−${fmtPts(d.behind)}` : ""}</td>
        </tr>`;
      }).join("")}</tbody></table></div>`).join("");
}

// -- rounds and results ---------------------------------------------------------

// Points each driver scored in a round; with class and overall
// championships, both ("overall / class").
// What each driver scored in a round, in every championship they're in
// ("Overall 20 · Pro 10 · Rookie Cup 10"; just the points when there's one).
function roundPoints(roundId) {
  const parts = {};
  for (const g of (champ.standings && champ.standings.groups) || []) {
    for (const d of g.drivers) {
      const s = d.rounds.find((x) => x.round === roundId);
      if (!s || !s.result) continue;
      (parts[d.driver] = parts[d.driver] || []).push([g.name, s.result.short ? "DNF" : fmtPts(s.points)]);
    }
  }
  const out = {};
  for (const [driver, list] of Object.entries(parts)) {
    out[driver] = list.length === 1 ? esc(list[0][1])
      : list.map(([name, pts]) => `<span class="pts-part"><span class="sub">${esc(name)}</span> ${esc(pts)}</span>`).join(" ");
  }
  return out;
}

// The season calendar's track list: pick a track, then one of its layouts.
const trackList = { groups: [], status: null, loaded: false };

async function loadTracks(force = false) {
  if (trackList.loaded && !force) return;
  try {
    const r = await api("/api/tracks");
    trackList.groups = r.tracks;
    trackList.status = r;
    trackList.loaded = true;
    $("#track-names").innerHTML = r.tracks.map((g) => `<option value="${esc(g.track)}"></option>`).join("");
    renderTrackStatus();
    if (champ.view === "rounds") renderChampRounds();
  } catch (e) { /* typing a track still works */ }
}

function trackGroup(name) {
  const n = String(name || "").trim().toLowerCase();
  return trackList.groups.find((g) => g.track.toLowerCase() === n);
}

// A round's layout: a list of the track's layouts when it's a known track.
// ``attrs`` says which field it is (data-round / data-build-row...).
function configField(rd, attrs) {
  const g = trackGroup(rd.track);
  if (!g) {
    return `<input ${attrs} value="${esc(rd.config || "")}" placeholder="Configuration" aria-label="Configuration">`;
  }
  const configs = g.configs.map((c) => c.config);
  const current = rd.config || "";
  const extra = current && !configs.includes(current) ? `<option selected>${esc(current)}</option>`
    : !current && !configs.includes("") ? '<option value="" selected>Pick a layout</option>' : "";
  return `<select ${attrs} aria-label="Configuration">${extra}${configs.map((c) =>
    `<option value="${esc(c)}" ${c === current ? "selected" : ""}>${esc(c || "(one layout)")}</option>`).join("")}</select>`;
}

function renderTrackStatus() {
  const st = trackList.status;
  if (!st) return;
  $("#track-source").textContent = st.official
    ? `${st.official} official layouts from iRacing${st.seen ? `, plus ${st.seen} seen in sessions` : ""}. A track not in the list can be typed in.`
    : `Built-in list of iRacing tracks${st.seen ? `, plus ${st.seen} layouts seen in sessions` : ""}. A track not in the list can be typed in.`;
}

function renderChampRounds() {
  loadTracks();
  const c = champData();
  const classes = ui.editing.classes || [];
  const cards = c.rounds.map((rd, i) => {
    const open = champ.open.has(rd.id);
    const isLive = c.live_round ? c.live_round === rd.id : c.rounds.find((r) => !(r.results || []).length) === rd;
    const pts = roundPoints(rd.id);
    const classIds = [...new Set([...classes.filter((x) => !isSecondary(x)).map((x) => x.id), ...(rd.results || []).map((r) => r.class_id).filter(Boolean)])];
    const results = (rd.results || []).map((r, j) => [r, j]).sort((a, b) => (a[0].position || 999) - (b[0].position || 999));
    return `<div class="round-card ${open ? "open" : ""}">
      <div class="round-head">
        <span class="round-num">R${i + 1}</span>
        <input data-round="${i}" data-rkey="name" value="${esc(rd.name)}" placeholder="Round name" aria-label="Round name">
        <input data-round="${i}" data-rkey="track" class="track-input" list="track-names" value="${esc(rd.track || "")}" placeholder="Track (type to search)" aria-label="Track">
        ${configField(rd, `data-round="${i}" data-rkey="config"`)}
        <input type="date" data-round="${i}" data-rkey="date" value="${esc(rd.date || "")}" aria-label="Date">
        <input type="time" data-round="${i}" data-rkey="time" value="${esc(rd.time || "")}" aria-label="Start time" title="Start time">
        <input data-round="${i}" data-rkey="length" class="narrow-text" value="${esc(rd.length || "")}" placeholder="Length" aria-label="Race length" title="e.g. 60 min, 30 laps">
        <label class="field" title="Points multiplier: 1 for normal points, 2 for double points, and so on">Points ×<input type="number" class="narrow" min="0" max="10" step="0.5" data-round="${i}" data-rkey="multiplier" value="${rd.multiplier ?? 1}"></label>
        <label class="field" title="This round always counts, even with drop rounds"><input type="checkbox" data-round="${i}" data-rkey="no_drop" ${rd.no_drop ? "checked" : ""}> Can't drop</label>
        <label class="field" title="The race in progress counts as this round in the live standings"><input type="radio" name="live-round" data-live-round="${esc(rd.id)}" ${isLive ? "checked" : ""}> Live</label>
        <span class="grow"></span>
        <span class="sub">${(rd.results || []).length ? `${rd.results.length} results` : "No results"}</span>
        <button class="btn" data-round-toggle="${esc(rd.id)}">${open ? "Close" : "Results"}</button>
        <button class="btn" data-round-import="${i}" title="Fill this round with the results of the race session you're in">⤓ Import from session</button>
        ${rd.event ? "" : `<button class="btn subtle" data-round-meeting="${i}" title="Make this round a race meeting of several races (heat races, say), each a round of its own. Its results stay with the first race.">⇉ Race meeting</button>`}
        <button class="btn icon danger" data-round-delete="${i}" title="Delete round">✕</button>
      </div>
      ${open ? `<div class="row transfer-row"><span class="hint">This round's results:</span>
        <button class="btn subtle" data-export="round" data-export-round="${esc(rd.id)}" title="To import into a round, here or on another PC">⤓ Export</button>
        <button class="btn subtle" data-export="round_csv" data-export-round="${esc(rd.id)}" title="As a spreadsheet (CSV)">⤓ CSV</button>
        <label class="btn subtle" title="From a round export (.json) or a CSV with the same columns as the CSV export">⤒ Import…<input type="file" accept=".json,.csv,application/json,text/csv" data-import="round" data-import-round="${esc(rd.id)}" hidden></label>
      </div>
      <div class="table-scroll"><table class="grid champ-table results-table">
        <thead><tr><th class="c-num">Pos</th><th>Driver</th><th>Class</th><th class="c-num">Start</th><th class="c-num">Laps</th><th class="c-num">Led</th><th>Fastest lap</th><th class="c-num">Inc</th><th>Status</th><th class="c-num" title="Extra points given (+) or taken (−) for this round">+/− pts</th><th class="c-num" title="Points scored in each championship (after saving)">Pts</th><th></th></tr></thead>
        <tbody>${results.map(([r, j]) => `<tr>
          <td><input type="number" class="c-num" min="1" data-round="${i}" data-res="${j}" data-key="position" value="${r.position ?? ""}"></td>
          <td><select data-round="${i}" data-res="${j}" data-key="driver">${rosterOptions(r.driver, r.name)}</select></td>
          <td><select data-round="${i}" data-res="${j}" data-key="class_id"><option value="">—</option>${classIds.map((id) => `<option value="${esc(id)}" ${id === r.class_id ? "selected" : ""}>${esc(champClassName(id))}</option>`).join("")}</select></td>
          <td><input type="number" class="c-num" min="1" data-round="${i}" data-res="${j}" data-key="start_position" value="${r.start_position ?? ""}"></td>
          <td><input type="number" class="c-num" min="0" data-round="${i}" data-res="${j}" data-key="laps" value="${r.laps ?? 0}"></td>
          <td><input type="number" class="c-num" min="0" data-round="${i}" data-res="${j}" data-key="laps_led" value="${r.laps_led ?? 0}"></td>
          <td><input class="lap-input" data-round="${i}" data-res="${j}" data-key="fastest_lap" value="${r.fastest_lap ? fmtLap(r.fastest_lap) : ""}" placeholder="1:28.123"></td>
          <td><input type="number" class="c-num" min="0" data-round="${i}" data-res="${j}" data-key="incidents" value="${r.incidents ?? 0}"></td>
          <td><select data-round="${i}" data-res="${j}" data-key="status">${STATUS_NAMES.map(([v, l]) => `<option value="${v}" ${v === r.status ? "selected" : ""}>${l}</option>`).join("")}</select></td>
          <td><input type="number" class="c-num" step="0.5" data-round="${i}" data-res="${j}" data-key="adjust" value="${r.adjust || 0}"></td>
          <td class="c-num"><b>${pts[r.driver] ?? ""}</b></td>
          <td><button class="btn icon danger" data-res-delete="${j}" data-round="${i}" title="Remove">✕</button></td>
        </tr>`).join("")}</tbody></table></div>
        <button class="btn subtle" data-res-add="${i}">+ Add result</button>` : ""}
    </div>`;
  });
  // A race meeting's rounds (next to each other, same event) go in one box.
  const html = [];
  for (let i = 0; i < c.rounds.length;) {
    const ev = c.rounds[i].event;
    let j = i + 1;
    while (ev && j < c.rounds.length && c.rounds[j].event === ev) j++;
    html.push(ev ? meetingHtml(i, j - 1, cards.slice(i, j).join("")) : cards[i]);
    i = j;
  }
  $("#champ-rounds").innerHTML = html.join("") || '<p class="hint">No rounds yet.</p>';
}

function meetingHtml(first, last, inner) {
  const c = champData();
  const n = last - first + 1;
  return `<div class="meeting">
    <div class="meeting-head">
      <span class="badge">RACE MEETING</span>
      <input data-meeting="${first}" value="${esc(c.rounds[first].event)}" aria-label="Race meeting name" title="Rename the meeting (empty: its races become separate rounds)">
      <span class="sub">${n} race${n === 1 ? "" : "s"} · round${n === 1 ? "" : "s"} ${first + 1}${n > 1 ? `–${last + 1}` : ""}</span>
      <span class="grow"></span>
      <button class="btn" data-meeting-import="${first}" title="Each race session of the event you're in (heats, then the feature...) into these races, in order">⤓ Import every race from session</button>
      <button class="btn subtle" data-meeting-add="${last}">+ Add a race</button>
      <button class="btn subtle" data-meeting-split="${first}" title="Its races become separate rounds again">Separate rounds</button>
    </div>
    ${inner}
  </div>`;
}

// The rounds of the race meeting starting at round ``first``.
function meetingRounds(first) {
  const c = champData();
  const ev = c.rounds[first].event;
  const out = [];
  for (let i = first; i < c.rounds.length && c.rounds[i].event === ev; i++) out.push(c.rounds[i]);
  return out;
}

async function importMeeting(rounds) {
  if (rounds.some((rd) => (rd.results || []).length) && !confirm("Replace the results already in these races with the session's?")) return;
  try {
    const saved = await saveEditor();
    const r = await api(`/api/leagues/${encodeURIComponent(saved.id)}/championship/import-meeting`,
      { method: "POST", body: { round_ids: rounds.map((rd) => rd.id) } });
    openEditor(r.league);
    const list = r.imported.map((x) => `${x.race} → ${x.round} (${x.count})`).join(", ");
    const more = r.races > r.rounds ? ` The session has ${r.races} races but the meeting ${r.rounds}: add a race for the rest.` : "";
    toast(`Imported ${list}${r.added ? `; ${r.added} new drivers added to the roster` : ""}.${more}`);
  } catch (err) {
    toast(err.message, true);
  }
}

// -- penalties -------------------------------------------------------------------

function renderChampPenalties() {
  const c = champData();
  const names = {};
  for (const rd of c.rounds) for (const r of rd.results || []) names[r.driver] = r.name;
  $("#champ-penalties").innerHTML = c.penalties.length ? c.penalties.map((p, i) => `<tr>
      <td><select data-pen="${i}" data-key="driver">${rosterOptions(p.driver, names[p.driver])}</select></td>
      <td><select data-pen="${i}" data-key="round_id"><option value="">—</option>${c.rounds.map((rd, k) =>
        `<option value="${esc(rd.id)}" ${rd.id === p.round_id ? "selected" : ""}>R${k + 1} ${esc(rd.name)}</option>`).join("")}</select></td>
      <td><input type="number" class="c-num" min="0" step="0.5" data-pen="${i}" data-key="points" value="${p.points || 0}"></td>
      <td><input type="number" class="c-num" min="0" data-pen="${i}" data-key="licence" value="${p.licence || 0}"></td>
      <td><input class="grow" data-pen="${i}" data-key="reason" value="${esc(p.reason || "")}" placeholder="e.g. Avoidable contact, T1 lap 1"></td>
      <td><button class="btn icon danger" data-pen-delete="${i}" title="Remove">✕</button></td>
    </tr>`).join("") : '<tr><td colspan="6" class="hint">No penalties.</td></tr>';
}

// -- rules -------------------------------------------------------------------------

const SCORING_HELP = {
  class: "Each class is a championship of its own, scored on class finishing positions with the class points.",
  overall: "One championship for everyone, scored on overall finishing positions with the overall points.",
  both: "Every race scores twice, each with its own points: a driver's class position in their class's championship (class points) and their overall position in the overall championship (overall points). Each has its own table and board.",
  sum: "Each driver scores once a race: the class points for their class position plus the overall points for their overall position, added up. Each class's table and the overall table rank those totals.",
};

// A points table for any class that scores differently (empty = the class points above).
function classPointsFields(r) {
  const classes = (ui.editing && ui.editing.classes) || [];
  const scored = classes.filter((c) => isSecondary(c) || (r.scoring || "class") !== "overall");
  if (!scored.length) return "";
  const own = r.class_points || {};
  return `<details class="wide class-points" ${Object.keys(own).length ? "open" : ""}><summary>Different points for a class</summary>
    <p class="hint">Leave a class empty to use the points for each finishing position above. Secondary classes rank their
      drivers by where they finished among each other.</p>
    <div class="class-points-grid">${scored.map((c) => `<label class="ov-field">${esc(c.name || "Unnamed")}${isSecondary(c) ? " (secondary)" : ""}
      <input data-class-points="${esc(c.id)}" value="${esc((own[c.id] || []).join(", "))}" placeholder="Same as above"></label>`).join("")}</div>
  </details>`;
}

// How each secondary class scores (rules.secondary_scoring, by class id).
function secondaryScoringFields(r) {
  const sec = ((ui.editing && ui.editing.classes) || []).filter(isSecondary);
  if (!sec.length) return "";
  const how = r.secondary_scoring || {};
  return `<div class="wide secondary-scoring"><h3 class="section-title">Secondary classes</h3>
    <div class="class-points-grid">${sec.map((c) => `<label class="ov-field">${esc(c.name || "Unnamed")} scores
      <select data-secondary-scoring="${esc(c.id)}">${[["own", "On where its drivers finish among each other"],
        ["class", "The points its drivers score in their own class"], ["overall", "The points its drivers score overall"]]
        .map(([v, l]) => `<option value="${v}" ${(how[c.id] || "own") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>`).join("")}</div>
    <p class="hint">A driver in a secondary class scores in it as well as in their main class (and overall), each on its
      own points. "Among each other" uses the class's own points table above, or the class points.</p></div>`;
}

function renderChampRules() {
  const r = champData().rules;
  const b = r.bonuses || {};
  const scoring = r.scoring || "class";
  const hasClass = scoring !== "overall";
  const hasOverall = scoring !== "class";
  const secondary = ((ui.editing && ui.editing.classes) || []).some(isSecondary);
  const overallPts = (r.overall_points || []).length ? r.overall_points : r.points || [];
  $("#champ-rules").innerHTML = `
    <h3 class="section-title wide">Championships</h3>
    <div class="wide champ-kinds">
      <div class="champ-kind ${hasClass ? "on" : ""}">
        <label class="check"><input type="checkbox" data-champ-kind="class" ${hasClass ? "checked" : ""}> <b>Class championships</b>
          <span class="hint">a championship for each class, scored on class finishing positions</span></label>
        ${hasClass || secondary ? `<label class="ov-field">${hasClass ? "Class points" : "Points for the secondary classes"} (1st, 2nd, 3rd… in class)
          <input data-rule="points" value="${esc((r.points || []).join(", "))}"></label>` : ""}
      </div>
      <div class="champ-kind ${hasOverall ? "on" : ""}">
        <label class="check"><input type="checkbox" data-champ-kind="overall" ${hasOverall ? "checked" : ""}> <b>Overall championship</b>
          <span class="hint">everyone together, scored on overall finishing positions, with its own points</span></label>
        ${hasOverall ? `<label class="ov-field">Overall points (1st, 2nd, 3rd… overall)
          <input data-rule="overall_points" value="${esc(overallPts.join(", "))}"></label>` : ""}
      </div>
      ${hasClass && hasOverall ? `<label class="ov-field">Class and overall points count
        <select data-rule="scoring">${[["both", "As two separate championships"], ["sum", "Added together into one total"]].map(([v, l]) =>
          `<option value="${v}" ${scoring === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>` : ""}
      <p class="hint">${esc(SCORING_HELP[scoring])}</p>
    </div>
    ${classPointsFields(r)}
    ${secondaryScoringFields(r)}
    <label class="ov-field wide">Qualifying points (pole, 2nd, 3rd…; leave empty for none). Uses the starting grid.
      <input data-rule="qualifying_points" value="${esc((r.qualifying_points || []).join(", "))}"></label>
    <label class="ov-field">Drop rounds (each driver's worst N don't count)
      <input type="number" min="0" max="50" data-rule="drop_rounds" value="${r.drop_rounds || 0}"></label>
    <label class="ov-field">Fastest-lap bonus only in the top N (0 = anyone)
      <input type="number" min="0" data-rule="fastest_lap_top" value="${r.fastest_lap_top || 0}"></label>
    <label class="ov-field">Must complete this % of the race (their class winner's laps) to score; anyone short is a DNF with no points (0 = off)
      <input type="number" min="0" max="100" data-rule="classified_pct" value="${r.classified_pct ?? 75}"></label>
    <label class="ov-field">Team championship: best N drivers per team each round (0 = all)
      <input type="number" min="0" max="20" data-rule="team_best" value="${r.team_best || 0}"></label>
    ${r.scoring === "both" ? `<label class="ov-field">Team championship counts its drivers'
      <select data-rule="team_points">${[["overall", "Overall points"], ["class", "Class points"]].map(([v, l]) =>
        `<option value="${v}" ${(r.team_points || "overall") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>` : ""}
    <label class="ov-field check"><input type="checkbox" data-rule="dnf_scores" ${r.dnf_scores !== false ? "checked" : ""}> DNFs score the points for where they're classified</label>
    <h3 class="section-title wide">Bonus points <span class="hint">(0 = not used; negative numbers take points off)</span></h3>
    ${champ.bonuses.map(([k, label]) => `<label class="ov-field">${esc(label)}
      <input type="number" step="0.5" data-bonus="${k}" value="${b[k] || 0}"></label>`).join("")}`;
}

// -- editing -------------------------------------------------------------------------

function champChange(e, final) {
  const el = e.target;
  const c = champData();
  const d = el.dataset;
  let rerender = false;
  if (d.champKind) {
    // Class and / or overall championships (at least one).
    if (!final) return;
    const r = c.rules;
    const scoring = r.scoring || "class";
    const want = { class: scoring !== "overall", overall: scoring !== "class", [d.champKind]: el.checked };
    if (!want.class && !want.overall) {
      el.checked = true;
      return toast("There has to be a class or an overall championship", true);
    }
    // A new overall championship starts from the class points, as its own copy.
    if (want.overall && !(r.overall_points || []).length) r.overall_points = [...(r.points || [])];
    r.scoring = want.class && want.overall ? (scoring === "sum" ? "sum" : "both") : want.class ? "class" : "overall";
    rerender = true;
  } else if (d.rule) {
    const r = c.rules;
    if (d.rule === "points" || d.rule === "qualifying_points" || d.rule === "overall_points") {
      if (!final) return;
      r[d.rule] = el.value.split(/[\s,;]+/).filter(Boolean).map(Number).filter((n) => !isNaN(n) && n >= 0);
      rerender = true;
    } else if (el.type === "checkbox") r[d.rule] = el.checked;
    else r[d.rule] = el.type === "number" ? +el.value : el.value;
    if (d.rule === "scoring" && final) rerender = true;
  } else if (d.secondaryScoring) {
    if (!final) return;
    c.rules.secondary_scoring = { ...(c.rules.secondary_scoring || {}), [d.secondaryScoring]: el.value };
    if (el.value === "own") delete c.rules.secondary_scoring[d.secondaryScoring];
    rerender = true;
  } else if (d.classPoints) {
    if (!final) return;
    const pts = el.value.split(/[\s,;]+/).filter(Boolean).map(Number).filter((n) => !isNaN(n) && n >= 0);
    c.rules.class_points = { ...(c.rules.class_points || {}) };
    if (pts.length) c.rules.class_points[d.classPoints] = pts;
    else delete c.rules.class_points[d.classPoints];
    rerender = true;
  } else if (d.bonus) {
    c.rules.bonuses = c.rules.bonuses || {};
    c.rules.bonuses[d.bonus] = +el.value || 0;
  } else if (d.liveRound) {
    c.live_round = d.liveRound;
  } else if (d.pen != null) {
    c.penalties[+d.pen][d.key] = el.type === "number" ? +el.value : el.value;
  } else if (d.res != null) {
    const r = c.rounds[+d.round].results[+d.res];
    if (d.key === "fastest_lap") {
      if (!final) return;
      r.fastest_lap = parseLapTime(el.value);
      rerender = true;
    } else if (d.key === "driver") {
      r.driver = el.value;
      const dr = (ui.editing.drivers || []).find((x) => driverKey(x) === el.value);
      r.name = dr ? dr.name : r.name;
    } else if (el.type === "number") {
      r[d.key] = el.value === "" ? null : +el.value;
      rerender = final && d.key === "position";
    } else r[d.key] = el.value;
  } else if (d.meeting != null) {
    if (!final) return;
    for (const rd of meetingRounds(+d.meeting)) rd.event = el.value.trim();
    rerender = true;
  } else if (d.round != null && d.rkey) {
    const rd = c.rounds[+d.round];
    rd[d.rkey] = el.type === "checkbox" ? el.checked : el.type === "number" ? +el.value : el.value;
    if (d.rkey === "track" || d.rkey === "config") {
      // A known track: its layouts fill the Configuration list.
      const g = trackGroup(rd.track);
      if (g && d.rkey === "track" && final) rd.config = g.configs[0].config;
      const layout = g && g.configs.find((x) => x.config === rd.config);
      rd.track_id = layout ? layout.id : null;
      if (final) rerender = true;
    }
  } else return;
  markChampDirty();
  if (rerender) renderChampionship();
}

$("#tab-championship").addEventListener("input", (e) => champChange(e, false));
$("#tab-championship").addEventListener("change", (e) => {
  if (e.target.classList.contains("league-picker")) return;
  champChange(e, true);
});

$("#tab-championship").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b || !ui.editing) return;
  const d = b.dataset;
  const c = champData();
  if (d.champView) {
    champ.view = d.champView;
    champLiveKey = "";
    return renderChampionship();
  }
  if (d.roundToggle) {
    champ.open.has(d.roundToggle) ? champ.open.delete(d.roundToggle) : champ.open.add(d.roundToggle);
    return renderChampionship();
  }
  if (d.roundDelete != null) {
    const rd = c.rounds[+d.roundDelete];
    if (!confirm(`Delete ${rd.name} and its results?`)) return;
    c.rounds.splice(+d.roundDelete, 1);
    c.penalties = c.penalties.filter((p) => p.round_id !== rd.id);
    if (c.live_round === rd.id) c.live_round = "";
  } else if (d.resAdd != null) {
    const rd = c.rounds[+d.resAdd];
    rd.results = rd.results || [];
    const next = Math.max(0, ...rd.results.map((r) => r.position || 0)) + 1;
    rd.results.push({ driver: "", name: "", class_id: "", position: next, start_position: null, laps: 0, laps_led: 0,
      fastest_lap: null, incidents: 0, status: "finished", adjust: 0 });
  } else if (d.resDelete != null) {
    c.rounds[+d.round].results.splice(+d.resDelete, 1);
  } else if (d.penDelete != null) {
    c.penalties.splice(+d.penDelete, 1);
  } else if (d.roundImport != null) {
    return importRound(c.rounds[+d.roundImport]);
  } else if (d.meetingImport != null) {
    return importMeeting(meetingRounds(+d.meetingImport));
  } else if (d.roundMeeting != null) {
    const races = askRaces();
    if (!races) return;
    toMeeting(c, +d.roundMeeting, races);
  } else if (d.meetingSplit != null) {
    const ev = c.rounds[+d.meetingSplit].event;
    for (const rd of meetingRounds(+d.meetingSplit)) {
      rd.name = `${ev} · ${rd.name}`;
      rd.event = "";
    }
  } else if (d.meetingAdd != null) {
    const last = c.rounds[+d.meetingAdd];
    const n = meetingRounds(c.rounds.findIndex((r) => r.event === last.event)).length;
    c.rounds.splice(+d.meetingAdd + 1, 0, { ...last, id: newId(), name: `Race ${n + 1}`, results: [], session: "" });
  } else return;
  markChampDirty();
  renderChampionship();
});

$("#btn-add-round").addEventListener("click", () => {
  if (!ui.editing) return toast("Pick a league first", true);
  const c = champData();
  c.rounds.push({ id: newId(), name: `Round ${c.rounds.length + 1}`, track: "", date: "", multiplier: 1, no_drop: false, results: [] });
  markChampDirty();
  renderChampionship();
});

// How many races at a race meeting (null: cancelled).
function askRaces() {
  const n = parseInt(prompt("How many races at the meeting? Each race is a round of its own.", "3"), 10);
  return n >= 2 && n <= 10 ? n : null;
}

// A name for a new race meeting made from round ``i``: the round's own name,
// unless it's just "Round 3" (each race is a round, so that would confuse):
// "Event 3", by where it is in the calendar (a meeting counts once).
function meetingName(c, i) {
  const used = new Set(c.rounds.filter((r) => r.event).map((r) => r.event));
  const own = String(c.rounds[i].name || "").trim();
  if (own && !/^round \d+$/i.test(own) && !used.has(own)) return own;
  let n = 1;
  for (let k = 0; k < i; k++) if (!c.rounds[k].event || c.rounds[k].event !== (c.rounds[k + 1] || {}).event) n++;
  while (used.has(`Event ${n}`)) n++;
  return `Event ${n}`;
}

// Round ``i`` becomes the first race of a meeting of ``races`` races (it keeps
// its results, penalties and session); the rest are new rounds after it, at
// the same track, date and time.
function toMeeting(c, i, races) {
  const rd = c.rounds[i];
  if (!rd.event) {
    rd.event = meetingName(c, i);
    rd.name = "Race 1";
  }
  const more = [];
  for (let k = 2; k <= races; k++) more.push({ ...rd, id: newId(), name: `Race ${k}`, results: [], session: "" });
  c.rounds.splice(i + 1, 0, ...more);
}

$("#btn-all-meetings").addEventListener("click", () => {
  if (!ui.editing) return toast("Pick a league first", true);
  const c = champData();
  const single = c.rounds.map((rd, i) => [rd, i]).filter(([rd]) => !rd.event);
  if (!single.length) return toast("Every round is a race meeting already");
  const races = askRaces();
  if (!races) return;
  // Named in order (Event 1, Event 2...), then filled in from the end so the
  // rounds still to fill keep their places.
  for (const [rd, i] of single) {
    rd.event = meetingName(c, i);
    rd.name = "Race 1";
  }
  for (const [, i] of single.reverse()) toMeeting(c, i, races);
  markChampDirty();
  renderChampionship();
  toast(`${single.length} round${single.length === 1 ? "" : "s"} made race meetings of ${races} races. Save to keep them.`);
});

$("#btn-add-meeting").addEventListener("click", () => {
  if (!ui.editing) return toast("Pick a league first", true);
  const n = parseInt(prompt("How many races at this meeting? Each race is a round of its own.", "3"), 10);
  if (!(n >= 1 && n <= 10)) return;
  const c = champData();
  const event = `Event ${new Set(c.rounds.filter((r) => r.event).map((r) => r.event)).size + 1}`;
  for (let k = 1; k <= n; k++) {
    c.rounds.push({ id: newId(), event, name: `Race ${k}`, track: "", date: "", multiplier: 1, no_drop: false, results: [] });
  }
  markChampDirty();
  renderChampionship();
});

// -- building the rounds from a calendar ------------------------------------------
// From a scanned calendar image or pasted text: the server finds the rounds,
// they're checked and corrected here, then made.

const build = { mode: null, busy: "", rounds: null, text: "", races: 1, raceName: "Race", replace: false, note: "" };

// 22/11 or 11/22: what this PC's language writes (a date that can only be one decides anyway).
const dayFirst = () => !/^en-US|^en-CA|^es-US|^fil/.test(navigator.language || "");

function renderBuild() {
  const box = $("#build-step");
  if (!box) return;
  if (build.busy) {
    box.innerHTML = `<p class="hint">${esc(build.busy)}</p>`;
    return;
  }
  let html = "";
  if (build.mode === "paste" && !build.rounds) {
    html = `<textarea data-b="text" rows="8" placeholder="Paste the calendar here, e.g.&#10;Round 1 - Spa - Sun 8th November - 8PM - 60 min&#10;Round 2 - Monza - 15/11/26 - 20:00 - 45 mins">${esc(build.text)}</textarea>
      <div class="row"><button class="btn primary" data-build="read">Find the rounds</button></div>`;
  }
  if (build.rounds) html += buildReviewHtml();
  box.innerHTML = html;
}

function buildReviewHtml() {
  const rows = build.rounds;
  if (!rows.length) {
    return `<p class="hint">No rounds found${build.mode === "scan" ? " in the image" : ""}: the track names have to be readable.
      ${build.text ? 'Correct the text below and try again.' : ""}</p>${build.text ? `<textarea data-b="text" rows="8">${esc(build.text)}</textarea>
      <div class="row"><button class="btn primary" data-build="read">Find the rounds</button></div>` : ""}`;
  }
  const races = Math.max(1, Math.min(10, build.races | 0));
  const total = rows.length * races;
  const c = champData();
  const unscored = c.rounds.filter((r) => !(r.results || []).length).length;
  return `${build.note ? `<p class="hint">${esc(build.note)}</p>` : ""}
    <div class="table-scroll"><table class="grid build-table">
      <thead><tr><th>Name</th><th>Track</th><th>Layout</th><th>Date</th><th>Time</th><th>Length</th><th></th></tr></thead>
      <tbody>${rows.map((r, i) => `<tr class="${r.unknown_track ? "warn" : ""}" title="${esc(r.text || "")}">
        <td><input data-build-row="${i}" data-bkey="name" value="${esc(r.name)}"></td>
        <td><input data-build-row="${i}" data-bkey="track" list="track-names" value="${esc(r.track)}" placeholder="Track"
          ${r.unknown_track ? 'title="Not in the track list: check it"' : ""}></td>
        <td>${configField(r, `data-build-row="${i}" data-bkey="config"`)}</td>
        <td><input type="date" data-build-row="${i}" data-bkey="date" value="${esc(r.date)}"></td>
        <td><input type="time" data-build-row="${i}" data-bkey="time" value="${esc(r.time)}"></td>
        <td><input class="narrow-text" data-build-row="${i}" data-bkey="length" value="${esc(r.length)}" placeholder="60 min"></td>
        <td><button class="btn icon danger" data-build-remove="${i}" title="Leave this one out">✕</button></td>
      </tr>`).join("")}</tbody></table></div>
    <div class="row build-options">
      <label class="field" title="For leagues that run several races a night (heat races, say) and count each as a round">Races at each
        <input type="number" class="narrow" min="1" max="10" data-b="races" value="${races}"></label>
      <label class="field" ${races > 1 ? "" : "hidden"}>called <select data-b="raceName">${["Race", "Heat"].map((n) =>
        `<option ${build.raceName === n ? "selected" : ""}>${n}</option>`).join("")}</select> 1, 2…</label>
      <label class="field"><input type="checkbox" data-b="replace" ${build.replace ? "checked" : ""}> Replace the ${unscored} round${unscored === 1 ? "" : "s"} without results</label>
      <span class="grow"></span>
      <button class="btn subtle" data-build="cancel">Cancel</button>
      <button class="btn primary" data-build="create">Make ${total} round${total === 1 ? "" : "s"}</button>
    </div>
    ${races > 1 ? `<p class="hint">Each calendar entry becomes a race meeting of ${races} races, each a round of its own for the points;
      the calendar board shows the meeting as one.</p>` : ""}`;
}

function buildFound(data, mode, note) {
  build.busy = "";
  build.mode = mode;
  build.rounds = (data.rounds || []).map((r) => ({ ...r }));
  if (data.text != null) build.text = data.text;
  build.note = note || "";
  renderBuild();
}

// The image as a PNG the reader can use: SVG and WebP drawn out, small ones
// enlarged, and a see-through background filled to contrast with the text.
async function imagePng(src) {
  const img = new Image();
  img.src = src;
  await img.decode();
  const w0 = img.naturalWidth || 1600, h0 = img.naturalHeight || 900;
  const scale = Math.max(1, Math.min(3, 2000 / Math.max(w0, h0)));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w0 * scale);
  canvas.height = Math.round(h0 * scale);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  const px = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  let light = 0, solid = 0, see = 0;
  for (let i = 0; i < px.length; i += 4 * 97) {
    if (px[i + 3] < 200) { see++; continue; }
    solid++;
    if (px[i] * 0.3 + px[i + 1] * 0.59 + px[i + 2] * 0.11 > 128) light++;
  }
  if (see) {
    // Light text on a see-through background needs a dark one, and dark text a light one.
    const back = document.createElement("canvas");
    back.width = canvas.width;
    back.height = canvas.height;
    const b = back.getContext("2d");
    b.fillStyle = solid && light / solid > 0.5 ? "#000" : "#fff";
    b.fillRect(0, 0, back.width, back.height);
    b.drawImage(canvas, 0, 0);
    return new Promise((ok) => back.toBlob(ok, "image/png"));
  }
  return new Promise((ok) => canvas.toBlob(ok, "image/png"));
}

async function scanImage(src) {
  build.mode = "scan";
  build.rounds = null;
  build.busy = "Reading the calendar… (this can take a few seconds)";
  renderBuild();
  try {
    const png = await imagePng(src);
    const res = await fetch(`/api/calendar/scan?day_first=${dayFirst() ? 1 : 0}`, { method: "POST", headers: { "Content-Type": "image/png" }, body: png });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || "Couldn't read the image");
    buildFound(data, "scan", "Read from the image: check every round (tracks the list didn't know are marked), then make them.");
  } catch (err) {
    build.busy = "";
    build.mode = "paste";
    renderBuild();
    toast(err.message, true);
  }
}

$("#build-rounds").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-build], [data-build-remove]");
  if (!b || !ui.editing) return;
  if (b.dataset.buildRemove != null) {
    build.rounds.splice(+b.dataset.buildRemove, 1);
    return renderBuild();
  }
  const what = b.dataset.build;
  try {
    if (what === "scan") {
      if (!ui.editing.calendar_image) return toast("Add the calendar image in the League builder (Logos tab), or choose an image to scan", true);
      return scanImage(logoSrc(ui.editing.calendar_image));
    } else if (what === "paste") {
      build.mode = "paste";
      build.rounds = null;
    } else if (what === "read") {
      build.text = $("#build-step [data-b=text]").value;
      build.busy = "Finding the rounds…";
      renderBuild();
      const data = await api("/api/calendar/parse", { method: "POST", body: { text: build.text, day_first: dayFirst() } });
      return buildFound({ ...data, text: build.text }, "paste", "Found in the text: check every round, then make them.");
    } else if (what === "cancel") {
      Object.assign(build, { mode: null, rounds: null, note: "" });
    } else if (what === "create") {
      return createBuiltRounds();
    }
  } catch (err) {
    build.busy = "";
    toast(err.message, true);
  }
  renderBuild();
});

$("#build-scan-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file || !ui.editing) return;
  const url = URL.createObjectURL(file);
  scanImage(url).finally(() => URL.revokeObjectURL(url));
});

$("#build-rounds").addEventListener("change", (e) => {
  const el = e.target;
  if (el.dataset.buildRow != null) {
    const r = build.rounds[+el.dataset.buildRow];
    r[el.dataset.bkey] = el.value;
    if (el.dataset.bkey === "track") {
      const g = trackGroup(r.track);
      r.config = g ? g.configs[0].config : r.config;
      r.unknown_track = !g;
    }
    if (el.dataset.bkey === "track" || el.dataset.bkey === "config") {
      const g = trackGroup(r.track);
      const layout = g && g.configs.find((x) => x.config === r.config);
      r.track_id = layout ? layout.id : null;
      renderBuild();
    }
    return;
  }
  const key = el.dataset.b;
  if (key === "races") build.races = Math.max(1, Math.min(10, +el.value || 1));
  else if (key === "raceName") build.raceName = el.value;
  else if (key === "replace") build.replace = el.checked;
  else if (key === "text") return void (build.text = el.value);  // no redraw: the click on Find would be lost
  else return;
  renderBuild();
});

function createBuiltRounds() {
  const c = champData();
  const races = Math.max(1, Math.min(10, build.races | 0));
  const made = [];
  let meetings = new Set(c.rounds.filter((r) => r.event).map((r) => r.event)).size;
  for (const r of build.rounds) {
    // Each race is a "round", so a meeting called "Round 2" would confuse: "Event 2".
    const event = races > 1 ? (/^round \d+$/i.test(r.name.trim()) ? `Event ${++meetings}` : r.name) : "";
    for (let k = 1; k <= races; k++) {
      made.push({
        id: newId(), name: races > 1 ? `${build.raceName} ${k}` : r.name, event,
        track: r.track, config: r.config || "", track_id: r.track_id ?? null, date: r.date, time: r.time, length: r.length,
        multiplier: 1, no_drop: false, results: [],
      });
    }
  }
  if (build.replace) {
    const gone = new Set(c.rounds.filter((r) => !(r.results || []).length).map((r) => r.id));
    c.rounds = c.rounds.filter((r) => !gone.has(r.id));
    c.penalties = c.penalties.filter((p) => !gone.has(p.round_id));
    if (gone.has(c.live_round)) c.live_round = "";
  }
  c.rounds.push(...made);
  Object.assign(build, { mode: null, rounds: null, note: "" });
  $("#build-rounds").open = false;
  markChampDirty();
  renderChampionship();
  renderBuild();
  toast(`Made ${made.length} rounds. Save to keep them.`);
}

$("#btn-add-penalty").addEventListener("click", () => {
  if (!ui.editing) return toast("Pick a league first", true);
  const c = champData();
  c.penalties.push({ id: newId(), driver: "", round_id: c.rounds.length ? c.rounds[c.rounds.length - 1].id : "", points: 0, licence: 0, reason: "" });
  markChampDirty();
  renderChampionship();
});

async function saveChampionship() {
  // Unfinished rows (no driver picked) would be dropped on save: say so.
  const c = champData();
  const blank = c.rounds.some((rd) => (rd.results || []).some((r) => !r.driver)) || c.penalties.some((p) => !p.driver);
  if (blank && !confirm("Results or penalties without a driver will be removed when saving. Save anyway?")) return false;
  await saveEditor();
  toast("Championship saved");
  return true;
}

$("#btn-save-champ").addEventListener("click", () => {
  if (!ui.editing) return toast("Pick a league first", true);
  saveChampionship().catch((err) => toast(err.message, true));
});

// Race results saved by the app when a race is over (see core._auto_results).
let resultsSeen = undefined;
function renderResultsAuto(ra) {
  if (!ra) return;
  const box = $("#auto-results");
  if (document.activeElement !== box) box.checked = !!ra.on;
  const key = ra.saved ? JSON.stringify(ra.saved) : "";
  if (resultsSeen === undefined) {
    resultsSeen = key;  // what was saved before this window opened: nothing to say
    return;
  }
  if (key === resultsSeen) return;
  resultsSeen = key;
  if (!ra.saved) return;
  const n = ra.saved;
  toast(`Race results saved to ${[n.event, n.name].filter(Boolean).join(" · ")} (${n.count} drivers): the standings are up to date`);
  if (ui.editing && ui.editing.id === n.league) mergeSavedRound(n).catch((err) => toast(err.message, true));
  loadChampStandings();
}

// Bring a round the app saved into the league being edited: straight in when
// nothing's been changed here, or merged into the changes not saved yet (so
// saving them doesn't lose the race).
async function mergeSavedRound(n) {
  const fresh = await api(`/api/leagues/${encodeURIComponent(n.league)}`);
  if (!champ.dirty) {
    openEditor(fresh);
    return;
  }
  const saved = (fresh.championship.rounds || []).find((r) => r.id === n.round);
  const c = champData();
  const mine = c.rounds.find((r) => r.id === n.round);
  if (mine) Object.assign(mine, { results: saved.results, session: saved.session, track: mine.track || saved.track });
  else c.rounds.push(saved);
  if (c.live_round === n.round) c.live_round = "";
  // Drivers the race added to the roster.
  const known = new Set((ui.editing.drivers || []).map(driverKey));
  for (const d of fresh.drivers || []) if (!known.has(driverKey(d))) ui.editing.drivers.push(d);
  renderChampionship();
}

$("#auto-results").addEventListener("change", (e) => cmd("auto_results", { enabled: e.target.checked },
  e.target.checked ? "Race results will be saved when each race is over" : "Race results won't be saved by themselves"));

async function importRound(rd) {
  if ((rd.results || []).length && !confirm(`Replace the results of ${rd.name} with the current session's?`)) return;
  try {
    const saved = await saveEditor();
    const r = await api(`/api/leagues/${encodeURIComponent(saved.id)}/championship/import`, { method: "POST", body: { round_id: rd.id } });
    champ.open.add(rd.id);
    openEditor(r.league);
    toast(`Imported ${r.count} results${r.added ? `, ${r.added} new drivers added to the roster` : ""}`);
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------------------------------------------------------------------------
// overlay settings (kept by the app, so every OBS source follows them)
// ---------------------------------------------------------------------------

const NAME_FORMATS = [["full", "Full name"], ["initial_last", "A. Driver"], ["last_initial", "Driver A."],
  ["last", "Last name"], ["first", "First name"], ["abbrev", "DRI (3 letters)"], ["nickname", "Nickname"]];

// Custom opacity per column: a tick box, then a slider for each column.
const columnOpacity = (cols) => [["col_opacity_on", "Custom opacity per column", "bool"],
  iff((v) => v.col_opacity_on, ["col_opacity", "Opacity of each column", "colopacity", cols])];

// Each overlay's settings, in named sections that open and close:
// [title, fields]. A field is [key, label, kind, opts]; `iff(when, field)`
// shows it only while when(values) holds (e.g. a timer for a flash that's on).
const iff = (when, field) => Object.assign(field, { when });
const LOOK = ["Size & background", [["scale", "Size", "size"], ["bg", "Background", "background"]]];
const OVERLAY_FIELDS = {
  standings: [
    ["What it shows", [
      ["mode", "Show", "select", [["overall", "Overall"], ["class", "By class"]]],
      ["class_key", "Class", "class"],
      ["rows", "Drivers shown", "number", { min: 1, max: 64 }],
      iff((v) => v.mode === "overall", ["rows_last", "Extra drivers under the top ones, when there are more (0 = none)", "number", { min: 0, max: 30 }]),
      iff((v) => v.mode === "overall" && v.rows_last > 0, ["rows_extra_mode", "Extra drivers show", "select",
        [["rotate", "The rest of the field, a set at a time"], ["last", "The last ones"]]]),
      iff((v) => v.mode === "overall" && v.rows_last > 0 && v.rows_extra_mode === "rotate",
        ["rows_extra_s", "Seconds per set of extra drivers", "number", { min: 1, max: 120, step: 1 }]),
      iff((v) => v.mode === "overall" && v.rows_last > 0, ["rows_extra_opacity", "Extra drivers' opacity (%)", "number", { min: 10, max: 100, step: 5 }]),
      ["reveal", "Race start: only the header until each driver completes lap 1 (they appear from the start of lap 2)", "bool"],
    ]],
    ["Header", [
      ["header_info", "Header shows", "select", [["auto", "Laps or time left (automatic)"], ["laps", "Lap x of y"],
        ["time", "Time left"], ["none", "Nothing"]]],
      ["show_series", "Series name (the league's name)", "bool"],
      ["show_track", "Track name", "bool"],
      ["title_race", "Race name (blank = RACE)", "text"],
      ["title_qualify", "Qualifying name (blank = QUALIFYING)", "text"],
      ["title_practice", "Practice / warm-up name (blank = iRacing's)", "text"],
      ["title_wrap", "Wrap a long session name onto two lines (off: one line, the tower widens for it)", "bool"],
      ["show_col_labels", "Column headings (GAP, INT…)", "bool"],
    ]],
    ["Columns", [
      ["show_gap", "Gap to leader / pole", "bool"],
      iff((v) => v.show_gap, ["leader_cell", "The leader's gap shows", "select", [["leader", "Leader"], ["lap", "Their current lap (Lap 12)"]]]),
      ["show_interval", "Interval to car ahead", "bool"],
      iff((v) => v.show_interval, ["close_s", "Interval goes red within (s, 0 = off)", "number", { min: 0, max: 2, step: 0.05 }]),
      ["show_pos_change", "Places gained / lost (race)", "bool"],
      ["show_best_lap", "Best lap", "bool"],
      ["show_last_lap", "Last lap", "bool"],
      ["show_laps", "Laps completed", "bool"],
      ["show_pits", "Pit stops", "bool"],
      ["show_pit_status", "PIT badge on pit road", "bool"],
      ["column_order", "Column order on the tower", "order", [["pos_change", "+/−", "show_pos_change"], ["laps", "Laps", "show_laps"],
        ["pits", "Pit stops", "show_pits"], ["last_lap", "Last lap", "show_last_lap"], ["best_lap", "Best lap", "show_best_lap"],
        ["gap", "Gap", "show_gap"], ["interval", "Interval", "show_interval"]]],
      ["screen_column_order", "Column order on the full screen", "order", [["laps", "Laps"], ["gap", "Gap"], ["interval", "Interval"],
        ["last_lap", "Last lap (races)"], ["best_lap", "Best lap"], ["pits", "Pit stops (races)"]]],
      ...columnOpacity([["pos", "Position"], ["number", "Car number"], ["logo", "Team logo"], ["name", "Driver"], ["team", "Team (full screen)"],
        ["pos_change", "+/−"], ["laps", "Laps"], ["pits", "Pit stops"], ["last_lap", "Last lap"], ["best_lap", "Best lap"], ["gap", "Gap"],
        ["interval", "Interval"]]),
    ]],
    ["Drivers", [
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_number", "Car numbers", "bool"],
      iff((v) => v.show_number, ["color_number", "Car number background, in the driver's class colour (off: just the number)", "bool"]),
      ["show_stripe", "Coloured bar by each driver", "bool"],
      ["show_team", "Team names", "bool"],
      ["show_logo", "Team logos", "bool"],
    ]],
    ["Fastest lap", [
      ["show_fastest_icon", "Purple stopwatch by the fastest lap (each class's in By class)", "bool"],
      ["fl_flash", "Flash a new fastest lap (top middle)", "bool"],
      iff((v) => v.fl_flash, ["fl_flash_s", "Flash stays for (s; the first 2 say NEW FASTEST LAP)", "number", { min: 3, max: 60, step: 0.5 }]),
      iff((v) => v.fl_flash, ["fl_flash_classes", "Also flash each class's new fastest lap", "bool"]),
    ]],
    ["Size & background", [
      ["width", "Width in px (0 = automatic: every column fits what's in it)", "number", { min: 0, max: 1400, step: 10 }],
      ["scale", "Size", "size"], ["bg", "Background", "background"],
    ]],
  ],
  laps: [
    ["What it shows", [
      ["count", "Small trackers", "number", { min: 0, max: 12 }],
      ["practice", "Also in practice", "bool"],
      ["show_invalid", "Track invalid laps too", "bool"],
      ["hide_s", "Hide finished lap after (s)", "number", { min: 0, max: 60, step: 0.5 }],
    ]],
    ["Sectors", [
      ["sectors", "Sectors", "select", [["3", "3 (like TV)"], ["2", "2"], ["4", "4"], ["0", "Every split point on the track"]]],
      ["reference", "Purple sector is", "select", [["personal", "Faster than their best"], ["session", "Fastest in class this session"]]],
      ["green_s", "Green within (s)", "number", { min: 0, max: 5, step: 0.05 }],
    ]],
    ["Drivers", [
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_number", "Car numbers", "bool"],
      ["show_driver_number", "Driver numbers", "bool"],
      ["show_team", "Team names", "bool"],
      ["show_logo", "Team logos", "bool"],
    ]],
    LOOK,
  ],
  sponsors: [
    ["Logos", [
      ["sponsor_ids", "Sponsors", "sponsors"],
      ["layout", "Show", "select", [["rotate", "One at a time"], ["row", "All together"]]],
      iff((v) => v.layout === "rotate", ["interval_s", "Seconds per logo", "number", { min: 1, max: 120, step: 1 }]),
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["size", "Logo height (px)", "number", { min: 30, max: 300, step: 5 }],
      ["title", "Caption above (e.g. Partners)", "text"],
    ]],
    ["Size & background", [
      ["background", "Dark panel behind", "bool"],
      ["scale", "Size", "size"], ["bg", "Background", "background"],
    ]],
  ],
  gridwalk: [LOOK],
  driver: [
    ["What it shows", [
      ["stay", "Stay up for as long as they're on camera", "bool"],
      iff((v) => !v.stay, ["hide_s", "Card stays on screen for (seconds; a new driver resets it)", "number", { min: 1, max: 120, step: 1 }]),
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_position", "Position (and in class)", "bool"],
      ["show_number", "Car number", "bool"],
      ["show_team", "Team", "bool"],
      iff((v) => v.show_team, ["show_logo", "Team logo", "bool"]),
      iff((v) => v.show_team, ["team_place", "Team and car badge", "select", [["under", "Team under the name, car badge at the end"],
        ["end", "Car badge under the name, team at the end"]]]),
      iff((v) => v.show_team && v.show_logo, ["team_logo_side", "Team logo", "select", [["first", "Logo, then the team name"],
        ["last", "Team name, then the logo"]]]),
      ["show_make", "Car badge", "bool"],
      ["show_class", "Class (multiclass)", "bool"],
    ]],
    LOOK,
  ],
};

// -- backgrounds: none, a solid colour or an uploaded image, at any opacity --

let bgLibrary = [];

async function loadBackgrounds() {
  try {
    bgLibrary = (await api("/api/backgrounds")).backgrounds || [];
  } catch (e) {
    bgLibrary = [];
  }
  overlayFormKey = "";
  boardSettingsKey = "";
  if (ui.snap) render();
}

// The Size setting: a slider, 50-200 %, showing its value as it moves.
function sizeField(v) {
  return `<label class="ov-field">Size: <span class="rng-val">${v}%</span>
    <input type="range" min="50" max="200" step="5" data-key="scale" data-kind="number" value="${v}"></label>`;
}

// The Background setting's fields; colour / image / opacity only when they apply.
// On an overlay it's the overlay's own panels; a board (a whole screen) and
// the full-screen versions fill their screen.
function backgroundFields(section, v) {
  const label = section.startsWith("board") ? "Board background"
    : section === "standings" || section === "laps" ? "Panel background (full screen: the whole screen)" : "Panel background";
  const out = [`<label class="ov-field">${label}<select data-key="bg" data-kind="select">${[["default", "Default"], ["color", "Solid colour"], ["image", "Custom image"]]
    .map(([o, l]) => `<option value="${o}" ${v.bg === o ? "selected" : ""}>${l}</option>`).join("")}</select></label>`];
  if (v.bg === "color") out.push(`<label class="ov-field">Colour<input type="color" data-key="bg_color" data-kind="color" value="${esc(v.bg_color)}"></label>`);
  if (v.bg === "image") {
    out.push(`<div class="ov-field bg-pick">Image<div>${bgLibrary.map((name) => `<label class="bg-thumb ${v.bg_image === name ? "on" : ""}" title="Use this image">
        <input type="radio" name="bg-${section}" data-key="bg_image" data-kind="select" value="${esc(name)}" ${v.bg_image === name ? "checked" : ""}>
        <img src="/api/backgrounds/${encodeURIComponent(name)}" alt=""></label>`).join("")}
      <label class="btn subtle bg-upload">Upload…<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-bg-upload="${section}" hidden></label></div></div>`);
  }
  if (v.bg !== "default") {
    out.push(`<label class="ov-field">Opacity: <span class="rng-val">${v.bg_opacity}%</span><input type="range" min="0" max="100" step="5" data-key="bg_opacity" data-kind="number" value="${v.bg_opacity}"></label>`);
  }
  return out.join("");
}

document.addEventListener("input", (e) => {
  // Show a slider's value (size, opacity) as it moves; it's saved when let go.
  const shown = e.target.type === "range" && e.target.closest("label") && e.target.closest("label").querySelector(".rng-val");
  if (shown) shown.textContent = `${e.target.value}%`;
});
document.addEventListener("change", async (e) => {
  const input = e.target.closest("[data-bg-upload]");
  if (!input || !input.files.length) return;
  try {
    const res = await fetch("/api/backgrounds", { method: "POST", headers: { "Content-Type": input.files[0].type || "application/octet-stream" }, body: input.files[0] });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "Upload failed");
    bgLibrary = data.backgrounds;
    await cmd("overlay_settings", { overlay: input.dataset.bgUpload, values: { bg: "image", bg_image: data.name } });
    overlayFormKey = "";
    boardSettingsKey = "";
    toast("Background added");
  } catch (err) {
    toast(err.message, true);
  }
});

// Tick boxes for which of the league's sponsors to show ("" = all, "none" = none).
function sponsorPicker(sponsors, value) {
  if (!sponsors.length) return '<p class="hint">No sponsor logos in the active league yet (League builder).</p>';
  const ids = value === "" ? null : new Set(value.split(","));
  return `<div class="ov-field wide sponsor-pick"><span>Sponsors</span><div>${sponsors.map((sp, i) => `<label class="check">
    <input type="checkbox" data-key="sponsor_ids" data-kind="sponsors" value="${esc(sp.id)}" ${!ids || ids.has(sp.id) ? "checked" : ""}>
    <img src="${esc(sp.url)}" alt="">${esc(sp.name || `Sponsor ${i + 1}`)}</label>`).join("")}</div></div>`;
}

// A settings field's new value.
function fieldValue(el) {
  if (el.dataset.kind === "colopacity") {
    return [...el.closest(".colop-field").querySelectorAll("input")].filter((i) => +i.value < 100)
      .map((i) => `${i.dataset.opcol}:${i.value}`).join(",");
  }
  if (el.dataset.kind === "sponsors") {
    const boxes = [...el.closest(".sponsor-pick").querySelectorAll("input")];
    const on = boxes.filter((b) => b.checked).map((b) => b.value);
    return on.length === boxes.length ? "" : on.length ? on.join(",") : "none";
  }
  return el.dataset.kind === "bool" ? el.checked : el.dataset.kind === "number" ? +el.value : el.value;
}

let overlayFormKey = "";

// Which settings sections are open, remembered between visits ("standings/Header": true).
const SECTIONS_OPEN = "apex.settingsOpen";
let sectionsOpen = {};
try {
  sectionsOpen = JSON.parse(localStorage.getItem(SECTIONS_OPEN)) || {};
} catch (e) { /* storage unavailable */ }

// "toggle" doesn't bubble: listen while it's on its way down.
document.addEventListener("toggle", (e) => {
  const group = e.target.closest && e.target.closest("details[data-group]");
  if (!group || group !== e.target) return;
  sectionsOpen[group.dataset.group] = group.open;
  try {
    localStorage.setItem(SECTIONS_OPEN, JSON.stringify(sectionsOpen));
  } catch (err) { /* storage unavailable */ }
}, true);

// One setting, as its input. `section` is the overlay or board it belongs to.
function fieldHtml(section, values, [k, label, kind, opts], s) {
  const v = values[k];
  const attrs = `data-key="${k}" data-kind="${kind === "banner" || kind === "class" ? "select" : kind}"`;
  if (kind === "background") return backgroundFields(section, values);
  if (kind === "size") return sizeField(v);
  if (kind === "order") return orderField(k, label, v, opts, values);
  if (kind === "colopacity") return opacityField(k, label, v, opts);
  if (kind === "bool") return `<label class="ov-field check"><input type="checkbox" ${attrs} ${v ? "checked" : ""}> ${label}</label>`;
  if (kind === "number") {
    return `<label class="ov-field">${label}<input type="number" ${attrs} min="${opts.min}" max="${opts.max}" step="${opts.step || 1}" value="${v}"></label>`;
  }
  if (kind === "text") return `<label class="ov-field">${label}<input ${attrs} value="${esc(v)}" maxlength="40"></label>`;
  if (kind === "sponsors") return sponsorPicker((s.league && s.league.sponsors) || [], v);
  if (kind === "class" && values.mode !== "class") return "";
  const options = kind === "class" ? [["", "Every class"], ...(s.classes || []).map((c) => [c.key, c.name])]
    : kind === "banner" ? [["", "The first of the right shape"], ...((s.league && s.league.banners) || []).map((b, i) =>
      [b.id, b.name || `${b.orientation === "vertical" ? "Vertical" : "Horizontal"} banner ${i + 1}`])]
      : opts;
  return `<label class="ov-field">${label}<select ${attrs}>${options.map(([o, l]) =>
    `<option value="${esc(o)}" ${String(o) === String(v) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
}

// A slider for each column's opacity (percent; 100 = as normal).
function opacityField(key, label, value, cols) {
  const set = Object.fromEntries(String(value || "").split(",").map((p) => p.split(":")).filter((p) => p.length === 2).map(([k, v]) => [k, +v]));
  return `<div class="ov-field wide colop-field"><span>${label}</span><div class="colop-grid">${cols.map(([k, name]) => `<label class="colop">
      <span>${esc(name)} <span class="rng-val">${set[k] ?? 100}%</span></span>
      <input type="range" min="10" max="100" step="5" data-key="${key}" data-kind="colopacity" data-opcol="${k}" value="${set[k] ?? 100}"></label>`).join("")}</div></div>`;
}

// A column order: chips to drag, or move with the arrows. ``cols``: [key,
// label, the setting that switches it on (shown dimmed while off)].
function orderField(key, label, value, cols, values) {
  const known = cols.map((c) => c[0]);
  const picked = String(value || "").split(",").filter((k) => known.includes(k));
  const keys = [...picked, ...known.filter((k) => !picked.includes(k))];
  return `<div class="ov-field wide order-field" data-order-key="${key}"><span>${label} <span class="hint">(drag, or use the arrows)</span></span>
    <div class="order-list">${keys.map((k, i) => {
      const [, name, flag] = cols.find((c) => c[0] === k);
      const off = flag && !values[flag];
      return `<span class="order-item ${off ? "off" : ""}" draggable="true" data-col="${k}" title="${off ? "Switched off: it takes this place when it's on" : ""}">
        <button type="button" data-order-move="-1" ${i === 0 ? "disabled" : ""} aria-label="Move earlier">◀</button>
        <span>${esc(name)}</span>
        <button type="button" data-order-move="1" ${i === keys.length - 1 ? "disabled" : ""} aria-label="Move later">▶</button></span>`;
    }).join("")}</div></div>`;
}

function saveOrder(field, keys) {
  const form = field.closest(".ov-form");
  overlayFormKey = "";
  boardSettingsKey = "";
  cmd("overlay_settings", { overlay: form.dataset.overlay, values: { [field.dataset.orderKey]: keys.join(",") } });
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-order-move]");
  if (!btn) return;
  const item = btn.closest(".order-item");
  const field = btn.closest(".order-field");
  const keys = [...field.querySelectorAll(".order-item")].map((x) => x.dataset.col);
  const i = keys.indexOf(item.dataset.col);
  const j = i + +btn.dataset.orderMove;
  if (j < 0 || j >= keys.length) return;
  [keys[i], keys[j]] = [keys[j], keys[i]];
  btn.blur();  // the settings don't redraw while something in them has focus
  saveOrder(field, keys);
});

let draggedCol = null;
document.addEventListener("dragstart", (e) => {
  const item = e.target.closest && e.target.closest(".order-item");
  if (!item) return;
  draggedCol = item;
  item.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
});
document.addEventListener("dragover", (e) => {
  const over = draggedCol && e.target.closest && e.target.closest(".order-item");
  if (over && over.parentElement === draggedCol.parentElement) e.preventDefault();
});
document.addEventListener("drop", (e) => {
  const over = draggedCol && e.target.closest && e.target.closest(".order-item");
  if (!over || over === draggedCol || over.parentElement !== draggedCol.parentElement) return;
  e.preventDefault();
  const r = over.getBoundingClientRect();
  over.parentElement.insertBefore(draggedCol, e.clientX > r.left + r.width / 2 ? over.nextSibling : over);
  saveOrder(over.closest(".order-field"), [...over.parentElement.children].map((x) => x.dataset.col));
});
document.addEventListener("dragend", () => {
  if (draggedCol) draggedCol.classList.remove("dragging");
  draggedCol = null;
});

// An overlay's or board's settings: its On screen switch, then its sections
// (the first one open until you choose otherwise).
function settingsHtml(section, values, groups, s) {
  const top = "visible" in values
    ? `<label class="ov-field check ov-visible"><input type="checkbox" data-key="visible" data-kind="bool" ${values.visible ? "checked" : ""}> Showing <span class="hint">(untick to hide it everywhere)</span></label>` : "";
  return top + groups.map(([title, fields], i) => {
    const id = `${section}/${title}`;
    const open = sectionsOpen[id] ?? i === 0;
    const body = fields.filter((f) => !f.when || f.when(values)).map((f) => fieldHtml(section, values, f, s)).join("");
    return `<details class="ov-group" data-group="${esc(id)}" ${open ? "open" : ""}><summary>${esc(title)}</summary>
      <div class="ov-grid">${body}</div></details>`;
  }).join("");
}

function renderOverlaySettings(s) {
  const ov = s.overlays;
  if (!ov) return;
  $("#tile-overlays").textContent = ov.laps.active ? "Lap tracker live (qualifying)" : `${ov.standings.length} in the standings`;
  // Don't redraw under the cursor; redraw when settings or classes change.
  const key = JSON.stringify([ov.settings, (s.classes || []).map((c) => [c.key, c.name]), (s.league && s.league.sponsors) || []]);
  if (key === overlayFormKey || document.activeElement.closest(".ov-form")) return;
  overlayFormKey = key;
  for (const [overlay, groups] of Object.entries(OVERLAY_FIELDS)) {
    $(`#ov-${overlay}`).innerHTML = settingsHtml(overlay, ov.settings[overlay], groups, s);
  }
}

document.querySelectorAll(".ov-form").forEach((form) => form.addEventListener("change", (e) => {
  const el = e.target;
  if (!el.dataset.key) return;
  const value = fieldValue(el);
  overlayFormKey = "";
  el.blur();
  cmd("overlay_settings", { overlay: form.dataset.overlay, values: { [el.dataset.key]: value } });
}));

// ---------------------------------------------------------------------------
// boards: the full-screen championship, calendar and results screens
// ---------------------------------------------------------------------------

// Every board: the league logo in its header, and a banner where (and which).
const BOARD_BRAND = [["league_logo", "League logo in the header", "bool"],
  ["banner", "Banner", "select", [["none", "None"], ["top", "Across the top"], ["bottom", "Across the bottom"], ["left", "Down the left"],
    ["right", "Down the right"]]],
  iff((v) => v.banner !== "none", ["banner_id", "Which banner", "banner"]),
  ["sponsors", "Sponsor logos", "select", [["none", "None"], ["top", "Across the top"], ["bottom", "Across the bottom"],
    ["left", "Down the left"], ["right", "Down the right"]]],
  iff((v) => v.sponsors !== "none", ["sponsor_ids", "Which sponsors", "sponsors"])];
const cards = (v) => v.style === "cards";

const BOARD_FIELDS = {
  board_championship: [["rows", "Drivers shown", "number", { min: 1, max: 64 }], ["rounds", "Points from the last N rounds", "number", { min: 0, max: 10 }],
    ["show_number", "Car numbers", "bool"], ["show_team", "Team names", "bool"], ["show_logo", "Team logos", "bool"],
    ["show_make", "Car badges", "bool"], ["show_gap", "Points gap to the leader", "bool"],
    ["show_ahead", "Points gap to the driver ahead", "bool"], ["show_wins", "Wins", "bool"],
    ["show_penalty", "Penalty points", "bool"],
    ...columnOpacity([["pos", "Position"], ["number", "Car number"], ["driver", "Driver"], ["team", "Team"], ["car", "Car badge"],
      ["rounds", "Round points"], ["wins", "Wins"], ["penalty", "Penalty points"], ["points", "Points"], ["gap", "Gap to leader"],
      ["ahead", "Gap to driver ahead"]])],
  board_teams: [["rows", "Teams shown", "number", { min: 1, max: 64 }], ["rounds", "Points from the last N rounds", "number", { min: 0, max: 10 }],
    ["show_logo", "Team logos", "bool"], ["show_color", "Team colour stripe", "bool"], ["show_drivers", "Drivers who scored", "bool"],
    ["show_gap", "Points gap to the leader", "bool"], ["show_ahead", "Points gap to the team ahead", "bool"],
    ["show_wins", "Wins", "bool"], ["show_penalty", "Penalty points", "bool"],
    ...columnOpacity([["pos", "Position"], ["team", "Team"], ["drivers", "Drivers"], ["rounds", "Round points"], ["wins", "Wins"],
      ["penalty", "Penalty points"], ["points", "Points"], ["gap", "Gap to leader"], ["ahead", "Gap to team ahead"]])],
  board_makes: [["rows", "Manufacturers shown", "number", { min: 1, max: 64 }], ["show_logo", "Badges", "bool"],
    ["show_wins", "Wins", "bool"], ["show_gap", "Gap to the leader", "bool"],
    ...columnOpacity([["pos", "Position"], ["make", "Manufacturer"], ["wins", "Wins"], ["points", "Points"], ["gap", "Gap"]])],
  board_calendar: [["style", "Show", "select", [["cards", "The calendar built from the rounds"], ["image", "The league's own calendar image"]]],
    iff(cards, ["round_title", "Round titles", "select", [["both", "Round 3 · your round name"], ["name", "Your round name"], ["number", "Round 3"]]]),
    iff(cards, ["show_date", "Dates", "bool"]),
    iff((v) => cards(v) && v.show_date, ["date_format", "Dates as", "select", [["weekday_short", "Sun 22 Nov"], ["numeric", "22/11/26"],
      ["day_month", "22nd November"], ["full", "22nd November 2026"], ["weekday", "Sunday 22nd November"]]]),
    iff(cards, ["show_time", "Start times", "bool"]), iff(cards, ["show_config", "Track layouts", "bool"]),
    iff(cards, ["show_length", "Race lengths", "bool"]), iff(cards, ["show_winners", "Winners of past rounds", "bool"]),
    iff(cards, ["show_multiplier", "Points multiplier (e.g. ×2 points) on rounds worth more", "bool"])],
  board_results: [["rows", "Drivers shown", "number", { min: 1, max: 64 }], ["show_gained", "Places gained / lost", "bool"],
    ["show_number", "Car numbers", "bool"], ["show_team", "Team names", "bool"], ["show_logo", "Team logos", "bool"],
    ["show_make", "Car badges", "bool"], ["show_laps", "Laps", "bool"], ["show_fastest", "Fastest lap", "bool"],
    ["show_status", "DNF / DSQ", "bool"], ["show_points", "Points scored", "bool"],
    ...columnOpacity([["pos", "Position"], ["gained", "Places gained"], ["number", "Car number"], ["driver", "Driver"], ["team", "Team"],
      ["car", "Car badge"], ["laps", "Laps"], ["fastest", "Fastest lap"], ["status", "DNF / DSQ"], ["points", "Points"]])],
};
const BOARD_SECTION_NAMES = {
  board_championship: "Championship standings", board_teams: "Teams' championship",
  board_makes: "Manufacturers' championship", board_calendar: "Season calendar", board_results: "Finishing order",
};

let boardButtonsKey = "";
let boardSettingsKey = "";
let boardRound = "latest";

function boardButton(label, kind, group = "", color = null, extra = {}) {
  const b = ui.snap && ui.snap.board;
  const on = b && ui.boardOn && ui.boardOn.kind === kind && ui.boardOn.group === group;
  return `<button class="btn board-btn ${on ? "on-air" : ""}" data-board="${kind}" data-group="${esc(group)}"
    ${extra.round ? `data-round="${esc(extra.round)}"` : ""} style="${color ? `--cls:${esc(color)}` : ""}">${color ? '<span class="swatch"></span>' : ""}${esc(label)}</button>`;
}

function renderBoards(s) {
  const opts = s.board_options || { groups: [], rounds: [] };
  ui.boardOn = s.board ? { kind: s.board.kind, group: s.board.group } : null;
  $("#board-onair").textContent = s.board ? `On screen: ${s.board.title}${s.board.subtitle ? ` · ${s.board.subtitle}` : ""}` : "Nothing on screen";
  $("#btn-board-hide").disabled = !s.board;
  const key = JSON.stringify([opts, s.league && s.league.id, ui.boardOn, boardRound, !!s.board]);
  if (key !== boardButtonsKey) {
    boardButtonsKey = key;
    const groups = opts.groups;
    const scored = opts.rounds.filter((r) => r.scored);
    $("#board-buttons").innerHTML = !s.league ? '<p class="hint">Activate a league (League builder) to use boards.</p>' : `
      <div class="board-group"><h4>Championship standings</h4>${groups.length ? groups.map((g) => boardButton(g.name, "championship", g.key, g.color)).join("")
        : '<span class="hint">No results yet.</span>'}</div>
      <div class="board-group"><h4>Teams</h4>${opts.teams ? boardButton("Teams' championship", "teams")
        : `<span class="hint">${opts.has_teams ? "No team points yet." : "Give drivers a team in the League builder (Teams tab) for a teams' championship."}</span>`}</div>
      <div class="board-group"><h4>Manufacturers</h4>${groups.map((g) => boardButton(g.name, "makes", g.key, g.color)).join("") || '<span class="hint">No results yet.</span>'}</div>
      <div class="board-group"><h4>Season</h4>${boardButton("Season calendar", "calendar")}</div>
      <div class="board-group"><h4>Finishing order</h4>
        <label class="field">From <select id="board-round">
          <option value="latest" ${boardRound === "latest" ? "selected" : ""}>Latest round</option>
          <option value="live" ${boardRound === "live" ? "selected" : ""}>This session (live)</option>
          ${scored.map((r) => `<option value="${esc(r.id)}" ${boardRound === r.id ? "selected" : ""}>${esc(r.name)}${r.track ? ` · ${esc(r.track)}` : ""}</option>`).join("")}
        </select></label>
        <div>${[{ key: "overall", name: "Overall", color: null }, ...groups.filter((g) => g.key !== "overall")]
          .map((g) => boardButton(g.name, "results", g.key, g.color)).join("")}</div></div>`;
  }
  const skey = JSON.stringify([s.overlays && s.overlays.settings, (s.league && s.league.banners) || [], (s.league && s.league.sponsors) || []]);
  if (skey !== boardSettingsKey && !document.activeElement.closest("#board-settings")) {
    boardSettingsKey = skey;
    renderBoardSettings(s);
  }
}

function renderBoardSettings(s) {
  const settings = s.overlays && s.overlays.settings;
  if (!settings) return;
  $("#board-settings").innerHTML = Object.entries(BOARD_FIELDS).map(([section, fields]) => `
    <div class="overlay-card"><h3>${BOARD_SECTION_NAMES[section]}</h3><div class="ov-form" data-overlay="${section}">
    ${settingsHtml(section, settings[section], [["What it shows", fields], ["Logo, banner & sponsors", BOARD_BRAND], LOOK], s)}</div></div>`).join("");
}

$("#board-buttons").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-board]");
  if (!b) return;
  const params = { kind: b.dataset.board, group: b.dataset.group || "" };
  if (params.kind === "results") params.round = boardRound;
  const r = await cmd("board_show", params);
  if (r) ui.boardOn = { kind: params.kind, group: params.group };
  boardButtonsKey = "";
});
$("#board-buttons").addEventListener("change", (e) => {
  if (e.target.id === "board-round") {
    boardRound = e.target.value;
    // Results already on screen switch to the new source straight away.
    if (ui.boardOn && ui.boardOn.kind === "results") cmd("board_show", { kind: "results", group: ui.boardOn.group, round: boardRound });
  }
});
$("#btn-board-hide").addEventListener("click", async () => {
  await cmd("board_hide");
  ui.boardOn = null;
  boardButtonsKey = "";
});
$("#board-settings").addEventListener("change", (e) => {
  const el = e.target;
  const form = el.closest(".ov-form");
  if (!el.dataset.key || !form) return;
  const value = fieldValue(el);
  boardSettingsKey = "";
  el.blur();
  cmd("overlay_settings", { overlay: form.dataset.overlay, values: { [el.dataset.key]: value } });
});
$("#url-board").textContent = `${location.origin}/board.html`;
$("#url-sponsors").textContent = `${location.origin}/sponsors.html`;
$("#url-driver").textContent = `${location.origin}/driver.html`;

for (const page of ["standings", "laps"]) {
  $(`#url-${page}`).textContent = `${location.origin}/${page}.html`;
  $(`#url-${page}-screen`).textContent = `${location.origin}/${page}.html?screen=1`;
}
document.addEventListener("click", (e) => {
  const copy = e.target.closest("[data-copy]");
  if (!copy) return;
  const text = document.getElementById(copy.dataset.copy).textContent;
  navigator.clipboard.writeText(text).then(() => toast("Copied"), () => toast(text));
});

$("#home-obs-url").textContent = `${location.origin}/gridwalk.html`;
loadBackgrounds();

// -- overlays straight on the user's screen (app window only) -------------------

const DESK_OK = "apex.desktopOk";  // the app version this PC was seen to show them see-through on
const DESK_CHECK_S = 15;
let deskKey = "";
let deskCheck = null;  // {page, left, timer} while asking

function screenName(sc, i, all) {
  return all.length > 1 ? `Screen ${i + 1} · ${sc.width}×${sc.height}` : "";
}

// The screen picked at the top of the Overlays tab (every overlay and the grid
// walk) or the Boards tab, remembered on this PC.
const DESK_SCREEN = "apex.deskScreen.";
const deskTab = (page) => (page === "board" ? "boards" : "overlays");

function deskScreen(tab, screens = (ui.snap && ui.snap.desktop && ui.snap.desktop.screens) || []) {
  let n = 0;
  try {
    n = +localStorage.getItem(DESK_SCREEN + tab) || 0;
  } catch (e) { /* storage unavailable */ }
  return n < screens.length ? n : 0;
}

function renderDesktop(s) {
  const d = s.desktop || { available: false, on_screen: {}, screens: [] };
  const key = JSON.stringify(d);
  if (key === deskKey) return;
  deskKey = key;
  const several = d.screens.length > 1;
  document.querySelectorAll("[data-desk]").forEach((el) => {
    const page = el.dataset.desk;
    el.hidden = !d.available;
    if (!d.available) return;
    const on = d.on_screen[page];
    el.innerHTML = on != null
      ? `<span class="desk-on">● On ${several ? `screen ${on + 1}` : "your screen"}</span><button class="btn subtle" data-desk-hide="${page}">Remove</button>`
      : `<button class="btn" data-desk-show="${page}" title="Put it straight on your screen, over the game">Show on my screen</button>`;
  });
  document.querySelectorAll("[data-desk-tab]").forEach((pick) => {
    pick.closest(".desk-screen").hidden = !d.available || !several;
    const n = deskScreen(pick.dataset.deskTab, d.screens);
    pick.innerHTML = d.screens.map((sc, i) =>
      `<option value="${i}" ${n === i ? "selected" : ""}>${esc(screenName(sc, i, d.screens))}</option>`).join("");
  });
  $("#desk-hide-all").hidden = !Object.keys(d.on_screen).length;
  document.querySelectorAll(".desk-help").forEach((el) => { el.hidden = !d.available; });
}

async function deskShow(page, screen) {
  const r = await cmd("desktop_show", { page, screen });
  if (!r) return;
  let ok = false;
  try {
    // Checked again after each update: a new version could show them differently.
    ok = localStorage.getItem(DESK_OK) === ui.version;
  } catch (e) { /* storage unavailable */ }
  if (!ok) startDeskCheck(page);
}

// Can they see through it? If it came up solid instead, it's covering their
// screen: no answer within DESK_CHECK_S seconds takes it down by itself.
function startDeskCheck(page) {
  stopDeskCheck();
  deskCheck = { page, left: DESK_CHECK_S };
  const tick = () => {
    $("#desk-check-text").textContent = `Can you see your screen through the overlay? If not, it goes away by itself in ${deskCheck.left} s.`;
    if (deskCheck.left-- <= 0) {
      cmd("desktop_hide", { page });
      stopDeskCheck();
      toast("Overlay removed. If it covered your screen, on-screen overlays don't work on this PC: use the OBS or browser link instead.", true);
    }
  };
  deskCheck.timer = setInterval(tick, 1000);
  tick();
  $("#desk-check").hidden = false;
}

function stopDeskCheck() {
  if (deskCheck) clearInterval(deskCheck.timer);
  deskCheck = null;
  $("#desk-check").hidden = true;
}

$("#desk-check-yes").addEventListener("click", () => {
  try {
    localStorage.setItem(DESK_OK, ui.version || "");
  } catch (e) { /* storage unavailable */ }
  stopDeskCheck();
  toast("Great: overlays will go straight on screen from now on");
});
$("#desk-check-no").addEventListener("click", () => {
  if (deskCheck) cmd("desktop_hide", { page: deskCheck.page });
  stopDeskCheck();
  toast("Removed. Use the OBS or browser link instead.");
});
document.addEventListener("click", (e) => {
  const show = e.target.closest("[data-desk-show]");
  if (show) deskShow(show.dataset.deskShow, deskScreen(deskTab(show.dataset.deskShow)));
  const hide = e.target.closest("[data-desk-hide]");
  if (hide) cmd("desktop_hide", { page: hide.dataset.deskHide });
});
document.querySelectorAll("[data-desk-tab]").forEach((pick) => pick.addEventListener("change", () => {
  const tab = pick.dataset.deskTab;
  try {
    localStorage.setItem(DESK_SCREEN + tab, pick.value);
  } catch (e) { /* storage unavailable */ }
  // Whatever from this tab is already on screen moves to the screen picked.
  const on = (ui.snap && ui.snap.desktop && ui.snap.desktop.on_screen) || {};
  for (const [page, screen] of Object.entries(on)) {
    if (deskTab(page) === tab && screen !== +pick.value) cmd("desktop_show", { page, screen: +pick.value });
  }
}));
$("#desk-hide-all").addEventListener("click", () => cmd("desktop_hide", {}));

// Scrolling the page with the mouse over a number box you'd clicked in
// changed its value (e.g. a round's points multiplier, or a position):
// scrolling now just scrolls.
document.addEventListener("wheel", (e) => {
  const el = document.activeElement;
  if (el && el.type === "number" && (e.target === el || el.contains(e.target))) el.blur();
}, { passive: true });

// -- export and import (apex/transfer.py) -----------------------------------------

let lastExport = null;

// Save the export (unsaved edits first) and say where it went.
async function exportFile(what, round) {
  try {
    let league = "";
    if (what !== "overlays") {
      if (!ui.editing) throw new Error("Pick a league first");
      league = (await saveEditor()).id;
    }
    const r = await api("/api/export", { method: "POST", body: { what, league, round: round || "" } });
    lastExport = r.path;
    $("#export-name").textContent = r.name;
    $("#export-folder").textContent = r.folder;
    $("#export-path").textContent = r.path;
    $("#exports-folder").textContent = r.folder;
    $("#export-modal").hidden = false;
  } catch (err) {
    toast(err.message, true);
  }
}

const IMPORT_CHECKS = {
  championship: "Replace this league's championship (points rules, calendar, results and penalties) with the one in the file?",
  overlays: "Replace all your overlay and board settings with the ones in the file?",
};

async function importFile(what, file, round) {
  if (IMPORT_CHECKS[what] && !confirm(IMPORT_CHECKS[what])) return;
  try {
    let league = "";
    if (what !== "league" && what !== "overlays") {
      if (!ui.editing) throw new Error("Pick a league first");
      league = (await saveEditor()).id;
      const rd = round && (champData().rounds || []).find((r) => r.id === round);
      if (rd && (rd.results || []).length && !confirm(`Replace the results of ${rd.name} with the ones in the file?`)) return;
    }
    const q = new URLSearchParams({ what, league, round: round || "" });
    const res = await fetch(`/api/import?${q}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "Import failed");
    const info = data.info || {};
    if (what === "league") {
      await loadLeagues();
      openEditor(data.league);
      showPage("league");
      return toast(`Imported ${data.league.name}`);
    }
    if (data.league) {
      if (round) champ.open.add(round);
      openEditor(data.league);
      await loadLeagues();
    }
    toast({
      teams: `Imported ${info.teams} teams${info.drivers ? `; ${info.drivers} drivers put in their team` : ""}`,
      championship: `Imported the championship: ${info.rounds} rounds`,
      round: `Imported ${info.results} results`,
      drivers: `Roster: ${info.added} drivers added, ${info.updated} updated`,
      overlays: `Imported the settings of ${info.sections} overlays and boards`,
    }[what] || "Imported");
    if (what === "overlays") {
      overlayFormKey = "";
      boardSettingsKey = "";
      loadBackgrounds();
    }
  } catch (err) {
    toast(err.message, true);
  }
}

document.addEventListener("click", (e) => {
  const ex = e.target.closest("[data-export]");
  if (ex) exportFile(ex.dataset.export, ex.dataset.exportRound);
  if (e.target.closest("[data-show-exports]")) api("/api/export/show", { method: "POST", body: {} }).catch((err) => toast(err.message, true));
});
document.addEventListener("change", (e) => {
  const input = e.target.closest("[data-import]");
  if (!input || !input.files.length) return;
  importFile(input.dataset.import, input.files[0], input.dataset.importRound);
  input.value = "";
});
$("#export-close").addEventListener("click", () => { $("#export-modal").hidden = true; });
$("#export-show").addEventListener("click", () => {
  api("/api/export/show", { method: "POST", body: { path: lastExport } }).catch((err) => toast(err.message, true));
});
$("#export-copy").addEventListener("click", () => {
  navigator.clipboard.writeText(lastExport || "").then(() => toast("Path copied"), () => toast(lastExport || ""));
});
api("/api/export/folder").then((r) => { $("#exports-folder").textContent = r.folder; }).catch(() => {});

// Pop out: the app opens the page in its own window; in a browser, a new browser window.
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-popout]");
  if (!btn) return;
  const page = btn.dataset.popout;
  const r = await cmd("popout", { page });
  if (!r || !r.opened) {
    const w = window.open(`/?popout=${page}`, `apex-${page}`, "width=1280,height=820");
    if (!w) toast("The browser blocked the pop-up window: allow pop-ups for this page.", true);
  }
});
if (POPOUT) {
  document.body.classList.add("popout");
  document.title = `${POPOUT[0].toUpperCase()}${POPOUT.slice(1)} – Apex Commentator`;
}
showPage(POPOUT || (() => {
  try {
    return localStorage.getItem(PAGE_KEY) || "home";
  } catch (e) {
    return "home";
  }
})());

// ---------------------------------------------------------------------------
// league builder
// ---------------------------------------------------------------------------

async function loadLeagues() {
  try {
    if (!ui.libraryLoaded) {
      ui.library = (await api("/api/logo-library")).logos;
      ui.libraryLoaded = true;
    }
    const { leagues, active } = await api("/api/leagues");
    ui.activeLeague = active;
    $("#league-list").innerHTML = leagues.length ? leagues.map((l) => `
      <li data-league="${esc(l.id)}" class="${ui.editing && ui.editing.id === l.id ? "selected" : ""}">
        <div><div>${esc(l.name)} ${l.active ? '<span class="badge live">ACTIVE</span>' : ""}</div>
        <div class="meta">${l.drivers} drivers${l.classes ? ` · ${l.classes} classes` : ""}${l.league_id ? ` · ID ${l.league_id}` : ""}</div></div>
        <button class="btn icon danger" data-delete="${esc(l.id)}" title="Delete">✕</button>
      </li>`).join("") : '<li class="meta">No saved leagues yet</li>';
  } catch (e) {
    toast(e.message, true);
  }
}

function openEditor(profile) {
  ui.editing = profile;
  $("#league-editor").hidden = false;
  $("#edit-name").value = profile.name || "";
  $("#edit-strip-class").checked = !!profile.strip_class_prefix;
  $("#btn-activate-league").textContent = profile.id && profile.id === ui.activeLeague ? "Active in overlay" : "Use in overlay";
  profile.classes = profile.classes || [];
  renderClasses();
  renderTeams();
  renderRoster();
  renderBanners();
  renderSponsors();
  renderLeagueImages();
  champ.dirty = false;
  champ.standings = null;
  renderChampionship();
  loadChampStandings();
  document.querySelectorAll("#league-list li").forEach((li) => li.classList.toggle("selected", li.dataset.league === profile.id));
}

// The league editor's tabs (Drivers, Classes, Logos...), the last one used remembered.
const LEAGUE_TAB = "apex.leagueTab";

function showLeagueTab(name) {
  if (!document.querySelector(`[data-ltab-panel="${name}"]`)) name = "drivers";
  document.querySelectorAll("[data-ltab]").forEach((b) => b.classList.toggle("active", b.dataset.ltab === name));
  document.querySelectorAll("[data-ltab-panel]").forEach((p) => { p.hidden = p.dataset.ltabPanel !== name; });
  try {
    localStorage.setItem(LEAGUE_TAB, name);
  } catch (e) { /* storage unavailable */ }
}

document.querySelectorAll("[data-ltab]").forEach((b) => b.addEventListener("click", () => showLeagueTab(b.dataset.ltab)));
try {
  showLeagueTab(localStorage.getItem(LEAGUE_TAB) || "drivers");
} catch (e) {
  showLeagueTab("drivers");
}

// A secondary class: picked by hand, only for its own championship.
function isSecondary(c) {
  return c.role === "secondary";
}

const ROSTER_FIELDS = [["name", ""], ["cust_id", "c-id"], ["car_number", "c-num"], ["driver_number", "c-num"], ["nickname", ""], ["team", ""], ["notes", ""]];

// Car makes (and their badges) the app knows, loaded once.
const makes = { list: [], loaded: false };

async function loadMakes() {
  if (makes.loaded) return;
  try {
    makes.list = (await api("/api/makes")).makes;
    makes.loaded = true;
    if (ui.editing) renderRoster();
  } catch (e) { /* the roster still works without badges */ }
}

function makeOptions(selected) {
  const known = makes.list.some((m) => m.name === selected);
  return `<option value="">Auto (iRacing car)</option>${selected && !known ? `<option selected>${esc(selected)}</option>` : ""}` +
    makes.list.map((m) => `<option ${m.name === selected ? "selected" : ""}>${esc(m.name)}</option>`).join("");
}

function makeBadge(name) {
  const m = makes.list.find((x) => x.name === name);
  return `<span class="make-badge">${m && m.logo ? `<img src="${esc(m.logo)}" alt="${esc(name)}">` : ""}</span>`;
}

// Sorting the roster: click a column heading for A-Z, again for Z-A, a third
// time for the order they were added. Only the list on screen is sorted; the
// league keeps its own order.
const ROSTER_SORT_KEY = "apex.rosterSort";
let rosterSort = (() => {
  try {
    return JSON.parse(localStorage.getItem(ROSTER_SORT_KEY)) || null;
  } catch (e) {
    return null;
  }
})();

function rosterOrder(drivers, classes) {
  const rows = drivers.map((d, i) => [d, i]);
  if (!rosterSort) return rows;
  const className = (id) => (classes.find((c) => c.id === id) || {}).name || "";
  const value = (d) => String((rosterSort.key === "class_id" || rosterSort.key === "class2_id"
    ? className(d[rosterSort.key]) : d[rosterSort.key]) ?? "").trim();
  const dir = rosterSort.dir === "desc" ? -1 : 1;
  return rows.sort(([a, ia], [b, ib]) => {
    const va = value(a), vb = value(b);
    if (!va !== !vb) return va ? -1 : 1;  // blanks last, either way round
    // Numbers as numbers (2 before 10); names whatever their capitals.
    return (va.localeCompare(vb, undefined, { numeric: true, sensitivity: "base" }) || ia - ib) * dir;
  });
}

$("#roster-head").addEventListener("click", (e) => {
  const th = e.target.closest("[data-sort]");
  if (!th) return;
  const key = th.dataset.sort;
  rosterSort = !rosterSort || rosterSort.key !== key ? { key, dir: "asc" } : rosterSort.dir === "asc" ? { key, dir: "desc" } : null;
  try {
    localStorage.setItem(ROSTER_SORT_KEY, JSON.stringify(rosterSort));
  } catch (err) { /* storage unavailable */ }
  renderRoster();
});

function renderRoster() {
  loadMakes();
  const drivers = ui.editing.drivers || [];
  const classes = ui.editing.classes || [];
  const options = (list, selected) => list.map((c) =>
    `<option value="${esc(c.id)}" ${c.id === selected ? "selected" : ""}>${esc(c.name || "Unnamed")}</option>`).join("");
  const main = classes.filter((c) => !isSecondary(c));
  const second = classes.filter(isSecondary);
  // The 2nd class column only once the league has a secondary class.
  document.querySelector(".roster").classList.toggle("no-class2", !second.length);
  $("#ltab-drivers").textContent = drivers.length || "";
  document.querySelectorAll("#roster-head [data-sort]").forEach((th) => {
    const on = rosterSort && rosterSort.key === th.dataset.sort;
    th.classList.toggle("sorted", !!on);
    th.dataset.dir = on ? rosterSort.dir : "";
    th.title = th.title.replace(/ \(click to sort.*$/, "") + " (click to sort)";
  });
  $("#roster-rows").innerHTML = rosterOrder(drivers, classes).map(([d, i]) => `<tr>${ROSTER_FIELDS.map(([f]) =>
    `<td><input data-row="${i}" data-field="${f}" value="${esc(d[f] ?? "")}" aria-label="${f}"></td>`).join("")}
    <td><select data-row="${i}" data-field="class_id" aria-label="Class"><option value="">Auto (by car)</option>${options(main, d.class_id || "")}</select></td>
    <td class="c-class2"><select data-row="${i}" data-field="class2_id" aria-label="Secondary class"><option value="">—</option>${options(second, d.class2_id || "")}</select></td>
    <td class="make-cell">${makeBadge(d.car_make)}<select data-row="${i}" data-field="car_make" aria-label="Car">${makeOptions(d.car_make || "")}</select></td>
    <td><div class="photos">${["car", "helmet"].map((kind) => photoButton(d, i, kind)).join("")}</div></td>
    <td><button class="btn icon danger" data-remove="${i}" title="Remove">✕</button></td></tr>`).join("");
}

function photoButton(d, i, kind) {
  const file = d[`${kind}_image`];
  const label = kind === "car" ? "Car" : "Helmet";
  return `<span class="photo">
    <label class="thumb" title="${file ? `Replace ${label.toLowerCase()} photo` : `Add ${label.toLowerCase()} photo`}">
      ${file ? `<img src="${esc(logoSrc(file))}" alt="${label}">` : `+ ${label}`}
      <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-photo="${kind}" data-row="${i}" hidden>
    </label>
    ${file ? `<button class="clear" data-clear-photo="${kind}" data-row="${i}" title="Remove ${label.toLowerCase()} photo">✕</button>` : ""}
  </span>`;
}

// Same key the server uses (league.driver_key) to find a roster driver.
function driverKey(d) {
  const id = String(d.cust_id ?? "").trim();
  return /^\d+$/.test(id) ? `cust:${+id}` : `name:${String(d.name || "").trim().toLowerCase()}`;
}

// Save the league, then upload an image for one of its classes, teams or drivers.
async function uploadImage(target, file) {
  const saved = await saveEditor();
  const res = await fetch(`/api/leagues/${encodeURIComponent(saved.id)}/images?target=${encodeURIComponent(target)}`, {
    method: "POST",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) throw new Error(data.error || "Upload failed");
  openEditor(data.league);
  return data.league;
}

// -- league logo, calendar image and banners ---------------------------------------

const LEAGUE_IMAGES = { logo: ["#league-logo-slot", "league logo"], calendar_image: ["#calendar-image-slot", "calendar image"] };

function renderLeagueImages() {
  for (const [field, [slot, label]] of Object.entries(LEAGUE_IMAGES)) {
    const file = ui.editing && ui.editing[field];
    $(slot).innerHTML = `<div class="image-slot-img ${field}">${file ? `<img src="${esc(logoSrc(file))}" alt="">` : `<span class="hint">No ${label}</span>`}</div>
      <label class="btn subtle">${file ? "Replace" : "Upload"} ${label}<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-league-image="${field}" hidden></label>
      ${file ? `<button class="btn subtle" data-league-image-remove="${field}">Remove</button>` : ""}`;
  }
}

$("#league-editor").addEventListener("change", async (e) => {
  const input = e.target.closest("[data-league-image]");
  if (!input || !input.files.length) return;
  try {
    await uploadImage(`league:${input.dataset.leagueImage}`, input.files[0]);
    toast("Image added");
  } catch (err) {
    toast(err.message, true);
  }
});
$("#league-editor").addEventListener("click", (e) => {
  const rm = e.target.closest("[data-league-image-remove]");
  if (!rm) return;
  ui.editing[rm.dataset.leagueImageRemove] = null;
  renderLeagueImages();
  toast("Removed: save the league to keep the change");
});

function renderBanners() {
  const list = (ui.editing && ui.editing.banners) || [];
  $("#banner-list").innerHTML = list.length ? list.map((b, i) => `<div class="banner-card ${b.orientation}">
      <div class="banner-img"><img src="${esc(logoSrc(b.file))}" alt=""></div>
      <div class="banner-fields">
        <input data-banner="${i}" data-key="name" value="${esc(b.name || "")}" placeholder="Name (optional)" aria-label="Banner name">
        <select data-banner="${i}" data-key="orientation" aria-label="Shape">
          <option value="horizontal" ${b.orientation === "horizontal" ? "selected" : ""}>Horizontal</option>
          <option value="vertical" ${b.orientation === "vertical" ? "selected" : ""}>Vertical</option></select>
        <button class="btn icon danger" data-banner-remove="${i}" title="Remove">✕</button>
      </div></div>`).join("") : '<p class="hint">No logos or banners yet.</p>';
}

$("#league-editor").addEventListener("change", async (e) => {
  const up = e.target.closest("[data-banner-upload]");
  if (up && up.files.length) {
    try {
      await uploadImage(`banner:${up.dataset.bannerUpload}`, up.files[0]);
      toast("Banner added");
    } catch (err) {
      toast(err.message, true);
    }
    up.value = "";
    return;
  }
  const field = e.target.closest("[data-banner]");
  if (field) {
    ui.editing.banners[+field.dataset.banner][field.dataset.key] = field.value;
    renderBanners();
  }
});
function renderSponsors() {
  const list = (ui.editing && ui.editing.sponsors) || [];
  $("#sponsor-list").innerHTML = list.length ? list.map((sp, i) => `<div class="sponsor-card">
      <div class="sponsor-img"><img src="${esc(logoSrc(sp.file))}" alt=""></div>
      <input data-sponsor="${i}" value="${esc(sp.name || "")}" placeholder="Sponsor name" aria-label="Sponsor name">
      <button class="btn icon danger" data-sponsor-remove="${i}" title="Remove">✕</button>
    </div>`).join("") : '<p class="hint">No sponsors yet.</p>';
}

$("#league-editor").addEventListener("change", async (e) => {
  const up = e.target.closest("[data-sponsor-upload]");
  if (up && up.files.length) {
    try {
      // One at a time: each upload saves the league and adds one sponsor.
      for (const file of up.files) await uploadImage(`sponsor:${file.name.replace(/\.[a-z0-9]+$/i, "").replace(/[-_]+/g, " ")}`, file);
      toast(up.files.length > 1 ? `${up.files.length} sponsors added` : "Sponsor added");
    } catch (err) {
      toast(err.message, true);
    }
    up.value = "";
    return;
  }
  const field = e.target.closest("[data-sponsor]");
  if (field) ui.editing.sponsors[+field.dataset.sponsor].name = field.value;
});
$("#sponsor-list").addEventListener("click", (e) => {
  const rm = e.target.closest("[data-sponsor-remove]");
  if (!rm) return;
  ui.editing.sponsors.splice(+rm.dataset.sponsorRemove, 1);
  renderSponsors();
  toast("Removed: save the league to keep the change");
});

$("#banner-list").addEventListener("click", (e) => {
  const rm = e.target.closest("[data-banner-remove]");
  if (!rm) return;
  ui.editing.banners.splice(+rm.dataset.bannerRemove, 1);
  renderBanners();
  toast("Removed: save the league to keep the change");
});

// -- team builder ---------------------------------------------------------------
// Edits the same league as the League builder (ui.editing); a driver's team is
// their roster Team field.

function editorTeams() {
  const teams = (ui.editing.teams = ui.editing.teams || []);
  const known = new Set(teams.map((t) => t.name.toLowerCase()));
  for (const d of ui.editing.drivers || []) {
    const name = String(d.team || "").trim();
    if (name && !known.has(name.toLowerCase())) {
      known.add(name.toLowerCase());
      teams.push({ name, short: "", color: "", logo: null });
    }
  }
  return teams;
}

const sameTeam = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();

// The league pickers on the Teams and Championship pages. They all edit the
// League builder's league (ui.editing); with none open, the active one opens.
async function renderLeaguePickers() {
  try {
    const { leagues } = await api("/api/leagues");
    ui.leagueList = leagues;
    const current = ui.editing && ui.editing.id;
    const html = `<option value="">${leagues.length ? "Pick a league…" : "No saved leagues yet"}</option>` +
      leagues.map((l) => `<option value="${esc(l.id)}" ${l.id === current ? "selected" : ""}>${esc(l.name)}${l.active ? " (active)" : ""}</option>`).join("");
    for (const sel of document.querySelectorAll(".league-picker")) sel.innerHTML = html;
    if (!current) {
      const active = leagues.find((l) => l.active);
      if (active) return openLeague(active.id);
    }
  } catch (err) {
    toast(err.message, true);
  }
  renderTeams();
  renderChampionship();
}

async function openLeague(id) {
  const league = await api(`/api/leagues/${encodeURIComponent(id)}`);
  openEditor(league);
  for (const sel of document.querySelectorAll(".league-picker")) sel.value = league.id;
}

function renderTeams() {
  const cards = $("#team-cards");
  if (!ui.editing) {
    cards.innerHTML = '<p class="hint">Pick a league above, or build one in the League builder first.</p>';
    $("#team-free").innerHTML = "";
    return;
  }
  const teams = editorTeams();
  const drivers = ui.editing.drivers || [];
  const label = (d) => `${d.car_number ? `#${esc(d.car_number)} ` : ""}${esc(d.name || "Unnamed")}`;
  const otherLeagues = (ui.leagueList || []).filter((l) => l.id !== ui.editing.id);
  cards.innerHTML = teams.length ? teams.map((t, i) => {
    const members = drivers.map((d, j) => [d, j]).filter(([d]) => sameTeam(d.team, t.name));
    const others = drivers.map((d, j) => [d, j]).filter(([d]) => !sameTeam(d.team, t.name));
    return `<div class="team-card" style="--team:${esc(t.color || "#3a4150")}">
      <div class="team-card-head">
        <label class="team-logo big" title="${t.logo ? "Replace logo" : "Upload logo"}">
          ${t.logo ? `<img src="${esc(logoSrc(t.logo))}" alt="">` : "+ Logo"}
          <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-team-logo="${i}" hidden>
        </label>
        <div class="team-fields">
          <input data-team="${i}" data-key="name" value="${esc(t.name)}" placeholder="Team name" aria-label="Team name">
          <div class="row">
            <input data-team="${i}" data-key="short" class="narrow" maxlength="8" value="${esc(t.short || "")}" placeholder="Short" aria-label="Short name">
            <input type="color" data-team="${i}" data-key="color" value="${esc(t.color || "#3a4150")}" aria-label="Team colour" title="Team colour">
            ${t.color ? `<button class="btn subtle" data-team-nocolor="${i}" title="Use the class colour instead">No colour</button>` : ""}
            ${t.logo ? `<button class="btn subtle" data-team-nologo="${i}">Remove logo</button>` : ""}
            <button class="btn icon danger" data-team-delete="${i}" title="Delete team">✕</button>
          </div>
        </div>
      </div>
      <div class="chips team-members">${members.map(([d, j]) => `<span class="chip">${label(d)}
        <button class="clear" data-team-unassign="${j}" title="Take out of the team">✕</button></span>`).join("") || '<span class="hint">No drivers yet</span>'}</div>
      <select data-team-add="${i}" aria-label="Add a driver to ${esc(t.name)}">
        <option value="">+ Add driver…</option>
        ${others.map(([d, j]) => `<option value="${j}">${label(d)}${d.team ? ` (${esc(d.team)})` : ""}</option>`).join("")}
      </select>
      ${otherLeagues.length ? `<div class="team-shared"><span class="hint" title="The team, and its drivers who race there too, in these leagues as well. Drivers who join one later are put in the team by themselves.">Also in:</span>
        ${otherLeagues.map((l) => `<label class="chip ${(t.shared || []).includes(l.id) ? "active" : ""}">
          <input type="checkbox" data-team-share="${i}" value="${esc(l.id)}" ${(t.shared || []).includes(l.id) ? "checked" : ""} hidden>${esc(l.name)}</label>`).join("")}</div>` : ""}
    </div>`;
  }).join("") : '<p class="hint">No teams yet: add one, or fill in the Team column in the League builder roster.</p>';
  const free = drivers.map((d, j) => [d, j]).filter(([d]) => !String(d.team || "").trim());
  $("#team-free").innerHTML = free.length ? free.map(([d]) => `<span class="chip">${label(d)}</span>`).join("")
    : '<span class="hint">Everyone is in a team.</span>';
}

document.querySelectorAll(".league-picker").forEach((sel) => sel.addEventListener("change", (e) => {
  if (!e.target.value) return;
  if (champ.dirty && !confirm("Leave without saving the championship changes?")) {
    e.target.value = ui.editing ? ui.editing.id : "";
    return;
  }
  openLeague(e.target.value).catch((err) => toast(err.message, true));
}));

$("#btn-add-team").addEventListener("click", () => {
  if (!ui.editing) return toast("Pick a league first", true);
  const teams = editorTeams();
  let n = teams.length + 1;
  while (teams.some((t) => sameTeam(t.name, `Team ${n}`))) n++;
  teams.push({ name: `Team ${n}`, short: "", color: "", logo: null });
  renderTeams();
});

$("#btn-save-teams").addEventListener("click", () => {
  if (!ui.editing) return toast("Pick a league first", true);
  saveEditor().then(() => toast("Teams saved")).catch((err) => toast(err.message, true));
});

$("#team-cards").addEventListener("change", async (e) => {
  const teams = editorTeams();
  const el = e.target;
  if (el.dataset.teamLogo != null) {
    const team = teams[+el.dataset.teamLogo];
    if (!el.files.length) return;
    try {
      await uploadImage(`team:${team.name}`, el.files[0]);
      toast(`Logo added to ${team.name}`);
    } catch (err) {
      toast(err.message, true);
    }
    return;
  }
  if (el.dataset.teamShare != null) {
    const team = teams[+el.dataset.teamShare];
    const shared = new Set(team.shared || []);
    if (el.checked) shared.add(el.value);
    else shared.delete(el.value);
    team.shared = [...shared];
    renderTeams();
    toast(el.checked ? `Save to add ${team.name} (and its drivers) to that league` : "Save to unlink it (that league keeps its copy)");
    return;
  }
  if (el.dataset.teamAdd != null) {
    if (el.value !== "") ui.editing.drivers[+el.value].team = teams[+el.dataset.teamAdd].name;
    renderTeams();
    renderRoster();
    return;
  }
  if (el.dataset.team == null) return;
  const team = teams[+el.dataset.team];
  const key = el.dataset.key;
  if (key === "name") {
    const name = el.value.trim();
    if (!name || teams.some((t) => t !== team && sameTeam(t.name, name))) {
      toast(name ? `There's already a team called ${name}` : "A team needs a name", true);
      el.value = team.name;
      return;
    }
    // Renaming moves the team's drivers with it.
    for (const d of ui.editing.drivers || []) if (sameTeam(d.team, team.name)) d.team = name;
    team.name = name;
    renderRoster();
  } else {
    team[key] = el.value.trim();
  }
  renderTeams();
});

$("#team-cards").addEventListener("click", (e) => {
  const teams = editorTeams();
  const b = e.target.closest("button");
  if (!b) return;
  const d = b.dataset;
  if (d.teamUnassign != null) ui.editing.drivers[+d.teamUnassign].team = "";
  else if (d.teamNocolor != null) teams[+d.teamNocolor].color = "";
  else if (d.teamNologo != null) teams[+d.teamNologo].logo = null;
  else if (d.teamDelete != null) {
    const team = teams[+d.teamDelete];
    if (!confirm(`Delete ${team.name}? Its drivers stay in the league without a team.`)) return;
    for (const dr of ui.editing.drivers || []) if (sameTeam(dr.team, team.name)) dr.team = "";
    teams.splice(+d.teamDelete, 1);
  } else return;
  renderTeams();
  renderRoster();
});

// -- classes ------------------------------------------------------------------

const CLASS_PALETTE = ["#e8463c", "#2f80ed", "#27ae60", "#f2c94c", "#9b51e0", "#f2994a", "#56ccf2", "#eb5ea8"];

// The class as the overlay would show it, for the editor preview.
function logoSrc(logo) {
  if (!logo) return null;
  if (logo.startsWith("lib:")) return `/logos/${encodeURIComponent(logo.slice(4))}`;
  return ui.editing.id ? `/api/logos/${encodeURIComponent(ui.editing.id)}/${encodeURIComponent(logo)}` : null;
}

// A library logo whose title matches the class name, e.g. class "Pro" -> PRO.
function libraryLogoFor(name) {
  const norm = (v) => String(v || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const key = norm(name);
  const hit = key && ui.library.find((l) => norm(l.title) === key);
  return hit ? hit.id : null;
}

function previewClass(c) {
  return {
    name: c.name || "Unnamed class",
    color: c.color,
    logo: logoSrc(c.logo),
    logo_bg: c.logo_bg || "auto",
    logo_tolerance: c.logo_tolerance ?? 18,
    logo_fill: c.logo_fill || "edges",
  };
}

function renderClasses() {
  const classes = ui.editing.classes;
  $("#ltab-classes").textContent = classes.length || "";
  $("#class-list").innerHTML = classes.length ? classes.map((c, i) => {
    const mode = c.logo_bg === "keep" ? "keep" : /^#/.test(c.logo_bg || "") ? "pick" : "auto";
    return `<div class="class-card ${isSecondary(c) ? "secondary" : ""}" data-class="${i}">
      <div class="class-preview"></div>
      <div class="class-fields">
        <label>Name <input data-cfield="name" value="${esc(c.name)}" placeholder="e.g. Pro"></label>
        <label>Colour <input type="color" data-cfield="color" value="${esc(c.color)}"></label>
        <label title="Main: shown on the overlays. Secondary: picked by hand, only for its own championship">Kind
          <select data-cfield="role">
            <option value="main" ${isSecondary(c) ? "" : "selected"}>Main class (on the overlays)</option>
            <option value="secondary" ${isSecondary(c) ? "selected" : ""}>Secondary class (own championship only)</option>
          </select></label>
        ${isSecondary(c) ? '<span class="grow hint">Give drivers this class in the Drivers list\'s <i>2nd class</i> column.</span>'
          : `<label class="grow">iRacing classes <input data-cfield="match" value="${esc((c.match || []).join(", "))}" placeholder="e.g. GT3, GT4 (optional)"></label>`}
        <button class="btn icon danger" data-remove-class="${i}" title="Remove class">✕</button>
      </div>
      <div class="class-fields">
        <span class="field-label">Logo</span>
        <select data-cfield="library" aria-label="Logo from library">
          <option value="">${ui.library.length ? "Library…" : "No library logos"}</option>
          ${ui.library.map((l) => `<option value="${esc(l.id)}" ${c.logo === l.id ? "selected" : ""}>${esc(l.title)}</option>`).join("")}
        </select>
        <label class="btn">${c.logo && !c.logo.startsWith("lib:") ? "Replace" : "Upload"}<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-upload="${i}" hidden></label>
        ${c.logo ? `<button class="btn subtle" data-clear-logo="${i}">Remove</button>` : ""}
        <label ${c.logo ? "" : "hidden"}>Background
          <select data-cfield="bgmode">
            <option value="auto" ${mode === "auto" ? "selected" : ""}>Match class colour</option>
            <option value="pick" class="raster-only" ${mode === "pick" ? "selected" : ""}>Pick logo background</option>
            <option value="keep" ${mode === "keep" ? "selected" : ""}>Keep logo as is</option>
          </select>
        </label>
        <input type="color" class="raster-only" data-cfield="bgcolor" value="${mode === "pick" ? esc(c.logo_bg) : "#ffffff"}" title="Logo background colour to replace" ${c.logo && mode === "pick" ? "" : "hidden"}>
        <label class="raster-only" ${c.logo && mode !== "keep" ? "" : "hidden"} title="How different a pixel can be from the background and still be recoloured">Tolerance
          <input type="range" min="0" max="60" data-cfield="logo_tolerance" value="${c.logo_tolerance ?? 18}"></label>
        <label class="raster-only" ${c.logo && mode !== "keep" ? "" : "hidden"} title="Also recolour background-coloured areas enclosed by the logo, like the inside of an O">
          <input type="checkbox" data-cfield="logo_fill" ${c.logo_fill === "all" ? "checked" : ""}> Enclosed areas too</label>
        <span class="detected hint"></span>
      </div>
    </div>`;
  }).join("") : '<p class="hint">No classes yet: drivers are grouped by their iRacing car class.</p>';
  classes.forEach((_, i) => renderClassPreview(i));
}

const previewTimers = {};

function renderClassPreview(i) {
  const card = document.querySelector(`.class-card[data-class="${i}"]`);
  const c = ui.editing && ui.editing.classes[i];
  if (!card || !c) return;
  const cls = previewClass(c);
  const count = (ui.editing.drivers || []).filter((d) => (isSecondary(c) ? d.class2_id : d.class_id) === c.id).length;
  card.querySelector(".class-preview").innerHTML =
    classHeaderHtml(cls, count ? `${count} assigned` : "", () => renderClassPreview(i));
  const hit = cls.logo && logoCache.get([cls.logo, cls.color, cls.logo_bg, cls.logo_tolerance, cls.logo_fill].join("|"));
  const detected = card.querySelector(".detected");
  card.classList.toggle("layered", !!(hit && hit.detected === "layered"));
  if (hit && hit.failed) detected.textContent = "Couldn't read this logo";
  else if (hit && hit.detected === "layered") {
    detected.textContent = c.logo_bg === "keep" ? "Layered SVG, shown as drawn" : "Layered SVG: badge is set to the class colour";
  } else if (hit && hit.detected) {
    detected.innerHTML = hit.detected === "transparent"
      ? "Detected: transparent background"
      : `Detected background <span class="swatch" style="background:${esc(hit.detected)}"></span> ${esc(hit.detected)}`;
    // Start the picker from the detected colour.
    const picker = card.querySelector('[data-cfield="bgcolor"]');
    if (picker.hidden && hit.detected !== "transparent") picker.value = hit.detected;
  } else detected.textContent = "";
}

$("#class-list").addEventListener("input", (e) => {
  const card = e.target.closest(".class-card");
  const field = e.target.dataset.cfield;
  if (!card || !field) return;
  const i = +card.dataset.class;
  const c = ui.editing.classes[i];
  const v = e.target.value;
  if (field === "role") {
    // Drivers picked for it move to the matching column.
    c.role = v;
    const [from, to] = v === "secondary" ? ["class_id", "class2_id"] : ["class2_id", "class_id"];
    (ui.editing.drivers || []).forEach((d) => {
      if (d[from] === c.id) {
        d[from] = "";
        if (!d[to]) d[to] = c.id;
      }
    });
    renderClasses();
    return renderRoster();
  }
  if (field === "library") {
    c.logo = v || null;
    c.autoLogo = false;
    return renderClasses();
  }
  if (field === "name" && (!c.logo || c.autoLogo)) {
    // Follow the name to a matching library logo until a logo is chosen by hand.
    const lib = libraryLogoFor(v);
    if (lib !== c.logo && (lib || c.autoLogo)) {
      c.logo = lib;
      c.autoLogo = !!lib;
      c.name = v;
      renderRoster();
      renderClasses();
      const input = document.querySelector(`.class-card[data-class="${i}"] [data-cfield="name"]`);
      input.focus();
      input.setSelectionRange(v.length, v.length);
      return;
    }
  }
  if (field === "match") c.match = v.split(",").map((m) => m.trim()).filter(Boolean);
  else if (field === "logo_tolerance") c.logo_tolerance = +v;
  else if (field === "logo_fill") c.logo_fill = e.target.checked ? "all" : "edges";
  else if (field === "bgcolor") c.logo_bg = v;
  else if (field === "bgmode") {
    c.logo_bg = v === "pick" ? card.querySelector('[data-cfield="bgcolor"]').value : v;
    return renderClasses();
  } else c[field] = v;
  if (field === "name") renderRoster();
  // Colour pickers fire continuously while dragging; recolour once it settles.
  clearTimeout(previewTimers[i]);
  previewTimers[i] = setTimeout(() => renderClassPreview(i), 60);
});

$("#class-list").addEventListener("change", async (e) => {
  const input = e.target.closest("[data-upload]");
  if (!input || !input.files.length) return;
  const i = +input.dataset.upload;
  const file = input.files[0];
  try {
    // Class ids are set when a class is added and kept on save.
    const saved = await uploadImage(`class:${ui.editing.classes[i].id}`, file);
    toast(`Logo added to ${saved.classes[i].name}`);
  } catch (err) {
    toast(err.message, true);
  }
});

$("#class-list").addEventListener("click", (e) => {
  const rm = e.target.closest("[data-remove-class]");
  if (rm) {
    const [removed] = ui.editing.classes.splice(+rm.dataset.removeClass, 1);
    ui.editing.drivers.forEach((d) => {
      if (d.class_id === removed.id) d.class_id = "";
      if (d.class2_id === removed.id) d.class2_id = "";
    });
    renderClasses();
    renderRoster();
    return;
  }
  const clear = e.target.closest("[data-clear-logo]");
  if (clear) {
    ui.editing.classes[+clear.dataset.clearLogo].logo = null;
    renderClasses();
  }
});

$("#btn-add-class").addEventListener("click", () => {
  const used = new Set(ui.editing.classes.map((c) => c.color));
  const color = CLASS_PALETTE.find((c) => !used.has(c)) || CLASS_PALETTE[ui.editing.classes.length % CLASS_PALETTE.length];
  // Client-side id so roster picks work before the first save.
  ui.editing.classes.push({ id: `class-${Date.now().toString(36)}`, name: "", color, match: [], logo: null, logo_bg: "auto", logo_tolerance: 18, logo_fill: "edges", role: "main" });
  renderClasses();
  renderRoster();
  $("#class-list .class-card:last-child input").focus();
});

function readEditor() {
  const p = ui.editing;
  p.name = $("#edit-name").value.trim();
  p.strip_class_prefix = $("#edit-strip-class").checked;
  return p;
}

// "(P) Dave Price" -> "Dave Price" (same rule as league.strip_class_prefix).
const CLASS_PREFIX = /^\s*\([^()]*\)\s*/;

$("#edit-strip-class").addEventListener("change", (e) => {
  if (!ui.editing) return;
  ui.editing.strip_class_prefix = e.target.checked;
  if (!e.target.checked) return;
  let filled = 0;
  for (const d of ui.editing.drivers || []) {
    const name = String(d.name || "");
    if (!d.nickname && CLASS_PREFIX.test(name)) {
      d.nickname = name.replace(CLASS_PREFIX, "").trim() || name.trim();
      filled++;
    }
  }
  renderRoster();
  toast(filled ? `Filled ${filled} nicknames with names minus their class tag. Save to keep them.`
    : "No empty nicknames to fill. Overlays will show names without the class tag.");
});

$("#roster-rows").addEventListener("input", (e) => {
  const { row, field } = e.target.dataset;
  if (row != null) ui.editing.drivers[+row][field] = e.target.value;
});
$("#roster-rows").addEventListener("change", async (e) => {
  if (e.target.dataset.field === "team") return renderTeams();
  if (e.target.dataset.field === "car_make") return renderRoster();  // update the badge
  const input = e.target.closest("[data-photo]");
  if (!input || !input.files.length) return;
  const d = ui.editing.drivers[+input.dataset.row];
  if (!d.name && !d.cust_id) return toast("Give the driver a name first", true);
  try {
    await uploadImage(`${input.dataset.photo}:${driverKey(d)}`, input.files[0]);
    toast(`${input.dataset.photo === "car" ? "Car" : "Helmet"} photo added for ${d.name}`);
  } catch (err) {
    toast(err.message, true);
  }
});
$("#roster-rows").addEventListener("click", (e) => {
  const clearPhoto = e.target.closest("[data-clear-photo]");
  if (clearPhoto) {
    ui.editing.drivers[+clearPhoto.dataset.row][`${clearPhoto.dataset.clearPhoto}_image`] = "";
    return renderRoster();
  }
  const rm = e.target.closest("[data-remove]");
  if (rm) {
    ui.editing.drivers.splice(+rm.dataset.remove, 1);
    renderRoster();
  }
});
$("#btn-import-session").addEventListener("click", async () => {
  try {
    const saved = await saveEditor();
    const r = await api(`/api/leagues/${encodeURIComponent(saved.id)}/import-session`, { method: "POST", body: {} });
    openEditor(r.league);
    toast(r.added ? `Added ${r.added} driver${r.added === 1 ? "" : "s"} from the session` : "Everyone in the session is already in this league");
  } catch (err) {
    toast(err.message, true);
  }
});

$("#btn-add-driver").addEventListener("click", () => {
  ui.editing.drivers.push({ name: "", cust_id: "", car_number: "", driver_number: "", nickname: "", team: "", notes: "", class_id: "", class2_id: "" });
  renderRoster();
  $("#roster-rows tr:last-child input").focus();
});

$("#league-list").addEventListener("click", async (e) => {
  const del = e.target.closest("[data-delete]");
  if (del) {
    e.stopPropagation();
    if (!confirm("Delete this league profile?")) return;
    await api(`/api/leagues/${encodeURIComponent(del.dataset.delete)}`, { method: "DELETE" }).catch((err) => toast(err.message, true));
    if (ui.editing && ui.editing.id === del.dataset.delete) {
      ui.editing = null;
      $("#league-editor").hidden = true;
    }
    return loadLeagues();
  }
  const li = e.target.closest("li[data-league]");
  if (li) {
    try {
      openEditor(await api(`/api/leagues/${encodeURIComponent(li.dataset.league)}`));
    } catch (err) {
      toast(err.message, true);
    }
  }
});

$("#session-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const { league } = await api("/api/leagues/from-session", { method: "POST", body: { name: $("#session-name").value } });
    toast(`Built ${league.name} from ${league.drivers.length} drivers`);
    await loadLeagues();
    openEditor(league);
  } catch (err) {
    toast(err.message, true);
  }
});

$("#btn-new-league").addEventListener("click", () => {
  openEditor({ id: "", name: "", league_id: null, source: "manual", classes: [], teams: [], drivers: [] });
  $("#edit-name").focus();
});

async function saveEditor() {
  const { league } = await api("/api/leagues", { method: "POST", body: readEditor() });
  ui.editing = league;
  await loadLeagues();
  openEditor(league);
  return league;
}

$("#btn-save-league").addEventListener("click", () =>
  saveEditor().then(() => toast("League saved")).catch((err) => toast(err.message, true)));

$("#btn-activate-league").addEventListener("click", async () => {
  try {
    const league = await saveEditor();
    await api("/api/leagues/active", { method: "POST", body: { id: league.id } });
    toast(`${league.name} is now active in the overlay`);
    await loadLeagues();
    openEditor(league);
  } catch (err) {
    toast(err.message, true);
  }
});

// ---------------------------------------------------------------------------
// updates
// ---------------------------------------------------------------------------

const update = { status: null, dismissed: false };
try {
  update.dismissed = sessionStorage.getItem("apex.updateLater") !== null;
} catch (e) { /* storage unavailable */ }

// The Updates panel on the Home page: always there, whatever the check found.
function renderUpdatePanel(st) {
  if (!st) return;
  const status = $("#upd-status");
  let text = "";
  if (!st.enabled) text = `v${st.current} · update checks are turned off in config.json`;
  else if (st.installed) text = `v${st.installed} installed, restarting…`;
  else if (st.available) text = `v${st.current} → <b>v${esc(st.latest.version)}</b> is available`;
  else if (st.checked_at && !st.error) text = `v${st.current} · up to date (checked ${new Date(st.checked_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })})`;
  else if (!st.checked_at) text = `v${st.current} · checking…`;
  else text = `v${st.current}`;
  status.innerHTML = text;
  $("#upd-error").hidden = !st.error;
  $("#upd-error").textContent = st.error || "";
  $("#upd-install").hidden = !(st.available && st.can_install && !st.installed);
  $("#upd-install").disabled = !!st.installing;
  $("#upd-check").disabled = !st.enabled;
  const page = $("#upd-page");
  page.hidden = !(st.latest && st.latest.url);
  if (st.latest) page.href = st.latest.url;
  $("#upd-token-clear").hidden = !st.has_token;
  // Open the token box when the repository can't be seen without one.
  if (st.error && !st.has_token && /private/.test(st.error)) $("#upd-token-box").open = true;
}

let updateKey = "";

// The live feed says when a check finished or found something: fetch the
// full status then (pop-up included).
function renderUpdates(u) {
  if (!u) return;
  const key = JSON.stringify(u);
  if (key === updateKey) return;
  updateKey = key;
  api("/api/update").then((st) => {
    renderUpdatePanel(st);
    showUpdate(st);
  }).catch(() => {});
}

async function updateAction(path, body = {}) {
  const st = await api(`/api/update/${path}`, { method: "POST", body });
  renderUpdatePanel(st);
  showUpdate(st);
  return st;
}

$("#upd-check").addEventListener("click", async () => {
  $("#upd-check").disabled = true;
  try {
    const st = await updateAction("check");
    if (!st.error && !st.available) toast("You're on the newest version");
  } catch (err) {
    toast(err.message, true);
  } finally {
    $("#upd-check").disabled = false;
  }
});
$("#upd-install").addEventListener("click", () => {
  showUpdate(update.status, true);
});
$("#upd-token-save").addEventListener("click", async () => {
  const token = $("#upd-token").value.trim();
  if (!token) return toast("Paste a token first", true);
  try {
    const st = await updateAction("token", { token });
    $("#upd-token").value = "";
    toast(st.error ? "Token saved, but the check failed: see Updates" : "Token saved");
  } catch (err) {
    toast(err.message, true);
  }
});
$("#upd-token-clear").addEventListener("click", async () => {
  try {
    await updateAction("token", { token: "" });
    toast("Token removed");
  } catch (err) {
    toast(err.message, true);
  }
});

function showUpdate(status, force = false) {
  update.status = status;
  const available = status && status.available && !status.installed;
  $("#update-badge").hidden = !available;
  if (!available) return;
  $("#update-badge").textContent = `Update to v${status.latest.version}`;
  // Pop up once per session, unless this version was skipped.
  if (!force && (update.dismissed || status.skipped)) return;
  $("#update-current").textContent = `v${status.current}`;
  $("#update-latest").textContent = `v${status.latest.version}`;
  $("#update-notes").innerHTML = notesHtml(status.latest.notes || "");
  $("#update-hint").innerHTML = status.git_checkout
    ? "This copy is a git checkout: run <code>git pull</code> to update, then restart."
    : `Your settings and leagues are kept. The app restarts by itself. <a href="${esc(status.latest.url)}" target="_blank" rel="noopener">Release page</a>`;
  $("#update-install").hidden = !status.can_install;
  $("#update-install").disabled = false;
  $("#update-install").textContent = "Update now";
  $("#update-modal").hidden = false;
}

// Just enough markdown for release notes: headings ("## v1.2.3" versions,
// "### Fixes" sections), bullets, **bold**, `code`. A wrapped line carries
// on the bullet or paragraph above it.
function notesHtml(md) {
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const blocks = [];  // [kind, text]: "ver", "h", "li" or "p"
  for (const raw of md.trim().split(/\r?\n/)) {
    const line = raw.trim();
    const last = blocks[blocks.length - 1];
    if (!line) {
      if (last) last.done = true;
      continue;
    }
    const bullet = line.match(/^[-*]\s+(.*)/);
    if (/^#{1,2}\s/.test(line)) blocks.push({ kind: "ver", text: line.replace(/^#+\s*/, ""), done: true });
    else if (/^#{3,6}\s/.test(line)) blocks.push({ kind: "h", text: line.replace(/^#+\s*/, ""), done: true });
    else if (bullet) blocks.push({ kind: "li", text: bullet[1] });
    else if (last && !last.done && (last.kind === "li" || last.kind === "p")) last.text += ` ${line}`;
    else blocks.push({ kind: "p", text: line });
  }
  const out = [];
  blocks.forEach((b, i) => {
    const prev = blocks[i - 1];
    if (b.kind === "li" && (!prev || prev.kind !== "li")) out.push("<ul>");
    if (b.kind === "ver") out.push(`<h3 class="notes-ver">${inline(b.text)}</h3>`);
    else if (b.kind === "h") out.push(`<h4>${inline(b.text)}</h4>`);
    else if (b.kind === "li") out.push(`<li>${inline(b.text)}</li>`);
    else out.push(`<p>${inline(b.text)}</p>`);
    const next = blocks[i + 1];
    if (b.kind === "li" && (!next || next.kind !== "li")) out.push("</ul>");
  });
  return out.join("");
}

function closeUpdate() {
  $("#update-modal").hidden = true;
}

async function checkForUpdate(attempt = 0) {
  try {
    const status = await api("/api/update");
    if (!status.enabled) return renderUpdatePanel(status);
    renderUpdatePanel(status);
    // The server checks GitHub in the background at start: wait for it.
    if (!status.checked_at && attempt < 10) return setTimeout(() => checkForUpdate(attempt + 1), 3000);
    showUpdate(status);
  } catch (e) { /* server not reachable yet: the stream reconnect handles it */ }
}

$("#update-badge").addEventListener("click", () => showUpdate(update.status, true));
$("#update-later").addEventListener("click", () => {
  update.dismissed = true;
  try {
    sessionStorage.setItem("apex.updateLater", "1");
  } catch (e) { /* storage unavailable */ }
  closeUpdate();
});
$("#update-skip").addEventListener("click", async () => {
  await api("/api/update/skip", { method: "POST", body: { version: update.status.latest.version } }).catch(() => {});
  closeUpdate();
  toast(`You won't be asked about v${update.status.latest.version} again`);
});
$("#update-install").addEventListener("click", async () => {
  const btn = $("#update-install");
  btn.disabled = true;
  btn.textContent = "Installing…";
  try {
    const r = await api("/api/update/install", { method: "POST", body: {} });
    btn.textContent = "Restarting…";
    ui.expectVersion = r.version;
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Update now";
    toast(err.message, true);
  }
});
$("#update-modal").addEventListener("click", (e) => {
  if (e.target.id === "update-modal") closeUpdate();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#update-modal").hidden) closeUpdate();
});

connectStream();
checkForUpdate();
