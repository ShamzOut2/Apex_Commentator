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
  { battleGap: 0.15, battleColor: "#ff3b6b", rewind: 10, logPreroll: 10, hotkeys: null, actionKeys: {},
    nameFormat: "full", showNick: true, keepLeft: true, logHidden: [], timingCols: 1, clock: "elapsed" },
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

// Started once this script has run, even if a later part of it fails, so the
// page still gets the app's state (Show / Hide, settings, hotkeys).
setTimeout(connectStream, 0);

// A part of the page that fails to draw is written to apex.log and skipped,
// rather than stopping the rest of the page from being drawn.
const failedParts = new Set();
function safely(part, draw) {
  try {
    draw();
  } catch (e) {
    if (failedParts.has(part)) return;
    failedParts.add(part);
    console.error(e);
    try {
      fetch("/api/client_error", { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
        body: JSON.stringify({ page: location.pathname + location.search, message: `${part}: ${e && e.message ? e.message : e}`,
          source: "app.js", line: 0, stack: String((e && e.stack) || "").slice(0, 3000) }) }).catch(() => {});
    } catch (err) { /* nowhere to send it */ }
  }
}

function connectStream() {
  liveStream((snap) => {
    ui.snap = snap;
    if (snap.overlays && snap.overlays.settings && snap.overlays.settings.general) GENERAL = snap.overlays.settings.general;
    // After an update the server restarts on the new version: load its UI.
    if (ui.version && ui.snap.version && ui.snap.version !== ui.version) return location.reload();
    ui.version = ui.version || ui.snap.version;
    $(".brand").title = `Apex Commentator v${ui.snap.version}`;
    safely("render", render);
  }, () => {
    $("#status-dot").classList.remove("on");
    $("#session-line").textContent = "Overlay server not reachable, retrying…";
  });
}

// ---------------------------------------------------------------------------
// dual commentary: this app's camera shared, or another app's followed (remote.py)
// ---------------------------------------------------------------------------

function renderDual(r) {
  if (!r) return;
  const sh = r.share;
  const fo = r.follow;
  const box = $("#share-on");
  if (document.activeElement !== box) box.checked = sh.on;
  $("#share-info").hidden = !sh.on;
  const addrs = (sh.addresses || []).map((a) => `${a}:${sh.port}`);
  $("#share-addr").textContent = addrs.join("  or  ") || `this PC's address:${sh.port}`;
  $("#share-code").textContent = sh.code;
  $("#share-followers").textContent = sh.followers ? `${sh.followers} following your camera` : "Nobody following yet";
  document.querySelectorAll(".share-port").forEach((el) => { el.textContent = sh.port; });
  for (const [id, v] of [["#follow-address", fo.address], ["#follow-code", fo.code]]) {
    if (document.activeElement !== $(id) && !$(id).dataset.typed) $(id).value = v;
  }
  $("#follow-start").hidden = fo.on;
  $("#follow-stop").hidden = !fo.on;
  const host = fo.host;
  $("#follow-status").textContent = !fo.on ? ""
    : fo.status === "following" ? `Following: ${host && host.car ? `#${host.car} ${host.driver}${host.group ? `, ${host.group}` : ""}${host.live === false ? " (replay)" : ""}` : "connected"}`
      : fo.status === "connecting" ? "Connecting…" : `${fo.error || "Not connected"}: trying again…`;
  $("#follow-status").className = `hint ${fo.on && fo.status === "error" ? "bad" : ""}`;
  $("#dual-state").textContent = sh.on ? `Sharing your camera${sh.followers ? ` · ${sh.followers} following` : ""}` : fo.on ? "Following" : "";
  const badge = $("#dual-badge");
  badge.hidden = !sh.on && !fo.on;
  badge.textContent = fo.on ? (fo.status !== "following" ? "○ Following: not connected" : fo.free ? "◌ Free mode" : "● Following the host")
    : `📡 Camera shared${sh.followers ? ` (${sh.followers})` : ""}`;
  badge.classList.toggle("live", fo.on ? fo.status === "following" && !fo.free : sh.followers > 0);
  badge.classList.toggle("free", fo.on && fo.free);
  // Free mode (their own camera) and Sync (back with the host), while following.
  $("#dual-follow").hidden = !fo.on;
  $("#cam-sync").hidden = !fo.on;
  badge.hidden = badge.hidden || (fo.on && fo.status === "following");  // the FREE | SYNC pill says it
  for (const pill of document.querySelectorAll(".sync-pill")) {
    pill.classList.toggle("free", !!fo.free);
    pill.classList.toggle("off", fo.status !== "following");
  }
  ui.followFree = !!fo.free;
}

// The FREE | SYNC switch in a small window on top of iRacing (sync.html); in a
// browser, a small browser window.
document.addEventListener("click", async (e) => {
  if (!e.target.closest("[data-sync-widget]")) return;
  const r = await cmd("sync_widget", { on: true });
  if (r && r.opened) return toast("FREE | SYNC is on your screen: drag it by ⠿, close it with ✕");
  const w = window.open("/sync.html", "apex-sync", "width=340,height=80");
  if (!w) toast("The browser blocked the pop-up window: allow pop-ups for this page.", true);
});

// The FREE | SYNC pill (top bar, Timing Screen): click to switch.
document.addEventListener("click", (e) => {
  const pill = e.target.closest("[data-sync-toggle]");
  if (!pill) return;
  pill.blur();
  const free = !ui.followFree;
  cmd("follow_free", { on: free }, free ? "Free mode: your own camera until you Sync" : "Synced with the host");
});

$("#share-on").addEventListener("change", (e) => {
  e.target.blur();
  cmd("share_camera", { on: e.target.checked }, e.target.checked ? "Your camera can be followed" : "Stopped sharing your camera");
});
$("#share-new-code").addEventListener("click", () => cmd("share_new_code", {}, "New code: tell your co-commentator"));
for (const id of ["#follow-address", "#follow-code"]) $(id).addEventListener("input", (e) => { e.target.dataset.typed = "1"; });
$("#follow-start").addEventListener("click", async () => {
  const r = await cmd("follow_camera", { on: true, address: $("#follow-address").value, code: $("#follow-code").value }, "Following the host's camera");
  if (r) for (const id of ["#follow-address", "#follow-code"]) delete $(id).dataset.typed;
});
$("#follow-stop").addEventListener("click", () => cmd("follow_camera", { on: false }, "Stopped following"));
$("#follow-code").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#follow-start").click(); });

// ---------------------------------------------------------------------------
// live timing website for spectators (spectate.py)
// ---------------------------------------------------------------------------

function renderLive(sp) {
  if (!sp) return;
  const box = $("#live-on");
  if (document.activeElement !== box) box.checked = sp.on;
  $("#live-info").hidden = !sp.on;
  const url = sp.url || sp.address;
  $("#live-url").textContent = url || (sp.status === "downloading" ? "Getting Cloudflare's tunnel (first time only)…" : sp.status === "error" ? "Not online yet" : "Starting…");
  $("#live-open").href = url || sp.local || "#";
  $("#live-open").hidden = !(url || sp.local);
  $("#live-detail").textContent = !sp.on ? "" : sp.status === "error" ? `${sp.error || "The tunnel stopped"}: trying again…`
    : `${sp.viewers} watching. ${sp.own ? "Your own address." : "A free link: it changes each time it's turned on."} On this PC only: ${sp.local}`;
  $("#live-detail").classList.toggle("bad", sp.status === "error");
  $("#live-state").textContent = sp.on ? (sp.status === "online" ? `online · ${sp.viewers} watching` : sp.status) : "";
  $("#home-live-state").textContent = $("#live-state").textContent || "off";
  // The preview: the page itself, from this PC (not counted as watching).
  const frame = $("#live-frame");
  const src = sp.on && sp.local ? `${sp.local}?preview=1` : "";
  if ((frame.getAttribute("src") || "") !== src) {
    if (src) frame.setAttribute("src", src);
    else frame.removeAttribute("src");
  }
  $("#live-frame-off").hidden = !!src;
  if (document.activeElement !== $("#live-address") && !$("#live-address").dataset.typed) $("#live-address").value = sp.address || "";
  $("#live-token").placeholder = sp.own ? "Tunnel token (saved: paste a new one to change it)" : "Tunnel token";
}

// The preview is drawn at a PC's size (1280 x 720) and shrunk to fit.
new ResizeObserver(([e]) => {
  $("#live-frame").style.transform = `scale(${e.contentRect.width / 1280})`;
}).observe(document.querySelector(".live-frame"));

// The page's settings (the "live" settings, saved like a widget's).
let liveFormKey = "";
function renderLiveForm(s) {
  const values = s.overlays && s.overlays.settings && s.overlays.settings.live;
  if (!values) return;
  const key = JSON.stringify([values, !!ovDefaults]);
  if (key === liveFormKey || document.activeElement.closest("#live-form")) return;
  liveFormKey = key;
  $("#live-form").innerHTML = plainSettingsHtml("live", values, LIVE_FIELDS, s);
}

$("#live-on").addEventListener("change", (e) => {
  e.target.blur();
  cmd("spectate", { on: e.target.checked }, e.target.checked ? "Live timing going online…" : "Live timing offline");
});
$("#live-address").addEventListener("input", (e) => { e.target.dataset.typed = "1"; });
$("#live-save").addEventListener("click", async () => {
  const on = !!(ui.snap && ui.snap.spectate && ui.snap.spectate.on);
  const token = $("#live-token").value.trim();
  const params = { on, address: $("#live-address").value.trim() };
  if (token || !params.address) params.token = token;  // empty address and token: back to the free link
  const r = await cmd("spectate", params, "Saved");
  if (r) {
    $("#live-token").value = "";
    delete $("#live-address").dataset.typed;
  }
});

// ---------------------------------------------------------------------------
// rendering
// ---------------------------------------------------------------------------

let hotkeysSent = false;

function render() {
  const s = ui.snap;
  // The app's saved keys win; a window with keys the app hasn't saved yet (from
  // before they were kept there) hands them over once.
  const savedKeys = s.hotkeys && s.hotkeys.saved;
  if (savedKeys) safely("adoptHotkeys", () => adoptHotkeys(s));
  if (!hotkeysSent && s.camera) {
    hotkeysSent = true;
    if (!savedKeys) sendHotkeys();  // this window's keys, once the cameras are known
  }
  $("#status-dot").classList.toggle("on", !!s.connected);
  safely("renderDual", () => renderDual(s.remote));
  safely("renderLive", () => renderLive(s.spectate));
  safely("renderLiveForm", () => renderLiveForm(s));
  if (s.data_delay_s != null && document.activeElement !== $("#data-delay")) $("#data-delay").value = s.data_delay_s;
  const general = s.overlays && s.overlays.settings && s.overlays.settings.general;
  if (general && document.activeElement !== $("#timing-decimals")) $("#timing-decimals").value = String(general.race_decimals);
  const league = s.league;
  const off = s.officials || { on: false, league: null };
  const lb = $("#league-badge");
  lb.textContent = off.on ? (off.league || "No league") : league ? league.name : "No league";
  lb.classList.toggle("active", !off.on && !!league);
  lb.classList.toggle("muted", off.on || !league);
  $("#officials-badge").classList.toggle("active", !!off.on);
  safely("renderGridwalk", () => renderGridwalk(s));
  safely("renderHome", () => renderHome(s));
  safely("renderUpdates", () => renderUpdates(s.update));
  safely("renderResultsAuto", () => renderResultsAuto(s.results_auto));
  safely("renderOverlaySettings", () => renderOverlaySettings(s));
  safely("renderBattlePick", () => renderBattlePick(s));
  safely("renderStrategyPick", () => renderStrategyPick(s));
  safely("renderInsightPicks", () => renderInsightPicks(s));
  safely("renderTalking", () => renderTalking(s));
  safely("renderRaceControl", () => renderRaceControl(s));
  safely("renderChampLive", () => renderChampLive(s));
  safely("renderBoards", () => renderBoards(s));
  safely("renderDesktop", () => renderDesktop(s));

  if (!s.connected) {
    $("#session-line").textContent = s.source === "iracing" ? "Waiting for iRacing…" : "Not connected";
    $("#replay-badge").textContent = "—";
    $("#replay-badge").className = "badge";
    $("#standings-rows").innerHTML = "";
    secondList().innerHTML = "";
    rowEls.clear();
    safely("updateBattleHints", () => updateBattleHints());
    $("#standings-empty").hidden = false;
    $("#log-status").textContent = "";
    return;
  }

  const ses = s.session;
  const track = [ses.track, ses.track_config].filter(Boolean).join(" – ");
  // The session clock: time passed, or time left (click it to switch; kept for this PC).
  const remaining = settings.clock === "remaining" && ses.time_remain != null;
  const clock = remaining ? `${fmtClock(ses.time_remain)} left` : fmtClock(ses.time);
  const clockTip = ses.time_remain == null ? "Time passed (the session isn't timed)"
    : remaining ? "Time left: click for time passed" : "Time passed: click for time left";
  $("#session-line").innerHTML =
    `<b>${esc(track)}</b> · ${esc(ses.type || ses.name)} · ${esc(ses.state)} · <button type="button" class="clock-btn" data-clock title="${clockTip}">${clock}</button>` +
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

  safely("renderCamButtons", () => renderCamButtons(s.camera));
  safely("renderStandings", () => renderStandings(s));
  safely("renderLog", () => renderLog(s));
  safely("renderReplayData", () => renderReplayData(s));
}

// What iRacing sends for the cars during a replay (set, or found by the app),
// and the replay data check (a file, a row a second).
function renderReplayData(s) {
  const rd = s.replay_data;
  if (!rd) return;
  const sel = $("#replay-car-data");
  if (document.activeElement !== sel && sel.value !== rd.mode) sel.value = rd.mode;
  const found = { live: "live during replays", replay: "the replay's: timed at the line" }[rd.found];
  $("#replay-found").textContent = rd.mode === "auto" ? (found ? `found: ${found}` : "not known yet: pause a replay mid-race") : "";
  const btn = $("#replay-check");
  btn.textContent = rd.check.on ? `■ Stop check (${rd.check.rows} s)` : "● Record check";
  btn.classList.toggle("on-air", !!rd.check.on);
  btn.dataset.on = rd.check.on ? "1" : "";
}
$("#show-log").addEventListener("click", () => cmd("show_log", {}, (r) => `Opened the folder with ${r.path}`));
$("#replay-check-folder").addEventListener("click", () => cmd("replay_check_folder", {}, (r) => `Opened ${r.folder}`));
$("#session-line").addEventListener("click", (e) => {
  if (!e.target.closest("[data-clock]")) return;
  settings.clock = settings.clock === "remaining" ? "elapsed" : "remaining";
  saveSettings();
  if (ui.snap && ui.snap.connected) render();
});
$("#replay-car-data").addEventListener("change", (e) => cmd("replay_car_data", { mode: e.target.value }, "Replay data set"));
$("#replay-check").addEventListener("click", async (e) => {
  const on = !e.currentTarget.dataset.on;
  const r = await cmd("replay_check", { on });
  if (r && r.check) toast(on ? `Recording the replay data check: ${r.check.file}` : `Replay data check saved: ${r.check.file} (${r.check.rows} rows)`);
});

// -- pages ----------------------------------------------------------------------

const PAGE_KEY = "apex.page";
// ?popout=timing: one page in a window of its own (the Pop out buttons), without the tabs.
const POPOUT = new URLSearchParams(location.search).get("popout");

// The Timing tab's name style (Names): any but the full name leaves off a "(P)" class tag.
function timingName(name) {
  if (settings.nameFormat === "full") return name;
  return formatName({ name: String(name || "").replace(/^\s*\([^()]*\)\s*/, "") }, settings.nameFormat);
}

// A nickname that's just the name without its "(P)" class tag says nothing new.
function sameButClassTag(name, nickname) {
  return String(name || "").replace(/^\s*\([^()]*\)\s*/, "").trim().toLowerCase() === String(nickname || "").trim().toLowerCase();
}

function showPage(name) {
  name = { overlays: "widgets", boards: "widgets" }[name] || name;  // the tabs they became
  if (!document.getElementById(`tab-${name}`)) name = "home";
  const was = document.querySelector(".panel.active");
  if (was && was.id === "tab-hotkeys" && name !== "hotkeys") {
    // Leaving the Hotkeys tab: the camera and board buttons show their new keys.
    hotkeyTarget = null;
    camKey = "";
    boardButtonsKey = "";
    if (ui.snap && ui.snap.connected) renderCamButtons(ui.snap.camera);
  }
  if (name === "hotkeys") {
    hotkeyTarget = null;
    renderHotkeyList();
    $("#hotkeys-back").hidden = !POPOUT;
  }
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
    ? `${drivers} drivers · ${s.events_total ?? (s.events || []).length} logged${battles ? ` · ${battles} in battles` : ""}`
    : "Offline";
  const league = s.league;
  $("#tile-teams").textContent = league ? `${league.teams} teams in ${league.name}` : "No league active";
  const g = s.gridwalk || {};
  const keysSet = Object.keys(settings.actionKeys || {}).length + Object.keys(settings.hotkeys || {}).length;
  $("#tile-hotkeys").textContent = keysSet ? `${keysSet} keys set` : "No keys set yet";
  $("#tile-gridwalk").textContent = g.visible ? (g.running ? "● On air" : "❚❚ On air, paused") : `${(g.entries || []).length} on the grid`;
  $("#tile-league").textContent = s.league ? `Active: ${s.league.name}` : "No league active";
  renderChecklist(s, keysSet);
}

// Home: the race-day checklist. Each line says how it stands and goes to where it's set.
let checklistKey = "";
function renderChecklist(s, keysSet) {
  const ov = s.overlays && s.overlays.settings || {};
  const onAir = WIDGETS.filter((w) => !w.general && !w.board && ov[w.key] && ov[w.key].visible).map((w) => w.name);
  const sp = s.spectate || {};
  const items = [
    s.connected ? ["good", "iRacing connected", $("#home-session").textContent, "timing", "Timing Screen"]
      : ["warn", "iRacing not connected", "Join or spectate a session in iRacing: the app connects by itself.", "", ""],
    s.league ? ["good", `League: ${s.league.name}`, `Its names, ${s.league.teams} teams, classes and logos on every widget.`, "league", "League builder"]
      : [s.officials && s.officials.on ? "good" : "warn", s.officials && s.officials.on ? "Officials mode" : "No league picked", s.officials && s.officials.on ? "Plain iRacing names and classes." : "Pick your league for names, teams and colours on stream.", "league", "League builder"],
    [onAir.length ? "good" : "idle", onAir.length ? `On stream: ${onAir.slice(0, 4).join(", ")}${onAir.length > 4 ? ` and ${onAir.length - 4} more` : ""}` : "Nothing on stream yet",
      "Each overlay is a Browser Source in OBS (its link is in Widget Settings).", "widgets", "Widgets"],
    [sp.on ? "good" : "idle", sp.on ? "Live timing website online" : "Live timing website off", sp.on ? (sp.url || "Starting…") : "Optional: a timing page for spectators.", "live", "Live timing"],
    [keysSet ? "good" : "idle", keysSet ? `${keysSet} hotkeys set` : "No hotkeys set", "Keys for cameras, overlays and boards, from any program.", "hotkeys", "Hotkeys"],
  ];
  const key = JSON.stringify(items);
  if (key === checklistKey) return;
  checklistKey = key;
  $("#race-checklist").innerHTML = `<h3>Race day</h3>${items.map(([state, title, detail, tab, label]) => `<div class="check-line ${state}">
    <i aria-hidden="true"></i><div><b>${esc(title)}</b><small>${esc(detail)}</small></div>
    ${tab ? `<button type="button" class="btn subtle" data-goto="${tab}">${esc(label)} ›</button>` : ""}</div>`).join("")}`;
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
  const one = (p) => ({ arrowup: "↑", arrowdown: "↓", " ": "Space", ctrl: "Ctrl", alt: "Alt", shift: "Shift" }[p]
    || (/^num\d$/.test(p) ? `Num ${p.slice(3)}` : p.length === 1 || /^f\d+$/.test(p) ? p.toUpperCase() : p));
  return String(k).split("+").map((p) => one(p || "+")).join("+");
}

// A key as the hotkeys keep it: "c", "1", or with Ctrl / Alt (and Shift)
// "ctrl+alt+1". With modifiers, the key itself is read from where it is on
// the keyboard (so Shift+1 is "shift+1", not "!").
function keyOf(e) {
  const mods = (e.ctrlKey ? "ctrl+" : "") + (e.altKey ? "alt+" : "") + ((e.ctrlKey || e.altKey) && e.shiftKey ? "shift+" : "");
  if (!mods) return e.key.toLowerCase();
  const c = e.code || "";
  const base = /^Key[A-Z]$/.test(c) ? c.slice(3).toLowerCase() : /^Digit\d$/.test(c) ? c.slice(5)
    : /^Numpad\d$/.test(c) ? `num${c.slice(6)}` : /^F\d{1,2}$/.test(c) ? c.toLowerCase() : e.key.toLowerCase();
  return mods + base;
}

// Keys with Ctrl or Alt work whichever program is in front (the app registers
// them with Windows; see apex/hotkeys.py): it's told about every change.
const systemWide = (k) => /(^|\+)(ctrl|alt)\+/.test(k);
// The keys live in the app's settings (cmd_hotkeys), so every window (the app,
// pop-outs, a browser) has the same ones and they survive updates. ``hotkeyV``:
// the version of them this window has.
let hotkeyV = null;
let hotkeySending = 0;
function sendHotkeys() {
  const groups = (ui.snap && ui.snap.camera && ui.snap.camera.groups) || [];
  const keys = {};
  for (const [name, k] of Object.entries(hotkeys(groups))) if (systemWide(k)) keys[k] = `cam:${name}`;
  for (const [id, k] of Object.entries(settings.actionKeys || {})) if (systemWide(k)) keys[k] = id;
  hotkeySending += 1;
  return api("/api/cmd", { method: "POST", body: { action: "hotkeys", params: { keys, cameras: settings.hotkeys, actions: settings.actionKeys || {} } } })
    .then((r) => { if (r && r.v != null) hotkeyV = r.v; })
    .catch(() => {})
    .finally(() => { hotkeySending -= 1; });
}

// Keys saved by another window (or before an update): use them here too.
function adoptHotkeys(s) {
  const saved = s.hotkeys && s.hotkeys.saved;
  if (!saved || hotkeySending || saved.v === hotkeyV || hotkeyTarget) return false;
  hotkeyV = saved.v;
  settings.hotkeys = saved.cameras || null;
  settings.actionKeys = saved.actions || {};
  saveSettings();
  camKey = "";
  boardButtonsKey = "";
  return true;
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
  // Drivers who've left the event: listed (marked LEFT) unless that's turned off.
  const rows = (s.drivers || []).filter((r) => (ui.classFilter === "all" || r.class_key === ui.classFilter)
    && (settings.keepLeft || !r.left));
  const race = isRace(s);
  const fastest = Math.min(...rows.map((r) => r.best_lap || Infinity));
  // The best lap in purple, as the tower's stopwatch is set: each class's
  // fastest, the overall one in All and the class's in a class ("view"), or
  // the overall fastest only (the session's, whichever class is picked).
  const all = (s.drivers || []).filter((r) => !r.hidden && r.best_lap > 0);
  const overallBest = Math.min(...all.map((r) => r.best_lap), Infinity);
  const classBest = {};
  for (const r of all) classBest[r.class_key] = Math.min(classBest[r.class_key] ?? Infinity, r.best_lap);
  const flFor = (((s.overlays || {}).settings || {}).standings || {}).fastest_icon_for || "classes";
  const purple = (r) => {
    if (!(r.best_lap > 0)) return false;
    const ov = r.best_lap === overallBest, cl = r.best_lap === classBest[r.class_key];
    return flFor === "overall" ? ov : flFor === "view" ? (ui.classFilter === "all" ? ov : cl) : ov || cl;
  };
  const leaderGap = rows.length ? rows[0].gap : null;
  let prev = null;
  return rows.map((r) => {
    let gap = null, int = null;
    if (race && r.gap != null && leaderGap != null) {
      // A class picked: its own timing against the class leader (never below 0:
      // the leader's ahead of it, whatever two gaps measured apart say).
      gap = ui.classFilter !== "all" && r.class_gap != null ? r.class_gap : Math.max(0, r.gap - leaderGap);
      if (prev && prev.gap != null) int = Math.max(0, r.gap - prev.gap);
    }
    const down = race ? (ui.classFilter === "all" ? r.laps_down : r.class_laps_down) || 0 : 0;
    const v = { r, gap, int, down, fastestLap: isFinite(fastest) && r.best_lap === fastest, fastest, purple: purple(r) };
    prev = r;
    return v;
  });
}

// car_idx of every driver within the battle gap of the car ahead (just them,
// not the car they're closing on).
function findBattles(s, rows) {
  const out = new Set();
  if (!isRace(s) || s.session.state !== "Racing") return out;
  const view = rows === s.drivers ? standingsView(s) : rows;
  view.forEach((v, i) => {
    const ahead = view[i - 1];
    const fighting = (x) => x.r.in_world && !x.r.on_pit;
    if (ahead && v.int != null && v.int >= 0 && v.int <= settings.battleGap && fighting(v) && fighting(ahead)) {
      out.add(v.r.car_idx);
    }
  });
  return out;
}

const FLAG_LABELS = {
  green: "Green", yellow: "Yellow", blue: "Blue", white: "White", checkered: "Chequered",
  black: "Black", meatball: "Meatball", warning: "Slow down", dq: "DQ",
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
      // The leader's interval: as the tower has it (Leader, their lap, or nothing).
      const lead = (((s.overlays || {}).settings || {}).standings || {}).leader_interval || "leader";
      int = v.r === firstRow ? (lead === "blank" ? "" : lead === "lap" && r.lap ? `Lap ${r.lap}` : "Leader")
        : v.int == null ? "" : fmtDelta(v.int);
      // Gone from the session (or out of the car, not finished): OUT instead.
      if ((r.left || (!r.in_world && r.laps_completed > 0)) && v.r !== firstRow) gap = int = '<span class="tag out">OUT</span>';
    } else if (r.best_lap && isFinite(v.fastest)) {
      gap = v.fastestLap ? "Fastest" : fmtDelta(r.best_lap - v.fastest, false);
    }
    const status = r.left ? '<span class="tag out" title="Left the session">LEFT</span>'
      : !r.in_world ? '<span class="tag out">OUT</span>'
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
      [r.make_logo ? `<img class="make-logo" src="${esc(r.make_logo)}" alt="${esc(r.make || "")}" title="${esc(r.make || "")}">` : "", "c-make"],
      [`<span class="name">${esc(timingName(r.name))}</span>${settings.showNick && lg && lg.nickname && !sameButClassTag(r.name, lg.nickname) ? `<span class="nick">“${esc(lg.nickname)}”</span>` : ""}` +
        `${team ? `<span class="sub">${esc(team)}</span>` : ""} ${status}${r.hidden ? ' <span class="tag out" title="No class in the league: left off the overlays and out of the results">NO CLASS</span>' : ""}`, "driver-cell"],
      [String(r.lap ?? "")],
      [gap, "c-time"],
      // Within the battle gap of the car ahead: just this cell lit up.
      [int, `c-time ${battles.has(r.car_idx) ? "battle-cell" : ""}`],
      [fmtLap(r.last_lap), "c-time col-wide"],
      [fmtLap(r.best_lap), `c-time col-wide ${v.purple ? "best" : ""}`],
      [r.pit_stops ? String(r.pit_stops) : "", "col-wide"],
      [r.on_pit ? "PIT" : r.stint != null ? String(r.stint) : "", "c-num"],
      [tyreIcon(r.tyre), "c-tyre"],
      [flag],
      [(r.penalties || []).map((p) => `<span class="pen">⚑ ${esc(p)}</span>`).join(" ")],
      [r.incidents == null ? "" : r.incidents + "x"],
    ], { "data-car": String(r.car_idx), "data-pos": String(r.pos ?? ""), title: `Click to watch ${r.name}` });
  });
  const keep = new Set(ordered);
  for (const [key, tr] of rowEls) {
    if (!keep.has(tr)) {
      tr.remove();
      rowEls.delete(key);
    }
  }
  // One list, or two side by side: the first half of the field on the left.
  const half = settings.timingCols === 2 ? Math.ceil(ordered.length / 2) : ordered.length;
  const lists = [[$("#standings-rows"), ordered.slice(0, half)], [secondList(), ordered.slice(half)]];
  // Drivers changing places slide past each other (only looked at when the
  // order has changed: finding where rows are makes the browser lay out the page).
  const reorder = () => {
    for (const [body, rows] of lists) {
      rows.forEach((tr, i) => {
        if (body.children[i] !== tr) body.insertBefore(tr, body.children[i] || null);
      });
    }
  };
  const placed = lists.every(([body, rows]) => body.children.length === rows.length && rows.every((tr, i) => body.children[i] === tr));
  if (placed) reorder();
  else flipRows($("#std-lists"), "tr[data-car]", reorder, 350, (el) => el.dataset.car);
  updateBattleHints();
}

// The second list (two lists side by side): the same headings, the second half
// of the field. Made the first time it's wanted.
function secondList() {
  let body = document.getElementById("standings-rows-2");
  if (!body) {
    const first = $("#standings-table");
    const table = document.createElement("table");
    table.className = `${first.className} std-second`;
    table.appendChild(first.tHead.cloneNode(true));
    body = table.appendChild(document.createElement("tbody"));
    body.id = "standings-rows-2";
    $("#std-lists").appendChild(table);
  }
  return body;
}

// A battle (a driver within the battle gap of the car ahead) scrolled out of
// sight: a pill at the top or bottom of the list says so (the nearest one's
// place, and how many); click it to go there.
function updateBattleHints() {
  const box = $("#standings-scroll");
  const view = box.getBoundingClientRect();
  const head = ($("#standings-table").tHead || {}).offsetHeight || 0;
  const above = [], below = [];
  for (const tr of box.querySelectorAll("tr.battle")) {
    const at = tr.getBoundingClientRect();
    if (at.bottom <= view.top + head + 4) above.push(tr);
    else if (at.top >= view.bottom - 4) below.push(tr);
  }
  hint($("#battle-up"), above[above.length - 1], above.length, "▲", "above");
  hint($("#battle-down"), below[0], below.length, "▼", "below");
}

function hint(el, nearest, count, arrow, where) {
  el.hidden = !count;
  if (!count) return;
  const pos = nearest.dataset.pos ? ` · P${nearest.dataset.pos}` : "";
  const text = `${arrow} ${count === 1 ? "Battle" : `${count} battles`} ${where}${pos}`;
  if (el.textContent !== text) el.textContent = text;
  el.dataset.car = nearest.dataset.car;
}

$("#standings-scroll").addEventListener("scroll", updateBattleHints, { passive: true });
window.addEventListener("resize", updateBattleHints);
for (const id of ["#battle-up", "#battle-down"]) {
  $(id).addEventListener("click", (e) => {
    e.stopPropagation();
    const tr = rowEls.get(`d${e.currentTarget.dataset.car}`);
    if (tr) tr.scrollIntoView({ block: "center", behavior: "smooth" });
  });
}

// One list or two side by side (kept for this PC).
function applyTimingCols() {
  const dual = settings.timingCols === 2;
  $(".standings-pane").classList.toggle("two-lists", dual);
  $(".timing-body").classList.toggle("two-lists", dual);
  document.querySelectorAll("#timing-cols [data-cols]").forEach((b) => b.classList.toggle("active", +b.dataset.cols === (dual ? 2 : 1)));
}
$("#timing-cols").addEventListener("click", (e) => {
  const b = e.target.closest("[data-cols]");
  if (!b) return;
  settings.timingCols = +b.dataset.cols === 2 ? 2 : 1;
  saveSettings();
  applyTimingCols();
  if (ui.snap && ui.snap.connected) renderStandings(ui.snap);
});
applyTimingCols();

// What the Timing Screen shows in this window (each window its own: the app's,
// and a popped-out one): its parts, and the driver list's columns.
const TIMING_PARTS = [["cameras", "Camera buttons"], ["list", "Driver list"], ["talk", "Talking points"], ["log", "Race log"], ["replay", "Replay controls"]];
// The driver list's cells, in order (Driver always shows).
const TIMING_COLS = [["pos", "Pos"], ["cls", "Class position"], ["chg", "+/− places"], ["num", "Car number"], ["make", "Car make"],
  ["driver", "Driver"], ["lap", "Lap"], ["gap", "Gap"], ["int", "Interval"], ["last", "Last lap"], ["best", "Best lap"],
  ["pit", "Pit stops"], ["stint", "Stint"], ["tyre", "Tyre"], ["flag", "Flag"], ["pen", "Penalty"], ["inc", "Incidents"]];
const SHOW_KEY = `apex.timingShow.${POPOUT === "timing" ? "popout" : "main"}`;
let timingHide = new Set();
try {
  timingHide = new Set(JSON.parse(localStorage.getItem(SHOW_KEY)) || []);
} catch (e) { /* storage unavailable */ }

function applyTimingShow() {
  // The driver list, the talking points or the race log: never none of them.
  if (timingHide.has("list") && timingHide.has("log") && timingHide.has("talk")) timingHide.delete("list");
  timingHide.delete("driver");
  for (const [k] of TIMING_PARTS) $("#tab-timing").classList.toggle(`hide-${k}`, timingHide.has(k));
  let style = document.getElementById("timing-col-style");
  if (!style) {
    style = document.head.appendChild(document.createElement("style"));
    style.id = "timing-col-style";
  }
  style.textContent = TIMING_COLS.map(([k], i) => timingHide.has(k) ? `#std-lists tr > :nth-child(${i + 1}) { display: none; }` : "").join("\n");
  const tick = ([k, label]) => `<label class="check"><input type="checkbox" data-show="${k}" ${timingHide.has(k) ? "" : "checked"}
    ${["list", "log", "talk"].includes(k) && ["list", "log", "talk"].filter((x) => x !== k).every((x) => timingHide.has(x)) ? "disabled" : ""}><span>${esc(label)}</span></label>`;
  $("#timing-parts").innerHTML = TIMING_PARTS.map(tick).join("");
  $("#timing-colpick").innerHTML = TIMING_COLS.filter(([k]) => k !== "driver").map(tick).join("");
  const n = timingHide.size;
  $("#timing-show > summary").innerHTML = `▦ Show${n ? ` <span class="count">${n} hidden</span>` : ""}`;
}
function saveTimingShow() {
  try {
    localStorage.setItem(SHOW_KEY, JSON.stringify([...timingHide]));
  } catch (e) { /* storage unavailable */ }
  applyTimingShow();
  updateBattleHints();
}
$("#timing-show").addEventListener("change", (e) => {
  const box = e.target.closest("[data-show]");
  if (!box) return;
  if (box.checked) timingHide.delete(box.dataset.show);
  else timingHide.add(box.dataset.show);
  saveTimingShow();
});
$("#timing-show-all").addEventListener("click", () => {
  timingHide.clear();
  saveTimingShow();
});
document.addEventListener("click", (e) => {
  const menu = $("#timing-show");
  if (menu.open && !menu.contains(e.target)) menu.open = false;
});
applyTimingShow();

// -- race log -------------------------------------------------------------------

const LOG_LABELS = {
  overtake: "PASS", offtrack: "OFF", slowdown: "SLOW", spin: "SPIN", contact: "CONTACT", incident: "INC", pit_in: "PIT", pit_out: "PIT",
  position: "LOST", penalty: "PEN", fastest_lap: "FAST",
};
const LOG_GROUPS = {
  incident: ["contact", "offtrack", "slowdown", "spin", "incident"], pit: ["pit_in", "pit_out"],
};
const PREROLL_CHOICES = [5, 10, 15, 20, 25, 30];
// Kinds of event that can be left out of the log (Hide…), kept for this PC.
const LOG_KINDS = [["overtake", "Overtakes"], ["accident", "Accidents (crashes and slowdowns)"], ["contact", "Contact"], ["offtrack", "Off track"],
  ["spin", "Spins"], ["incident", "Incident points"], ["pit", "Pit stops"], ["position", "Places lost"],
  ["warning", "Slow downs (penalty)"], ["penalty", "Other penalties"], ["fastest_lap", "Fastest laps"]];
// iRacing's furled flag ("Warning" in older logs) is shown as SLOW DOWN.
const isSlowDown = (ev) => ev.type === "penalty" && /warn|slow down/i.test(ev.penalty || "");
// A crash (or any slowdown): ACCIDENT, its row red.
const isAccident = (ev) => !!ev.accident || ev.type === "slowdown";
function logKind(ev) {
  if (isAccident(ev)) return "accident";
  if (ev.spin) return "spin";
  if (ev.type === "pit_in" || ev.type === "pit_out") return "pit";
  if (ev.type === "penalty") return isSlowDown(ev) ? "warning" : "penalty";
  return ev.type;
}
function renderLogHide() {
  const hidden = new Set(settings.logHidden || []);
  $("#log-hide-menu").innerHTML = LOG_KINDS.map(([k, label]) => `<label class="check"><input type="checkbox" data-log-kind="${k}" ${hidden.has(k) ? "" : "checked"}> ${label}</label>`).join("");
  $("#log-hide-count").textContent = hidden.size ? `${hidden.size} hidden` : "";
}
renderLogHide();
$("#log-hide-menu").addEventListener("change", (e) => {
  const box = e.target.closest("[data-log-kind]");
  if (!box) return;
  const hidden = new Set(settings.logHidden || []);
  if (box.checked) hidden.delete(box.dataset.logKind);
  else hidden.add(box.dataset.logKind);
  settings.logHidden = [...hidden];
  saveSettings();
  renderLogHide();
  if (ui.snap && ui.snap.connected) renderLog(ui.snap);
});
document.addEventListener("click", (e) => {
  const open = $("#log-hide");
  if (open.open && !e.target.closest("#log-hide")) open.open = false;
});

function car(num, name) {
  return `<span class="num">${esc(num)}</span> ${esc(name)}`;
}

function eventText(ev) {
  const who = car(ev.car_number, ev.driver);
  const pts = ev.incidents ? ` <b>${ev.incidents}x</b>` : "";
  switch (ev.type) {
    case "overtake":
      return `${who} passes ${car(ev.other_car_number, ev.other_driver)}${ev.position ? ` for <b>P${ev.position}</b>` : ""}${ev.at_line ? ' <span class="muted">(at the line, during a replay)</span>' : ""}`;
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
      const served = { drive_through: " · drive-through", stop_go: " · stop-and-go" }[ev.stop] || "";
      return `${who} rejoins <b>P${ev.position ?? "?"}</b>${lost > 0 ? ` (lost ${lost})` : ""} · ${ev.duration}s in the pits${served}`;
    }
    case "position":
      return `${who} loses <b>${ev.position - ev.from_position}</b> place${ev.position - ev.from_position === 1 ? "" : "s"} after going off (P${ev.from_position} → P${ev.position})`;
    case "penalty":
      return `${who}: <b>${isSlowDown(ev) ? "Slow down" : esc(ev.penalty)}</b>`;
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
    replay_live: "● Replay on screen, the race goes on: the order, gaps and intervals stay the live race's, timed at the line as each car crosses it, and incident points and places gained at the line are still logged live (iRacing sends only the replay's car data, so passes on track, offs and contact pick up again back live).",
    waiting: "Waiting for the session to start…",
  }[s.detection] || "";
}

let logKey = "";

// The whole race log: the snapshot brings the newest (and their updates); the
// rest are fetched once (/api/events) and kept here. A new event (iRacing
// session) starts it afresh.
const logStore = new Map();
let logFirst;
let logFetching = false;
const LOG_PAGE = 300;
let logShown = LOG_PAGE;  // the newest this many on the page; "Show older" brings in more

function logEvents(s) {
  if (s.events_first_id !== logFirst) {
    logStore.clear();
    logFirst = s.events_first_id;
    logShown = LOG_PAGE;
  }
  for (const e of s.events || []) logStore.set(e.id, e);
  if ((s.events_total || 0) > logStore.size && !logFetching) {
    logFetching = true;
    api("/api/events").then((r) => {
      for (const e of r.events || []) if (!logStore.has(e.id)) logStore.set(e.id, e);
      logKey = "";
      if (ui.snap) renderLog(ui.snap);
    }).catch(() => {}).finally(() => { logFetching = false; });
  }
  return [...logStore.values()];
}

function renderLog(s) {
  const all = logEvents(s);
  $("#log-status").textContent = logStatus(s);
  $("#log-status").className = `log-status ${s.detection === "replay_live" ? "replay" : s.detection || ""}`;
  const types = LOG_GROUPS[ui.logFilter] || (ui.logFilter === "all" ? null : [ui.logFilter]);
  const hidden = new Set(settings.logHidden || []);
  const shown = all.filter((e) => (!types || types.includes(e.type)) && !hidden.has(logKind(e)))
    .sort((a, b) => b.session_num - a.session_num || b.session_time - a.session_time || b.id - a.id);
  $("#log-empty").hidden = shown.length > 0;
  const page = shown.slice(0, logShown);
  const key = JSON.stringify([page, shown.length, ui.selectedEvent, settings.logPreroll, settings.logHidden]);
  if (key === logKey) return;
  logKey = key;
  const older = shown.length - page.length;
  $("#race-log").innerHTML = page.map((ev) => {
    const selected = ev.id === ui.selectedEvent;
    const accident = isAccident(ev);
    const cls = accident ? "kind accident" : ev.incidents ? "kind has-points" : `kind ${ev.spin ? "spin" : ev.type}`;
    const label = accident ? "ACCIDENT" : isSlowDown(ev) ? "SLOW DOWN" : ev.spin ? "SPIN" : LOG_LABELS[ev.type] || ev.type;
    return `<li class="${selected ? "selected" : ""} ${accident ? "accident" : ""}" data-event="${ev.id}">
      <div class="log-line">
        <span class="when">L${ev.lap} · ${fmtClock(ev.session_time)}</span>
        <span class="${cls}">${label}</span>
        <span class="what">${eventText(ev)}</span>
      </div>
      ${selected ? `<div class="log-actions">
        <span class="label">Replay from</span>
        ${PREROLL_CHOICES.map((p) => `<button class="chip ${p === settings.logPreroll ? "active" : ""}" data-preroll="${p}"
            title="Replay from ${p} seconds before">−${p}s</button>`).join("")}
        <button class="btn icon" data-watch="${ev.car_idx}" title="Watch ${esc(ev.driver)} live">👁</button>
      </div>` : ""}
    </li>`;
  }).join("") + (older ? `<li class="log-more"><button class="btn subtle" data-log-more>Show older (${older} more)</button></li>` : "");
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-log-more]")) return;
  logShown += LOG_PAGE;
  logKey = "";
  if (ui.snap) renderLog(ui.snap);
});

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
  renderThumbs(g);
  for (const [id, value, prop] of [["#gw-interval", g.interval, "value"],
    ["#gw-loop", g.loop, "checked"], ["#gw-absent", g.include_absent, "checked"], ["#gw-autoplay", g.autoplay !== false, "checked"]]) {
    const el = $(id);
    if (document.activeElement !== el) el[prop] = value;
  }
  const sources = {
    qualifying: "Grid order from qualifying, as the starting grid board (reversed as set there).", "qualifying session": "Grid order from the qualifying session.",
    "current positions": "Grid order from the cars' current positions (as iRacing has them lined up).",
    "car number": "No qualifying results yet: ordered by car number.", manual: "Grid order set by hand.",
    "previous race": "Grid order from the race before's finish, as the starting grid board (reversed as set there).",
    "iRacing's grid": "Grid order: the grid iRacing has lined the race up on (reverse grids included).",
  };
  $("#gw-source").textContent = entries.length ? sources[g.source] || "" : "";
  $("#gw-reset-order").hidden = !g.manual_order;
  $("#gw-empty").hidden = entries.length > 0;
  // Rebuild rows only when they change, so buttons aren't replaced mid-click.
  const gwCfg = (s.overlays && s.overlays.settings && s.overlays.settings.gridwalk) || {};
  for (const [id, value, prop] of [["#gw-names", gwCfg.name_format || "full", "value"], ["#gw-nick", gwCfg.show_nickname !== false, "checked"]]) {
    const el = $(id);
    if (document.activeElement !== el) el[prop] = value;
  }
  const key = JSON.stringify([g.index, g.visible, gwCfg.name_format, gwCfg.show_nickname, entries.map((e) => [e.key, e.number, e.name, e.nickname, e.team,
    e.in_session, e.in_world, e.has_thumb, e.car_name, (classes.get(e.class_key) || {}).color])]);
  if (key === gwRowsKey) return;
  gwRowsKey = key;
  $("#gw-rows").innerHTML = entries.map((e, i) => {
    const onScreen = g.visible && (i === g.index || i === g.index + 1);
    const color = (classes.get(e.class_key) || {}).color || "var(--muted)";
    const status = !e.in_session ? '<span class="tag out">NOT IN SESSION</span>'
      : !e.in_world ? '<span class="tag out">NOT ON TRACK</span>' : "";
    // No picture in the folder: what it should be called.
    const want = e.cust_id ? `${e.class_tag ? `${e.class_tag}.` : ""}${e.cust_id}.${e.car_name || "Car name"}.png` : "";
    const pic = e.has_thumb ? '<span class="tag ok" title="Car picture found">✓ Picture</span>'
      : `<span class="tag" title="${want ? `No picture: name it ${esc(want)}` : "No iRacing ID to match a picture"}">No picture</span>`;
    return `<tr class="${onScreen ? "on-screen" : ""}">
      <td class="pos">P${e.grid_pos}</td>
      <td><span class="num" style="border-left-color:${esc(color)}">${esc(e.number)}</span></td>
      <td><span class="name">${esc(formatName(e, gwCfg.name_format))}</span>${gwCfg.show_nickname !== false && e.nickname && gwCfg.name_format !== "nickname" ? `<span class="nick">“${esc(e.nickname)}”</span>` : ""}</td>
      <td class="sub">${esc(e.team)}</td>
      <td>${pic} ${status}</td>
      <td><div class="actions">
        <button class="btn" data-gw-goto="${i}" title="Show this driver's pair now">Show</button>
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
  if (btn.dataset.gwMove) return cmd("gridwalk_move", { key: btn.dataset.gwMove, direction: +btn.dataset.dir });
  if (btn.id === "gw-reset-order") return cmd("gridwalk_reset_order", {}, "Grid order reset");
  if (btn.id === "gw-copy") {
    navigator.clipboard.writeText($("#gw-url").textContent).then(() => toast("Copied"), () => toast("Copy failed", true));
  }
});

// The seconds per pair: used as soon as it's typed (a whole number, 2 to 120), and kept.
let gwIntervalTimer = null;
const sendInterval = (el) => {
  const v = Math.round(+el.value);
  if (v >= 2 && v <= 120) cmd("gridwalk_settings", { interval: v });
};
$("#gw-interval").addEventListener("input", (e) => {
  clearTimeout(gwIntervalTimer);
  gwIntervalTimer = setTimeout(() => sendInterval(e.target), 600);
});
$("#gw-interval").addEventListener("change", (e) => {
  clearTimeout(gwIntervalTimer);
  sendInterval(e.target);
});
$("#gw-loop").addEventListener("change", (e) => cmd("gridwalk_settings", { loop: e.target.checked }));
$("#gw-autoplay").addEventListener("change", (e) => cmd("gridwalk_settings", { autoplay: e.target.checked }));
$("#gw-names").addEventListener("change", (e) => cmd("overlay_settings", { overlay: "gridwalk", values: { name_format: e.target.value } }));
$("#gw-nick").addEventListener("change", (e) => cmd("overlay_settings", { overlay: "gridwalk", values: { show_nickname: e.target.checked } }));
$("#gw-absent").addEventListener("change", (e) => cmd("gridwalk_settings", { include_absent: e.target.checked }));
$("#gw-url").textContent = `${location.origin}/gridwalk.html`;

// The grid walk's car pictures: a folder of iRacingID.Carname pictures.
let gwFolderShown = null;
function renderThumbs(g) {
  const th = g.thumbs || {};
  const input = $("#gw-folder");
  if (th.folder !== gwFolderShown && document.activeElement !== input) {
    gwFolderShown = th.folder;
    input.value = th.folder || "";
  }
  $("#gw-folder-clear").hidden = !th.folder;
  $("#gw-thumbs").textContent = th.error ? th.error
    : !th.folder ? "No folder picked yet: cars show as drawings in their livery colours."
      : `${th.count} picture${th.count === 1 ? "" : "s"} in the folder · ${th.matched} of ${th.drivers} drivers on the grid have one.`;
}

async function setThumbsFolder(folder) {
  const r = await cmd("gridwalk_folder", { folder });
  if (r) {
    gwFolderShown = null;
    toast(r.folder ? `Car pictures: ${r.count} found` : "Car pictures folder cleared");
  }
}
$("#gw-folder-save").addEventListener("click", () => setThumbsFolder($("#gw-folder").value.trim()));
$("#gw-folder").addEventListener("keydown", (e) => {
  if (e.key === "Enter") setThumbsFolder(e.target.value.trim());
});
$("#gw-folder-clear").addEventListener("click", () => setThumbsFolder(""));

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
  const logLine = e.target.closest("#race-log li:not(.log-more)");
  if (logLine) {
    const id = +logLine.dataset.event;
    ui.selectedEvent = ui.selectedEvent === id ? null : id;
    if (ui.snap && ui.snap.connected) renderLog(ui.snap);
    return;
  }

  // Standings: click a driver to put the camera on them.
  const row = e.target.closest("#standings-rows tr[data-car], #standings-rows-2 tr[data-car]");
  if (row) return cmd("watch", { car_idx: +row.dataset.car });

  const btn = e.target.closest("button[data-cmd]");
  if (btn) {
    const { cmd: action, ...rest } = btn.dataset;
    const params = {};
    for (const [k, v] of Object.entries(rest)) params[k] = isNaN(v) ? v : +v;
    if (action === "clear_events" && !confirm("Clear the race log?")) return;
    if (action === "replay_incident") {
      // The incident replayed: picked in the race log, as if clicked there.
      return cmd(action, params).then((r) => {
        if (r && r.incident != null) {
          ui.selectedEvent = r.incident;
          if (ui.snap) renderLog(ui.snap);
          const li = document.querySelector(`#race-log li[data-event="${r.incident}"]`);
          if (li) li.scrollIntoView({ block: "nearest" });
        }
      });
    }
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
$("#timing-names").value = settings.nameFormat;
$("#timing-nick").checked = settings.showNick;
$("#timing-left").checked = settings.keepLeft;
$("#data-delay").addEventListener("change", (e) => {
  const v = Math.min(10, Math.max(0, parseFloat(e.target.value) || 0));
  e.target.value = v;
  e.target.blur();
  cmd("data_delay", { seconds: v });
});
$("#timing-left").addEventListener("change", (e) => {
  settings.keepLeft = e.target.checked;
  saveSettings();
  if (ui.snap) renderStandings(ui.snap);
});
$("#timing-names").addEventListener("change", (e) => {
  settings.nameFormat = e.target.value;
  saveSettings();
  if (ui.snap) {
    renderStandings(ui.snap);
    renderGridwalk(ui.snap);
  }
});
// Decimal places of gaps and intervals: the shared setting (General), for every widget too.
$("#timing-decimals").addEventListener("change", (e) => {
  e.target.blur();
  cmd("overlay_settings", { overlay: "general", values: { race_decimals: +e.target.value } });
});

$("#timing-nick").addEventListener("change", (e) => {
  settings.showNick = e.target.checked;
  saveSettings();
  if (ui.snap) {
    renderStandings(ui.snap);
    renderGridwalk(ui.snap);
  }
});
$("#battle-color").addEventListener("input", (e) => {
  settings.battleColor = e.target.value;
  document.documentElement.style.setProperty("--battle", settings.battleColor);
  saveSettings();
});

// -- hotkeys: cameras, overlays, the grid walk and boards -----------------------------
// Cameras keep their own map (settings.hotkeys, by camera name; 1-9 until set
// by hand); everything else is settings.actionKeys, by action id. A key does
// one thing, and works in any app window (pop-outs too) when it's in front.

let hotkeyTarget = null;   // {kind: "cam" | "act", id, label} waiting for a key

const TOWER_COLUMN_HOTKEYS = [["pos_change", "Places gained / lost"], ["number", "Car number"], ["logo", "Team logo"],
  ["team", "Team name"], ["gap", "Gap"], ["interval", "Interval"], ["last_lap", "Last lap"], ["best_lap", "Best lap"],
  ["laps", "Laps"], ["pits", "Pit stops"], ["stint", "Current stint"], ["tyre", "Tyres"], ["make", "Car manufacturer"],
  ["pit_status", "PIT badge"], ["stripe", "Coloured bar"], ["fastest_icon", "Fastest lap stopwatch"]];
const OVERLAY_TOGGLES = [["standings", "Standings tower"], ["laps", "Lap tracker"], ["driver", "Driver on camera"], ["sponsors", "Sponsors"],
  ["battle", "Championship battle"], ["pits", "Pit stops"], ["duel", "On-track battle"], ["strategy", "Pit strategy"],
  ["catching", "Catching"], ["season", "Driver's season"], ["h2h", "Head to head"], ["trackmap", "Track map"],
  ["lights", "Starting lights on / off (comes up at the start; Hide all leaves it ready)"], ["flags", "Flags on / off (shows while a sector's yellow; Hide all leaves it ready)"]];
const NOT_KEYS = new Set(["shift", "control", "alt", "meta", "tab", "capslock", "enter"]);

// What a key can do besides cameras: [[section, [[id, label, run]]]], from
// the snapshot (the boards there are, what's on).
function hotkeyActions(s = ui.snap || {}) {
  const ov = (s.overlays && s.overlays.settings) || {};
  const opts = s.board_options || { groups: [] };
  const groups = opts.groups || [];
  const boards = [["board:off", "Take the board off screen", () => cmd("board_hide", {}, "Board off screen")],
    ["board:next", "Next page of the board", () => cmd("board_page", { step: "next" })],
    ["board:prev", "Previous page of the board", () => cmd("board_page", { step: "prev" })],
    ["board:row_next", "Starting grid: the next row", () => cmd("board_reveal", { step: "next" })],
    ["board:row_prev", "Starting grid: back a row", () => cmd("board_reveal", { step: "prev" })],
    ["board:row_all", "Starting grid: every row", () => cmd("board_reveal", { step: "all" })]];
  const add = (kind, group, label) => boards.push([`board:${kind}:${group}`, label, () => toggleBoard(kind, group)]);
  groups.forEach((g) => add("championship", g.key, `Standings · ${g.name}`));
  if (opts.teams) add("teams", "", "Teams' championship");
  groups.forEach((g) => add("makes", g.key, `Manufacturers · ${g.name}`));
  add("calendar", "", "Season calendar");
  add("track", "", "Track details (round, track, weather)");
  resultGroups(opts).forEach((g) => add("recap", g.key, `Race recap · ${g.name}`));
  resultGroups(opts).forEach((g) => add("results", g.key, `Finishing order · ${g.name}`));
  resultGroups(opts).forEach((g) => add("qualifying", g.key, `Qualifying results · ${g.name}`));
  resultGroups(opts).forEach((g) => add("grid", g.key, `Starting grid · ${g.name}`));
  const on = (k) => !!(ov[k] && ov[k].visible);
  return [
    ["Everything", [
      ["all:overlays", "Every overlay (and the grid walk) off screen, and back again", () => cmd("hotkey", { action: "all:overlays" },
        (r) => (r && r.shown ? "Overlays back on screen" : "Overlays off screen"))],
      ["all:boards", "The board off screen, and back again (any board: qualifying results, starting grid…)", () => cmd("hotkey", { action: "all:boards" },
        (r) => (r && r.shown ? "Board back on screen" : "Board off screen"))],
      ["all:toggle", "Every overlay and board off screen, and back again", () => cmd("hotkey", { action: "all:toggle" },
      (r) => (r && r.shown ? "Overlays back on screen" : "Everything off screen"))]]],
    ["Commentator tools", [
      ["talk:top", "Talking points: put the top one on screen (its board, catching, the driver's season…)", () => cmd("talk_do", {}, "On screen")],
      ["catching:ahead", "Catching: the driver on camera and the car ahead", () => cmd("catching_pick", { mode: "ahead" }, "Catching: the car ahead")],
      ["catching:behind", "Catching: the driver on camera and the car behind", () => cmd("catching_pick", { mode: "behind" }, "Catching: the car behind")],
      ["catching:nearest", "Catching: the driver on camera and the nearer car", () => cmd("catching_pick", { mode: "nearest" }, "Catching: the nearer car")],
      ["season:camera", "Driver's season: the driver on camera", () => cmd("season_show", {}, "Driver's season on screen")],
      ["h2h:camera", "Head to head: the driver on camera and the car ahead", () => cmd("h2h_pick", { mode: "camera" }, "Head to head on screen")],
      ["season:champ", "Driver's season: by class or overall (switch)", () => cmd("hotkey", { action: "season:champ" },
        `Driver's season: ${ov.season && ov.season.champ === "class" ? "overall" : "by class"}`)],
      ["h2h:champ", "Head to head: by class or overall (switch)", () => cmd("hotkey", { action: "h2h:champ" },
        `Head to head: ${ov.h2h && ov.h2h.champ === "class" ? "overall" : "by class"}`)],
    ]],
    ["Overlays (on / off)", OVERLAY_TOGGLES.map(([k, label]) => [`ov:${k}`, label,
      () => cmd("overlay_settings", { overlay: k, values: { visible: !on(k) } }, `${label} ${on(k) ? "off" : "on"}`)])],
    ["Timing tower", [
      ["tower:sponsor", "Sponsor bar under the header (on / off)", () => cmd("hotkey", { action: "tower:sponsor" },
        `Sponsor bar ${ov.standings && ov.standings.sponsor_bar ? "off" : "on"}`)],
      ["tower:mode", "Overall / by class", () => cmd("hotkey", { action: "tower:mode" },
        ov.standings && ov.standings.mode === "class" ? "Tower: overall" : "Tower: by class")],
      ["tower:header", "Header: laps left / time left", () => cmd("hotkey", { action: "tower:header" }, "Tower header changed")],
    ]],
    // Each column of the tower (and the full screen) on and off.
    ["Timing tower columns (on / off)", TOWER_COLUMN_HOTKEYS.map(([k, label]) => [`tower:col:${k}`, label,
      () => cmd("hotkey", { action: `tower:col:${k}` }, `${label} ${ov.standings && ov.standings[`show_${k}`] ? "off" : "on"}`)])],
    ["Grid walk", [
      ["gw:toggle", "On / off (starts from P1)", () => (s.gridwalk && s.gridwalk.visible
        ? cmd("gridwalk_hide", {}, "Grid walk off") : cmd("gridwalk_start", { index: 0 }, "Grid walk on"))],
      ["gw:next", "Next pair", () => cmd("gridwalk_next", {})],
      ["gw:prev", "Previous pair", () => cmd("gridwalk_prev", {})],
    ]],
    ["On my screen (the app window only)", [
      ["desk:overlays", "Every overlay on my screen", () => deskShowAll("overlays")],
      ["desk:boards", "Boards on my screen", () => deskShowAll("boards")],
      ["desk:gridwalk", "Grid walk on my screen", () => deskShowAll("gridwalk")],
      ["desk:off", "Remove everything from my screen", () => cmd("desktop_hide", {}, "Removed from your screen")],
    ]],
    ["Starting grid", [
      ["grid:toggle", "Starting grid (Overall, the race on now / next) on / off", () => cmd("hotkey", { action: "grid:toggle" })],
      ["grid:mode", "Full grid / row by row (switch)", () => cmd("hotkey", { action: "grid:mode" },
        (r) => (r && r.grid_reveal === "rows" ? "Starting grid: row by row" : "Starting grid: full grid"))],
      ["grid:full", "Full grid (every driver at once)", () => cmd("hotkey", { action: "grid:full" }, "Starting grid: full grid")],
      ["grid:rows", "Row by row (from the front row)", () => cmd("hotkey", { action: "grid:rows" }, "Starting grid: row by row")],
      ["grid:next", "Next row", () => cmd("hotkey", { action: "grid:next" })],
      ["grid:prev", "Back a row", () => cmd("hotkey", { action: "grid:prev" })],
      ["grid:all", "Every row now", () => cmd("hotkey", { action: "grid:all" })],
      ["desk:boards_toggle", "Boards on my screen / off it (the app window)", () => cmd("hotkey", { action: "desk:boards_toggle" })],
    ]],
    ["Dual commentary (following a host's camera)", [
      ["follow:free", "Free mode: your own camera (replay something, watch someone else)", () => cmd("hotkey", { action: "follow:free" }, "Free mode")],
      ["follow:sync", "Sync: back to what the host is showing, and following", () => cmd("hotkey", { action: "follow:sync" }, "Synced with the host")],
      ["follow:toggle", "Free mode / Sync (switch)", () => cmd("hotkey", { action: "follow:toggle" })],
    ]],
    ["Starting lights", [
      ["lights:count", "Count down now (a light a step, held lit until the green)", () => cmd("hotkey", { action: "lights:count" }, "Starting lights: counting down")],
      ["lights:reset", "Put the lights away", () => cmd("hotkey", { action: "lights:reset" }, "Starting lights away")],
    ]],
    ["Flags (yellow by sector, safety car)", [
      ...Array.from({ length: (ov.flags && ov.flags.flag_sectors) || 3 }, (_, i) => [`flags:s${i + 1}`, `Sector ${i + 1} yellow / clear`,
        () => cmd("hotkey", { action: `flags:s${i + 1}` }, (r) => flagToast(r))]),
      ["flags:all", "Every sector yellow (All Sectors)", () => cmd("hotkey", { action: "flags:all" }, "Yellow flag: All Sectors")],
      ["flags:sc", "Safety car out / in", () => cmd("hotkey", { action: "flags:sc" }, (r) => (r && r.sc ? "Safety car out" : "Safety car in"))],
      ["flags:clear", "Clear every yellow (Track Clear)", () => cmd("hotkey", { action: "flags:clear" }, "Track clear")],
    ]],
    ["Boards (press again: off screen)", boards],
    ["Championship battle", [
      ["battle:toggle", "The drivers picked in its settings, on / off", () => cmd("hotkey", { action: "battle:toggle" },
        ov.battle && ov.battle.visible ? "Championship battle off" : "Championship battle on")],
      ...BATTLE_PICKS.map(([mode, label]) => [`battle:${mode}`, `${label} (picks them and shows it)`,
        () => cmd("battle_pick", { mode }, "Championship battle on")])]],
    ["Pit strategy", [
      ["strategy:toggle", "The cars picked, on / off", () => cmd("hotkey", { action: "strategy:toggle" },
        ov.strategy && ov.strategy.visible ? "Pit strategy off" : "Pit strategy on")],
      ...STRATEGY_PICKS.map(([mode, , label]) => [`strategy:${mode}`, `${label} (picks them and shows it)`,
        () => cmd("strategy_pick", { mode }, "Pit strategy on")])]],
  ];
}

// The flag overlay's sectors after a hotkey: "Yellow flag: Sectors 1 & 3" / "Track clear".
function flagToast(r) {
  const s = (r && r.sectors) || [];
  if (!s.length) return "Track clear";
  return `Yellow flag: ${s.length > 1 ? `Sectors ${s.slice(0, -1).join(", ")} & ${s[s.length - 1]}` : `Sector ${s[0]}`}`;
}

// ---------------------------------------------------------------------------
// race control: penalties and race commands, sent as iRacing admin chat commands
// ---------------------------------------------------------------------------

const rcHold = {};  // car_idx -> {amount, unit}: each driver's stop & hold box, kept through redraws
let rcKey = "";
let rcLogKey = "";

function renderRaceControl(s) {
  const classes = new Map((s.classes || []).map((c) => [c.key, c]));
  const filter = $("#rc-filter").value.trim().toLowerCase();
  const drivers = (s.connected ? s.drivers || [] : [])
    .filter((d) => !filter || `${d.number} ${d.name}`.toLowerCase().includes(filter))
    .sort((a, b) => (a.pos || 999) - (b.pos || 999) || String(a.number).localeCompare(String(b.number), undefined, { numeric: true }));
  $("#rc-status").textContent = s.connected ? `${(s.drivers || []).length} drivers` : "Not connected to iRacing";
  ["#rc-clear-all", "#rc-grid", "#rc-start", "#rc-send"].forEach((id) => { $(id).disabled = !s.connected; });
  const key = JSON.stringify([drivers.map((d) => [d.car_idx, d.pos, d.number, d.name, d.class_key, d.in_world]), [...classes.keys()]]);
  const table = $("#rc-rows");
  // Not while something in the list is being typed in or picked.
  if (key !== rcKey && !(table.contains(document.activeElement) && /INPUT|SELECT/.test(document.activeElement.tagName))) {
    rcKey = key;
    table.innerHTML = drivers.map((d) => {
      const cls = classes.get(d.class_key);
      const hold = rcHold[d.car_idx] || { amount: "", unit: "seconds" };
      return `<tr data-car="${d.car_idx}" class="${d.in_world ? "" : "rc-out"} ${hold.amount ? "rc-typed" : ""}">
        <td class="r">${d.pos || "–"}</td>
        <td><span class="num" style="${cls ? `background:${esc(cls.color)};color:${inkFor(cls.color)}` : ""}">${esc(d.number)}</span></td>
        <td class="rc-name">${esc(d.name)}${d.in_world ? "" : ' <span class="hint">(not in the car)</span>'}</td>
        <td class="rc-pen">
          <button class="btn subtle" data-rc="clear" title="Clear their penalties (!clear)">Clear</button>
          <button class="btn" data-rc="drive_through" title="Drive-through (!black D)">Drive-through</button>
          <button class="btn" data-rc="stop_go" title="Stop & go (!black)">Stop &amp; go</button>
        </td>
        <td class="rc-hold">
          <input type="number" min="1" step="1" data-rc-amount value="${esc(hold.amount)}" placeholder="0" aria-label="How long">
          <select data-rc-unit aria-label="Seconds, minutes or laps">${[["seconds", "Seconds"], ["minutes", "Minutes"], ["laps", "Laps"]].map(([v, l]) =>
            `<option value="${v}" ${hold.unit === v ? "selected" : ""}>${l}</option>`).join("")}</select>
          <button class="btn" data-rc="stop_hold" title="Stop and hold for this long (!black with a time or laps)">Stop &amp; hold</button>
        </td></tr>`;
    }).join("");
  }
  $("#rc-empty").hidden = drivers.length > 0;
  const log = (s.race_control && s.race_control.log) || [];
  const logKey = JSON.stringify(log);
  if (logKey !== rcLogKey) {
    rcLogKey = logKey;
    $("#rc-log").innerHTML = log.length ? [...log].reverse().map((l) => `<li><span class="hint">${esc(l.at)}</span> ${esc(l.label)}
      <code>${esc(l.line)}</code></li>`).join("") : '<li class="hint">Nothing sent yet.</li>';
  }
}

$("#rc-filter").addEventListener("input", () => { rcKey = ""; renderRaceControl(ui.snap); });
$("#rc-rows").addEventListener("input", (e) => {
  const row = e.target.closest("tr[data-car]");
  if (!row) return;
  rcHold[row.dataset.car] = { amount: row.querySelector("[data-rc-amount]").value, unit: row.querySelector("[data-rc-unit]").value };
});
$("#rc-rows").addEventListener("change", (e) => {
  const row = e.target.closest("tr[data-car]");
  if (row) rcHold[row.dataset.car] = { amount: row.querySelector("[data-rc-amount]").value, unit: row.querySelector("[data-rc-unit]").value };
});
$("#rc-rows").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-rc]");
  if (!btn) return;
  const row = btn.closest("tr[data-car]");
  const params = { car_idx: +row.dataset.car, kind: btn.dataset.rc };
  if (params.kind === "stop_hold") {
    params.amount = row.querySelector("[data-rc-amount]").value;
    params.unit = row.querySelector("[data-rc-unit]").value;
  }
  btn.blur();
  const r = await cmd("rc_penalty", params);
  if (r) toast(`Sent: ${r.sent}`);
});
$("#rc-clear-all").addEventListener("click", async () => {
  if (!confirm("Clear every driver's penalties?")) return;
  const r = await cmd("rc_clear_all");
  if (r) toast("All penalties cleared");
});
$("#rc-grid").addEventListener("click", async () => {
  const r = await cmd("rc_grid", { minutes: $("#rc-grid-min").value });
  if (r) toast(`Grid time set: ${$("#rc-grid-min").value} min`);
});
$("#rc-start").addEventListener("click", async () => {
  if (!confirm("Start the race now?")) return;
  const r = await cmd("rc_start");
  if (r) toast("Race start sent");
});
async function rcSend() {
  const box = $("#rc-message");
  const r = await cmd("rc_message", { text: box.value });
  if (r) {
    toast("Message sent to all");
    box.value = "";
  }
}
$("#rc-send").addEventListener("click", rcSend);
$("#rc-message").addEventListener("keydown", (e) => {
  if (e.key === "Enter") rcSend();
});

// The championship battle's quick picks (cmd_battle_pick).
const BATTLE_PICKS = [["ahead", "The car on camera and the one ahead"], ["around", "The car on camera and the cars either side"],
  ["top", "The championship's top 3"]];

// The championship battle: which championship, which drivers.
let battlePickKey = "";
function renderBattlePick(s) {
  const el = $("#battle-pick");
  const cfg = s.overlays && s.overlays.settings && s.overlays.settings.battle;
  if (!el || !cfg) return;
  const champ = s.championship;
  const groups = (champ && champ.groups) || [];
  const group = groups.find((g) => g.key === cfg.group);
  const picked = cfg.drivers ? cfg.drivers.split(",") : [];
  const drivers = (group && group.drivers) || [];
  const key = JSON.stringify([cfg.group, cfg.drivers, cfg.visible, groups.map((g) => [g.key, g.name]),
    drivers.map((d) => [d.driver, d.name, d.pos]), !!s.league]);
  // Not while a list in it is open.
  if (key === battlePickKey || (el.contains(document.activeElement) && document.activeElement.tagName === "SELECT")) return;
  battlePickKey = key;
  if (!s.league) {
    el.innerHTML = '<p class="hint">Activate a league (League builder) to use it.</p>';
    return;
  }
  if (!groups.length) {
    el.innerHTML = '<p class="hint">It shows once the championship has standings: after the first round\'s results, or live during a race.</p>';
    return;
  }
  const nameOf = (k) => (drivers.find((d) => d.driver === k) || {}).name || k.replace(/^(cust|name):/, "");
  const chips = picked.map((k) => {
    const d = drivers.find((x) => x.driver === k);
    return `<span class="bp-chip ${d ? "" : "missing"}" title="${d ? "" : "Not in this championship"}">${d && d.pos ? `P${d.pos} ` : ""}${esc(nameOf(k))}
      <button type="button" data-battle-remove="${esc(k)}" aria-label="Remove">×</button></span>`;
  }).join("");
  const free = drivers.filter((d) => !picked.includes(d.driver));
  el.innerHTML = `
    <label class="ov-field">Championship <select data-battle-group>${groups.map((g) =>
      `<option value="${esc(g.key)}" ${g.key === cfg.group ? "selected" : ""}>${esc(g.name)}</option>`).join("")}
      ${group ? "" : `<option value="${esc(cfg.group)}" selected>Pick one</option>`}</select></label>
    <div class="bp-drivers"><span>Drivers <span class="hint">(up to 6)</span></span>
      <div class="bp-chips">${chips || '<span class="hint">None picked yet</span>'}
        ${picked.length < 6 && free.length ? `<select data-battle-add aria-label="Add a driver"><option value="">+ Add a driver…</option>${[...free].sort(byName()).map((d) =>
          `<option value="${esc(d.driver)}">P${d.pos} · ${esc(d.name)} (${esc(String(d.points))} pts)</option>`).join("")}</select>` : ""}
      </div></div>
    <div class="row bp-quick">${BATTLE_PICKS.map(([mode, label]) => `<button type="button" class="btn subtle" data-battle-pick="${mode}"
      title="Pick these and show it">${esc(label)}</button>`).join("")}
      ${picked.length ? '<button type="button" class="btn subtle" data-battle-clear>Clear</button>' : ""}</div>
    ${champ.live ? `<p class="hint">Live: as if ${esc(champ.round || "this race")} ended now.</p>` : ""}`;
}

function setBattle(values, done) {
  battlePickKey = "";
  return cmd("overlay_settings", { overlay: "battle", values }, done);
}

// The drivers picked, as the card shows them.
function battlePicked() {
  const cfg = ui.snap.overlays.settings.battle;
  return cfg.drivers ? cfg.drivers.split(",") : [];
}

$("#battle-pick").addEventListener("change", (e) => {
  const picked = battlePicked();
  if (e.target.matches("[data-battle-group]")) setBattle({ group: e.target.value });
  if (e.target.matches("[data-battle-add]") && e.target.value) setBattle({ drivers: [...picked, e.target.value].join(",") });
  e.target.blur();
});
$("#battle-pick").addEventListener("click", (e) => {
  const picked = battlePicked();
  const remove = e.target.closest("[data-battle-remove]");
  if (remove) setBattle({ drivers: picked.filter((k) => k !== remove.dataset.battleRemove).join(",") });
  const pick = e.target.closest("[data-battle-pick]");
  if (pick) {
    battlePickKey = "";
    cmd("battle_pick", { mode: pick.dataset.battlePick }, "Championship battle on");
  }
  if (e.target.closest("[data-battle-clear]")) setBattle({ drivers: "", visible: false });
  if (e.target.closest("button")) e.target.closest("button").blur();
});

// -- pit strategy: the cars it follows -------------------------------------------

// [mode, button, what it picks]
const STRATEGY_PICKS = [["top", "Top 5", "The top 5"], ["around", "Around camera", "The car on camera and two either side of it (its class)"],
  ["camera", "Camera car", "The car on camera"], ["leaders", "Class leaders", "Each class's leader"]];
const STRATEGY_MAX = 8;
let strategyPickKey = "";

function renderStrategyPick(s) {
  const el = $("#strategy-pick");
  const cfg = s.overlays && s.overlays.settings && s.overlays.settings.strategy;
  if (!el || !cfg) return;
  const picked = cfg.cars ? cfg.cars.split(",") : [];
  // Everyone in the session with a number, by number (the tower's leaving out safety cars and the like).
  const cars = (s.drivers || []).filter((d) => d.number && !d.hidden);
  const key = JSON.stringify([cfg.cars, cars.map((d) => [d.number, d.name, d.pos]), !!s.connected]);
  if (key === strategyPickKey || (el.contains(document.activeElement) && document.activeElement.tagName === "SELECT")) return;
  strategyPickKey = key;
  const byNumber = new Map(cars.map((d) => [String(d.number), d]));
  const chips = picked.map((n) => {
    const d = byNumber.get(n);
    return `<span class="bp-chip ${d ? "" : "missing"}" title="${d ? "" : "Not in this session"}">#${esc(n)}${d ? ` ${esc(d.name)}` : ""}
      <button type="button" data-strat-remove="${esc(n)}" aria-label="Remove">×</button></span>`;
  }).join("");
  const free = cars.filter((d) => !picked.includes(String(d.number)))
    .sort((a, b) => String(a.number).localeCompare(String(b.number), undefined, { numeric: true }));
  el.innerHTML = `
    <div class="bp-drivers"><span>Cars <span class="hint">(up to ${STRATEGY_MAX}, by number: a team's car stays picked when its drivers swap)</span></span>
      <div class="bp-chips">${chips || '<span class="hint">None picked yet</span>'}
        ${picked.length < STRATEGY_MAX && free.length ? `<select data-strat-add aria-label="Add a car"><option value="">+ Add a car…</option>${free.map((d) =>
          `<option value="${esc(d.number)}">#${esc(d.number)} · ${esc(d.name)}${d.pos ? ` (P${d.pos})` : ""}</option>`).join("")}</select>` : ""}
      </div></div>
    <div class="row bp-quick">${STRATEGY_PICKS.map(([mode, label, about]) => `<button type="button" class="btn subtle" data-strat-pick="${mode}"
      title="${esc(about)}: pick them and show it">${esc(label)}</button>`).join("")}
      ${picked.length ? '<button type="button" class="btn subtle" data-strat-clear>Clear</button>' : ""}</div>`;
}

// The new commentator widgets' quick picks (Widgets tab): catching's car
// ahead / behind / nearer, the driver's season for the driver on camera, and
// head to head's two drivers.
let insightPickKey = "";
function renderInsightPicks(s) {
  const el = $("#h2h-pick");
  const cfg = s.overlays && s.overlays.settings && s.overlays.settings.h2h;
  if (!el || !cfg) return;
  // Everyone to pick from: the championship's drivers, then anyone else in the session.
  const seen = new Map();
  for (const g of (s.championship && s.championship.groups) || []) for (const d of g.drivers) if (!seen.has(d.driver)) seen.set(d.driver, d.name);
  for (const d of s.drivers || []) if (d.cust_id != null && !d.hidden && !seen.has(`cust:${d.cust_id}`)) seen.set(`cust:${d.cust_id}`, d.name);
  const all = [...seen].sort((a, b) => String(a[1]).localeCompare(String(b[1])));
  const picked = (cfg.drivers || "").split(",").filter(Boolean);
  const key = JSON.stringify([cfg.drivers, all]);
  if (key === insightPickKey || (el.contains(document.activeElement) && document.activeElement.tagName === "SELECT")) return;
  insightPickKey = key;
  const select = (i) => `<select data-h2h="${i}" aria-label="Driver ${i + 1}"><option value="">Pick a driver…</option>${all.map(([k, n]) =>
    `<option value="${esc(k)}" ${picked[i] === k ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>`;
  el.innerHTML = `<div class="h2h-sel">${select(0)}<span class="hint">vs</span>${select(1)}</div>
    <div class="row bp-quick"><button type="button" class="btn subtle" data-h2h-camera title="The driver on camera and the car ahead of them (behind, if they lead): pick them and show it">On camera vs the car ahead</button></div>`;
}
$("#h2h-pick").addEventListener("change", (e) => {
  const sel = e.target.closest("[data-h2h]");
  if (!sel) return;
  const both = [...$("#h2h-pick").querySelectorAll("[data-h2h]")].map((x) => x.value);
  insightPickKey = "";
  sel.blur();
  if (both[0] && both[1] && both[0] !== both[1]) cmd("h2h_pick", { drivers: both, show: false }, "Head to head picked");
  else if (both[0] && both[0] === both[1]) toast("Pick two different drivers", true);
});
$("#h2h-pick").addEventListener("click", (e) => {
  if (e.target.closest("[data-h2h-camera]")) cmd("h2h_pick", { mode: "camera" }, "Head to head on screen");
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-catch-pick]");
  if (b) return cmd("catching_pick", { mode: b.dataset.catchPick }, `Catching: ${b.textContent.trim().toLowerCase()}`);
  if (e.target.closest("[data-season-camera]")) cmd("season_show", {}, "Driver's season on screen");
});

// Talking points (the Timing Screen): what's worth saying now, worked out as
// the race runs, each with a button putting its board or widget on screen.
let talkKey = "";
function renderTalking(s) {
  const box = $("#talk-list");
  if (!box) return;
  const pts = s.talking || [];
  const key = JSON.stringify(pts.map((p) => [p.key, p.text, p.age < 20]));
  if (key === talkKey) return;
  talkKey = key;
  $("#talk-count").textContent = pts.length ? String(pts.length) : "";
  const what = (a) => (!a ? "" : a.board ? "Show the standings" : a.catching ? "Show catching" : a.season ? "Show their season" : a.ov ? "Show it" : "");
  box.innerHTML = pts.length ? pts.map((p) => `<li class="talk-item ${p.kind} ${p.age < 20 ? "new" : ""}">
      <span class="talk-text">${esc(p.text)}</span>${what(p.action) ? `<button type="button" class="btn subtle slim" data-talk="${esc(p.key)}">${what(p.action)}</button>` : ""}</li>`).join("")
    : `<li class="hint">${s.connected ? "Nothing yet: places gained, a car closing in, a championship lead changing… show up here during a race." : "Talking points show up here during a race."}</li>`;
}
$("#talk-list").addEventListener("click", (e) => {
  const b = e.target.closest("[data-talk]");
  if (b) cmd("talk_do", { key: b.dataset.talk }, "On screen");
});

function setStrategy(values, done) {
  strategyPickKey = "";
  return cmd("overlay_settings", { overlay: "strategy", values }, done);
}

const strategyPicked = () => (ui.snap.overlays.settings.strategy.cars || "").split(",").filter(Boolean);

$("#strategy-pick").addEventListener("change", (e) => {
  if (e.target.matches("[data-strat-add]") && e.target.value) setStrategy({ cars: [...strategyPicked(), e.target.value].join(",") });
  e.target.blur();
});
$("#strategy-pick").addEventListener("click", (e) => {
  const remove = e.target.closest("[data-strat-remove]");
  if (remove) setStrategy({ cars: strategyPicked().filter((n) => n !== remove.dataset.stratRemove).join(",") });
  const pick = e.target.closest("[data-strat-pick]");
  if (pick) {
    strategyPickKey = "";
    cmd("strategy_pick", { mode: pick.dataset.stratPick }, "Pit strategy on");
  }
  if (e.target.closest("[data-strat-clear]")) setStrategy({ cars: "", visible: false });
  if (e.target.closest("button")) e.target.closest("button").blur();
});

// Finishing orders on offer: overall, each championship, and every other class
// of the league (secondary ones too), points or not.
function resultGroups(opts) {
  const out = [{ key: "overall", name: "Overall", color: null }];
  for (const g of [...(opts.groups || []), ...(opts.classes || [])]) {
    if (!out.some((x) => x.key === g.key)) out.push(g);
  }
  return out;
}

// A board's key: on screen, or off if it's the one up already.
async function toggleBoard(kind, group) {
  if (ui.boardOn && ui.boardOn.kind === kind && ui.boardOn.group === group) return cmd("board_hide", {}, "Board off screen");
  const params = { kind, group };
  if (boardSource(kind)) params.round = boardSource(kind);
  const r = await cmd("board_show", params);
  if (r) ui.boardOn = { kind, group };
  boardButtonsKey = "";
  return r;
}

function renderHotkeyList() {
  const groups = (ui.snap && ui.snap.camera && ui.snap.camera.groups) || [];
  const cams = hotkeys(groups);
  const acts = settings.actionKeys || {};
  const hk = (ui.snap && ui.snap.hotkeys) || {};
  const taken = new Set(hk.taken || []);
  const btn = (kind, id, label, key) => {
    const wide = key && systemWide(key) && hk.system_wide;
    const note = !key ? "" : taken.has(key) ? "Another program has this combination: pick another"
      : wide ? "Works whichever program is in front" : "Works when an Apex Commentator window is in front";
    return `<button class="btn hk ${hotkeyTarget && hotkeyTarget.kind === kind && hotkeyTarget.id === id ? "primary" : ""} ${taken.has(key) ? "taken" : ""}"
      data-hk-kind="${kind}" data-hk="${esc(id)}" data-hk-label="${esc(label)}" title="${note}">${esc(label)}
      <kbd>${key ? `${wide ? "🌐 " : ""}${esc(keyLabel(key))}` : "–"}</kbd></button>`;
  };
  const actions = hotkeyActions();
  const sections = [["Cameras", groups.length ? groups.map((g) => btn("cam", g.name, g.name, cams[g.name])).join("")
    : '<p class="hint">Cameras appear once iRacing is connected.</p>'],
  ...actions.map(([title, items]) => [title, items.map(([id, label]) => btn("act", id, label, acts[id])).join("")])];
  // Every key that's set, at a glance (click one to change it).
  const labels = new Map(actions.flatMap(([title, items]) => items.map(([id, label]) => [id, `${title.replace(/ \(.*\)$/, "")}: ${label}`])));
  const set = [
    ...groups.filter((g) => cams[g.name]).map((g) => ["cam", g.name, `Camera: ${g.name}`, cams[g.name]]),
    ...Object.entries(acts).filter(([id, k]) => k && labels.has(id)).map(([id, k]) => ["act", id, labels.get(id), k]),
  ].sort((a, b) => keyLabel(a[3]).localeCompare(keyLabel(b[3]), undefined, { numeric: true }));
  const summary = set.length ? `<h4 class="hk-section">Keys set (${set.length})</h4><div class="hk-set">${set.map(([kind, id, label, k]) =>
    `<button class="hk-chip" data-hk-kind="${kind}" data-hk="${esc(id)}" data-hk-label="${esc(label)}"><kbd>${esc(keyLabel(k))}</kbd> ${esc(label)}</button>`).join("")}</div>`
    : '<p class="hint">No keys set yet.</p>';
  $("#hotkey-list").innerHTML = summary + sections.map(([title, html]) => `<details class="hk-group" data-hk-group="${esc(title)}" ${hkFolded.has(title) ? "" : "open"}>
    <summary class="hk-section">${esc(title)}</summary><div class="hotkey-list">${html}</div></details>`).join("");
  $("#hotkey-prompt").textContent = hotkeyTarget ? `Press a key for ${hotkeyTarget.label}…` : "";
  hkFilter();
}

// Hotkeys: find one, only those set, sections folded away (remembered).
const hkFolded = new Set();
try {
  JSON.parse(localStorage.getItem("apex.hkFolded") || "[]").forEach((t) => hkFolded.add(t));
} catch (e) { /* storage unavailable */ }
function hkFilter() {
  const words = ($("#hk-search").value || "").toLowerCase().split(/\s+/).filter(Boolean);
  const onlySet = $("#hk-only-set").checked;
  for (const g of document.querySelectorAll("#hotkey-list .hk-group")) {
    let any = 0;
    for (const b of g.querySelectorAll(".hotkey-list > *")) {
      const text = `${g.dataset.hkGroup} ${b.textContent}`.toLowerCase();
      const k = b.querySelector("kbd");
      const isSet = k && k.textContent.trim() && k.textContent.trim() !== "–";
      const show = words.every((w) => text.includes(w)) && (!onlySet || isSet);
      b.hidden = !show;
      any += show ? 1 : 0;
    }
    g.hidden = !any;
    if (words.length && any) g.open = true;
  }
}
$("#hk-search").addEventListener("input", hkFilter);
$("#hk-search").addEventListener("focus", () => {  // typing here, not setting a key
  if (!hotkeyTarget) return;
  hotkeyTarget = null;
  renderHotkeyList();
});
$("#hk-only-set").addEventListener("change", hkFilter);
document.addEventListener("toggle", (e) => {
  const g = e.target.closest && e.target.closest("details.hk-group");
  if (!g || g !== e.target || ($("#hk-search").value || "").trim()) return;
  if (g.open) hkFolded.delete(g.dataset.hkGroup); else hkFolded.add(g.dataset.hkGroup);
  try {
    localStorage.setItem("apex.hkFolded", JSON.stringify([...hkFolded]));
  } catch (err) { /* storage unavailable */ }
}, true);

// The ⌨ Hotkeys buttons on other tabs: the Hotkeys tab (in a pop-out, with a Back button).
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-open-hotkeys]")) return;
  showPage("hotkeys");
});
$("#hotkeys-back").addEventListener("click", () => showPage(POPOUT || "home"));
const hotkeysOpen = () => $("#tab-hotkeys").classList.contains("active");
$("#hotkey-list").addEventListener("click", (e) => {
  const b = e.target.closest("[data-hk]");
  if (!b) return;
  hotkeyTarget = { kind: b.dataset.hkKind, id: b.dataset.hk, label: b.dataset.hkLabel };
  renderHotkeyList();
});
$("#hotkey-reset").addEventListener("click", () => {
  settings.hotkeys = null;
  saveSettings();
  sendHotkeys();
  renderHotkeyList();
});

function captureHotkey(e) {
  const t = hotkeyTarget;
  if (e.key === "Escape") {
    hotkeyTarget = null;
    return renderHotkeyList();
  }
  if (NOT_KEYS.has(e.key.toLowerCase())) return;  // a modifier on its own: wait for the key
  const key = keyOf(e);
  const groups = (ui.snap && ui.snap.camera && ui.snap.camera.groups) || [];
  const cams = { ...hotkeys(groups) };
  const acts = { ...(settings.actionKeys || {}) };
  const mine = t.kind === "cam" ? cams : acts;
  if (key === "backspace" || key === "delete") {
    delete mine[t.id];
  } else if (RESERVED_KEYS.has(key)) {
    $("#hotkey-prompt").textContent = `${keyLabel(key)} is taken. Pick another key for ${t.label}.`;
    return;
  } else {
    // A key does one thing.
    for (const map of [cams, acts]) for (const [id, k] of Object.entries(map)) if (k === key) delete map[id];
    mine[t.id] = key;
  }
  settings.hotkeys = cams;
  settings.actionKeys = acts;
  saveSettings();
  sendHotkeys();
  hotkeyTarget = null;
  renderHotkeyList();
}

document.addEventListener("keydown", (e) => {
  if (hotkeysOpen() && hotkeyTarget && !e.target.closest("#hk-search")) {
    e.preventDefault();
    return captureHotkey(e);
  }
  if (e.target.closest("input, select, textarea") || e.metaKey) return;
  if (hotkeysOpen() || !$("#update-modal").hidden) return;
  // (System-wide ones reach the app through Windows instead; these are the rest,
  // and all of them when the app runs in a browser.)
  const key = keyOf(e);
  const act = Object.entries(settings.actionKeys || {}).find(([, k]) => k === key);
  const action = act && hotkeyActions().flatMap(([, items]) => items).find(([id]) => id === act[0]);
  if (action) {
    e.preventDefault();
    action[2]();
    return;
  }
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

// Lists of names in drop-downs go in alphabetical order (a "(P)" class tag in
// front of a name doesn't count; numbers as numbers).
const nameKey = (s) => String(s || "").replace(/^\s*\([^()]*\)\s*/, "").trim();
const byName = (get = (x) => x.name) => (a, b) => nameKey(get(a)).localeCompare(nameKey(get(b)), undefined, { numeric: true, sensitivity: "base" });

function rosterOptions(selected, fallbackName) {
  const drivers = [...(ui.editing.drivers || [])].sort(byName());
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

// Which championships the standings show, when a league has categories in its
// car classes (LMP2 · Pro...): a car class (and one of its championships), or all.
const champView = { car: "all", cat: "all" };

function champPicker(groups) {
  if (!groups.some((g) => g.car_class && g.category)) return { html: "", shown: groups, teams: true };
  const cars = [];
  for (const g of groups) {
    const id = g.key === "overall" ? "overall" : g.car_class ? g.car_class : g.category ? `field:${g.key}` : null;
    if (id && !cars.some((c) => c.id === id)) {
      const whole = groups.find((x) => x.key === g.car_class);
      const name = g.key === "overall" ? "Overall" : g.car_class ? (whole ? whole.name : g.name.split(" · ")[0]) : g.name;
      cars.push({ id, name, color: g.color });
    }
  }
  if (!cars.some((c) => c.id === champView.car)) champView.car = "all";
  const inCar = champView.car.startsWith("field:") || champView.car === "overall" ? [] : groups.filter((g) => g.car_class === champView.car);
  const cats = inCar.filter((g) => g.category).map((g) => ({ id: g.category, name: g.name.split(" · ").slice(1).join(" · ") || g.name }));
  if (champView.cat !== "all" && champView.cat !== "whole" && !cats.some((c) => c.id === champView.cat)) champView.cat = "all";
  const pill = (attr, id, on, label, color) => `<button class="chip ${on ? "active" : ""}" ${attr}="${esc(id)}">${color ? `<span class="swatch" style="background:${esc(color)}"></span>` : ""}${esc(label)}</button>`;
  const html = `<div class="champ-picker">
      <div class="row">${pill("data-champ-car", "all", champView.car === "all", "All")}${cars.map((c) => pill("data-champ-car", c.id, champView.car === c.id, c.name, c.color)).join("")}</div>
      ${cats.length ? `<div class="row">${pill("data-champ-cat", "all", champView.cat === "all", "All of them")}${inCar.some((g) => !g.category) ? pill("data-champ-cat", "whole", champView.cat === "whole", "Whole class") : ""}${cats.map((c) => pill("data-champ-cat", c.id, champView.cat === c.id, c.name)).join("")}</div>` : ""}
    </div>`;
  let shown = groups;
  if (champView.car === "overall") shown = groups.filter((g) => g.key === "overall");
  else if (champView.car.startsWith("field:")) shown = groups.filter((g) => g.key === champView.car.slice(6));
  else if (champView.car !== "all") {
    shown = inCar.filter((g) => champView.cat === "all" || (champView.cat === "whole" ? !g.category : g.category === champView.cat));
  }
  return { html, shown, teams: champView.car === "all" };
}

$("#champ-standings").addEventListener("click", (e) => {
  const car = e.target.closest("[data-champ-car]");
  const cat = e.target.closest("[data-champ-cat]");
  if (!car && !cat) return;
  if (car) {
    champView.car = car.dataset.champCar;
    champView.cat = "all";
  } else champView.cat = cat.dataset.champCat;
  renderChampStandings();
});

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
  const both = ["both", "sum", "overall_class"].includes(rules.scoring);
  const teamPen = st.teams.some((t) => t.penalty_points);
  const teamBasis = both ? ` <span class="hint">${(rules.team_points || "overall") === "class" ? "Drivers' class points" : "Drivers' overall points"}</span>` : "";
  const help = rules.scoring === "both"
    ? "Class and overall are separate championships: each driver scores in their class (on class positions) and overall (on overall positions), and each table adds up its own points. Bonuses and penalties apply in both."
    : rules.scoring === "sum" ? "Each driver's points are their class points plus their overall points, added up; each table ranks those totals. Bonuses count once."
      : "";
  const anySecondary = st.groups.some((g) => g.secondary);
  const pick = champPicker(st.groups);
  box.innerHTML = (help ? `<p class="hint">${help}</p>` : "") + pick.html + pick.shown.map((g) => `<div class="champ-group">
      ${g.key || st.groups.length > 1 ? `<div class="champ-group-head" style="--cls:${esc(g.color || "#8b93a3")}">${esc(g.name)}${g.secondary ? ' <span class="badge">CATEGORY</span>' : ""}${both || anySecondary ? ` <span class="hint">${esc(g.basis)}</span>` : ""}</div>` : ""}
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
    </div>`).join("") + (st.teams.length && pick.teams ? `<div class="champ-group">
      <div class="champ-group-head">Teams${teamBasis}</div>
      <div class="table-scroll"><table class="grid champ-table"><thead><tr><th class="c-num">Pos</th><th>Team</th><th>Drivers</th>${head}<th class="c-num">Wins</th>${teamPen ? '<th class="c-num" title="Penalty points taken off">Pen</th>' : ""}<th class="c-num">Points</th><th class="c-num">Gap</th></tr></thead>
      <tbody>${st.teams.map((t) => `<tr><td class="c-num"><b>${t.pos}</b></td><td>${esc(t.team)}</td>
        <td class="sub">${t.drivers.map((d) => `${esc(d.name)} (${fmtPts(d.points)})`).join(", ")}</td>
        ${rounds.map((r) => { const x = t.rounds.find((y) => y.round === r.id); return `<td class="c-rd ${x && x.dropped ? "dropped" : ""}" title="${x && x.dropped ? "Dropped" : ""}">${x && x.points != null ? fmtPts(x.points) : "–"}</td>`; }).join("")}
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
// A round's race length as a number and a unit: "45 min", "2 h" or "30 laps".
const LENGTH_UNITS = [["min", "minutes"], ["h", "hours"], ["laps", "laps"]];
function parseLength(text) {
  const m = /^\s*(\d+(?:\.\d+)?)\s*(min|minutes?|mins?|h|hours?|hrs?|laps?)?/i.exec(text || "");
  if (!m) return { n: "", unit: "min" };
  const u = (m[2] || "min").toLowerCase();
  return { n: m[1], unit: u.startsWith("l") ? "laps" : u.startsWith("h") ? "h" : "min" };
}
function lengthField(rd, i) {
  const { n, unit } = parseLength(rd.length);
  return `<span class="len-field" title="Race length: a time or a number of laps">
    <input type="number" min="0" step="1" class="narrow" data-round="${i}" data-rlen="n" value="${esc(n)}" placeholder="Length" aria-label="Race length">
    <select data-round="${i}" data-rlen="u" aria-label="Minutes, hours or laps">${LENGTH_UNITS.map(([v, l]) =>
      `<option value="${v}" ${unit === v ? "selected" : ""}>${l}</option>`).join("")}</select></span>`;
}

// A round's own (``other``): "+ Another layout…" at the end, to type one the
// list hasn't got (remembered for next time, Your own tracks).
function configField(rd, attrs, other = false) {
  const g = trackGroup(rd.track);
  if (!g || rd._typing) {
    return `<input ${attrs} value="${esc(rd.config || "")}" placeholder="${rd._typing ? "Type the layout" : "Configuration"}" aria-label="Configuration">`;
  }
  const configs = g.configs.map((c) => c.config);
  const current = rd.config || "";
  const extra = current && !configs.includes(current) ? `<option selected>${esc(current)}</option>`
    : !current && !configs.includes("") ? '<option value="" selected>Pick a layout</option>' : "";
  return `<select ${attrs} aria-label="Configuration">${extra}${configs.map((c) =>
    `<option value="${esc(c)}" ${c === current ? "selected" : ""}>${esc(c || "(one layout)")}</option>`).join("")}${other
    ? '<option value="__other__">＋ Another layout…</option>' : ""}</select>`;
}

// A track or layout typed in that the list hasn't got: kept as one of yours.
async function rememberTrack(track, config) {
  track = String(track || "").trim();
  config = String(config || "").trim();
  if (!track) return;
  const g = trackGroup(track);
  if (g && g.configs.some((c) => c.config === config)) return;
  try {
    const r = await api("/api/tracks", { method: "POST", body: { track, config } });
    if (r.added) toast(`${track}${config ? ` · ${config}` : ""} added to your tracks`);
    trackList.groups = r.tracks;
    trackList.status = r;
    $("#track-names").innerHTML = r.tracks.map((x) => `<option value="${esc(x.track)}"></option>`).join("");
    renderTrackStatus();
  } catch (err) {
    toast(err.message, true);
  }
}

function renderTrackStatus() {
  const st = trackList.status;
  if (!st) return;
  // Your own tracks and layouts, each with ✕ to take it off again.
  const mine = st.custom || [];
  $("#mt-list").innerHTML = mine.length ? mine.map((t) => `<li><span>${esc(t.track)}${t.config ? ` · ${esc(t.config)}` : ""}</span>
      <button type="button" class="btn icon danger" data-mt-remove="${esc(JSON.stringify([t.track, t.config]))}" title="Take it off the list" aria-label="Remove">✕</button></li>`).join("")
    : '<li class="hint">None yet. Add a track or layout the list hasn\'t got (or type one into a round: it\'s kept here).</li>';
  $("#track-source").textContent = st.official
    ? `${st.official} official layouts from iRacing${st.seen ? `, plus ${st.seen} seen in sessions` : ""}. A track or layout not in the list can be typed in (or added under Your own tracks).`
    : `Built-in list of iRacing tracks${st.seen ? `, plus ${st.seen} layouts seen in sessions` : ""}. A track or layout not in the list can be typed in (or added under Your own tracks).`;
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
    // Time penalties for this race (Penalties): the finishing order and points take them into account.
    const timePen = {};
    for (const p of c.penalties || []) if (p.round_id === rd.id && +p.seconds > 0) timePen[p.driver] = (timePen[p.driver] || 0) + +p.seconds;
    return `<div class="round-card ${open ? "open" : ""}">
      <div class="round-head">
        <span class="round-num">R${i + 1}</span>
        <input data-round="${i}" data-rkey="name" value="${esc(rd.name)}" placeholder="Round name" aria-label="Round name">
        <input data-round="${i}" data-rkey="track" class="track-input" list="track-names" value="${esc(rd.track || "")}" placeholder="Track (type to search)" aria-label="Track">
        ${configField(rd, `data-round="${i}" data-rkey="config"`, true)}
        <input type="date" data-round="${i}" data-rkey="date" value="${esc(rd.date || "")}" aria-label="Date">
        <input type="time" data-round="${i}" data-rkey="time" value="${esc(rd.time || "")}" aria-label="Start time" title="Start time">
        ${lengthField(rd, i)}
        <label class="field" title="Points multiplier: 1 for normal points, 2 for double points, and so on">Points ×<input type="number" class="narrow" min="0" max="10" step="0.5" data-round="${i}" data-rkey="multiplier" value="${rd.multiplier ?? 1}"></label>
        <label class="field" title="This round always counts, even with drop rounds"><input type="checkbox" data-round="${i}" data-rkey="no_drop" ${rd.no_drop ? "checked" : ""}> Can't drop</label>
        ${rd.event ? `<label class="field" title="This race's grid has its first N turned round: the starting grid board shows it so when its grid is from qualifying or the previous race (Automatic and as the cars line up take iRacing's grid as it is)"><input type="checkbox" data-round="${i}" data-rkey="reverse_grid" ${rd.reverse_grid ? "checked" : ""}> Reverse grid</label>
        <label class="field" title="How many from the front are turned round (with Reverse grid ticked)">Reverse top<input type="number" class="narrow" min="0" max="60" step="1" data-round="${i}" data-rkey="reverse_top" value="${rd.reverse_top || 0}" aria-label="How many cars are reversed"></label>` : ""}
        ${c.rules.custom_schemes && (c.rules.schemes || []).length ? `<label class="field" title="The points system this round is scored with">Points
          <select data-round="${i}" data-rkey="scheme"><option value="">Usual points</option>${c.rules.schemes.map((sc) =>
            `<option value="${esc(sc.id)}" ${rd.scheme === sc.id ? "selected" : ""}>${esc(sc.name || "Unnamed")}</option>`).join("")}</select></label>` : ""}
        <label class="field" title="The race in progress counts as this round in the live standings"><input type="radio" name="live-round" data-live-round="${esc(rd.id)}" ${isLive ? "checked" : ""}> Live</label>
        <span class="grow"></span>
        <span class="sub">${(rd.results || []).length ? `${rd.results.length} results` : "No results"}</span>
        <button class="btn" data-round-toggle="${esc(rd.id)}">${open ? "Close" : "Results"}</button>
        <button class="btn" data-round-import="${i}" title="Fill this round with the results of the race session you're in">⤓ Import from session</button>
        ${rd.event ? "" : `<button class="btn subtle" data-round-meeting="${i}" title="Make this round a race meeting of several races (heat races, say), each a round of its own. Its results stay with the first race.">⇉ Race meeting</button>`}
        ${(rd.results || []).length ? `<button class="btn subtle" data-round-clear="${i}" title="Take this race's results off: the round stays, to import or type them again">⌫ Clear results</button>` : ""}
        <button class="btn icon danger" data-round-delete="${i}" title="Delete round">✕</button>
      </div>
      ${open ? `<div class="row transfer-row"><span class="hint">This round's results:</span>
        <button class="btn subtle" data-export="round" data-export-round="${esc(rd.id)}" title="To import into a round, here or on another PC">⤓ Export</button>
        <button class="btn subtle" data-export="round_csv" data-export-round="${esc(rd.id)}" title="As a spreadsheet (CSV)">⤓ CSV</button>
        <label class="btn subtle" title="iRacing's event result export (.csv, from the results page), a round export (.json) or a CSV with the same columns as the CSV export">⤒ Import…<input type="file" accept=".json,.csv,application/json,text/csv" data-import="round" data-import-round="${esc(rd.id)}" hidden></label>
      </div>
      <div class="table-scroll"><table class="grid champ-table results-table">
        <thead><tr><th class="c-num">Pos</th><th>Driver</th><th>Class</th><th class="c-num">Start</th><th class="c-num">Laps</th><th class="c-num">Led</th><th>Fastest lap</th><th class="c-num">Inc</th><th>Status</th><th class="c-num" title="Extra points given (+) or taken (−) for this round">+/− pts</th><th class="c-num" title="Points scored in each championship (after saving)">Pts</th><th></th></tr></thead>
        <tbody>${results.map(([r, j]) => `<tr>
          <td><input type="number" class="c-num" min="1" data-round="${i}" data-res="${j}" data-key="position" value="${r.position ?? ""}"
            title="Where they crossed the line">${timePen[r.driver] ? `<span class="tag pen-time" title="Time penalty (Penalties): the finishing order and points take it into account">+${fmtPts(timePen[r.driver])} s</span>` : ""}</td>
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

// A race meeting's format: which race of the iRacing event goes with which of its rounds.
const MEETING_FORMATS = [["", "Auto (by name and order)"], ["single", "Single race"], ["heat2", "2-race heat: heat, feature"],
  ["heat3", "3-race heat: heat, consolation, feature"]];
const FORMAT_RACES = { single: ["The race (the feature, if it's a heat event)"], heat2: ["Heat (every heat)", "Feature"],
  heat3: ["Heat (every heat)", "Consolation", "Feature"] };

function meetingHtml(first, last, inner) {
  const c = champData();
  const n = last - first + 1;
  const fmt = c.rounds[first].format || "";
  const races = FORMAT_RACES[fmt];
  // Which round takes which race (its name replaces iRacing's on stream).
  const map = races ? `<p class="hint meeting-map">${races.map((race, k) => {
    const rd = c.rounds[first + k];
    return `${esc(race)} → ${rd ? `<b>R${first + k + 1} · ${esc(rd.name)}</b>` : "<i>no round: add a race</i>"}`;
  }).join(" &nbsp;·&nbsp; ")}</p>` : "";
  return `<div class="meeting">
    <div class="meeting-head">
      <span class="badge">RACE MEETING</span>
      <input data-meeting="${first}" value="${esc(c.rounds[first].event)}" aria-label="Race meeting name" title="Rename the meeting (empty: its races become separate rounds)">
      <span class="sub">${n} race${n === 1 ? "" : "s"} · round${n === 1 ? "" : "s"} ${first + 1}${n > 1 ? `–${last + 1}` : ""}</span>
      <label class="meeting-format" title="Which race of the iRacing event goes with which round: each round's name replaces iRacing's race name on stream">Races in this event
        <select data-meeting-format="${first}">${MEETING_FORMATS.map(([v, l]) => `<option value="${v}" ${fmt === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
      <span class="grow"></span>
      <button class="btn" data-meeting-import="${first}" title="Each race session of the event you're in (heats, then the feature...) into these races, in order">⤓ Import every race from session</button>
      <button class="btn subtle" data-meeting-add="${last}">+ Add a race</button>
      <button class="btn subtle" data-meeting-split="${first}" title="Its races become separate rounds again">Separate rounds</button>
    </div>
    ${map}
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
      <td><input type="number" class="c-num ${p.seconds && !p.round_id ? "bad-input" : ""}" min="0" max="3600" step="1" data-pen="${i}" data-key="seconds" value="${p.seconds || 0}"
        title="${p.seconds && !p.round_id ? "Pick the round: a time penalty is for one race" : "Seconds added to their race time in that round"}"></td>
      <td><input type="number" class="c-num" min="0" step="0.5" data-pen="${i}" data-key="points" value="${p.points || 0}"></td>
      <td><input type="number" class="c-num" min="0" data-pen="${i}" data-key="licence" value="${p.licence || 0}"></td>
      <td><input class="grow" data-pen="${i}" data-key="reason" value="${esc(p.reason || "")}" placeholder="e.g. Avoidable contact, T1 lap 1"></td>
      <td><button class="btn icon danger" data-pen-delete="${i}" title="Remove">✕</button></td>
    </tr>`).join("") : '<tr><td colspan="7" class="hint">No penalties.</td></tr>';
}

// -- rules -------------------------------------------------------------------------

const SCORING_HELP = {
  class: "Each class is a championship of its own, scored on class finishing positions with the class points.",
  overall: "One championship for everyone, scored on overall finishing positions with the overall points.",
  both: "Every race scores twice, each with its own points: a driver's class position in their class's championship (class points) and their overall position in the overall championship (overall points). Each has its own table and board.",
  sum: "Each driver scores once a race: the class points for their class position plus the overall points for their overall position, added up. Each class's table and the overall table rank those totals.",
  overall_class: "Each driver scores the overall points for their overall position, and those same points count in their class's championship: each class's table ranks its drivers on their overall points.",
};

// A points table for any class that scores differently (empty = the class points above).
function classPointsFields(r) {
  const classes = (ui.editing && ui.editing.classes) || [];
  const scored = classes.filter((c) => isSecondary(c) || (r.scoring || "class") !== "overall");
  if (!scored.length) return "";
  const own = r.class_points || {};
  return `<details class="wide class-points" ${Object.keys(own).length ? "open" : ""}><summary>Different points for a class</summary>
    <p class="hint">Leave a class empty to use the points for each finishing position above. Categories rank their
      drivers by where they finished among each other (in each car class, for one scored in each), on their own table here.</p>
    <div class="class-points-grid">${scored.map((c) => `<label class="ov-field">${esc(c.name || "Unnamed")}${isSecondary(c) ? " (category)" : ""}
      <input data-class-points="${esc(c.id)}" value="${esc((own[c.id] || []).join(", "))}" placeholder="Same as above"></label>`).join("")}</div>
  </details>`;
}

// How each secondary class scores (rules.secondary_scoring, by class id).
function secondaryScoringFields(r) {
  const sec = ((ui.editing && ui.editing.classes) || []).filter(isSecondary);
  if (!sec.length) return "";
  const how = r.secondary_scoring || {};
  return `<div class="wide secondary-scoring"><h3 class="section-title">Category points come from</h3>
    <div class="class-points-grid">${sec.map((c) => `<label class="ov-field">${esc(c.name || "Unnamed")}${c.scope === "class" ? " (in each car class)" : ""}
      <select data-secondary-scoring="${esc(c.id)}">${[["own", "Finishing order in the category (recommended)"],
        ["class", "Their car class points"], ["overall", "Their overall points"]]
        .map(([v, l]) => `<option value="${v}" ${(how[c.id] || "own") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>`).join("")}</div>
    <p class="hint">A driver in a category scores in it as well as in their car class (and overall), each on its own points.
      <b>Finishing order in the category</b>: the first Pro home in LMP2 scores the winner's points, even if 3rd in LMP2.
      <b>Their car class points</b>: a Pro 3rd in LMP2 scores LMP2's 3rd place points in the Pro table.</p></div>`;
}

// Which championships the league runs: a tick for each car class's own, each
// category's in it, and each category for the whole field (rules.hidden: off).
function championshipGrid(r) {
  const classes = (ui.editing && ui.editing.classes) || [];
  const mains = classes.filter((c) => !isSecondary(c));
  const cats = classes.filter(isSecondary);
  if (!mains.length && !cats.length) return "";
  const perClass = cats.filter((c) => c.scope === "class");
  const field = cats.filter((c) => c.scope !== "class");
  const hasClass = (r.scoring || "class") !== "overall";
  const off = new Set(r.hidden || []);
  const tick = (key, label) => `<label class="check champ-tick" title="${esc(label)}"><input type="checkbox" data-champ-on="${esc(key)}" ${off.has(key) ? "" : "checked"} aria-label="${esc(label)}"></label>`;
  return `<div class="wide champ-grid-box"><h3 class="section-title">Which championships run</h3>
    <table class="grid champ-grid"><thead><tr><th></th><th>Whole class</th>${perClass.map((c) => `<th>${esc(c.name || "Unnamed")}</th>`).join("")}</tr></thead>
    <tbody>${mains.map((m) => `<tr><th><span class="swatch" style="background:${esc(m.color)}"></span>${esc(m.name || "Unnamed")}</th>
      <td>${hasClass ? tick(m.id, `${m.name} championship`) : '<span class="sub" title="Only an overall championship is scored">—</span>'}</td>
      ${perClass.map((c) => `<td>${!c.in || !c.in.length || c.in.includes(m.id) ? tick(`${m.id}/${c.id}`, `${m.name} · ${c.name}`) : '<span class="sub" title="Not in this car class (Classes tab)">—</span>'}</td>`).join("")}</tr>`).join("")}</tbody></table>
    ${field.length ? `<div class="row">${field.map((c) => `<label class="check"><input type="checkbox" data-champ-on="${esc(c.id)}" ${off.has(c.id) ? "" : "checked"}> ${esc(c.name || "Unnamed")} (whole field)</label>`).join("")}</div>` : ""}
    <p class="hint">Untick one to leave it out of the standings, boards and overlays (its drivers still score in the others).
      Car classes, categories and who's in each are set in the League builder (Classes and Drivers). Results already in are
      scored again to whatever is set here.</p></div>`;
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
        ${hasClass || secondary ? `<label class="ov-field">${hasClass ? "Class points" : "Points for the categories"} (1st, 2nd, 3rd… in class)
          <input data-rule="points" value="${esc((r.points || []).join(", "))}"></label>` : ""}
      </div>
      <div class="champ-kind ${hasOverall ? "on" : ""}">
        <label class="check"><input type="checkbox" data-champ-kind="overall" ${hasOverall ? "checked" : ""}> <b>Overall championship</b>
          <span class="hint">everyone together, scored on overall finishing positions, with its own points</span></label>
        ${hasOverall ? `<label class="ov-field">Overall points (1st, 2nd, 3rd… overall)
          <input data-rule="overall_points" value="${esc(overallPts.join(", "))}"></label>` : ""}
      </div>
      ${hasClass && hasOverall ? `<label class="ov-field">Class and overall points count
        <select data-rule="scoring">${[["both", "As two separate championships"], ["sum", "Added together into one total"],
          ["overall_class", "Overall points count as class points"]].map(([v, l]) =>
          `<option value="${v}" ${scoring === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>` : ""}
      <p class="hint">${esc(SCORING_HELP[scoring])}</p>
    </div>
    ${championshipGrid(r)}
    ${classPointsFields(r)}
    ${secondaryScoringFields(r)}
    <label class="ov-field wide">Qualifying points (pole, 2nd, 3rd…; leave empty for none). Uses the starting grid.
      <input data-rule="qualifying_points" value="${esc((r.qualifying_points || []).join(", "))}"></label>
    <label class="ov-field">Drop rounds (each driver's worst N don't count)
      <input type="number" min="0" max="50" data-rule="drop_rounds" value="${r.drop_rounds || 0}"></label>
    <label class="ov-field check" title="A race meeting (heats, a sprint and a feature…) drops as one: its races' points added up, all of them dropped together"><input type="checkbox" data-rule="drop_meetings" ${r.drop_meetings ? "checked" : ""}> A race meeting drops as a whole (its races together, as one)</label>
    <h3 class="section-title wide">Custom points systems</h3>
    <label class="ov-field check wide"><input type="checkbox" data-rule="custom_schemes" ${r.custom_schemes ? "checked" : ""}> <b>Custom points system</b>
      <span class="hint">points tables of your own for different kinds of race (a sprint, a feature…); pick one for each round under Calendar &amp; results</span></label>
    ${r.custom_schemes ? `<div class="wide schemes">${(r.schemes || []).map((sc, i) => `<div class="scheme">
        <input data-scheme="${i}" data-skey="name" value="${esc(sc.name)}" placeholder="Name (e.g. Sprint)" aria-label="Points system name">
        <label class="ov-field grow">Points (1st, 2nd, 3rd…)<input data-scheme="${i}" data-skey="points" value="${esc((sc.points || []).join(", "))}" placeholder="e.g. 15, 12, 10, 8"></label>
        ${hasOverall ? `<label class="ov-field grow">Overall points (empty: the same)<input data-scheme="${i}" data-skey="overall_points" value="${esc((sc.overall_points || []).join(", "))}"></label>` : ""}
        <button class="btn icon danger" data-scheme-remove="${i}" title="Remove this points system">✕</button>
        <label class="check scheme-own"><input type="checkbox" data-scheme="${i}" data-skey="own_bonuses" ${sc.own_bonuses ? "checked" : ""}>
          Its own bonus points <span class="hint">(instead of the bonus points below, for rounds on this system)</span></label>
        ${sc.own_bonuses ? `<div class="scheme-bonuses">${champ.bonuses.map(([k, label]) => `<label class="ov-field">${esc(label)}
          <input type="number" step="0.5" data-scheme="${i}" data-skey="bonus" data-sbonus="${k}" value="${(sc.bonuses || {})[k] || 0}"></label>`).join("")}</div>` : ""}
      </div>`).join("")}
      <button class="btn subtle" data-scheme-add>+ Add a points system</button></div>` : ""}
    <label class="ov-field">Fastest-lap bonus only in the top N (0 = anyone)
      <input type="number" min="0" data-rule="fastest_lap_top" value="${r.fastest_lap_top || 0}"></label>
    <label class="ov-field">Must complete this % of the race (their class winner's laps) to score; anyone short is a DNF with no points (0 = off)
      <input type="number" min="0" max="100" data-rule="classified_pct" value="${r.classified_pct ?? 75}"></label>
    <label class="ov-field">Team championship: each round counts
      <select data-team-count>${[["all", "All the team's drivers, added together"], ["best", "Its best drivers (the best N)"]].map(([v, l]) =>
        `<option value="${v}" ${(r.team_best ? "best" : "all") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    ${r.team_best ? `<label class="ov-field">How many of its drivers count (the best N)
      <input type="number" min="1" max="20" data-rule="team_best" value="${r.team_best}"></label>` : ""}
    <label class="ov-field check" title="A race meeting (heats, a sprint and a feature…) counts as one for the teams: each driver's points over the meeting added up, and the team's best N over the meeting count"><input type="checkbox" data-rule="team_meetings" ${r.team_meetings ? "checked" : ""}> Teams: a race meeting counts as one (the best N over the whole meeting)</label>
    ${r.drop_rounds > 0 ? `<label class="ov-field">Teams: drop rounds
      <select data-rule="team_drop_mode" title="The team's own: the team's worst rounds don't count. The drivers': each driver's dropped rounds don't count for their team. None: every round counts for the teams">${[
        ["team", "The team's own worst rounds"], ["drivers", "Each driver's dropped rounds"], ["none", "None (every round counts)"]].map(([v, l]) =>
        `<option value="${v}" ${(r.team_drop_mode || (r.team_drops === false ? "none" : "team")) === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>` : ""}
    ${r.scoring === "both" ? `<label class="ov-field">Team championship counts its drivers'
      <select data-rule="team_points">${[["overall", "Overall points"], ["class", "Class points"]].map(([v, l]) =>
        `<option value="${v}" ${(r.team_points || "overall") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>` : ""}
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
  // Points & rules (and which round is Live) are saved as they're changed:
  // the standings, boards and overlays use them straight away.
  const isRule = !!(d.champKind || d.champOn || d.rule || d.teamCount != null || d.secondaryScoring || d.classPoints || d.bonus || d.liveRound
    || (d.scheme != null && d.skey));
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
    r.scoring = want.class && want.overall ? (["sum", "overall_class"].includes(scoring) ? scoring : "both") : want.class ? "class" : "overall";
    rerender = true;
  } else if (d.rule) {
    const r = c.rules;
    if (d.rule === "points" || d.rule === "qualifying_points" || d.rule === "overall_points") {
      if (!final) return;
      r[d.rule] = el.value.split(/[\s,;]+/).filter(Boolean).map(Number).filter((n) => !isNaN(n) && n >= 0);
      rerender = true;
    } else if (el.type === "checkbox") {
      r[d.rule] = el.checked;
      if (d.rule === "custom_schemes" && final) {
        r.schemes = r.schemes || [];
        if (el.checked && !r.schemes.length) r.schemes.push({ id: `s${Date.now().toString(36)}`, name: "Sprint", points: [], overall_points: [] });
        rerender = true;
      }
    }
    else r[d.rule] = el.type === "number" ? +el.value : el.value;
    if ((d.rule === "scoring" || d.rule === "drop_rounds") && final) rerender = true;  // drop rounds: the teams' box comes and goes
  } else if (d.teamCount != null) {
    // All the team's drivers (team_best 0), or its best N (2 to start with).
    if (!final) return;
    c.rules.team_best = el.value === "best" ? (c.rules.team_best || 2) : 0;
    rerender = true;
  } else if (d.champOn) {
    // A championship run or not (rules.hidden).
    if (!final) return;
    const off = new Set(c.rules.hidden || []);
    if (el.checked) off.delete(d.champOn);
    else off.add(d.champOn);
    c.rules.hidden = [...off];
    rerender = true;
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
  } else if (d.scheme != null && d.skey) {
    // A custom points system's name or points.
    const sc = c.rules.schemes[+d.scheme];
    if (d.skey === "own_bonuses") {
      // Its own bonus points: starting from the usual ones.
      if (!final) return;
      sc.own_bonuses = el.checked;
      if (el.checked && !sc.bonuses) sc.bonuses = { ...(c.rules.bonuses || {}) };
      rerender = true;
    } else if (d.skey === "bonus") {
      sc.bonuses = sc.bonuses || {};
      sc.bonuses[d.sbonus] = +el.value || 0;
    } else {
      sc[d.skey] = d.skey === "name" ? el.value : el.value.split(/[\s,;]+/).filter(Boolean).map(Number).filter((n) => !isNaN(n) && n >= 0);
      if (final && d.skey === "name") rerender = true;
    }
  } else if (d.meeting != null) {
    if (!final) return;
    for (const rd of meetingRounds(+d.meeting)) rd.event = el.value.trim();
    rerender = true;
  } else if (d.meetingFormat != null) {
    // The meeting's format: on each of its rounds; a heat format adds the rounds it needs.
    if (!final) return;
    // Exactly the rounds the format has: more added (named for their race),
    // extra ones without results taken away (ones with results stay, said so).
    const first = +d.meetingFormat;
    const rounds = meetingRounds(first);
    for (const rd of rounds) rd.format = el.value;
    const need = { single: 1, heat2: 2, heat3: 3 }[el.value] || 0;
    const names = { single: ["Race"], heat2: ["Heat", "Feature"], heat3: ["Heat", "Consolation", "Feature"] }[el.value] || [];
    const DEFAULT_NAMES = ["Race", "Heat", "Consolation", "Feature"];
    if (need) {
      for (let k = rounds.length; k < need; k++) {
        const last = c.rounds[first + k - 1];
        c.rounds.splice(first + k, 0, { ...last, id: newId(), name: names[k], results: [], session: "", format: el.value });
      }
      // A round still called after another race (added for an earlier format): named for its race now.
      meetingRounds(first).slice(0, need).forEach((rd, k) => {
        if (DEFAULT_NAMES.includes(rd.name) && !(rd.results || []).length) rd.name = names[k];
      });
      const extra = meetingRounds(first).slice(need);
      const kept = extra.filter((rd) => (rd.results || []).length);
      for (const rd of extra) if (!kept.includes(rd)) c.rounds.splice(c.rounds.indexOf(rd), 1);
      if (kept.length) {
        toast(`${kept.map((rd) => rd.name).join(", ")} ${kept.length > 1 ? "have" : "has"} results, so ${kept.length > 1 ? "they stay" : "it stays"} in the meeting: remove ${kept.length > 1 ? "them" : "it"} by hand if ${kept.length > 1 ? "they're" : "it's"} not needed`);
      }
    }
    rerender = true;
  } else if (d.round != null && d.rlen) {
    // Race length: a number and its unit (minutes, hours or laps).
    const box = el.closest(".len-field");
    const n = box.querySelector("[data-rlen=n]").value;
    const unit = box.querySelector("[data-rlen=u]").value;
    c.rounds[+d.round].length = n !== "" && +n > 0 ? `${+n} ${unit}` : "";
  } else if (d.round != null && d.rkey) {
    const rd = c.rounds[+d.round];
    // The date it had before this change (typing saves as it goes, so not rd's).
    const before = el.defaultValue;
    rd[d.rkey] = el.type === "checkbox" ? el.checked : el.type === "number" ? +el.value : el.value;
    if (d.rkey === "date" && final) el.defaultValue = el.value;
    if (d.rkey === "date" && final && rd.event && rd.date) {
      // A race meeting's races are run the same day: the date goes on the others
      // with none yet, or still on the date this one had (so moving the meeting
      // moves them all). One given a day of its own (a feature the day after) keeps it.
      let first = +d.round;
      while (first > 0 && c.rounds[first - 1].event === rd.event) first -= 1;
      const filled = meetingRounds(first).filter((o) => o !== rd && (!o.date || (before && o.date === before)));
      for (const o of filled) o.date = rd.date;
      if (filled.length) {
        rerender = true;
        toast(`Same date set on ${filled.length === 1 ? "the meeting's other race" : `the meeting's other ${filled.length} races`}`);
      }
    }
    if (d.rkey === "config" && el.value === "__other__") {
      // + Another layout…: a box to type it in.
      rd.config = "";
      rd._typing = true;
      renderChampionship();
      const box = document.querySelector(`[data-round="${d.round}"][data-rkey="config"]`);
      if (box) box.focus();
      return;
    }
    if (d.rkey === "track" || d.rkey === "config") {
      // A known track: its layouts fill the Configuration list.
      const g = trackGroup(rd.track);
      if (g && d.rkey === "track" && final && !rd._typing) rd.config = g.configs[0].config;
      // Typed in and not in the list: remembered (Your own tracks).
      if (final && el.tagName === "INPUT" && rd.track && (d.rkey === "config" || (!g && rd.config))) {
        rememberTrack(rd.track, rd.config).then(() => { delete rd._typing; renderChampionship(); });
      }
      const layout = g && g.configs.find((x) => x.config === rd.config);
      rd.track_id = layout ? layout.id : null;
      if (final) rerender = true;
    }
  } else return;
  if (isRule) {
    if (final) saveRulesSoon();
  } else markChampDirty();
  if (rerender) renderChampionship();
}

let rulesTimer = null;
function saveRulesSoon() {
  clearTimeout(rulesTimer);
  const id = ui.editing && ui.editing.id;
  if (!id) return;
  rulesTimer = setTimeout(async () => {
    if (!ui.editing || ui.editing.id !== id) return;
    const c = champData();
    try {
      const r = await api(`/api/leagues/${encodeURIComponent(id)}/championship/rules`, { method: "POST", body: { rules: c.rules, live_round: c.live_round } });
      if (ui.editing && ui.editing.id === id) {
        champ.standings = r.standings;  // shown next time the standings are (not redrawn under the rules being typed in)
        if (champ.view === "standings") renderChampionship();
      }
    } catch (err) {
      toast(err.message, true);
    }
  }, 300);
}

$("#tab-championship").addEventListener("input", (e) => champChange(e, false));
$("#tab-championship").addEventListener("change", (e) => {
  if (e.target.classList.contains("league-picker")) return;
  champChange(e, true);
});

$("#tab-championship").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b || !ui.editing) return;
  if (b.dataset.schemeAdd != null || b.dataset.schemeRemove != null) {
    const r = champData().rules;
    r.schemes = r.schemes || [];
    if (b.dataset.schemeAdd != null) r.schemes.push({ id: `s${Date.now().toString(36)}`, name: "", points: [], overall_points: [] });
    else {
      const [gone] = r.schemes.splice(+b.dataset.schemeRemove, 1);
      for (const rd of champData().rounds) if (rd.scheme === gone.id) rd.scheme = "";  // back on the usual points
    }
    markChampDirty();
    renderChampionship();
    return;
  }
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
  } else if (d.roundClear != null) {
    const rd = c.rounds[+d.roundClear];
    const pens = c.penalties.filter((p) => p.round_id === rd.id).length;
    if (!confirm(`Clear the results of ${rd.name}? The round stays, to import or type its results again.` +
      (pens ? ` Its ${pens} penalt${pens === 1 ? "y stays" : "ies stay"} (Penalties).` : ""))) return;
    rd.results = [];
    rd.session = "";  // free to take the results of a race again (Import from session, or saved after the race)
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
  c.penalties.push({ id: newId(), driver: "", round_id: c.rounds.length ? c.rounds[c.rounds.length - 1].id : "", seconds: 0, points: 0, licence: 0, reason: "" });
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

// The Live timing tab: how the spectators' page looks and what it shows.
const LIVE_FIELDS = [
  ["Delay", [["delay_s", "Extra delay, to match your stream's delay (seconds, on top of the overlays' delay; 0 = none). Spectators then see the race as the stream shows it, not ahead of it", "number", { min: 0, max: 300, step: 0.5 }]]],
  ["Header", [["title", "Heading (empty: the league's name)", "text"], ["show_series_logo", "League logo", "bool"],
    ["accent_color", "Colour of the top bar (and the drivers picked)", "color"]]],
  ["Drivers", [["name_format", "Names", "select", NAME_FORMATS], ["show_team", "Team name under each driver", "bool"],
    ["show_logo", "Team logo by each driver", "bool"], ["show_number", "Car number (in the class colour)", "bool"]]],
  ["Leaderboard columns", [["show_pos_change", "Places gained / lost (race)", "bool"], ["show_interval", "Interval to the car ahead (race)", "bool"],
    ["show_last", "Last lap", "bool"], ["show_best", "Best lap", "bool"], ["show_sectors", "Sector times of the lap on now", "bool"],
    ["show_tyre", "Tyres", "bool"], ["show_laps", "Laps", "bool"], ["show_status", "PIT and the finish flag", "bool"]]],
  ["Driver tracker", [["tracker", "The Driver tracker tab (head to head and track map)", "bool"],
    ["map_label", "Labels on the track map", "select", [["abbr", "3 letters (VER)"], ["number", "Car number"], ["name", "Name (as above)"], ["none", "None"]]]]],
];

// Custom opacity per column: a tick box, then a slider for each column.
const columnOpacity = (cols) => [["col_opacity_on", "A background of its own for each column", "bool"],
  iff((v) => v.col_opacity_on, ["col_bg_color", "Column background colour", "color"]),
  iff((v) => v.col_opacity_on, ["col_opacity", "Background opacity of each column (the text stays as it is)", "colopacity", cols])];

// Each overlay's settings, in named sections that open and close:
// [title, fields]. A field is [key, label, kind, opts]; `iff(when, field)`
// shows it only while when(values) holds (e.g. a timer for a flash that's on).
const iff = (when, field) => Object.assign(field, { when });
// A setting kept in another section (shared by several widgets) shown here too:
// read from and saved to that section.
const shared = (section, field) => Object.assign(field, { section });
// A setting set in under another one shown only while it's on (the one it
// depends on, when that isn't simply the one before it).
const under = (parent, field) => Object.assign(field, { parent });
// Team logos' size, where there are team logos.
const LOGO_KIND = iff((v) => "team_logo_kind" in v, ["team_logo_kind", "Team logo", "select",
  [["full", "The team's full logo"], ["small", "The team's small logo"]]]);
const LOGO_SIZE = iff((v) => "logo_scale" in v, ["logo_scale", "Team logo size (%; 100 = usual)", "number", { min: 40, max: 250, step: 5 }]);
const LOOK = ["Size & background", [["scale", "Size", "size"], LOGO_KIND, LOGO_SIZE, ["bg", "Background", "background"]]];
// Overlays can also be moved from where they sit (px on the 1920×1080 screen), to keep clear of each other.
// One Move setting (right and down, with nudge buttons) for offset_x and offset_y.
const OFFSET = [["offset_x", "Move (right / down, px on the 1920×1080 screen; minus goes left / up)", "move"]];
const OVERLAY_LOOK = ["Size, position & background", [["scale", "Size", "size"], LOGO_KIND, LOGO_SIZE, ...OFFSET, ["bg", "Background", "background"]]];
// Session names: what the tower, the timing screen and every board call each
// session (kept with the tower's settings, as they always were).
const SESSION_NAME_FIELDS = [
  ["Names on stream", [
    shared("standings", ["title_race", "Race name (blank = RACE)", "text"]),
    shared("standings", ["title_qualify", "Qualifying name (blank = QUALIFYING)", "text"]),
    shared("standings", ["title_practice", "Practice / warm-up name (blank = iRacing's)", "text"]),
    shared("standings", ["title_heat", "Heat race name (blank = iRacing's, e.g. HEAT 1; a number is added for several)", "text"]),
    shared("standings", ["title_consolation", "Consolation race name (blank = iRacing's)", "text"]),
    shared("standings", ["title_feature", "Feature race name (blank = iRacing's)", "text"]),
  ]],
  ["Race meetings", [
    shared("standings", ["round_titles", "Heat events: each race takes its round's name from the Championship tab", "select", [["name", "Yes"], ["off", "No"]]]),
  ]],
];
const OVERLAY_FIELDS = {
  session_names: SESSION_NAME_FIELDS,
  standings: [
    ["What it shows", [
      ["mode", "Show", "select", [["overall", "Overall"], ["class", "By class"]]],
      iff((v) => v.mode === "class", ["class_keys", "Classes shown, in this order", "classorder"]),
      iff((v) => v.mode !== "class", ["rows", "Drivers shown (overall)", "number", { min: 1, max: 64 }]),
      iff((v) => v.mode !== "class", ["rows_last", "Extra drivers under the top ones, when there are more (overall; 0 = none)", "number", { min: 0, max: 30 }]),
      iff((v) => v.mode === "class", ["rows_class", "Drivers shown in each class (by class)", "number", { min: 1, max: 64 }]),
      iff((v) => v.mode === "class", ["rows_last_class", "Extra drivers under each class's top ones (by class; 0 = none)", "number", { min: 0, max: 30 }]),
      iff((v) => (v.mode === "class" ? v.rows_last_class : v.rows_last) > 0, ["rows_extra_mode", "Extra drivers show", "select",
        [["rotate", "The rest of the field (or class), a set at a time (always the full number)"], ["last", "The last ones"]]]),
      iff((v) => (v.mode === "class" ? v.rows_last_class : v.rows_last) > 0 && v.rows_extra_mode === "rotate",
        ["rows_extra_s", "Seconds per set of extra drivers", "number", { min: 1, max: 120, step: 1 }]),
      iff((v) => (v.mode === "class" ? v.rows_last_class : v.rows_last) > 0, ["rows_extra_opacity", "Extra drivers' opacity (%)", "number", { min: 10, max: 100, step: 5 }]),
      ["reveal", "Race start: only the header until each driver completes lap 1 (they appear from the start of lap 2)", "bool"],
    ]],
    ["Header", [
      ["header_info", "Header shows", "select", [["auto", "Laps or time left (automatic)"], ["laps", "Lap x of y"],
        ["time", "Time left"], ["none", "Nothing"]]],
      ["replay_header", "Watching a replay: REPLAY in the header, on the accent colour", "bool"],
      ["replay_hide_rows", "Watching a replay: hide the drivers, just the header saying REPLAY (they're back when it's live)", "bool"],
      ["show_series", "Series name (the league's name)", "bool"],
      ["show_track", "Track name", "bool"],
      ["time_left_word", "\"LEFT\" after the time left (12:34 LEFT)", "bool"],
      ["finished_word", "\"FINISHED\" in the header once the race is over (untick: nothing there)", "bool"],
      ["accent", "Accent colour (time / lap, the header's bar and line)", "select", [["default", "Orange"], ["color", "A colour of my own"],
        ["session", "By session: practice, qualifying, race"]]],
      iff((v) => v.accent === "color", ["accent_color", "Accent colour", "color"]),
      iff((v) => v.accent === "session", ["accent_practice", "Practice", "color"]),
      iff((v) => v.accent === "session", ["accent_qualify", "Qualifying", "color"]),
      iff((v) => v.accent === "session", ["accent_race", "Race", "color"]),
      ["sponsor_bar", "Sponsor logo bar under the header (tower)", "bool"],
      iff((v) => v.sponsor_bar, ["sponsor_bar_ids", "Sponsors in the bar (several take turns)", "sponsors"]),
      iff((v) => v.sponsor_bar, ["sponsor_bar_s", "Seconds per logo", "number", { min: 2, max: 120, step: 1 }]),
      iff((v) => v.sponsor_bar, ["sponsor_bar_size", "Bar height (px)", "number", { min: 20, max: 120, step: 2 }]),
      ["title_wrap", "Wrap a long session name onto two lines (off: one line, the tower widens for it)", "bool"],
      ["show_col_labels", "Column headings (GAP, INT…)", "bool"],
    ]],
    ["Columns", [
      ["show_gap", "Gap to leader / pole", "bool"],
      iff((v) => v.show_gap, ["leader_cell", "The leader's gap shows", "select", [["leader", "Leader"], ["lap", "Their current lap (Lap 12)"]]]),
      ["show_interval", "Interval to car ahead", "bool"],
      iff((v) => v.show_interval, ["leader_interval", "The leader's interval shows", "select", [["leader", "Leader"],
        ["lap", "Their current lap (Lap 12)"], ["blank", "Nothing"]]]),
      iff((v) => v.show_interval, ["close_s", "Interval goes red within (s, 0 = off)", "number", { min: 0, max: 2, step: 0.05 }]),
      ["show_pos_change", "Places gained / lost (race)", "bool"],
      ["show_best_lap", "Best lap", "bool"],
      ["show_last_lap", "Last lap", "bool"],
      ["show_laps", "Laps completed", "bool"],
      ["show_pits", "Pit stops", "bool"],
      ["show_pit_status", "PIT badge on pit road", "bool"],
      ["show_tyre", "Tyres: a white dry tyre or a blue wet one (the full screen too)", "bool"],
      ["show_stint", "Current stint: laps since their last pit stop (races; the full screen too)", "bool"],
      ["show_make", "Car manufacturer badge (the full screen too)", "bool"],
      ["column_order", "Column order on the tower", "order", [["pos_change", "+/−", "show_pos_change"], ["laps", "Laps", "show_laps"],
        ["pits", "Pit stops", "show_pits"], ["last_lap", "Last lap", "show_last_lap"], ["best_lap", "Best lap", "show_best_lap"],
        ["gap", "Gap", "show_gap"], ["interval", "Interval", "show_interval"], ["tyre", "Tyres", "show_tyre"],
        ["stint", "Stint", "show_stint"], ["make", "Car", "show_make"]]],
      ["screen_column_order", "Column order on the full screen", "order", [["laps", "Laps"], ["gap", "Gap"], ["interval", "Interval"],
        ["last_lap", "Last lap (races)"], ["best_lap", "Best lap"], ["pits", "Pit stops (races)"], ["tyre", "Tyres"],
        ["stint", "Stint (races)"], ["make", "Car"]]],
      ["screen_keep_left", "Keep drivers who leave the session in the list, where they were (tower and full screen; greyed out)", "bool"],
      ...columnOpacity([["pos", "Position"], ["number", "Car number"], ["logo", "Team logo"], ["name", "Driver"], ["team", "Team name"],
        ["pos_change", "+/−"], ["laps", "Laps"], ["pits", "Pit stops"], ["last_lap", "Last lap"], ["best_lap", "Best lap"], ["gap", "Gap"],
        ["interval", "Interval"]]),
    ]],
    ["Drivers", [
      ["name_format", "Names", "select", NAME_FORMATS],
      ["finish_flag", "Chequered flag by each driver as they finish the race (a waving flag on a tab at the tower's right edge)", "bool"],
      ["penalty_flags", "Black flag, meatball and slow-down (warning) flags by a driver while iRacing shows them one (on the same tab)", "bool"],
      iff((v) => v.penalty_flags, ["flag_black_bg_color", "Black flag (and DQ) tab colour", "color"]),
      iff((v) => v.penalty_flags, ["flag_meatball_bg_color", "Meatball tab colour", "color"]),
      iff((v) => v.penalty_flags, ["flag_warning_bg_color", "Slow-down (warning) tab colour", "color"]),
      ["show_number", "Car numbers", "bool"],
      iff((v) => v.show_number, ["color_number", "Car number on a coloured background (off: just the number)", "bool"]),
      under("color_number", iff((v) => (v.show_number && v.color_number) || (v.show_stripe && (v.stripe_colors || "same") === "same"),
        ["class_colors", "Car number background colour from", "select", [["main", "The driver's main class"],
        ["secondary", "The driver's category"], ["team", "The driver's team colour (their main class's if the team has none)"]]])),
      ["show_stripe", "Coloured bar by each driver", "bool"],
      iff((v) => v.show_stripe, ["stripe_colors", "Coloured bar's colour from", "select", [["same", "The same as the car number"],
        ["main", "The driver's main class"], ["secondary", "The driver's category"], ["team", "The driver's team colour"]]]),
      ["category_tag", "Driver's category (Pro, Semi-Pro…)", "select", [["off", "Not shown"], ["tag", "A tag after the name (PRO)"],
        ["bar", "A bar in its colour before the name"]]],
      ["show_team", "Team names (a column of their own)", "bool"],
      iff((v) => v.show_team, ["team_name_place", "Team name on the tower", "select", [["under", "Under the driver's name"],
        ["column", "In its own column, after the driver's name"]]]),
      ["show_logo", "Team logos (a column of their own)", "bool"],
      iff((v) => v.show_logo, ["team_logo_side", "Team logo column", "select", [["first", "Before the driver / team name"],
        ["last", "After the driver / team name"]]]),
    ]],
    ["Fastest lap", [
      ["show_fastest_icon", "Purple stopwatch by the fastest lap", "bool"],
      iff((v) => v.show_fastest_icon, ["fastest_icon_for", "Who gets the stopwatch", "select", [
        ["classes", "Each class's fastest, by class and overall"], ["view", "Each class's fastest by class, the overall fastest overall"],
        ["overall", "The overall fastest only"]]]),
      ["fl_flash", "Flash a new fastest lap (top middle)", "bool"],
      iff((v) => v.fl_flash, ["fl_flash_s", "Flash stays for (s; the first 2 say NEW FASTEST LAP)", "number", { min: 3, max: 60, step: 0.5 }]),
      iff((v) => v.fl_flash, ["fl_flash_classes", "Also flash each class's new fastest lap", "bool"]),
      iff((v) => v.fl_flash, ["fl_flash_many", "Several at once (different classes)", "select", [["stack", "Side by side, each for its time"],
        ["queue", "One after another, each in full"]]]),
    ]],
    ["Size, position & background", [
      ["width", "Width in px (0 = automatic: every column fits what's in it)", "number", { min: 0, max: 1400, step: 10 }],
      ["name_width", "Driver name column width in px (0 = automatic; longer names end in …)", "number", { min: 0, max: 600, step: 5 }],
      ["scale", "Size", "size"], LOGO_KIND, LOGO_SIZE, ...OFFSET, ["bg", "Background", "background"],
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
      ["reference", "Sectors compared with (purple: beats it; green: beats their own best; yellow: slower than their own best)", "select",
        [["overall", "Session overall best"], ["session", "Session class best"], ["personal", "Session personal best"],
          ["leader", "The class leader's lap (its sectors)"], ["leader_overall", "The overall leader's lap (its sectors)"]]],
      ["sector_delta_s", "A sector just done: its difference to what it's compared with first, for (s; 0 = just its time)", "number", { min: 0, max: 10, step: 0.5 }],
      ["invalid_text_color", "INVALID (in the lap time's place)", "color"],
      ["invalid_sector_color", "Invalidated sectors", "color"],
      ["invalid_line_color", "The line through an invalidated sector", "color"],
    ]],
    ["Drivers", [
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_number", "Car numbers", "bool"],
      ["show_driver_number", "Driver numbers", "bool"],
      ["show_team", "Team names", "bool"],
      ["show_logo", "Team logos", "bool"],
    ]],
    OVERLAY_LOOK,
  ],
  general: [
    ["Shared by every widget", [
      ["note", "Every widget on these follows them. A widget given its own (on its page) keeps it: \"Use theme\" there puts it back on these.", "note"],
      ["theme_name_format", "Names", "select", NAME_FORMATS],
      ["theme_accent_color", "Accent colour (the tower's header and the boards)", "color"],
      ["theme_team_logo_kind", "Team logo", "select", [["full", "Full logo"], ["small", "Small logo"]]],
      ["theme_bg_opacity", "Panel opacity (%; low lets the race show through)", "number", { min: 0, max: 100, step: 5 }],
    ]],
    ["Board sponsors", [
      ["note", "Set once, for every board: a board shows these unless it's given its own logos (on its page, Logo, banner & sponsors).", "note"],
      ["board_sponsor_list", "Shown on", "boardsponsors"],
      ["board_sponsors", "Where", "select", [["top", "Across the top"], ["bottom", "Across the bottom"], ["left", "Down the left"], ["right", "Down the right"]]],
      ["board_sponsor_ids", "Which sponsors", "sponsors"],
      ["board_sponsor_size", "Sponsor logo size (%; 100 = usual)", "number", { min: 40, max: 250, step: 5 }],
    ]],
    ["Gaps & intervals", [
      ["race_decimals", "Decimal places: live race gaps and intervals (tower, timing screen, Timing tab)", "number", { min: 0, max: 3 }],
      ["qual_decimals", "Decimal places: qualifying, the lap tracker, the grid and results boards", "number", { min: 1, max: 3 }],
    ]],
    ["Font", [
      ["font", "The font every overlay and board uses (its text sized to fit the same room, so nothing changes size)", "select",
        Object.entries(FONTS).map(([id, [name]]) => [id, name])],
    ]],
    ["Names", [
      ["show_pronouns", "Each driver's pronouns after their name, in brackets, e.g. (she/her) (set them in the League builder)", "bool"],
      ["strip_name_numbers", "Leave off a number on the end of a name, e.g. Shamoy Samuel3 → Shamoy Samuel (a driver's second iRacing account; Officials mode too)", "bool"],
    ]],
    ["Pit stops", [
      ["penalty_stops", "Penalties served in the pit lane (a drive-through, a stop-and-go) count as pit stops: the Pits and Stint columns, the live timing website and the pit strategy (untick: only stops in the pit box count)", "bool"],
    ]],
    ["Colours", [
      ["solid_colors", "Class, team and accent colours stay as picked whatever a widget's opacity (untick: they fade with the panels)", "bool"],
    ]],
    ["While a board is on screen", [
      ["board_overlays", "The overlays", "select", [["stay", "Stay as they are"], ["dim", "Dim"], ["hide", "Hide (back when the board goes)"]]],
      iff((v) => v.board_overlays === "dim", ["board_dim", "Dimmed to (% opacity)", "number", { min: 0, max: 90, step: 5 }]),
      ["note", "The sponsors set to stay up are never dimmed or hidden. Each board's own background opacity is in its Size & background.", "note"],
    ]],
  ],
  sponsors: [
    ["Logos", [
      ["sponsor_ids", "Sponsors", "sponsors"],
      ["anchor_id", "Always shown (the others rotate beside it)", "sponsor"],
      iff((v) => !!v.anchor_id, ["anchor_side", "Where it goes", "select", [["first", "First (left, or top)"], ["last", "Last (right, or bottom)"]]]),
      ["stay", "Stay up: not put away with everything else, and not dimmed or hidden under a board (in OBS, put this source above the boards)", "bool"],
      ["layout", "Show", "select", [["rotate", "One at a time"], ["row", "All together"]]],
      iff((v) => v.layout === "rotate", ["interval_s", "Seconds per logo", "number", { min: 1, max: 120, step: 1 }]),
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["size", "Logo height (px)", "number", { min: 30, max: 300, step: 5 }],
      ["title", "Caption above (e.g. Partners)", "text"],
    ]],
    ["Size, position & background", [
      ["background", "Dark panel behind", "bool"],
      ["scale", "Size", "size"], ...OFFSET, ["bg", "Background", "background"],
    ]],
  ],
  gridwalk: [["Drivers' cards", [["name_format", "Names", "select", NAME_FORMATS], ["show_nickname", "Nickname under the name", "bool"],
      ["show_position", "Grid position", "bool"],
      iff((v) => v.show_position, ["position_shown", "Position shown", "select", [["overall", "Overall (P3)"],
        ["class", "In class only (P1, the class under it)"], ["both", "Both (P3, and P1 GT3 under it)"],
        ["class_both", "Both, class first (P1 GT3, and P3 overall under it)"]]]),
      iff((v) => v.show_position && v.position_shown !== "overall", ["pos_class_name", "Class name with the class position (P1 GT3; off: just P1)", "bool"]),
      ["class_colors", "Car number (and card accent) colour from", "select", [["main", "The driver's main class"], ["secondary", "The driver's category"], ["team", "The driver's team colour (their main class's if the team has none)"]]],
      ["show_number", "Car number", "bool"],
      ["show_class", "Class badge by the name", "bool"],
      ["show_team", "Team name", "bool"],
      ["show_logo", "Team logo", "bool"],
      ["show_make", "Car badge", "bool"],
      ["qual_shown", "Qualifying", "select", [["gap", "Gap to the class pole"], ["interval", "Interval to the car ahead in class"],
        ["time", "Lap time"], ["none", "Nothing"]]],
      iff((v) => v.qual_shown !== "none", ["track_qual", "Also painted on the track, under each box's number", "bool"]),
      ["show_status", "NOT ON TRACK / NOT IN SESSION tag", "bool"],
      ["card_scale", "Card size (%; 100 = usual)", "number", { min: 40, max: 200, step: 5 }]]],
    ["Car pictures", [["car_scale", "Car picture size (%; 100 = usual, up to 600)", "number", { min: 40, max: 600, step: 5 }],
      ["car_scale_top", "Top row of cars (P1, P3…): size (% of the above, up to 400)", "number", { min: 40, max: 400, step: 5 }],
      ["car_top_x", "Top row: move right (px; minus moves left)", "number", { min: -1920, max: 1920, step: 5 }],
      ["car_top_y", "Top row: move down (px; minus moves up)", "number", { min: -1080, max: 1080, step: 5 }],
      ["car_top_rotate", "Top row: turn the pictures (degrees; plus is clockwise) to line up with the boxes", "number", { min: -45, max: 45, step: 0.5 }],
      ["car_scale_bottom", "Bottom row of cars (P2, P4…): size (% of the above, up to 400)", "number", { min: 40, max: 400, step: 5 }],
      ["car_bottom_x", "Bottom row: move right (px; minus moves left)", "number", { min: -1920, max: 1920, step: 5 }],
      ["car_bottom_y", "Bottom row: move down (px; minus moves up)", "number", { min: -1080, max: 1080, step: 5 }],
      ["car_bottom_rotate", "Bottom row: turn the pictures (degrees; plus is clockwise)", "number", { min: -45, max: 45, step: 0.5 }],
      ["neighbours", "Cars either side on the grid", "select", [["show", "Show them in their boxes"],
      ["hide", "Hide them: just the pair"]]],
      ["flip_cars", "Flip the car pictures (for pictures of cars pointing left)", "bool"]]], OVERLAY_LOOK],
  pits: [
    ["What it shows", [
      ["who", "Show", "select", [["all", "Every car in the pit lane (the one on camera first)"], ["camera", "Only the car on camera"]]],
      iff((v) => v.who === "all", ["count", "How many drivers at once (the most cards on screen)", "number", { min: 1, max: 12, step: 1 }]),
      ["show_s", "Each driver's card goes after (seconds in the pit lane; 0 = stays until they leave)", "number", { min: 0, max: 300, step: 1 }],
      ["hold_s", "Card stays after they cross the pit exit line, with the final times (seconds; 0 = goes at once)", "number", { min: 0, max: 60, step: 1 }],
      ["race_only", "Races only", "bool"],
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_position", "Position (overall or in class, as the standings tower is)", "bool"],
      ["show_number", "Car number", "bool"],
      ["show_team", "Team name", "bool"],
      ["show_logo", "Team logo", "bool"],
      ["class_colors", "Car number (and card accent) colour from", "select", [["main", "The driver's main class"], ["secondary", "The driver's category"], ["team", "The driver's team colour (their main class's if the team has none)"]]],
    ]],
    OVERLAY_LOOK,
  ],
  duel: [
    ["What it shows", [
      ["auto", "Comes up by itself when someone's within the gap of the driver on camera, and goes when no one is (untick: show and hide it yourself)", "bool"],
      ["gap_s", "Cars within this many seconds of the driver on camera, ahead and behind", "number", { min: 0.1, max: 30, step: 0.1 }],
      ["settle_s", "A car joins (or leaves) once it's been within (or outside) that gap this long (seconds; 0 = at once)", "number", { min: 0, max: 3, step: 0.5 }],
      ["scope", "Cars from", "select", [["class", "Their class only"], ["overall", "Every class (overall)"]]],
      iff((v) => v.auto, ["hold_s", "Stays up after the battle breaks up (seconds)", "number", { min: 0, max: 30, step: 0.5 }]),
      ["ahead", "Most cars ahead of the driver on camera", "number", { min: 0, max: 6, step: 1 }],
      ["behind", "Most cars behind them", "number", { min: 0, max: 6, step: 1 }],
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["title", "Heading (empty: Battle for P3)", "text"],
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_number", "Car numbers (in the class colour)", "bool"],
      ["show_team", "Team names", "bool"],
      ["show_logo", "Team logos", "bool"],
      ["show_interval", "Gaps", "bool"],
      iff((v) => v.show_interval, ["gap_shown", "Each car's gap", "select", [["ahead", "To the car ahead of it"], ["camera", "To the driver on camera (− ahead, + behind)"]]]),
    ]],
    OVERLAY_LOOK,
  ],
  catching: [
    ["What it shows", [
      ["target", "Follows", "select", [["ahead", "The driver on camera and the car ahead"], ["behind", "The driver on camera and the car behind"],
        ["nearest", "The driver on camera and the nearer of the two"], ["picked", "Two cars picked on the Widgets tab"]]],
      iff((v) => v.target !== "picked", ["scope", "The car ahead / behind in", "select", [["class", "Their class"], ["overall", "Every class (overall)"]]]),
      ["trend_laps", "Laps in the trend and the graph", "number", { min: 2, max: 15, step: 1 }],
      ["show_rate", "How fast the gap's changing (s a lap)", "bool"],
      ["show_catch", "Closing: the laps until it's gone (On them in about 4 laps)", "bool"],
      ["show_graph", "The gap lap by lap (a small graph)", "bool"],
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["title", "Heading (empty: Catching / Pulling away / The gap)", "text"],
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_number", "Car numbers (in the class colour)", "bool"],
      ["show_logo", "Team logos", "bool"],
    ]],
    OVERLAY_LOOK,
  ],
  season: [
    ["What it shows", [
      ["note", "It comes up for the driver on camera each time the camera moves to someone (or when you pick a driver), and goes after the time below.", "note"],
      ["hide_s", "Goes after (seconds; 0 = stays until hidden)", "number", { min: 0, max: 120, step: 1 }],
      ["champ", "Stats by", "select", [["class", "By class"], ["overall", "Overall"]]],
      ["note", "By class: their class's championship and class finishes (a class win is a win). Overall: the overall championship and overall finishes. Where the league doesn't score that championship (overall in a class league), it shows the finishes without a championship place or points.", "note"],
      ["show_points", "Points", "bool"],
      ["show_behind", "Points to the leader", "bool"],
      ["show_wins", "Wins", "bool"],
      ["show_podiums", "Podiums", "bool"],
      ["show_best", "Best finish", "bool"],
      ["show_form", "Their last results (P3 · P1 · DNF)", "bool"],
      iff((v) => v.show_form, ["form", "How many", "number", { min: 1, max: 10, step: 1 }]),
      ["show_notes", "Your notes on them (League builder)", "bool"],
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_number", "Car number (in the class colour)", "bool"],
      ["show_team", "Team name", "bool"],
      ["show_logo", "Team logo", "bool"],
    ]],
    OVERLAY_LOOK,
  ],
  h2h: [
    ["What it shows", [
      ["note", "Pick the two drivers on the Widgets tab (or the On camera vs the car ahead button, or its hotkey).", "note"],
      ["champ", "Stats by", "select", [["class", "By class"], ["overall", "Overall"]]],
      ["note", "By class: their class's championship, class finishes and today's class positions (drivers in different classes are compared overall). Overall: the overall championship, finishes and positions. Where the league doesn't score that championship, it shows the finishes without a championship place or points.", "note"],
      ["show_season", "Their seasons (place, points, wins, podiums, best finish, finished ahead)", "bool"],
      ["show_today", "Today (place, best and last lap, the gap between them)", "bool"],
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["title", "Heading (empty: Head to head)", "text"],
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_number", "Car numbers (in the class colour)", "bool"],
      ["show_logo", "Team logos", "bool"],
    ]],
    OVERLAY_LOOK,
  ],
  strategy: [
    ["What it shows", [
      ["order", "Cars in", "select", [["position", "Running order"], ["picked", "The order you picked them"]]],
      ["scale_to", "The lap scale", "select", [["race", "The race's length (in laps), else the laps run so far"], ["so_far", "The laps run so far"]]],
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["panel_width", "Width (px)", "number", { min: 700, max: 1840, step: 10 }],
      ["title", "Heading (empty: Pit strategy)", "text"],
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_position", "Position", "bool"],
      iff((v) => v.show_position, ["position_shown", "Position shown", "select", [["overall", "Overall"], ["class", "In class"]]]),
      ["show_number", "Car numbers", "bool"],
      ["class_colors", "Car number and lap scale colour from", "select", [["main", "The driver's main class"], ["secondary", "The driver's category"], ["team", "The driver's team colour (their main class's if the team has none)"]]],
      ["show_logo", "Team logos", "bool"],
      ["show_stops", "Number of stops", "bool"],
      ["show_stint", "Laps on the current stint", "bool"],
      ["show_penalties", "Penalties served in the pit lane on the scale too (red DT for a drive-through, SG for a stop-and-go); whether they count as stops is in All overlays & boards", "bool"],
    ]],
    OVERLAY_LOOK,
  ],
  lights: [
    ["What it shows", [
      ["visible", "Comes up by itself as a race is about to start (untick: never)", "bool"],
      ["start_from", "The lights count down from", "select", [["all", "iRacing's start lights (standing start), or the leader's run to the line on the lap to the green (rolling start)"],
        ["standing", "iRacing's start lights only (standing starts)"], ["hand", "The Count down button / hotkey only"]]],
      ["lights", "Lights", "number", { min: 3, max: 8, step: 1 }],
      ["step_s", "A light every (seconds)", "number", { min: 0.3, max: 3, step: 0.1 }],
      ["out_s", "Lights out stays (seconds)", "number", { min: 0, max: 10, step: 0.5 }],
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
    ]],
    OVERLAY_LOOK,
  ],
  flags: [
    ["What it shows", [
      ["visible", "Shows while a sector's yellow (untick: never)", "bool"],
      ["flag_sectors", "Sectors in a lap (from the track's split points)", "number", { min: 2, max: 9, step: 1 }],
      ["sc_auto", "Safety car: shows by itself while iRacing has a full course caution (the pace car out)", "bool"],
      ["auto_yellow", "Also by itself: a sector goes yellow while a car's stopped in it (not one that's finished)", "bool"],
      iff((v) => v.auto_yellow, ["hold_s", "A stopped car's sector stays yellow after it gets going (seconds)", "number", { min: 0, max: 60, step: 1 }]),
      ["clear_s", "\"Track Clear\" (green) once the last yellow's cleared, for (seconds; 0 = not shown)", "number", { min: 0, max: 10, step: 0.5 }],
      ["show_map", "The track's outline with the yellow sectors marked", "bool"],
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
    ]],
    OVERLAY_LOOK,
  ],
  trackmap: [
    ["What it shows", [
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["map_size", "Size (px across)", "number", { min: 150, max: 1400, step: 10 }],
      ["colors", "Each car's dot in", "select", [["main", "Their main class colour"], ["secondary", "Their category colour"]]],
      ["labels", "On the dots", "select", [["none", "Nothing"], ["number", "Car number"], ["position", "Position"]]],
      ["dot_size", "Dot size (%)", "number", { min: 40, max: 250, step: 5 }],
      ["camera", "The car on camera bigger, with a white ring", "bool"],
      ["track_color", "Track colour", "color"],
      ["track_width", "Track line thickness (%)", "number", { min: 40, max: 300, step: 10 }],
      ["start_line", "Start / finish line", "bool"],
    ]],
    ["Size & position", [["scale", "Size", "size"], ...OFFSET]],
  ],
  battle: [
    ["What it shows", [
      ["place", "Where", "select", [["top-left", "Top left"], ["top", "Top (centre)"], ["top-right", "Top right"], ["left", "Left (middle)"],
        ["right", "Right (middle)"], ["bottom-left", "Bottom left"], ["bottom", "Bottom (centre)"], ["bottom-right", "Bottom right"]]],
      ["title", "Heading (empty: Championship)", "text"],
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_number", "Car numbers", "bool"],
      ["show_logo", "Team logos", "bool"],
      ["show_team", "Team names", "bool"],
      ["gap_to", "Points gap", "select", [["first", "To the first of them"], ["ahead", "To the driver above"]]],
      ["show_race_points", "During a race: the points this race gives them", "bool"],
      ["show_change", "During a race: places gained / lost in the championship", "bool"],
    ]],
    OVERLAY_LOOK,
  ],
  driver: [
    ["What it shows", [
      ["follow", "Changes to a new driver", "select", [["delay", "With the delay"], ["now", "As the camera cuts"]]],
      ["note", "With the delay: as the Timing Screen and every other overlay (Delay, under ⚙ View there). As the camera cuts: straight away, for a stream that isn't behind.", "note"],
      ["stay", "Stay up for as long as they're on camera", "bool"],
      iff((v) => !v.stay, ["hide_s", "Card stays on screen for (seconds; a new driver resets it)", "number", { min: 1, max: 120, step: 1 }]),
      ["name_format", "Names", "select", NAME_FORMATS],
      ["show_position", "Position (overall)", "bool"],
      iff((v) => v.show_position, ["position_shown", "Position shown", "select", [["overall", "Overall (P3)"],
        ["class", "In class only (P1, the class under it)"], ["both", "Both (P3, and P1 GT3 under it)"]]]),
      iff((v) => v.show_position && v.position_shown !== "overall", ["pos_class_name", "Class name with the class position (P1 GT3; off: just P1)", "bool"]),
      ["class_colors", "Car number (and card accent) colour from", "select", [["main", "The driver's main class"], ["secondary", "The driver's category"], ["team", "The driver's team colour (their main class's if the team has none)"]]],
      ["show_number", "Car number", "bool"],
      ["show_team", "Team", "bool"],
      iff((v) => v.show_team, ["show_logo", "Team logo", "bool"]),
      ["show_tyre", "Tyres by the name (a white dry tyre or a blue wet one)", "bool"],
      ["team_place", "Team logo and car badge", "select", [["under", "Team logo by the team name, car badge at the end"],
        ["end", "Car badge by the team name, team logo at the end"]]],
      ["team_logo_side", "By the team name", "select", [["first", "Logo / badge, then the team name"],
        ["last", "Team name, then the logo / badge"]]],
      ["show_make", "Car badge", "bool"],
      ["show_class", "Class (multiclass)", "bool"],
    ]],
    OVERLAY_LOOK,
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
  resetForms();
  if (ui.snap) render();
}

// The Size setting: a slider, 50-200 %, showing its value as it moves.
function sizeField(v, values = {}) {
  const font = values.font_scale ?? 100;
  return `<label class="ov-field">Size: <span class="rng-val">${v}%</span>
    <input type="range" min="50" max="200" step="5" data-key="scale" data-kind="number" value="${v}"></label>
    <label class="ov-field">Text size (the boxes stay as they are): <span class="rng-val">${font}%</span>
    <input type="range" min="60" max="200" step="5" data-key="font_scale" data-kind="number" value="${font}"></label>`;
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
  // The default look too: low, and the race shows through (a see-through board).
  out.push(`<label class="ov-field">${v.bg === "default" ? "Opacity: everything but the text (low: the race shows through)" : "Opacity: everything but the text"}: <span class="rng-val">${v.bg_opacity}%</span><input type="range" min="0" max="100" step="5" data-key="bg_opacity" data-kind="number" value="${v.bg_opacity}"></label>`);
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
    resetForms();
    toast("Background added");
  } catch (err) {
    toast(err.message, true);
  }
});

// The Theme's Board sponsors: each board's sponsor logos on / off, and which
// of them have logos of their own instead of these (a link to that board).
function boardSponsorList(s) {
  const all = (s.overlays && s.overlays.settings) || {};
  return `<div class="ov-field wide bsp-list">${labelHtml("Shown on (each board can also be switched on its own page)")}<div>${Object.entries(BOARD_SECTION_NAMES).map(([k, name]) => {
    const b = all[k] || {};
    return `<div class="bsp-row"><label class="check"><span class="switch"><input type="checkbox" role="switch" data-bsp="${k}" ${b.sponsor_show ? "checked" : ""}
      aria-label="Sponsor logos on ${esc(name)}"><i aria-hidden="true"></i></span><span>${esc(name)}</span></label>${b.sponsor_show && b.sponsor_mode === "own"
      ? `<button type="button" class="link" data-open-ws="${k}" data-open-ws-section="Logo, banner & sponsors" title="This board shows logos of its own, not these">its own logos</button>` : ""}</div>`;
  }).join("")}</div></div>`;
}
document.addEventListener("change", (e) => {
  const box = e.target.closest("[data-bsp]");
  if (box) cmd("overlay_settings", { overlay: box.dataset.bsp, values: { sponsor_show: box.checked } });
});

// Tick boxes for which of the league's sponsors to show ("" = all, "none" = none).
function sponsorPicker(sponsors, value, key = "sponsor_ids", label = "Sponsors") {
  if (!sponsors.length) return '<p class="hint">No sponsor logos in the active league yet (League builder).</p>';
  const ids = value === "" ? null : new Set(value.split(","));
  return `<div class="ov-field wide sponsor-pick"><span>${esc(label)}</span><div>${sponsors.map((sp, i) => `<label class="check">
    <input type="checkbox" data-key="${key}" data-kind="sponsors" value="${esc(sp.id)}" ${!ids || ids.has(sp.id) ? "checked" : ""}>
    <img src="${esc(sp.url)}" alt="">${esc(sp.name || `Sponsor ${i + 1}`)}</label>`).join("")}</div></div>`;
}

// Tick boxes for which championships (Overall, each class) to show ("" = all,
// "none" = none): the same values as the sponsor picker's.
function groupPicker(groups, value, key, label) {
  if (!groups.length) return '<p class="hint">No championships yet: they appear once the league has results.</p>';
  const ids = value === "" ? null : new Set(value.split(","));
  return `<div class="ov-field wide sponsor-pick"><span>${esc(label)}</span><div>${groups.map((g) => `<label class="check">
    <input type="checkbox" data-key="${key}" data-kind="sponsors" value="${esc(g.key)}" ${!ids || ids.has(g.key) ? "checked" : ""}>
    <span class="dot" style="background:${esc(g.color || "#8b93a3")}"></span>${esc(g.name)}</label>`).join("")}</div></div>`;
}

// A board's own size for each of its sponsor logos ("id:percent,…"; 100 = as
// the sponsor is everywhere, left out): the ones the board shows.
function sponsorScales(s, values, key, label, value) {
  const all = (s.league && s.league.sponsors) || [];
  const general = (s.overlays && s.overlays.settings && s.overlays.settings.general) || {};
  const ids = values.sponsor_mode === "own" ? values.sponsor_ids : general.board_sponsor_ids;
  const shown = ids === "none" ? [] : ids ? all.filter((sp) => ids.split(",").includes(sp.id)) : all;
  if (!shown.length) return "";
  const set = Object.fromEntries(String(value || "").split(",").map((p) => p.split(":")).filter((p) => p.length === 2).map(([k, v]) => [k, +v]));
  return `<div class="ov-field wide sponsor-scales"><span>${esc(label)}</span><div>${shown.map((sp, i) => `<label class="sp-scale">
    <img src="${esc(sp.url)}" alt=""><span>${esc(sp.name || `Sponsor ${i + 1}`)}</span>
    <input type="number" min="20" max="400" step="5" data-key="${key}" data-kind="sponsorscales" data-sponsor-id="${esc(sp.id)}" value="${set[sp.id] ?? 100}" aria-label="Size of ${esc(sp.name || "the sponsor")} on this board (%)">%</label>`).join("")}</div></div>`;
}

// A settings field's new value.
function fieldValue(el) {
  if (el.dataset.kind === "sponsorscales") {
    return [...el.closest(".sponsor-scales").querySelectorAll("input")].filter((i) => +i.value && +i.value !== 100)
      .map((i) => `${i.dataset.sponsorId}:${Math.round(+i.value)}`).join(",");
  }
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

// A setting's label: its name, and what a bracket at its end explains on a
// grey line under it ("Team logo size (%; 100 = usual)": "Team logo size", "%; 100 = usual").
function labelHtml(label) {
  const m = String(label).match(/^([^(]*\S)\s+\(([^()]+(?:\([^()]*\)[^()]*)*)\)$/);
  if (!m || m[1].length < 3) return `<span class="ov-lab">${label}</span>`;
  const hint = m[2].charAt(0).toUpperCase() + m[2].slice(1);
  return `<span class="ov-lab">${m[1]}<small class="ov-hint">${hint}</small></span>`;
}

// A choice of a few short options: buttons side by side (one lit), not a drop-down.
let segUid = 0;
function segmentable(options) {
  return options.length >= 2 && options.length <= 4 && options.every(([, l]) => String(l).length <= 18)
    && options.reduce((n, [, l]) => n + String(l).length, 0) <= 44;
}

// One setting, as its input. `section` is the overlay or board it belongs to.
function fieldHtml(section, values, [k, label, kind, opts], s) {
  const v = values[k];
  const attrs = `data-key="${k}" data-kind="${kind === "banner" || kind === "class" || kind === "sponsor" ? "select" : kind}"`;
  if (kind === "note") return `<p class="hint ov-field wide">${esc(label)}</p>`;
  if (kind === "bsptheme") {
    return `<p class="hint ov-field wide">${esc(label)} <button type="button" class="link" data-open-ws="general" data-open-ws-section="Board sponsors">Theme › Board sponsors</button></p>`;
  }
  if (kind === "boardsponsors") return boardSponsorList(s);
  if (kind === "background") return backgroundFields(section, values);
  if (kind === "size") return sizeField(v, values);
  if (kind === "order") return orderField(k, label, v, opts, values);
  if (kind === "classorder") return classOrderField(k, label, values, s.classes || []);
  if (kind === "colopacity") return opacityField(k, label, v, opts);
  if (kind === "move") {
    const box = (key, a, b) => `<span class="nudge"><button type="button" data-nudge="${key}" data-by="-10" aria-label="${a}">${a === "Left" ? "◀" : "▲"}</button>
      <input type="number" data-key="${key}" data-kind="number" min="${key === "offset_x" ? -1920 : -1080}" max="${key === "offset_x" ? 1920 : 1080}" step="5" value="${values[key] ?? 0}" aria-label="${key === "offset_x" ? "Right" : "Down"} (px)">
      <button type="button" data-nudge="${key}" data-by="10" aria-label="${b}">${b === "Right" ? "▶" : "▼"}</button></span>`;
    return `<div class="ov-field move-field">${labelHtml(label)}<div class="move-ctl">${box("offset_x", "Left", "Right")}${box("offset_y", "Up", "Down")}</div></div>`;
  }
  if (kind === "bool") {
    return `<label class="ov-field check">${labelHtml(label)}<span class="switch"><input type="checkbox" role="switch" ${attrs} ${v ? "checked" : ""}><i aria-hidden="true"></i></span></label>`;
  }
  if (kind === "number") {
    return `<label class="ov-field">${labelHtml(label)}<input type="number" ${attrs} min="${opts.min}" max="${opts.max}" step="${opts.step || 1}" value="${v}"></label>`;
  }
  if (kind === "text") return `<label class="ov-field">${labelHtml(label)}<input ${attrs} value="${esc(v)}" maxlength="40"></label>`;
  if (kind === "sponsors") return sponsorPicker((s.league && s.league.sponsors) || [], v, k, label);
  if (kind === "sponsorscales") return sponsorScales(s, values, k, label, v);
  if (kind === "groups") return groupPicker(((s.board_options || {}).groups) || [], v, k, label);
  if (kind === "color") return `<label class="ov-field">${labelHtml(label)}<input type="color" ${attrs} value="${esc(v)}"></label>`;
  if (kind === "swatches") {
    // Colours from the background image (filled in by fillSwatches once it's loaded).
    return `<div class="ov-field wide swatch-field"><span>${label}</span><div class="swatches" data-swatch-key="${k}"
      data-swatch-img="/api/backgrounds/${encodeURIComponent(values.bg_image)}"></div></div>`;
  }
  if (kind === "class" && values.mode !== "class") return "";
  const options = kind === "sponsor" ? [["", "None"], ...((s.league && s.league.sponsors) || []).map((sp) => [sp.id, sp.name || "Sponsor"])]
    : kind === "class" ? [["", "Every class"], ...(s.classes || []).map((c) => [c.key, c.name])]
    : kind === "banner" ? [["", "The first of the right shape"], ...((s.league && s.league.banners) || []).map((b, i) =>
      [b.id, b.name || `${b.orientation === "vertical" ? "Vertical" : "Horizontal"} banner ${i + 1}`])]
      : opts;
  if (kind === "select" && segmentable(options)) {
    const name = `seg-${section}-${k}-${(segUid += 1)}`;
    return `<div class="ov-field seg-field">${labelHtml(label)}<div class="segs" role="radiogroup">${options.map(([o, l]) =>
      `<label class="${String(o) === String(v) ? "on" : ""}"><input type="radio" name="${name}" ${attrs} value="${esc(o)}" ${String(o) === String(v) ? "checked" : ""}><span>${esc(l)}</span></label>`).join("")}</div></div>`;
  }
  return `<label class="ov-field">${labelHtml(label)}<select ${attrs}>${options.map(([o, l]) =>
    `<option value="${esc(o)}" ${String(o) === String(v) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
}

// The main colours of a background image, to pick an accent colour from:
// the image drawn small, its colours rounded and counted, the most common
// (the colourful ones a little ahead) that differ enough from each other.
const swatchCache = new Map();
function imagePalette(url) {
  if (swatchCache.has(url)) return swatchCache.get(url);
  const done = new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = 80;
      c.height = 45;
      const g = c.getContext("2d");
      g.drawImage(img, 0, 0, c.width, c.height);
      let data;
      try {
        data = g.getImageData(0, 0, c.width, c.height).data;
      } catch (e) {
        return resolve([]);
      }
      const buckets = new Map();
      for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] < 128) continue;
        const key = (data[i] >> 4) << 8 | (data[i + 1] >> 4) << 4 | (data[i + 2] >> 4);
        const b = buckets.get(key) || { n: 0, r: 0, g: 0, b: 0 };
        b.n += 1; b.r += data[i]; b.g += data[i + 1]; b.b += data[i + 2];
        buckets.set(key, b);
      }
      const colours = [...buckets.values()].map((b) => {
        const [r, gg, bb] = [b.r / b.n, b.g / b.n, b.b / b.n];
        const sat = (Math.max(r, gg, bb) - Math.min(r, gg, bb)) / 255;
        return { r, g: gg, b: bb, score: b.n * (0.35 + sat) };
      }).sort((a, b) => b.score - a.score);
      const picked = [];
      for (const col of colours) {
        if (picked.every((p) => Math.hypot(p.r - col.r, p.g - col.g, p.b - col.b) > 60)) picked.push(col);
        if (picked.length === 8) break;
      }
      resolve(picked.map((p) => `#${[p.r, p.g, p.b].map((x) => Math.round(x).toString(16).padStart(2, "0")).join("")}`));
    };
    img.onerror = () => resolve([]);
    img.src = url;
  });
  swatchCache.set(url, done);
  return done;
}

function fillSwatches(root = document) {
  root.querySelectorAll(".swatches[data-swatch-img]:not([data-filled])").forEach(async (el) => {
    el.dataset.filled = "1";
    const colours = await imagePalette(el.dataset.swatchImg);
    el.innerHTML = colours.length ? colours.map((c) => `<button type="button" class="swatch" data-swatch="${c}" style="background:${c}" title="${c}"></button>`).join("")
      : '<span class="hint">No colours found in the image.</span>';
  });
}
new MutationObserver(() => fillSwatches()).observe(document.body, { childList: true, subtree: true });
document.addEventListener("click", (e) => {
  const sw = e.target.closest("[data-swatch]");
  if (!sw) return;
  const form = sw.closest(".ov-form");
  const key = sw.closest("[data-swatch-key]").dataset.swatchKey;
  resetForms();
  cmd("overlay_settings", { overlay: form.dataset.overlay, values: { [key]: sw.dataset.swatch, accent: "color" } }, `Accent colour ${sw.dataset.swatch}`);
});

// A slider for each column's opacity (percent; 100 = as normal).
function opacityField(key, label, value, cols) {
  const set = Object.fromEntries(String(value || "").split(",").map((p) => p.split(":")).filter((p) => p.length === 2).map(([k, v]) => [k, +v]));
  return `<div class="ov-field wide colop-field"><span>${label}</span><div class="colop-grid">${cols.map(([k, name]) => `<label class="colop">
      <span>${esc(name)} <span class="rng-val">${set[k] ?? 100}%</span></span>
      <input type="range" min="0" max="100" step="5" data-key="${key}" data-kind="colopacity" data-opcol="${k}" value="${set[k] ?? 100}"></label>`).join("")}</div></div>`;
}

// A column order: chips to drag, or move with the arrows. ``cols``: [key,
// label, the setting that switches it on (shown dimmed while off)].
function orderField(key, label, value, cols, values) {
  const known = cols.map((c) => c[0]);
  const picked = String(value || "").split(",").filter((k) => known.includes(k));
  const keys = [...picked, ...known.filter((k) => !picked.includes(k))];
  return `<div class="ov-field wide order-field" data-order-key="${key}"><span>${label} <span class="hint">(tick to show, drag or use the arrows to order)</span></span>
    <div class="order-list">${keys.map((k, i) => {
      const [, name, flag] = cols.find((c) => c[0] === k);
      const off = flag && !values[flag];
      return `<span class="order-item ${off ? "off" : ""}" draggable="true" data-col="${k}" title="${off ? "Off: tick it to show it here" : "Drag to move it; untick to hide it"}">
        <button type="button" data-order-move="-1" ${i === 0 ? "disabled" : ""} aria-label="Move earlier">◀</button>
        ${flag ? `<input type="checkbox" data-key="${flag}" data-kind="bool" ${values[flag] ? "checked" : ""} aria-label="Show ${esc(name)}">` : ""}<span>${esc(name)}</span>
        <button type="button" data-order-move="1" ${i === keys.length - 1 ? "disabled" : ""} aria-label="Move later">▶</button></span>`;
    }).join("")}</div></div>`;
}

function saveOrder(field, keys) {
  const form = field.closest(".ov-form");
  resetForms();
  const values = field.dataset.orderKind === "classes" ? classOrderValue(field, keys)
    : { [field.dataset.orderKey]: keys.join(",") };
  cmd("overlay_settings", { overlay: form.dataset.overlay, values });
}

// The tower's classes (by class): every class in the session, a tick box
// each for whether it shows, in the order they're shown (drag or arrows).
// Saved as the ticked ones in order ("" = every class in the league's
// order); picked classes not in this session keep their place at the end.
function classOrderField(key, label, values, classes) {
  if (!classes.length) return '<p class="hint">The classes show here once there are drivers in the session.</p>';
  const known = classes.map((c) => c.key);
  const picked = String(values.class_keys || values.class_key || "").split(",").filter(Boolean);
  const keys = [...picked.filter((k) => known.includes(k)), ...known.filter((k) => !picked.includes(k))];
  const away = picked.filter((k) => !known.includes(k));
  return `<div class="ov-field wide order-field class-order" data-order-key="${key}" data-order-kind="classes"
      data-default="${esc(known.join(","))}" data-away="${esc(away.join(","))}">
    <span>${label} <span class="hint">(tick the ones to show; drag, or use the arrows, to order them)</span></span>
    <div class="order-list">${keys.map((k, i) => {
      const c = classes.find((x) => x.key === k);
      const on = !picked.length || picked.includes(k);
      return `<span class="order-item ${on ? "" : "off"}" draggable="true" data-col="${esc(k)}">
        <button type="button" data-order-move="-1" ${i === 0 ? "disabled" : ""} aria-label="Move earlier">◀</button>
        <label class="check"><input type="checkbox" data-class-show ${on ? "checked" : ""}>
          <span class="dot" style="background:${esc(c.color || "#8b93a3")}"></span>${esc(c.name)}</label>
        <button type="button" data-order-move="1" ${i === keys.length - 1 ? "disabled" : ""} aria-label="Move later">▶</button></span>`;
    }).join("")}</div></div>`;
}

function classOrderValue(field, keys) {
  const on = new Set([...field.querySelectorAll(".order-item")].filter((x) => x.querySelector("[data-class-show]").checked)
    .map((x) => x.dataset.col));
  const away = field.dataset.away ? field.dataset.away.split(",") : [];
  const shown = keys.filter((k) => on.has(k));
  const all = shown.length === keys.length && !away.length && shown.join(",") === field.dataset.default;
  return { class_keys: all ? "" : [...shown, ...away].join(","), class_key: "" };
}

document.addEventListener("change", (e) => {
  const box = e.target.closest && e.target.closest("[data-class-show]");
  if (!box) return;
  const field = box.closest(".order-field");
  // At least one class stays ticked.
  if (!field.querySelector("[data-class-show]:checked")) {
    box.checked = true;
    return;
  }
  box.blur();
  saveOrder(field, [...field.querySelectorAll(".order-item")].map((x) => x.dataset.col));
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-order-move]");
  if (!btn) return;
  const item = btn.closest(".order-item");
  const field = btn.closest(".order-field");
  // Moved here straight away (a second click before the settings come back
  // moves it again, not the old order), then saved.
  const other = +btn.dataset.orderMove < 0 ? item.previousElementSibling : item.nextElementSibling;
  if (!other) return;
  if (+btn.dataset.orderMove < 0) item.parentElement.insertBefore(item, other);
  else item.parentElement.insertBefore(other, item);
  const items = [...field.querySelectorAll(".order-item")];
  items.forEach((x, k) => {
    x.querySelector('[data-order-move="-1"]').disabled = k === 0;
    x.querySelector('[data-order-move="1"]').disabled = k === items.length - 1;
  });
  btn.blur();  // the settings don't redraw while something in them has focus
  saveOrder(field, items.map((x) => x.dataset.col));
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
function settingsHtml(section, values, groups, s, allOpen = false) {
  const top = "visible" in values
    ? `<label class="ov-field check ov-visible"><span class="ov-lab">On stream<small class="ov-hint">Off: hidden everywhere</small></span><span class="switch"><input type="checkbox" role="switch" data-key="visible" data-kind="bool" ${values.visible ? "checked" : ""}><i aria-hidden="true"></i></span></label>` : "";
  return top + groups.map(([title, fields], i) => {
    const id = `${section}/${title}`;
    const open = sectionsOpen[id] ?? (allOpen || i === 0);
    const body = fields.filter((f) => !f.when || f.when(values)).map((f) => (f.section
      ? fieldHtml(f.section, (s.overlays && s.overlays.settings && s.overlays.settings[f.section]) || {}, f, s)
        .replace(/data-key="/, `data-section="${f.section}" data-key="`)
      : fieldHtml(section, values, f, s))).join("");
    return `<details class="ov-group" data-group="${esc(id)}" ${open ? "open" : ""}><summary>${esc(title)}</summary>
      <div class="ov-grid">${body}</div></details>`;
  }).join("");
}

function renderOverlaySettings(s) {
  const ov = s.overlays;
  if (!ov) return;
  $("#tile-overlays").textContent = ov.laps.active ? "Lap tracker live (qualifying)" : `${ov.standings.length} in the standings`;
  renderWidgets(s);
  renderWidgetSettings(s);
  // The Grid walk tab has the grid walk's settings too. Not redrawn under the cursor.
  const key = JSON.stringify([ov.settings.gridwalk]);
  if (key === overlayFormKey || document.activeElement.closest("#ov-gridwalk")) return;
  overlayFormKey = key;
  // Its settings live in Widget Settings (one place for each setting).
  $("#ov-gridwalk").innerHTML = `<div class="ws-sec gw-settings-link"><header><b>Drivers' cards, car pictures, size</b></header>
    <p class="hint">The grid walk's look is set in Widget Settings, with a preview: names, what's on each card, the car pictures' size and angle, the background.</p>
    <p><button type="button" class="btn" data-open-ws="gridwalk">⚙ Grid walk settings</button></p></div>`;
}

// Any settings form (Widget Settings, a widget's card, the Grid walk tab): a
// change is saved straight away.
document.addEventListener("change", (e) => {
  const el = e.target;
  const form = el.closest && el.closest(".ov-form");
  if (!form || !el.dataset.key) return;
  const value = fieldValue(el);
  resetForms();
  el.blur();
  cmd("overlay_settings", { overlay: el.dataset.section || form.dataset.overlay, values: { [el.dataset.key]: value } });
});

// ---------------------------------------------------------------------------
// boards: the full-screen championship, calendar and results screens
// ---------------------------------------------------------------------------

// Where a board's sponsor logos go.
const SPONSOR_PLACES = [["top", "Across the top"], ["bottom", "Across the bottom"], ["left", "Down the left"], ["right", "Down the right"]];

// Every board: the league logo in its header, and a banner where (and which).
const BOARD_BRAND = [["league_logo", "League logo in the header", "bool"],
  ["banner", "Banner", "select", [["none", "None"], ["top", "Across the top"], ["bottom", "Across the bottom"], ["left", "Down the left"],
    ["right", "Down the right"]]],
  iff((v) => v.banner !== "none", ["banner_id", "Which banner", "banner"]),
  ["sponsor_show", "Sponsor logos", "bool"],
  iff((v) => v.sponsor_show, ["sponsor_mode", "Which logos", "select", [["theme", "The boards' sponsors"], ["own", "This board's own"]]]),
  iff((v) => v.sponsor_show && v.sponsor_mode !== "own", ["bsp_theme", "Where, which and how big: set once for every board in", "bsptheme"]),
  iff((v) => v.sponsor_show && v.sponsor_mode === "own", ["sponsors", "Where", "select", SPONSOR_PLACES]),
  iff((v) => v.sponsor_show && v.sponsor_mode === "own", ["sponsor_ids", "Which sponsors", "sponsors"]),
  iff((v) => v.sponsor_show && v.sponsor_mode === "own", ["sponsor_size", "Sponsor logo size (%; 100 = usual)", "number", { min: 40, max: 250, step: 5 }]),
  iff((v) => v.sponsor_show, ["sponsor_scales", "Each sponsor's size on this board (%; 100 = its usual size)", "sponsorscales"]),
  ["page_number", "\"Page 2 / 3\" in the header when it runs to more than one page", "bool"],
  ["show_league", "League name in the header", "bool"],
  ["accent", "Accent colour (the line under the header…)", "select", [["default", "The championship's class colour (else orange)"],
    ["color", "A colour of my own"]]],
  iff((v) => v.accent === "color", ["accent_color", "Accent colour", "color"]),
  iff((v) => v.accent === "color" && v.bg === "image" && v.bg_image, ["accent_color", "Or pick one from the background", "swatches"]),
  iff((v) => !("style" in v), ["podium", "Gold, silver and bronze for places 1–3", "bool"]),
  iff((v) => !("style" in v), ["keep_leader", "The leader at the top of every page (the rest carry on under them)", "bool"])];
const cards = (v) => v.style === "cards";

const BOARD_FIELDS = {
  board_championship: [["rows", "Drivers a page (the rest on the next pages)", "number", { min: 1, max: 64 }], ["name_format", "Names", "select", NAME_FORMATS], ["rounds", "Points from the last N rounds", "number", { min: 0, max: 10 }],
    ["show_number", "Car numbers", "bool"], ["show_team", "Team names (a column)", "bool"], ["show_logo", "Team logos (a column)", "bool"],
    iff((v) => v.show_logo, ["team_logo_side", "Team logo column", "select", [["first", "Before the team name"], ["last", "After the team name"]]]),
    ["show_make", "Car badges", "bool"], ["show_gap", "Points gap to the leader", "bool"],
    ["show_ahead", "Points gap to the driver ahead", "bool"], ["show_wins", "Wins", "bool"],
    ["show_penalty", "Penalty points", "bool"],
    ...columnOpacity([["pos", "Position"], ["number", "Car number"], ["driver", "Driver"], ["team", "Team"], ["logo", "Team logo"], ["car", "Car badge"],
      ["rounds", "Round points"], ["wins", "Wins"], ["penalty", "Penalty points"], ["points", "Points"], ["gap", "Gap to leader"],
      ["ahead", "Gap to driver ahead"]])],
  board_teams: [["rows", "Teams a page (the rest on the next pages)", "number", { min: 1, max: 64 }], ["name_format", "Names of the drivers", "select", NAME_FORMATS], ["rounds", "Points from the last N rounds", "number", { min: 0, max: 10 }],
    ["show_logo", "Team logos (a column)", "bool"], iff((v) => v.show_logo, ["team_logo_side", "Team logo column", "select", [["first", "Before the team name"], ["last", "After the team name"]]]), ["show_color", "Team colour stripe", "bool"], ["show_drivers", "Drivers who scored", "bool"],
    ["show_gap", "Points gap to the leader", "bool"], ["show_ahead", "Points gap to the team ahead", "bool"],
    ["show_wins", "Wins", "bool"], ["show_penalty", "Penalty points", "bool"],
    ...columnOpacity([["pos", "Position"], ["team", "Team"], ["logo", "Team logo"], ["drivers", "Drivers"], ["rounds", "Round points"], ["wins", "Wins"],
      ["penalty", "Penalty points"], ["points", "Points"], ["gap", "Gap to leader"], ["ahead", "Gap to team ahead"]])],
  board_makes: [["rows", "Manufacturers a page (the rest on the next pages)", "number", { min: 1, max: 64 }], ["show_logo", "Badges", "bool"],
    ["show_wins", "Wins", "bool"], ["show_gap", "Gap to the leader", "bool"],
    ...columnOpacity([["pos", "Position"], ["make", "Manufacturer"], ["wins", "Wins"], ["points", "Points"], ["gap", "Gap"]])],
  board_recap: [["note", "The race this app followed (it fills in as the race runs): who gained most, passed most on track and was cleanest, and every car's place lap by lap.", "note"],
    ["title", "Heading (empty: Race recap)", "text"], ["name_format", "Names", "select", NAME_FORMATS],
    ["show_gainer", "Biggest gainer (places gained since the start)", "bool"],
    ["show_overtakes", "Most overtakes (passes on track, from the race log)", "bool"],
    ["show_cleanest", "Cleanest driver (fewest incident points, still running)", "bool"],
    ["show_chart", "Each car's place lap by lap (a chart)", "bool"],
    iff((v) => v.show_chart, ["chart_cars", "Cars in the chart (the best placed first; 0 = every car)", "number", { min: 0, max: 64, step: 1 }])],
  board_track: [["title", "Round line in the header (empty: the league's round this race counts as, e.g. Round 3)", "text"],
    ["units", "Units", "select", [["metric", "Metric (°C, km/h, km)"], ["imperial", "Imperial (°F, mph, mi)"]]],
    ["show_map", "The track's outline in the middle", "bool"],
    ["show_details", "Where it is, its length and turns (under its name)", "bool"],
    ["show_air", "Air temperature", "bool"], ["show_track_temp", "Track temperature", "bool"],
    ["show_wind", "Wind speed and direction", "bool"], ["show_skies", "Conditions (sky, humidity)", "bool"]],
  board_calendar: [["style", "Show", "select", [["cards", "The calendar built from the rounds"], ["image", "The league's own calendar image"]]],
    iff(cards, ["round_title", "Round titles", "select", [["both", "Round 3 · your round name"], ["name", "Your round name"], ["number", "Round 3"]]]),
    iff(cards, ["show_date", "Dates", "bool"]),
    iff((v) => cards(v) && v.show_date, ["date_format", "Dates as", "select", [["weekday_short", "Sun 22 Nov"], ["numeric", "22/11/26"],
      ["day_month", "22nd November"], ["full", "22nd November 2026"], ["weekday", "Sunday 22nd November"]]]),
    iff(cards, ["show_time", "Start times", "bool"]), iff(cards, ["show_config", "Track layouts", "bool"]),
    iff(cards, ["show_length", "Race lengths", "bool"]),
    iff(cards, ["show_race_name", "Each race's name in its box (Sprint, Feature…)", "bool"]),
    iff(cards, ["show_winners", "Winners of past rounds (each class's, under its race)", "bool"]),
    iff((v) => cards(v) && v.show_winners, ["winner_groups", "Winners shown (tick the classes)", "groups"]),
    iff((v) => cards(v) && v.show_winners, ["show_winner_class", "The class name by each winner (Gold: D. Price)", "bool"]),
    iff((v) => cards(v) && v.show_winners, ["winner_name_format", "Winners' names", "select", NAME_FORMATS]),
    iff(cards, ["show_multiplier", "Points multiplier (e.g. ×2 points) on rounds worth more", "bool"]),
    iff(cards, ["rows", "Race meetings a page (the rest on the next pages)", "number", { min: 1, max: 64 }])],
  board_results: [["rows", "Drivers a page (the rest on the next pages)", "number", { min: 1, max: 64 }], ["name_format", "Names", "select", NAME_FORMATS], ["show_gained", "Places gained / lost", "bool"],
    ["show_number", "Car numbers", "bool"], ["show_team", "Team names (a column)", "bool"], ["show_logo", "Team logos (a column)", "bool"],
    iff((v) => v.show_logo, ["team_logo_side", "Team logo column", "select", [["first", "Before the team name"], ["last", "After the team name"]]]),
    ["show_make", "Car badges", "bool"], ["show_laps", "Laps", "bool"], ["show_fastest", "Fastest lap", "bool"],
    ["show_gap", "Gap to the winner (DNF / DNS / DSQ show here)", "bool"],
    ["show_interval", "Interval to the car ahead", "bool"],
    iff((v) => v.show_gap || v.show_interval, ["winner_cell", "The winner's Gap and Int show (everyone else: their gap and interval)", "select",
      [["time", "The time it took them to complete the race (where iRacing gives it; else their laps)"], ["laps", "Laps completed (13 Laps)"]]]),
    ["show_points", "Points scored", "bool"],
    ...columnOpacity([["pos", "Position"], ["gained", "Places gained"], ["number", "Car number"], ["driver", "Driver"], ["team", "Team"], ["logo", "Team logo"],
      ["car", "Car badge"], ["laps", "Laps"], ["fastest", "Fastest lap"], ["gap", "Gap"], ["interval", "Interval"], ["points", "Points"]])],
  board_qualifying: [["rows", "Drivers a page (the rest on the next pages)", "number", { min: 1, max: 64 }], ["name_format", "Names", "select", NAME_FORMATS],
    ["show_number", "Car numbers", "bool"], ["show_team", "Team names (a column)", "bool"], ["show_logo", "Team logos (a column)", "bool"],
    iff((v) => v.show_logo, ["team_logo_side", "Team logo column", "select", [["first", "Before the team name"], ["last", "After the team name"]]]),
    ["show_make", "Car badges", "bool"], ["show_best", "Best lap", "bool"], ["show_gap", "Gap to pole (the class's pole in a class)", "bool"],
    ["show_interval", "Interval to the car ahead", "bool"], ["show_laps", "Laps", "bool"],
    ...columnOpacity([["pos", "Position"], ["number", "Car number"], ["driver", "Driver"], ["team", "Team"], ["logo", "Team logo"],
      ["car", "Car badge"], ["laps", "Laps"], ["best", "Best lap"], ["gap", "Gap"], ["interval", "Interval"]])],
  board_grid: [["grid_source", "The grid from", "select", [["auto", "Automatic: iRacing's grid list for the race (as Apex Overlays), fixed from before anyone's out; without one, heats from qualifying, every race after from the race before's finish"],
      ["qualifying", "Qualifying (its order)"], ["previous", "The previous race's finish"],
      ["gridwalk", "The grid walk's order (as set by hand on the Grid walk tab)"],
      ["current", "As the cars line up on the grid (changes as they're put there)"]]],
    iff((v) => ["auto", "current"].includes(v.grid_source), ["note", "Automatic and \"as the cars line up\" take the grid as iRacing set it (reversed already, if the race is): no reverse is put on top, a race meeting round's Reverse grid included.", "note"]),
    iff((v) => !["auto", "current"].includes(v.grid_source), ["reverse_top", "Reverse grid: the first N turned round (0 = none; a race meeting's round can set its own)", "number", { min: 0, max: 64 }]),
    iff((v) => !["auto", "current"].includes(v.grid_source) && v.reverse_top > 0, ["reverse_in_class", "Reverse the first N of each class (not overall)", "bool"]),
    ["grid_layout", "Layout", "select", [["list", "A list"], ["grid", "As the cars line up (two staggered columns)"]]],
    ["grid_reveal", "Show the drivers", "select", [["all", "All at once (each comes in in turn)"],
      ["rows", "Row by row: the front row first, then Next row (button or hotkey) for each one after"]]],
    iff((v) => v.grid_reveal === "rows", ["grid_scroll", "Row by row, once the screen is full", "select",
      [["page", "A new page (the next set of drivers)"], ["scroll", "Scroll: the top row slides up and off as the next comes in"]]]),
    ["rows", "Drivers on screen at once (fewer: bigger name plates; the rest on the next pages)", "number", { min: 1, max: 64 }],
    ["grid_fill", "Name plates grow to fill the page, however many drivers are on it", "bool"],
    ["grid_size", "Name plate size (%; bigger or smaller by hand)", "number", { min: 50, max: 250, step: 5 }],
    ["name_format", "Names", "select", NAME_FORMATS],
    ["show_class_pos", "Place in class too (on the overall grid)", "bool"],
    ["show_number", "Car numbers", "bool"], ["show_team", "Team names", "bool"], ["show_logo", "Team logos", "bool"],
    iff((v) => v.show_logo && v.grid_layout !== "grid", ["team_logo_side", "Team logo column", "select", [["first", "Before the team name"], ["last", "After the team name"]]]),
    ["show_make", "Car badges", "bool"], ["show_qual", "Qualifying lap", "bool"], ["show_gap", "Gap to the class's fastest qualifier", "bool"],
    ["show_from", "Where they finished the previous race (a grid from it)", "bool"],
    ...columnOpacity([["pos", "Grid place"], ["class_pos", "Place in class"], ["number", "Car number"], ["driver", "Driver"], ["team", "Team"],
      ["logo", "Team logo"], ["car", "Car badge"], ["qual", "Qualifying"], ["gap", "Gap"], ["from", "Finished"]])],
};
const BOARD_SECTION_NAMES = {
  board_championship: "Championship standings", board_teams: "Teams' championship",
  board_makes: "Manufacturers' championship", board_calendar: "Season calendar", board_results: "Finishing order",
  board_qualifying: "Qualifying results", board_grid: "Starting grid", board_track: "Track details", board_recap: "Race recap",
};

let boardButtonsKey = "";
let boardSettingsKey = "";
let boardRound = "latest";
let qualRound = "latest";  // the qualifying board's session ("latest": the latest qualifying)
let gridRound = "next";    // the starting grid board's race ("next": the race on now, else the next one)
// A board's source, by kind: the session or round picked for it.
const boardSource = (kind) => ({ results: boardRound, qualifying: qualRound, grid: gridRound })[kind];

function boardButton(label, kind, group = "", color = null, extra = {}) {
  const b = ui.snap && ui.snap.board;
  const on = b && ui.boardOn && ui.boardOn.kind === kind && ui.boardOn.group === group;
  const key = (settings.actionKeys || {})[`board:${kind}:${group}`];
  return `<button class="btn board-btn ${on ? "on-air" : ""}" data-board="${kind}" data-group="${esc(group)}"
    ${extra.round ? `data-round="${esc(extra.round)}"` : ""} style="${color ? `--cls:${esc(color)}` : ""}">${color ? '<span class="swatch"></span>' : ""}${esc(label)}${key ? `<kbd>${esc(keyLabel(key))}</kbd>` : ""}</button>`;
}

// iRacing's session names ("QUALIFY", "HEAT 1") as words ("Qualify", "Heat 1").
const sessionLabel = (name) => String(name || "").toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase());

function renderBoards(s) {
  const opts = s.board_options || { groups: [], rounds: [] };
  ui.boardOn = s.board ? { kind: s.board.kind, group: s.board.group } : null;
  $("#board-onair").textContent = s.board ? `On screen: ${s.board.title}${s.board.subtitle ? ` · ${s.board.subtitle}` : ""}` : "Nothing on screen";
  $("#btn-board-hide").disabled = !s.board;
  // A board that runs to more than one page: the rest of it, a page at a time.
  const pages = (s.board && s.board.pages) || 1;
  // The starting grid row by row: the next row (or back one, or all of them).
  const rowsOn = !!(s.board && s.board.kind === "grid" && s.board.reveal != null);
  $("#board-reveal").hidden = !rowsOn;
  if (rowsOn) {
    $("#board-rows").textContent = `Row ${s.board.reveal} of ${s.board.reveal_total}`;
    $("#btn-row-prev").disabled = s.board.reveal <= 1;
    $("#btn-row-next").disabled = $("#btn-row-all").disabled = s.board.reveal >= s.board.reveal_total;
  }
  $("#board-pager").hidden = pages < 2;
  if (pages > 1) {
    $("#board-page").textContent = `Page ${s.board.page + 1} of ${pages}`;
    $("#btn-board-prev").disabled = s.board.page === 0;
    $("#btn-board-next").disabled = s.board.page >= pages - 1;
  }
  if (s.officials && s.officials.on && boardRound === "latest") boardRound = "live";  // no championship rounds without a league
  const key = JSON.stringify([opts, s.league && s.league.id, s.officials && s.officials.on, ui.boardOn, boardRound, qualRound, gridRound, !!s.board, settings.actionKeys]);
  if (key !== boardButtonsKey) {
    boardButtonsKey = key;
    const groups = opts.groups;
    const scored = opts.rounds.filter((r) => r.scored);
    const officials = s.officials && s.officials.on;
    $("#board-buttons").innerHTML = officials ? officialBoardsHtml(opts) : !s.league ? '<p class="hint">Activate a league (League builder) to use boards.</p>' : `
      <div class="board-group"><h4>Championship standings<button class="btn subtle icon" data-wsettings="board_championship" title="Its settings">⚙</button></h4>${groups.length ? groups.map((g) => boardButton(g.name, "championship", g.key, g.color)).join("")
        : '<span class="hint">No results yet.</span>'}</div>
      <div class="board-group"><h4>Teams<button class="btn subtle icon" data-wsettings="board_teams" title="Its settings">⚙</button></h4>${opts.teams ? boardButton("Teams' championship", "teams")
        : `<span class="hint">${opts.has_teams ? "No team points yet." : "Give drivers a team in the League builder (Teams tab) for a teams' championship."}</span>`}</div>
      <div class="board-group"><h4>Manufacturers<button class="btn subtle icon" data-wsettings="board_makes" title="Its settings">⚙</button></h4>${groups.map((g) => boardButton(g.name, "makes", g.key, g.color)).join("") || '<span class="hint">No results yet.</span>'}</div>
      <div class="board-group"><h4>Season<button class="btn subtle icon" data-wsettings="board_calendar" title="Its settings">⚙</button></h4>${boardButton("Season calendar", "calendar")}</div>
      <div class="board-group"><h4>Track details<button class="btn subtle icon" data-wsettings="board_track" title="Its settings">⚙</button></h4>${boardButton("Round, track & weather", "track")}</div>
      <div class="board-group"><h4>Race recap<button class="btn subtle icon" data-wsettings="board_recap" title="Its settings">⚙</button></h4>${resultGroups(opts).map((g) => boardButton(g.name, "recap", g.key, g.color)).join("")}</div>
      <div class="board-group"><h4>Finishing order<button class="btn subtle icon" data-wsettings="board_results" title="Its settings">⚙</button></h4>
        <label class="field">From <select id="board-round">
          <option value="latest" ${boardRound === "latest" ? "selected" : ""}>Latest round</option>
          <option value="live" ${boardRound === "live" ? "selected" : ""}>This session (live)</option>
          ${(opts.sessions || []).length ? `<optgroup label="This event in iRacing">${opts.sessions.map((x) => `<option value="${esc(x.source)}"
            ${boardRound === x.source ? "selected" : ""}>${esc(sessionLabel(x.name))}${x.current ? " (on now)" : x.results ? "" : " (no results yet)"}</option>`).join("")}</optgroup>` : ""}
          ${scored.length ? `<optgroup label="Championship rounds">${scored.map((r) => `<option value="${esc(r.id)}" ${boardRound === r.id ? "selected" : ""}>${esc(r.name)}${r.track ? ` · ${esc(r.track)}` : ""}</option>`).join("")}</optgroup>` : ""}
        </select></label>
        <div>${resultGroups(opts).map((g) => boardButton(g.name, "results", g.key, g.color)).join("")}</div></div>
      <div class="board-group"><h4>Qualifying results<button class="btn subtle icon" data-wsettings="board_qualifying" title="Its settings">⚙</button></h4>
        <label class="field">From <select id="board-qual">
          <option value="latest" ${qualRound === "latest" ? "selected" : ""}>The latest qualifying</option>
          ${(opts.sessions || []).filter((x) => x.kind === "qualify").map((x) => `<option value="${esc(x.source)}"
            ${qualRound === x.source ? "selected" : ""}>${esc(sessionLabel(x.name))}${x.current ? " (on now)" : x.results ? "" : " (no results yet)"}</option>`).join("")}
        </select></label>
        <div>${resultGroups(opts).map((g) => boardButton(g.name, "qualifying", g.key, g.color)).join("")}</div></div>
      <div class="board-group"><h4>Starting grid<button class="btn subtle icon" data-wsettings="board_grid" title="Its settings">⚙</button></h4>
        <label class="field">For <select id="board-grid">
          <option value="next" ${gridRound === "next" ? "selected" : ""}>The race on now, else the next one</option>
          ${(opts.sessions || []).filter((x) => x.kind === "race").map((x) => `<option value="${esc(x.source)}"
            ${gridRound === x.source ? "selected" : ""}>${esc(sessionLabel(x.name))}${x.current ? " (on now)" : ""}</option>`).join("")}
        </select></label>
        <div>${resultGroups(opts).map((g) => boardButton(g.name, "grid", g.key, g.color)).join("")}</div></div>`;
  }
}

// Officials mode: the boards that come from the iRacing event (no league).
function officialBoardsHtml(opts) {
  const sessions = opts.sessions || [];
  return `<p class="hint">Officials mode: the boards from the iRacing event (championship boards need a league).</p>
    <div class="board-group"><h4>Track details<button class="btn subtle icon" data-wsettings="board_track" title="Its settings">⚙</button></h4>${boardButton("Round, track & weather", "track")}</div>
    <div class="board-group"><h4>Finishing order<button class="btn subtle icon" data-wsettings="board_results" title="Its settings">⚙</button></h4>
      <label class="field">From <select id="board-round">
        <option value="live" ${boardRound === "live" ? "selected" : ""}>This session (live)</option>
        ${sessions.map((x) => `<option value="${esc(x.source)}" ${boardRound === x.source ? "selected" : ""}>${esc(sessionLabel(x.name))}${x.current ? " (on now)" : x.results ? "" : " (no results yet)"}</option>`).join("")}
      </select></label>
      <div>${resultGroups(opts).map((g) => boardButton(g.name, "results", g.key, g.color)).join("")}</div></div>
    <div class="board-group"><h4>Qualifying results<button class="btn subtle icon" data-wsettings="board_qualifying" title="Its settings">⚙</button></h4>
      <label class="field">From <select id="board-qual">
        <option value="latest" ${qualRound === "latest" ? "selected" : ""}>The latest qualifying</option>
        ${sessions.filter((x) => x.kind === "qualify").map((x) => `<option value="${esc(x.source)}" ${qualRound === x.source ? "selected" : ""}>${esc(sessionLabel(x.name))}</option>`).join("")}
      </select></label>
      <div>${resultGroups(opts).map((g) => boardButton(g.name, "qualifying", g.key, g.color)).join("")}</div></div>
    <div class="board-group"><h4>Starting grid<button class="btn subtle icon" data-wsettings="board_grid" title="Its settings">⚙</button></h4>
      <label class="field">For <select id="board-grid">
        <option value="next" ${gridRound === "next" ? "selected" : ""}>The race on now, else the next one</option>
        ${sessions.filter((x) => x.kind === "race").map((x) => `<option value="${esc(x.source)}" ${gridRound === x.source ? "selected" : ""}>${esc(sessionLabel(x.name))}</option>`).join("")}
      </select></label>
      <div>${resultGroups(opts).map((g) => boardButton(g.name, "grid", g.key, g.color)).join("")}</div></div>`;
}

$("#board-buttons").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-board]");
  if (!b) return;
  const params = { kind: b.dataset.board, group: b.dataset.group || "" };
  if (boardSource(params.kind)) params.round = boardSource(params.kind);
  const r = await cmd("board_show", params);
  if (r) ui.boardOn = { kind: params.kind, group: params.group };
  boardButtonsKey = "";
});
$("#board-buttons").addEventListener("change", (e) => {
  for (const [id, kind] of [["board-qual", "qualifying"], ["board-grid", "grid"]]) {
    if (e.target.id !== id) continue;
    if (kind === "qualifying") qualRound = e.target.value;
    else gridRound = e.target.value;
    if (ui.boardOn && ui.boardOn.kind === kind) cmd("board_show", { kind, group: ui.boardOn.group, round: e.target.value });
  }
  if (e.target.id === "board-round") {
    boardRound = e.target.value;
    // Results already on screen switch to the new source straight away.
    if (ui.boardOn && ui.boardOn.kind === "results") cmd("board_show", { kind: "results", group: ui.boardOn.group, round: boardRound });
  }
});
$("#btn-board-prev").addEventListener("click", () => cmd("board_page", { step: "prev" }));
$("#btn-row-next").addEventListener("click", () => cmd("board_reveal", { step: "next" }));
$("#btn-row-prev").addEventListener("click", () => cmd("board_reveal", { step: "prev" }));
$("#btn-row-all").addEventListener("click", () => cmd("board_reveal", { step: "all" }));
$("#btn-board-next").addEventListener("click", () => cmd("board_page", { step: "next" }));
$("#btn-board-hide").addEventListener("click", async () => {
  await cmd("board_hide");
  ui.boardOn = null;
  boardButtonsKey = "";
});
document.addEventListener("click", (e) => {
  const copy = e.target.closest("[data-copy]");
  if (!copy) return;
  const text = document.getElementById(copy.dataset.copy).textContent;
  navigator.clipboard.writeText(text).then(() => toast("Copied"), () => toast(text));
});

$("#home-obs-url").textContent = `${location.origin}/gridwalk.html`;
loadBackgrounds();

// ---------------------------------------------------------------------------
// widgets: the Widgets tab (each overlay and board on or off, with the
// settings that change most) and Widget Settings (every setting of one)
// ---------------------------------------------------------------------------

// Every widget, in the order they're listed. ``page``: its OBS page;
// ``screen``: it has a full-screen version too.
const WIDGETS = [
  { key: "general", name: "Theme", page: "standings", general: true,
    about: "What every overlay and board shares: names, the accent colour, team logos, panel opacity, the font and decimal places; and what the overlays do while a full-screen board is up." },
  { key: "session_names", name: "Session names", page: "standings", general: true,
    about: "What the tower, the timing screen and every board call each session: your own names for races, qualifying, heats, the consolation and the feature, or a race meeting's round names." },
  { key: "standings", name: "Timing tower", page: "standings", screen: true,
    about: "Race: running order and gap to the leader. Qualifying and practice: fastest clean lap. The full-screen version is a timing screen of its own, with every driver." },
  { key: "laps", name: "Lap tracker", page: "laps", screen: true,
    about: "Qualifying: one big tracker for the car on camera and small ones for the others on a timed lap, with sector colours and the lap time as it lands." },
  { key: "driver", name: "Driver on camera", page: "driver",
    about: "A board at the bottom centre naming the driver the camera is on: position, number, name, team and car. It slides in each time the camera moves to someone." },
  { key: "pits", name: "Pit stops", page: "pits",
    about: "A card for a car in the pit lane: its time since the pit lane entry and its time in its pit box, ticking; after the exit line, its final times for a few seconds." },
  { key: "battle", name: "Championship battle", page: "battle",
    about: "A few drivers fighting for the championship: their place and points (as if the race ended now), what this race gives them and the points between them. Pick them on the Widgets tab." },
  { key: "duel", name: "On-track battle", page: "duel",
    about: "The car on camera and the cars just ahead and behind it, within the gap you pick: \"Battle for P3\", their names and the gaps between them. It can come up by itself whenever there's a battle." },
  { key: "strategy", name: "Pit strategy", page: "strategy",
    about: "A few cars you pick, each with its race so far along a lap scale and a tag at the lap of each pit stop; where it is now (PIT in the pit lane), its stops and the laps on its current stint. Pick the cars on the Widgets tab." },
  { key: "catching", name: "Catching", page: "catching",
    about: "Two cars on track and the gap between them lap by lap: how fast it's closing (or growing) and, closing, how many laps until it's gone. The driver on camera and the car ahead or behind, or two cars you pick." },
  { key: "season", name: "Driver's season", page: "season",
    about: "The driver on camera's season (or a driver you pick): championship place, points, the points to the leader, wins, podiums, best finish and their last few results. It comes up for each new driver and goes after a few seconds." },
  { key: "h2h", name: "Head to head", page: "h2h",
    about: "Two drivers you pick, side by side: their seasons, how often each finished ahead of the other and, in a session, today's places and laps and the gap between them." },
  { key: "trackmap", name: "Track map", page: "trackmap",
    about: "The track's outline with no background and a dot for every car where it is, in its car class or category colour (the live timing website's map)." },
  { key: "lights", name: "Starting lights", page: "lights",
    about: "Red lights counting down to the start, one by one, then lights out at the green. Only on screen as a race is about to start: from iRacing's start lights, the leader's run to the line on a rolling start, or the Count down button." },
  { key: "flags", name: "Flags", page: "flags",
    about: "Not on screen until a sector goes yellow: a waving yellow flag naming them (Sector 1, Sectors 1 & 2, All Sectors), the sectors in a strip and on the track's outline. Set them with the buttons or hotkeys, or let it find stopped cars." },
  { key: "sponsors", name: "Sponsors", page: "sponsors",
    about: "The active league's sponsor logos, in a corner or along an edge: all together, or one at a time." },
  { key: "gridwalk", name: "Grid walk", page: "gridwalk",
    about: "The starting grid on stream, two drivers at a time. Its running order and car pictures are on the Grid walk tab." },
  ...Object.entries(BOARD_SECTION_NAMES).map(([key, name]) => ({ key, name, page: "board", board: true,
    about: "A full-screen board. Put it on screen from the Widgets tab; the preview shows whichever board is on screen." })),
];
const WIDGET = Object.fromEntries(WIDGETS.map((w) => [w.key, w]));

// A widget's settings, in sections.
function widgetGroups(key) {
  return OVERLAY_FIELDS[key] || [["What it shows", BOARD_FIELDS[key]], ["Logo, banner & sponsors", BOARD_BRAND], LOOK];
}

// ---- Widget Settings: the same four tabs on every widget, Essentials first --
// Where each setting goes: by its key, else (a setting shown only while
// another is on) with the one it hangs off, else by its section, else Content.
const WS_TABS = ["Content", "Look", "Position", "Behaviour"];
const WS_TAB_OF = Object.fromEntries(Object.entries({
  Position: ["scale", "offset_x", "offset_y", "width", "name_width", "panel_width", "map_size", "place", "card_scale", "size",
    "grid_size", "grid_fill", "grid_layout"],
  Look: ["font", "solid_colors", "accent", "accent_color", "accent_practice", "accent_qualify", "accent_race", "class_colors",
    "stripe_colors", "show_stripe", "category_tag", "color_number", "team_logo_kind", "logo_scale", "col_opacity_on", "col_bg_color", "col_opacity",
    "flag_black_bg_color", "flag_meatball_bg_color", "flag_warning_bg_color", "invalid_text_color", "invalid_sector_color",
    "invalid_line_color", "track_color", "track_width", "dot_size", "colors", "camera", "background", "bg", "podium", "title_wrap",
    "show_color"],
  Behaviour: ["reveal", "replay_header", "replay_hide_rows", "finish_flag", "penalty_flags", "stay", "hide_s", "show_s", "hold_s",
    "race_only", "auto", "settle_s", "follow", "interval_s", "visible", "start_from", "step_s", "out_s", "auto_yellow", "sc_auto", "clear_s", "practice",
    "sector_delta_s", "grid_reveal", "grid_scroll", "board_overlays", "board_dim", "penalty_stops", "keep_leader"],
  Content: ["neighbours"],
}).flatMap(([tab, keys]) => keys.map((k) => [k, tab])));
const WS_GROUP_TAB = { "Fastest lap": "Behaviour", "Logo, banner & sponsors": "Look", "Car pictures": "Position" };
// The settings most people change: shown first (Show all settings for the rest).
const WS_ESSENTIAL = new Set(["mode", "class_keys", "rows", "rows_class", "name_format", "show_number", "show_team", "show_logo",
  "show_position", "position_shown", "show_gap", "show_interval", "place", "title", "scale", "offset_x", "offset_y", "bg", "accent",
  "accent_color", "league_logo", "banner", "sponsors", "visible", "auto", "stay", "hide_s", "count", "who", "race_only", "style",
  "show_date", "show_winners", "grid_source", "reverse_top", "grid_layout", "grid_reveal", "units", "show_map", "show_air",
  "show_track_temp", "show_wind", "follow", "sponsor_ids", "anchor_id", "sponsor_show", "sponsor_mode", "bsp_theme", "sponsor_scales", "target", "trend_laps", "hide_s", "champ", "show_form", "show_season", "show_today", "show_gainer", "show_overtakes", "show_cleanest", "show_chart", "layout", "size", "sectors", "reference", "practice", "gap_s", "scope",
  "order", "show_stops", "show_penalties", "colors", "labels", "map_size", "start_from", "auto_yellow", "qual_shown", "card_scale",
  "car_scale", "show_points", "show_drivers", "show_wins", "header_info", "column_order", "show_series", "show_track", "sponsor_bar", "show_pos_change",
  "show_pits", "reveal", "replay_header", "fl_flash", "finish_flag", "gap_to", "show_race_points"]);
// The stored values a field of several parts sets (changed / put back as one).
const WS_PARTS = { size: ["scale", "font_scale"], background: ["bg", "bg_color", "bg_image", "bg_opacity"], move: ["offset_x", "offset_y"] };

// A widget's settings as [{tab, title, fields}] (each field also knows its tab).
const wsSectionCache = {};
function wsSections(key) {
  if (wsSectionCache[key]) return wsSectionCache[key];
  const out = [];
  for (const [group, fields] of widgetGroups(key)) {
    let lastTab = null;
    let lastKey = null;
    const placed = fields.map((f) => {
      const tab = WS_TAB_OF[f[0]] || (f.when && lastTab) || WS_GROUP_TAB[group] || "Content";
      if (f.when && !f.parent) f.parent = lastKey;
      if (!f.when) {
        lastTab = tab;
        lastKey = f[0];
      }
      return [tab, f];
    });
    for (const tab of WS_TABS) {
      const mine = placed.filter(([t]) => t === tab).map(([, f]) => f);
      if (!mine.length) continue;
      let title = group;
      if (/^Size/.test(group)) title = tab === "Position" ? (/position/.test(group) ? "Size & position" : "Size") : "Background & logos";
      out.push({ tab, title, group, fields: mine });
    }
  }
  wsSectionCache[key] = out;
  return out;
}

// Every widget's defaults (fetched once), to mark what's been changed and put it back.
let ovDefaults = null;
fetch("/api/overlay-defaults").then((r) => r.json()).then((d) => {
  ovDefaults = d;
  wsKey = liveFormKey = "";
  if (ui.snap && ui.snap.overlays) renderWidgetSettings(ui.snap);
}).catch(() => {});

function wsFieldKeys(f) { return WS_PARTS[f[2]] || [f[0]]; }
function wsChanged(section, values, f) {
  const d = ovDefaults && ovDefaults[f.section || section];
  if (!d || f[2] === "note") return false;
  return wsFieldKeys(f).some((k) => k in d && JSON.stringify(values[k] ?? null) !== JSON.stringify(d[k] ?? null));
}
function wsEssential(key, f) {
  const all = wsSections(key).reduce((n, sec) => n + sec.fields.length, 0);
  return all <= 14 || WS_ESSENTIAL.has(f[0]);
}

let wsTab = "Content";
let wsAll = false;
let wsQuery = "";
let wsReveal = null;  // a setting found by search: shown even among the Essentials
try {
  wsAll = localStorage.getItem("apex.wsAll") === "1";
  wsTab = WS_TABS.includes(localStorage.getItem("apex.wsTab")) ? localStorage.getItem("apex.wsTab") : "Content";
} catch (e) { /* storage unavailable */ }

// One setting in Widget Settings: its input, a dot and ↺ when it's been changed,
// set in from the one it hangs off.
function wsFieldHtml(key, values, f, s, depth = 0) {
  const section = f.section || key;
  const vals = f.section ? ((s.overlays && s.overlays.settings && s.overlays.settings[f.section]) || {}) : values;
  let html = fieldHtml(section, vals, f, s);
  if (f.section) html = html.replace(/data-key="/g, `data-section="${f.section}" data-key="`);
  html = themeMark(section, vals, f, s, html);
  const changed = wsChanged(key, vals, f);
  const cls = [changed ? "changed" : "", depth ? "child" : "", depth > 1 ? "child2" : "", wsReveal === f[0] ? "found" : ""].filter(Boolean).join(" ");
  const reset = changed ? `<button type="button" class="ws-reset" data-ws-reset="${esc(JSON.stringify({ [section]: wsFieldKeys(f) }))}"
    title="Back to how it came" aria-label="Back to how it came">↺</button>` : "";
  // Marked on its first element (a size field is two: both go back together).
  return html.replace(/^(\s*<(\w+))([^>]*?)(?: class="([^"]*)")?([^>]*)>/, (m, open, tag, a1, c, a2) =>
    `${open}${a1} class="${[c, cls].filter(Boolean).join(" ")}" data-field="${f[0]}"${a2}>${reset}`);
}

function wsFormHtml(w, values, s) {
  const secs = wsSections(w.key);
  const show = (f) => (!f.when || f.when(values)) && (wsAll || wsEssential(w.key, f) || wsChanged(w.key, values, f) || wsReveal === f[0]);
  const tabs = WS_TABS.filter((t) => secs.some((sec) => sec.tab === t && sec.fields.some((f) => !f.when || f.when(values))));
  if (!tabs.includes(wsTab)) wsTab = tabs[0];
  const counts = Object.fromEntries(tabs.map((t) => [t, secs.filter((sec) => sec.tab === t).reduce((n, sec) => n + sec.fields.filter(show).length, 0)]));
  const changedIn = (t) => secs.some((sec) => sec.tab === t && sec.fields.some((f) => wsChanged(w.key, values, f)));
  $("#ws-bar").innerHTML = `<div class="ws-tabs" role="tablist">${tabs.map((t) => `<button type="button" role="tab" class="ws-tab ${t === wsTab ? "active" : ""}"
      aria-selected="${t === wsTab}" data-ws-tab="${t}">${t}<span class="n">${counts[t]}</span>${changedIn(t) ? '<i class="dot-changed" title="Changed settings here"></i>' : ""}</button>`).join("")}</div>
    <label class="ws-all">Show all settings <span class="switch"><input type="checkbox" id="ws-all" role="switch" ${wsAll ? "checked" : ""}><i aria-hidden="true"></i></span></label>`;
  const top = "visible" in values
    ? `<label class="ov-field check ov-visible"><span class="ov-lab">On stream<small class="ov-hint">Off: hidden everywhere</small></span><span class="switch"><input type="checkbox" role="switch" data-key="visible" data-kind="bool" ${values.visible ? "checked" : ""}><i aria-hidden="true"></i></span></label>` : "";
  // A column a chip in a shown column order turns on and off: not a switch as well.
  const chips = new Set(secs.flatMap((sec) => sec.fields).filter((f) => f[2] === "order" && show(f))
    .flatMap((f) => f[3].map((c) => c[2]).filter(Boolean)));
  let hidden = 0;
  const body = secs.filter((sec) => sec.tab === wsTab).map((sec) => {
    const fields = sec.fields.filter((f) => (!f.when || f.when(values)) && !chips.has(f[0]));
    const shown = fields.filter(show);
    hidden += fields.length - shown.length;
    if (!shown.length) return "";
    return wsSectionHtml(w.key, values, sec.title, sec.fields, shown, s);
  }).join("");
  return top + body + (!wsAll && hidden ? `<p class="ws-more">${hidden} more on this tab. <button type="button" class="link" data-ws-showall>Show all settings</button></p>` : "")
    + (body ? "" : '<p class="hint">Nothing here for this widget.</p>');
}

// A section of settings: its title, ↺ Reset (its changed settings back to how
// they came), and the settings shown.
function wsSectionHtml(key, values, title, fields, shown, s) {
  const all = s.overlays && s.overlays.settings || {};
  const resets = {};
  for (const f of fields) {
    const section = f.section || key;
    const vals = f.section ? all[f.section] || {} : values;
    if ((!f.when || f.when(values)) && wsChanged(key, vals, f)) (resets[section] = resets[section] || []).push(...wsFieldKeys(f));
  }
  return `<section class="ws-sec"><header><b>${esc(title)}</b>${Object.keys(resets).length
    ? `<button type="button" class="ws-reset-sec" data-ws-reset="${esc(JSON.stringify(resets))}">↺ Reset ${esc(title.toLowerCase())}</button>` : ""}</header>
    <div class="ov-grid">${wsNested(shown).map(([f, depth]) => wsFieldHtml(key, values, f, s, depth)).join("")}</div></section>`;
}

// A settings page with no tabs (Live timing site, Session names…): every
// section open, the same switches, dots and ↺ as Widget Settings.
function plainSettingsHtml(key, values, groups, s) {
  return groups.map(([title, fields]) => {
    const shown = fields.filter((f) => !f.when || f.when(values));
    for (const f of fields) if (f.when && !f.parent) f.parent = fields.slice(0, fields.indexOf(f)).reverse().find((x) => !x.when)?.[0];
    return shown.length ? wsSectionHtml(key, values, title, fields, shown, s) : "";
  }).join("");
}

// Putting settings back to how they came (one, or a section's): {section: [keys]}.
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ws-reset]");
  if (!b || !ovDefaults) return;
  e.preventDefault();
  let what = {};
  try {
    what = JSON.parse(b.dataset.wsReset);
  } catch (err) { return; }
  b.blur();
  resetForms();
  for (const [section, keys] of Object.entries(what)) {
    const d = ovDefaults[section] || {};
    const values = Object.fromEntries(keys.filter((k) => k in d).map((k) => [k, d[k]]));
    if (Object.keys(values).length) cmd("overlay_settings", { overlay: section, values });
  }
});

// A widget's setting the Theme sets (names, team logo, accent colour, panel
// opacity): "Theme" while it follows it, else "Use theme" to put it back on it.
const THEME_OF = { name_format: "name_format", team_logo_kind: "team_logo_kind", accent: "accent_color", bg: "bg_opacity" };
function themeMark(section, vals, f, s, html) {
  const key = THEME_OF[f[0]];
  const general = s.overlays && s.overlays.settings && s.overlays.settings.general;
  if (!key || !general || ["general", "live", "session_names"].includes(section) || !(key in vals)) return html;
  const theme = general[`theme_${key}`];
  const follows = key === "accent_color" ? (vals.accent === "default" && theme === "#ff7a1a") || (vals.accent === "color" && vals.accent_color === theme)
    : vals[key] === theme;
  const tag = follows ? '<em class="theme-tag" title="Set in Theme, for every widget on it">Theme</em>'
    : `<button type="button" class="link theme-use" data-use-theme="${key}" data-use-theme-section="${section}" title="Back on the Theme's (${esc(String(theme))})">Use theme</button>`;
  // In the setting's name (a background: before its first field).
  return html.includes('<span class="ov-lab">') ? html.replace(/(<span class="ov-lab">[^<]*)/, `$1${tag}`) : html.replace(/^(\s*<\w+[^>]*>)/, `$1<span class="theme-line">${tag}</span>`);
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-use-theme]");
  if (!b || !ui.snap) return;
  e.preventDefault();
  const key = b.dataset.useTheme;
  const theme = ui.snap.overlays.settings.general[`theme_${key}`];
  const values = key === "accent_color" ? { accent: theme === "#ff7a1a" ? "default" : "color", accent_color: theme } : { [key]: theme };
  b.blur();
  resetForms();
  cmd("overlay_settings", { overlay: b.dataset.useThemeSection, values });
});

// How far in each setting sits: one step under the one it depends on, when
// that's shown above it in the same section (two at most).
function wsNested(fields) {
  const depth = {};
  return fields.map((f, i) => {
    const up = f.parent && fields.slice(0, i).some((x) => x[0] === f.parent) ? depth[f.parent] + 1 : 0;
    depth[f[0]] = Math.min(up, 2);
    return [f, depth[f[0]]];
  });
}

// Search: every widget's settings, by their names and the line under them.
function wsSearchHtml(q) {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const hits = [];
  for (const w of WIDGETS) {
    for (const sec of wsSections(w.key)) {
      for (const f of sec.fields) {
        if (f[2] === "note") continue;
        const text = `${f[1]} ${sec.title} ${w.name}`.replace(/<[^>]+>/g, "").toLowerCase();
        if (words.every((wd) => text.includes(wd))) hits.push({ w, sec, f });
      }
    }
  }
  const mark = (t) => esc(String(t).replace(/<[^>]+>/g, "")).replace(new RegExp(`(${words.map((wd) => wd.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "ig"), "<mark>$1</mark>");
  $("#ws-bar").innerHTML = `<p class="hint" style="margin:0">${hits.length} setting${hits.length === 1 ? "" : "s"} for “${esc(q)}”</p>`;
  return hits.length ? `<div class="ws-hits">${hits.slice(0, 120).map(({ w, sec, f }) => `<button type="button" class="ws-hit" data-ws-go="${w.key}" data-ws-go-tab="${sec.tab}" data-ws-go-key="${f[0]}">
      <span>${mark(f[1])}</span><small>${esc(w.name)} › ${sec.tab} › ${esc(sec.title)}</small></button>`).join("")}</div>`
    : '<p class="hint">Nothing matches. Try another word, like “colour”, “replay” or “names”.</p>';
}

const WS_KEY = "apex.widgetSettings";
let wsWidget = "standings";
try {
  wsWidget = WIDGET[localStorage.getItem(WS_KEY)] ? localStorage.getItem(WS_KEY) : "standings";
} catch (e) { /* storage unavailable */ }
let wsKey = "";
let wqKey = "";
let wsOpenSection = null;  // a section to open (from a widget's ⚙ Settings)

// Every settings form redraws next time (after a change, so it shows what was saved).
function resetForms() {
  overlayFormKey = wsKey = wqKey = liveFormKey = "";
}

// The quick settings on a widget's card: its fields by key, as in Widget Settings.
function quickFields(section, keys, values, s) {
  const all = widgetGroups(section).flatMap(([, fields]) => fields);
  return keys.map((k) => all.find((f) => f[0] === k)).filter((f) => f && (!f.when || f.when(values)))
    .map((f) => fieldHtml(section, values, f, s)).join("");
}

function renderWidgets(s) {
  const st = s.overlays.settings;
  const gw = s.gridwalk || {};
  // On or off: the Show button lit while it's on.
  for (const card of document.querySelectorAll("#tab-widgets [data-widget]")) {
    const key = card.dataset.widget;
    const on = key === "gridwalk" ? !!gw.visible : key === "fastest" ? !!st.standings.fl_flash : !!(st[key] && st[key].visible);
    card.classList.toggle("on", on);
  }
  $("#wgw-state").textContent = gw.visible ? (gw.running ? "on air" : "paused") : "";
  // The flag card: a button for each sector (lit while it's yellow), and what's showing.
  const fl = s.overlays.flags;
  const yellow = new Set((fl && !fl.clear && fl.sectors) || []);
  const count = (st.flags && st.flags.flag_sectors) || 3;
  const fbtns = $("#wflag-sectors");
  if (fbtns && fbtns.children.length !== count) {
    fbtns.innerHTML = Array.from({ length: count }, (_, i) => `<button class="btn subtle" data-wall="flags:s${i + 1}" title="Sector ${i + 1} yellow / clear">S${i + 1}</button>`).join("");
  }
  if (fbtns) [...fbtns.children].forEach((b, i) => b.classList.toggle("lit", yellow.has(i + 1)));
  const scBtn = $("#wflag-sc");
  if (scBtn) scBtn.classList.toggle("lit", !!(fl && fl.sc));
  $("#wflag-state").textContent = fl ? (fl.clear ? "track clear" : fl.text) : "";
  $("#wlights-state").textContent = s.overlays.lights ? (s.overlays.lights.out ? "lights out" : `${s.overlays.lights.lit} lit`) : "";
  $("#wgw-toggle").textContent = gw.running ? "❚❚ Pause" : "▶ Resume";
  const key = JSON.stringify([st, (s.classes || []).map((c) => [c.key, c.name, c.color])]);
  if (key === wqKey || document.activeElement.closest(".wq") || draggedCol) return;
  wqKey = key;
  for (const form of document.querySelectorAll(".wq")) {
    const section = form.dataset.overlay;
    form.innerHTML = quickFields(section, form.dataset.quick.split(","), st[section], s);
  }
}

function renderWidgetSettings(s) {
  renderWsCopy(s);
  const w = WIDGET[wsWidget];
  const values = s.overlays.settings[w.key] || {};
  const key = JSON.stringify([w.key, values, s.overlays.settings.general, (s.classes || []).map((c) => [c.key, c.name, c.color]),
    (s.league && s.league.sponsors) || [], (s.league && s.league.banners) || [], ((s.board_options || {}).groups || []).length,
    wsTab, wsAll, wsQuery, wsReveal, !!ovDefaults]);
  if (key === wsKey || document.activeElement.closest("#ws-form") || draggedCol) return;
  const changed = !wsKey.startsWith(`["${w.key}"`);
  wsKey = key;
  if (changed) {
    $("#ws-list").innerHTML = [["General", WIDGETS.filter((x) => x.general)], ["Overlays", WIDGETS.filter((x) => !x.board && !x.general)], ["Boards", WIDGETS.filter((x) => x.board)]]
      .map(([title, list]) => `<h5>${title}</h5>${list.map((x) => `<button class="ws-item ${x.key === w.key ? "active" : ""}" data-ws="${x.key}">${esc(x.name)}</button>`).join("")}`).join("");
    $("#ws-title").textContent = w.name;
    $("#ws-about").textContent = w.about;
    const base = `${location.origin}/${w.page}.html`;
    const links = [["Overlay", base, `/${w.page}.html?preview=1`, "Preview ↗"]];
    if (w.screen) links.push(["Full screen", `${base}?screen=1`, `/${w.page}.html?screen=1`, "Open ↗"]);
    if (w.board) links[0] = ["Board", base, `/${w.page}.html?preview=1`, "Open ↗"];
    if (w.general) links.length = 0;
    $("#ws-links").innerHTML = links.map(([kind, url, open, label], i) => `<p class="obs-url"><span class="obs-kind">${kind}</span><code id="ws-url-${i}">${esc(url)}</code>
      <button class="btn subtle" data-copy="ws-url-${i}">Copy</button> <a class="btn subtle" href="${open}" target="_blank" rel="noopener">${label}</a></p>`).join("")
      + (w.general ? "" : '<p class="hint">In OBS: a Browser Source at 1920×1080 (the overlays have a see-through background).</p>');
    const frame = $("#ws-frame");
    const src = `/${w.page}.html?preview=1`;
    if (frame.getAttribute("src") !== src) frame.setAttribute("src", src);
  }
  const form = $("#ws-form");
  form.dataset.overlay = w.key;
  $(".ws-main").classList.toggle("searching", !!wsQuery);
  if (wsQuery) form.innerHTML = wsSearchHtml(wsQuery);
  else if (w.general) {
    // Theme and Session names: short pages, every setting on one page (no tabs).
    $("#ws-bar").innerHTML = "";
    form.innerHTML = plainSettingsHtml(w.key, values, widgetGroups(w.key), s);
  } else form.innerHTML = wsFormHtml(w, values, s);
  if (wsOpenSection) {
    const sec = [...form.querySelectorAll(".ws-sec header b")].find((b) => b.textContent === wsOpenSection);
    if (sec) sec.closest(".ws-sec").scrollIntoView({ block: "start" });
    wsOpenSection = null;
  }
  if (wsReveal) {
    const el = form.querySelector(`[data-field="${wsReveal}"]`);
    if (el) el.scrollIntoView({ block: "center" });
  }
}

// Widget Settings: its tabs, Show all settings, putting settings back, search.
function wsRedraw() {
  wsKey = "";
  if (document.activeElement && document.activeElement.closest("#ws-form")) document.activeElement.blur();
  if (ui.snap && ui.snap.overlays) renderWidgetSettings(ui.snap);
}
function wsSave() {
  try {
    localStorage.setItem("apex.wsAll", wsAll ? "1" : "0");
    localStorage.setItem("apex.wsTab", wsTab);
  } catch (e) { /* storage unavailable */ }
}
$("#tab-widget-settings").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.wsTab) {
    wsTab = b.dataset.wsTab;
    wsReveal = null;
    wsSave();
    return wsRedraw();
  }
  if (b.hasAttribute("data-ws-showall")) {
    wsAll = true;
    wsSave();
    b.blur();
    return wsRedraw();
  }
  if (b.dataset.wsGo) {
    wsQuery = "";
    $("#ws-search").value = "";
    wsWidget = b.dataset.wsGo;
    wsTab = b.dataset.wsGoTab;
    wsReveal = b.dataset.wsGoKey;
    try {
      localStorage.setItem(WS_KEY, wsWidget);
    } catch (err) { /* storage unavailable */ }
    return wsRedraw();
  }
});
$("#tab-widget-settings").addEventListener("change", (e) => {
  if (e.target.id !== "ws-all") return;
  wsAll = e.target.checked;
  wsReveal = null;
  wsSave();
  wsRedraw();
});
$("#ws-search").addEventListener("input", (e) => {
  wsQuery = e.target.value.trim();
  wsRedraw();
});
$("#ws-search").addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    e.target.value = "";
    wsQuery = "";
    wsRedraw();
  }
});

function openWidgetSettings(key, section = null) {
  if (!WIDGET[key]) return;
  wsWidget = key;
  wsQuery = "";
  wsReveal = null;
  if ($("#ws-search")) $("#ws-search").value = "";
  // A section from a widget's card: the tab most of it is on.
  const sec = section && wsSections(key).find((x) => x.group === section);
  if (sec) wsTab = sec.tab;
  wsOpenSection = sec ? sec.title : null;
  wsKey = "";
  try {
    localStorage.setItem(WS_KEY, key);
  } catch (e) { /* storage unavailable */ }
  if (ui.snap && ui.snap.overlays) renderWidgetSettings(ui.snap);
  showPage("widget-settings");
}

// Each league's own widget settings: which league these are, and copying another's.
let wsCopyKey = "";
function renderWsCopy(s) {
  const others = s.overlay_leagues || [];
  const name = (s.league && s.league.name) || "";
  const key = JSON.stringify([others, name]);
  if (key === wsCopyKey) return;
  wsCopyKey = key;
  $("#ws-league-note").textContent = name
    ? `These are ${name}'s widget settings: each league keeps its own, brought in as you pick it.`
    : "Each league keeps its own widget settings, brought in as you pick it (these are for no league).";
  $("#ws-copy").hidden = !others.length;
  $("#ws-copy-league").innerHTML = `<option value="">Copy from another league…</option>${others.map((l) =>
    `<option value="${esc(l.id)}">${esc(l.name)}</option>`).join("")}`;
}
$("#ws-copy-btn").addEventListener("click", async () => {
  const id = $("#ws-copy-league").value;
  if (!id) return toast("Pick the league to copy from", true);
  const from = $("#ws-copy-league").selectedOptions[0].textContent;
  const r = await choose("Copy widget settings", `Every widget's settings from ${from}, in place of these (what's on screen stays as it is).`,
    [["copy", "Copy", true], ["cancel", "Cancel"]]);
  if (!r || r.value !== "copy") return;
  resetForms();
  cmd("overlay_copy_league", { league: id }, `Widget settings copied from ${from}`);
});

$("#ws-list").addEventListener("click", (e) => {
  const item = e.target.closest("[data-ws]");
  if (item) openWidgetSettings(item.dataset.ws);
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest("#tab-widgets button");
  if (!btn) return;
  const d = btn.dataset;
  if (d.wsettings) return openWidgetSettings(d.wsettings, d.wsection || null);
  if (d.wshow || d.whide) {
    const key = d.wshow || d.whide;
    resetForms();
    return cmd("overlay_settings", { overlay: key, values: { visible: !!d.wshow } });
  }
  if (d.wgw) {
    const g = ui.snap && ui.snap.gridwalk;
    const action = { start: "gridwalk_start", prev: "gridwalk_prev", next: "gridwalk_next", hide: "gridwalk_hide",
      toggle: g && g.running ? "gridwalk_pause" : "gridwalk_resume" }[d.wgw];
    return cmd(action, {});
  }
  if (d.wall) return cmd("hotkey", { action: d.wall });
});
// The fastest lap card's Show / Hide: the flash on or off.
for (const [attr, on] of [["wshow", true], ["whide", false]]) {
  const card = $('#tab-widgets [data-widget="fastest"]');
  const btn = document.createElement("button");
  btn.className = "wbtn";
  btn.textContent = on ? "Show" : "Hide";
  btn.addEventListener("click", () => {
    resetForms();
    cmd("overlay_settings", { overlay: "standings", values: { fl_flash: on } });
  });
  btn.dataset.flash = attr;
  let row = card.querySelector(".wbtns");
  if (!row) {
    row = document.createElement("div");
    row.className = "wbtns";
    card.querySelector("h4").after(row);
  }
  row.appendChild(btn);
}

// Each widget card folds away to its title and its Show / Hide (a click on
// the title, or its ▾), kept on this PC; Fold all / Open all at the top. The
// cards are packed down each column (each takes the rows its height needs),
// so a card folded away leaves no space under it, whatever's beside it.
const WFOLD = "apex.widgetsFolded";
const wcards = $("#tab-widgets .wcards");
let wfolded = new Set();
try {
  wfolded = new Set(JSON.parse(localStorage.getItem(WFOLD) || "[]"));
} catch (e) { /* storage unavailable: all open */ }
const saveFolds = () => {
  try {
    localStorage.setItem(WFOLD, JSON.stringify([...wfolded]));
  } catch (e) { /* storage unavailable */ }
};
function foldCard(card, folded) {
  card.classList.toggle("folded", folded);
  const btn = card.querySelector(".wfold");
  btn.setAttribute("aria-expanded", String(!folded));
  btn.title = folded ? "Show its settings" : "Fold away (its Show / Hide stays)";
  if (folded) wfolded.add(card.dataset.widget);
  else wfolded.delete(card.dataset.widget);
}
for (const card of wcards.querySelectorAll(".wcard[data-widget]")) {
  const main = card.querySelector(":scope > .wbtns");
  if (main) main.classList.add("wmain");
  const h4 = card.querySelector("h4");
  h4.insertAdjacentHTML("beforeend", '<button class="wfold" aria-expanded="true" aria-label="Fold away or show this widget\'s settings">▾</button>');
  h4.classList.add("wfold-head");
  foldCard(card, wfolded.has(card.dataset.widget));
}
wcards.addEventListener("click", (e) => {
  const head = e.target.closest(".wfold-head");
  // The title or its ▾ (not another button in the title, like the Grid walk tab link).
  if (!head || (e.target.closest("button, a, select, input") && !e.target.closest(".wfold"))) return;
  const card = head.closest(".wcard");
  foldCard(card, !card.classList.contains("folded"));
  saveFolds();
});
const foldBar = document.createElement("span");
foldBar.className = "row wfold-all";
foldBar.innerHTML = '<button class="btn subtle" data-fold-all="1" title="Fold every widget away to its Show / Hide">Fold all</button>'
  + '<button class="btn subtle" data-fold-all="0" title="Open every widget\'s settings">Open all</button>';
$("#tab-widgets .teams-head [data-open-hotkeys]").before(foldBar);
foldBar.addEventListener("click", (e) => {
  const b = e.target.closest("[data-fold-all]");
  if (!b) return;
  for (const card of wcards.querySelectorAll(".wcard[data-widget]")) foldCard(card, b.dataset.foldAll === "1");
  saveFolds();
});
// Packed down the columns: each card spans as many 1 px rows as it's tall (+ the gap).
const WGAP = 12;
const packCards = () => {
  for (const card of wcards.children) {
    const h = card.getBoundingClientRect().height;
    if (h > 0) card.style.gridRowEnd = `span ${Math.ceil(h) + WGAP}`;
  }
};
if (typeof ResizeObserver === "function") {
  const ro = new ResizeObserver(() => requestAnimationFrame(packCards));
  for (const card of wcards.children) ro.observe(card);
  wcards.classList.add("packed");
}


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
  // Kept by the app (so its hotkeys use it too); an older pick only this PC's browser had, else.
  const picked = ui.snap && ui.snap.desktop && ui.snap.desktop.picked;
  if (picked && picked[tab] != null) n = +picked[tab];
  else {
    try {
      n = +localStorage.getItem(DESK_SCREEN + tab) || 0;
    } catch (e) { /* storage unavailable */ }
  }
  return n < screens.length ? n : 0;
}

let deskMigrated = false;

function renderDesktop(s) {
  const d = s.desktop || { available: false, on_screen: {}, screens: [] };
  if (!deskMigrated && d.available) {
    deskMigrated = true;
    for (const tab of ["overlays", "boards"]) {
      let n = null;
      try {
        n = localStorage.getItem(DESK_SCREEN + tab);
      } catch (e) { /* storage unavailable */ }
      if (n != null && !(d.picked && d.picked[tab] != null)) cmd("desktop_screen", { tab, screen: +n });
    }
  }
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
      ? `<span class="desk-on">● On ${several ? `screen ${on + 1}` : "your screen"}</span><button class="btn subtle" data-desk-hide="${page}" title="Take it off your own screen (the stream isn't changed)">Off my screen</button>`
      : `<button class="btn" data-desk-show="${page}" title="Put it straight on your screen, over the game">Show on my screen</button>`;
  });
  document.querySelectorAll("[data-desk-tab]").forEach((pick) => {
    pick.closest(".desk-screen").hidden = !d.available || !several;
    const n = deskScreen(pick.dataset.deskTab, d.screens);
    pick.innerHTML = d.screens.map((sc, i) =>
      `<option value="${i}" ${n === i ? "selected" : ""}>${esc(screenName(sc, i, d.screens))}</option>`).join("");
  });
  $("#desk-hide-all").hidden = !Object.keys(d.on_screen).length;
  $("#desk-show-all").hidden = !d.available;
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

// Every overlay (or the boards) on screen at once: the Show all button and hotkeys.
async function deskShowAll(group) {
  const r = await cmd("desktop_show_all", { group }, group === "boards" ? "Boards on your screen" : group === "gridwalk" ? "Grid walk on your screen" : "Overlays on your screen");
  if (!r) return;
  let ok = false;
  try {
    ok = localStorage.getItem(DESK_OK) === ui.version;
  } catch (e) { /* storage unavailable */ }
  if (!ok) startDeskCheck(undefined);  // no answer: all of them come down
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
$("#desk-check-no").addEventListener("click", async () => {
  const page = deskCheck && deskCheck.page;
  const method = (ui.snap && ui.snap.desktop && ui.snap.desktop.method) || "auto";
  stopDeskCheck();
  if (method !== "colorkey") {
    // Another way of making them see-through (a colour key), for PCs where
    // the usual one comes up solid: put them up again with it, and ask again.
    const up = Object.keys((ui.snap && ui.snap.desktop && ui.snap.desktop.on_screen) || {});
    await cmd("desktop_method", { method: "colorkey" });
    for (const p of page ? [page] : up) await cmd("desktop_show", { page: p, screen: deskScreen(deskTab(p)) });
    toast("Trying another way of making it see-through…");
    startDeskCheck(page);
    return;
  }
  // Neither way works here: back to the usual one next time, and take it down.
  await cmd("desktop_method", { method: "auto" });
  if (page) cmd("desktop_hide", { page });
  else cmd("desktop_hide", {});
  toast("Removed: on-screen overlays don't work on this PC. Use the OBS or browser link instead.");
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
  cmd("desktop_screen", { tab, screen: +pick.value });  // the app keeps it, for its hotkeys
  // Whatever from this tab is already on screen moves to the screen picked.
  const on = (ui.snap && ui.snap.desktop && ui.snap.desktop.on_screen) || {};
  for (const [page, screen] of Object.entries(on)) {
    if (deskTab(page) === tab && screen !== +pick.value) cmd("desktop_show", { page, screen: +pick.value });
  }
}));
$("#desk-hide-all").addEventListener("click", () => cmd("desktop_hide", {}));
$("#desk-show-all").addEventListener("click", () => deskShowAll("overlays"));

// ---------------------------------------------------------------------------
// eyedropper: a button by every colour box. The system colour picker's own
// eyedropper doesn't work in the app window, so in the app the app reads the
// screen where you next click (pick_color); in a browser, its EyeDropper.
// ---------------------------------------------------------------------------

let dropping = false;

async function pickColor(input) {
  if (dropping) return;
  dropping = true;
  document.body.classList.add("dropping");
  try {
    let color = null;
    const inApp = !!(ui.snap && ui.snap.desktop && ui.snap.desktop.available);
    if (!inApp && window.EyeDropper) {
      try {
        color = (await new window.EyeDropper().open()).sRGBHex;
      } catch (e) { /* cancelled */ }
    } else {
      toast("Click anywhere on your screen to pick its colour (Esc to cancel)");
      const r = await cmd("pick_color", {});
      color = r && r.color;
    }
    if (color && /^#[0-9a-f]{6}$/i.test(color)) {
      input.value = color.toLowerCase();
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      toast(`Picked ${color.toLowerCase()}`);
    }
  } finally {
    dropping = false;
    document.body.classList.remove("dropping");
  }
}

const DROPPER_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M20.7 5.6 18.4 3.3a1 1 0 0 0-1.4 0l-3.1 3.1-1.4-1.4-1.4 1.4 1.4 1.4L4 16.3V20h3.7l8.5-8.5 1.4 1.4 1.4-1.4-1.4-1.4 3.1-3.1a1 1 0 0 0 0-1.4zM6.9 18H6v-.9l8.5-8.5.9.9z"/></svg>';

// Every colour box gets its button, including ones drawn later.
function addDroppers(root = document) {
  root.querySelectorAll('input[type="color"]:not([data-dropper])').forEach((input) => {
    input.dataset.dropper = "1";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn subtle icon dropper";
    b.title = "Pick a colour from the screen";
    b.setAttribute("aria-label", "Pick a colour from the screen");
    b.innerHTML = DROPPER_ICON;
    b.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      pickColor(input);
    });
    input.insertAdjacentElement("afterend", b);
  });
}
addDroppers();
new MutationObserver((list) => {
  for (const m of list) {
    for (const n of m.addedNodes) if (n.nodeType === 1) addDroppers(n.matches && n.matches('input[type="color"]') ? n.parentNode : n);
  }
}).observe(document.body, { childList: true, subtree: true });

// League or Officials: what the overlays and boards use (the top bar's switch).
document.querySelector(".mode-switch").addEventListener("click", (e) => {
  const b = e.target.closest("[data-mode]");
  if (!b) return;
  const want = b.dataset.mode === "officials";
  const off = (ui.snap && ui.snap.officials) || {};
  if (!!off.on === want) return;
  if (!want && !off.league) return toast("Pick a league to use in the League builder (Activate)", true);
  cmd("officials", { on: want }, want ? "Officials: iRacing's own data on screen" : `League: ${off.league}`);
});

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

// A league export: as a new league, or over one already here (the one with
// its name or id picked to start with). The query for the import, or null.
async function leagueImportChoice(file) {
  let inFile = {};
  try {
    inFile = (JSON.parse(await file.text()) || {}).league || {};
  } catch (e) { /* the server says what's wrong with it */ }
  let leagues = ui.leagueList || [];
  try {
    leagues = (await api("/api/leagues")).leagues;
  } catch (e) { /* the list the pickers have */ }
  leagues = [...leagues].sort(byName());
  const name = String(inFile.name || "").trim();
  const match = leagues.find((l) => l.id === inFile.id) || leagues.find((l) => name && l.name.toLowerCase() === name.toLowerCase());
  const html = `<div class="import-pick">
      <label class="check"><input type="radio" name="imp-how" value="new" ${match ? "" : "checked"}> As a new league</label>
      ${leagues.length ? `<label class="check"><input type="radio" name="imp-how" value="replace" ${match ? "checked" : ""}> Replace a league here:</label>
      <select id="imp-replace" aria-label="League to replace">${leagues.map((l) => `<option value="${esc(l.id)}" ${match && l.id === match.id ? "selected" : ""}>${esc(l.name)}</option>`).join("")}</select>
      <p class="hint">Replacing puts the file's classes, drivers, teams, championship, results and logos in place of that league's. It keeps its widget settings. This can't be undone (export it first to keep a copy).</p>` : ""}
    </div>`;
  const r = await choose(`Import ${name || "league"}`, match ? `You already have a league called ${match.name}.` : "Add it as a new league, or put it in place of one you have.",
    [["import", "Import", true], ["cancel", "Cancel"]], html);
  if (!r || r.value !== "import") return null;
  const how = (r.form.querySelector('input[name="imp-how"]:checked') || {}).value;
  if (how !== "replace") return {};
  const id = r.form.querySelector("#imp-replace").value;
  const target = leagues.find((l) => l.id === id);
  if (!confirm(`Replace ${target ? target.name : "that league"} with the league in the file?`)) return null;
  return { replace: id };
}

async function importFile(what, file, round) {
  if (IMPORT_CHECKS[what] && !confirm(IMPORT_CHECKS[what])) return;
  try {
    let league = "", extra = {};
    if (what === "league") {
      extra = await leagueImportChoice(file);
      if (!extra) return;
      if (extra.replace && ui.editing && ui.editing.id === extra.replace && editorUnsaved()) {
        if (!confirm("The league you're replacing has unsaved changes here: they'll be lost. Go on?")) return;
      }
    }
    if (what !== "league" && what !== "overlays") {
      if (!ui.editing) throw new Error("Pick a league first");
      league = (await saveEditor()).id;
      const rd = round && (champData().rounds || []).find((r) => r.id === round);
      if (rd && (rd.results || []).length && !confirm(`Replace the results of ${rd.name} with the ones in the file?`)) return;
    }
    const q = new URLSearchParams({ what, league, round: round || "", ...extra });
    const res = await fetch(`/api/import?${q}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "Import failed");
    const info = data.info || {};
    if (what === "league") {
      await loadLeagues();
      openEditor(data.league);
      showPage("league");
      return toast(info.replaced ? `${data.league.name} replaced with the file's` : `Imported ${data.league.name}`);
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
      resetForms();
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
  const names = { timing: "Timing Screen", widgets: "Widgets", racecontrol: "Race control" };
  document.title = `${names[POPOUT] || POPOUT[0].toUpperCase() + POPOUT.slice(1)} – Apex Commentator`;
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

// The archive (leagues whose championship has ended), open or folded.
let leagueArchiveOpen = false;

function fmtEnded(at) {
  const d = new Date(at);
  return isNaN(d) ? String(at || "").slice(0, 10) : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

async function loadLeagues() {
  try {
    if (!ui.libraryLoaded) {
      ui.library = (await api("/api/logo-library")).logos;
      ui.libraryLoaded = true;
    }
    const { leagues, active } = await api("/api/leagues");
    ui.activeLeague = active;
    const item = (l) => `
      <li data-league="${esc(l.id)}" class="${ui.editing && ui.editing.id === l.id ? "selected" : ""} ${l.ended ? "ended" : ""}">
        <div><div>${l.ended ? '<span title="Championship ended">🏁</span> ' : ""}${esc(l.name)} ${l.active ? '<span class="badge live">ACTIVE</span>' : ""}</div>
        <div class="meta">${l.ended ? `Ended ${esc(fmtEnded(l.ended.at))} · ` : ""}${l.drivers} drivers${l.classes ? ` · ${l.classes} classes` : ""}${l.league_id ? ` · ID ${l.league_id}` : ""}</div></div>
        <button class="btn icon" data-duplicate="${esc(l.id)}" title="Duplicate: a copy of this league (drivers, classes, teams, championship, images) to change">⧉</button>
        <button class="btn icon danger" data-delete="${esc(l.id)}" title="Delete">✕</button>
      </li>`;
    const running = leagues.filter((l) => !l.ended);
    const archived = leagues.filter((l) => l.ended);
    if (ui.editing && archived.some((l) => l.id === ui.editing.id)) leagueArchiveOpen = true;
    $("#league-list").innerHTML = (running.length ? running.map(item).join("") : `<li class="meta">${archived.length ? "No running leagues" : "No saved leagues yet"}</li>`)
      + (archived.length ? `<li class="archive-head"><button class="btn subtle" data-archive-toggle aria-expanded="${leagueArchiveOpen}"
          title="Leagues whose championship has ended: locked, kept to look back on and to copy settings from">${leagueArchiveOpen ? "▾" : "▸"} Archive
          <span class="count">${archived.length}</span></button></li>${leagueArchiveOpen ? archived.map(item).join("") : ""}` : "");
  } catch (e) {
    toast(e.message, true);
  }
}

function openEditor(profile) {
  ui.editing = profile;
  $("#league-editor").hidden = false;
  $("#edit-name").value = profile.name || "";
  $("#edit-strip-class").checked = !!profile.strip_class_prefix;
  $("#edit-hide-unclassed").checked = profile.hide_unclassed !== false;
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
  lockEditor(profile);
}

// A league whose championship has ended is locked: its tabs can be looked
// through but not changed (the app refuses changes too), until it's reopened.
function lockEditor(profile) {
  const ended = !!(profile && profile.ended);
  const ed = $("#league-editor");
  ed.classList.toggle("locked", ended);
  ed.querySelectorAll(".ltab").forEach((p) => { p.inert = ended; });
  $("#edit-name").disabled = ended;
  $("#btn-end-league").hidden = ended || !profile.id;
  $("#btn-copy-settings").disabled = ended;
  const banner = $("#league-ended");
  banner.hidden = !ended;
  banner.innerHTML = ended ? `<span>🏁 <b>Championship ended</b> ${esc(fmtEnded(profile.ended.at))}. It's locked as it ended (results,
      standings, drivers and settings) and kept in the Archive. Its standings can still go on the boards, and other leagues can
      copy its settings.</span>
    <span class="row"><button class="btn" data-league-next>Start the next season from it</button>
      <button class="btn subtle" data-league-reopen title="Unlock it to change it again">Reopen</button></span>` : "";
}

$("#league-ended").addEventListener("click", async (e) => {
  const p = ui.editing;
  if (!p || !p.id) return;
  try {
    if (e.target.closest("[data-league-reopen]")) {
      if (!confirm(`Reopen ${p.name}? It's unlocked and back with the running leagues.`)) return;
      const r = await api(`/api/leagues/${encodeURIComponent(p.id)}/reopen`, { method: "POST", body: {} });
      openEditor(r.league);
      await loadLeagues();
      return toast(`${r.league.name} reopened`);
    }
    if (e.target.closest("[data-league-next]")) {
      const name = prompt("Name of the new season's league", p.name.replace(/\d+(?!.*\d)/, (n) => String(+n + 1)) === p.name ? `${p.name} (next season)` : p.name.replace(/\d+(?!.*\d)/, (n) => String(+n + 1)));
      if (!name) return;
      const r = await api(`/api/leagues/${encodeURIComponent(p.id)}/duplicate`, { method: "POST", body: { name } });
      // The new season: everything but last season's results and penalties.
      const next = r.league;
      next.championship = next.championship || {};
      next.championship.rounds = (next.championship.rounds || []).map((rd) => ({ ...rd, results: [], session: "" }));
      next.championship.penalties = [];
      next.championship.live_round = "";
      const saved = await api("/api/leagues", { method: "POST", body: next });
      await loadLeagues();
      openEditor(saved.league);
      return toast(`Made ${saved.league.name}: the same drivers, classes, teams and rules, no results yet`);
    }
  } catch (err) {
    toast(err.message, true);
  }
});

$("#btn-end-league").addEventListener("click", async () => {
  const p = ui.editing;
  if (!p || !p.id) return;
  if (!confirm(`End ${p.name}'s championship? It's locked as it stands (results, standings, drivers and settings) and moved `
    + "to the Archive. You can still look at it, show its standings and copy its settings, and reopen it if you need to.")) return;
  try {
    if (editorUnsaved()) await saveEditor();
    const r = await api(`/api/leagues/${encodeURIComponent(p.id)}/end`, { method: "POST", body: {} });
    leagueArchiveOpen = true;
    openEditor(r.league);
    await loadLeagues();
    toast(`${r.league.name}'s championship has ended: it's in the Archive`);
  } catch (err) {
    toast(err.message, true);
  }
});

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

// Drivers ticked in the list (to set their category together), and the
// "No category" filter. Ticks are the driver objects, so sorting keeps them.
let rosterTicks = new Set();
let rosterNoCat = false;
let rosterLastTick = null;

const ROSTER_FIELDS = [["name", ""], ["cust_id", "c-id"], ["car_number", "c-num"], ["driver_number", "c-num"], ["nickname", ""], ["pronouns", "c-pron"], ["team", ""], ["notes", ""]];

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
  const raced = new Set(allResults().map((r) => r.driver));
  rosterTicks = new Set([...rosterTicks].filter((d) => drivers.includes(d)));
  const noCat = (d) => !second.some((c) => c.id === d.class2_id);
  if (!second.length) rosterNoCat = false;
  const shown = rosterOrder(drivers, classes).filter(([d]) => !rosterNoCat || noCat(d));
  const tagged = second.some((c) => c.name_tag);
  const missing = second.length ? drivers.filter(noCat).length : 0;
  $("#roster-tools").innerHTML = (second.length ? `<button class="chip ${rosterNoCat ? "active" : ""}" data-roster-nocat
      title="Only the drivers with no category yet">No category <span class="count">${missing}</span></button>` : "")
    + (rosterTicks.size ? `<div class="roster-bulk"><b>${rosterTicks.size} ticked</b>
      ${second.length ? `<span class="label">Set category:</span>${second.map((c) => `<button class="btn subtle" data-bulk-cat="${esc(c.id)}">${esc(c.name || "Unnamed")}</button>`).join("")}
        <button class="btn subtle" data-bulk-cat="${tagged ? "-" : ""}">None</button>`
        : '<span class="label">Add categories (Pro, Am…) in the Classes tab to set them for these drivers together.</span>'}
      <button class="btn subtle" data-bulk-untick>Untick all</button>
      <span class="label">Shift-click to tick a run of drivers</span></div>` : "");
  $("#roster-tick-all").checked = !!shown.length && shown.every(([d]) => rosterTicks.has(d));
  $("#roster-rows").innerHTML = shown.map(([d, i]) => `<tr class="${rosterTicks.has(d) ? "ticked" : ""}"><td class="c-tick"><input type="checkbox" data-tick="${i}" ${rosterTicks.has(d) ? "checked" : ""} aria-label="Tick ${esc(d.name || "driver")}"></td>${ROSTER_FIELDS.map(([f]) =>
    f === "team" && raced.has(driverKey(d))
      ? `<td><div class="team-cell"><input data-row="${i}" data-field="${f}" value="${esc(d[f] ?? "")}" aria-label="${f}"><button class="btn subtle icon" data-team-history="${i}" title="Teams by race: which team each of their races counts for">⇄</button></div></td>`
      : `<td><input data-row="${i}" data-field="${f}" value="${esc(d[f] ?? "")}" aria-label="${f}"${f === "pronouns" ? ' placeholder="e.g. she/her"' : ""}></td>`).join("")}
    <td><select data-row="${i}" data-field="class_id" aria-label="Class"><option value="">Auto (by car)</option><option value="-" ${d.class_id === "-" ? "selected" : ""} title="No car class: just the category, if any">—</option>${options(main, d.class_id || "")}</select></td>
    <td class="c-class2"><select data-row="${i}" data-field="class2_id" aria-label="Category"><option value="" title="${tagged ? "By the tag in front of their name, if it's a category's name tag" : "No category"}">${tagged ? "Auto (name tag)" : "—"}</option>${tagged ? `<option value="-" ${d.class2_id === "-" ? "selected" : ""} title="No category, whatever their name tag">None</option>` : ""}${options(second, d.class2_id || "")}</select></td>
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
      <label class="sponsor-scale" title="How big this logo is drawn next to the others, everywhere (sponsors overlay, tower bar, boards): 100 = as the others">Size
        <input type="number" data-sponsor-scale="${i}" min="40" max="250" step="5" value="${esc(sp.scale || 100)}" aria-label="Logo size (%)">%</label>
      <span class="sponsor-move">
        <button class="btn icon" data-sponsor-move="${i}" data-dir="-1" ${i ? "" : "disabled"} title="Earlier (shown first)">◀</button>
        <button class="btn icon" data-sponsor-move="${i}" data-dir="1" ${i < list.length - 1 ? "" : "disabled"} title="Later">▶</button>
      </span>
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
  const scale = e.target.closest("[data-sponsor-scale]");
  if (scale) ui.editing.sponsors[+scale.dataset.sponsorScale].scale = Math.min(250, Math.max(40, Math.round(+scale.value || 100)));
});
$("#sponsor-list").addEventListener("click", (e) => {
  const mv = e.target.closest("[data-sponsor-move]");
  if (mv) {
    // The order they're shown in, everywhere: boards, the sponsors overlay, the tower's sponsor bar.
    const list = ui.editing.sponsors;
    const i = +mv.dataset.sponsorMove;
    const j = i + +mv.dataset.dir;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    renderSponsors();
    toast("Moved: save the league to keep the order");
    return;
  }
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
      [...leagues].sort(byName()).map((l) => `<option value="${esc(l.id)}" ${l.id === current ? "selected" : ""}>${esc(l.name)}${l.active ? " (active)" : ""}</option>`).join("");
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

// -- arrow keys between the boxes (roster, classes, team cards) -------------
// The arrow keys move to the nearest box in that direction: up and down to
// the same field in the row (or card) above or below, left and right along
// the row. As in a spreadsheet, a box's text is selected on arrival, so left
// and right go straight on; once you click in it or type, they move through
// the text, and on to the next box from its start or end.

const NAV_FIELDS = "input:not([type=file]):not([type=hidden]):not([type=checkbox]), select";
const TEXTUAL = new Set(["text", "search", "number", "email", "url", "tel", ""]);

function nearestField(container, el, key) {
  const a = el.getBoundingClientRect();
  const ax = a.left + a.width / 2;
  const ay = a.top + a.height / 2;
  let best = null;
  let bestScore = Infinity;
  for (const f of container.querySelectorAll(NAV_FIELDS)) {
    if (f === el || f.disabled || !f.offsetParent) continue;
    const b = f.getBoundingClientRect();
    const dx = b.left + b.width / 2 - ax;
    const dy = b.top + b.height / 2 - ay;
    let score;
    if (key === "ArrowDown" || key === "ArrowUp") {
      const ahead = key === "ArrowDown" ? dy : -dy;
      if (ahead < a.height / 2) continue;
      score = ahead + 3 * Math.abs(dx);
    } else {
      const ahead = key === "ArrowRight" ? dx : -dx;
      if (ahead < 4 || Math.abs(dy) > a.height) continue;
      score = ahead + 6 * Math.abs(dy);
    }
    if (score < bestScore) {
      bestScore = score;
      best = f;
    }
  }
  return best;
}

function arrowNav(container) {
  container.addEventListener("keydown", (e) => {
    if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key) || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    const el = e.target;
    if (!el.matches || !el.matches(NAV_FIELDS)) return;
    const textual = el.tagName === "INPUT" && TEXTUAL.has(el.type) && el.type !== "number";
    if (textual && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      // All of it selected (just arrived, as in a spreadsheet): straight on. Else from the end of the text.
      const all = el.selectionStart === 0 && el.selectionEnd === el.value.length;
      const atStart = all || (el.selectionStart === 0 && el.selectionEnd === 0);
      const atEnd = all || (el.selectionStart === el.value.length && el.selectionEnd === el.value.length);
      if ((e.key === "ArrowLeft" && !atStart) || (e.key === "ArrowRight" && !atEnd)) return;
    }
    const next = nearestField(container, el, e.key);
    if (!next) return;
    e.preventDefault();
    e.stopPropagation();
    next.focus();
    if (next.tagName === "INPUT" && TEXTUAL.has(next.type) && next.type !== "number") next.select();
  });
}
["#roster-rows", "#class-list", "#team-cards"].forEach((sel) => { if ($(sel)) arrowNav($(sel)); });

// -- drivers, teams and classes from a spreadsheet (csvimport.py) ----------

const CSV_FIELDS = [["cust_id", "iRacing (customer) ID"], ["name", "Full name"], ["first", "First name"], ["last", "Last name"],
  ["number", "Car number"], ["team", "Team"], ["team_color", "Team colour"], ["class", "Class"], ["nickname", "Nickname"]];
let csvText = "";
let csvPreview = null;

document.addEventListener("change", async (e) => {
  const input = e.target.closest && e.target.closest("[data-csv]");
  if (!input || !input.files.length) return;
  const file = input.files[0];
  input.value = "";
  if (!ui.editing) return toast("Open a league first (League builder)", true);
  try {
    csvText = await file.text();
    csvPreview = await api("/api/csv/preview", { method: "POST", body: { text: csvText } });
    openCsv(csvPreview);
  } catch (err) {
    toast(err.message, true);
  }
});

function openCsv(p) {
  const first = p.sample[0] || [];
  $("#csv-count").textContent = `${p.rows} row${p.rows === 1 ? "" : "s"} in the sheet, going into ${ui.editing.name || "this league"}.`;
  $("#csv-map").innerHTML = CSV_FIELDS.map(([f, label]) => `<label class="ov-field">${esc(label)}<select data-csv-field="${f}">
    <option value="">— not in the sheet —</option>${p.headers.map((h, i) => `<option value="${i}" ${p.mapping[f] === i ? "selected" : ""}>${esc(h || `Column ${i + 1}`)}${first[i] ? ` (e.g. ${esc(first[i].slice(0, 24))})` : ""}</option>`).join("")}
  </select></label>`).join("");
  const hasSecondary = (ui.editing.classes || []).some((c) => c.role === "secondary");
  $("#csv-role").value = hasSecondary ? "secondary" : "main";
  $("#csv-classes").textContent = p.classes.length ? `Classes in the sheet: ${p.classes.join(", ")}.` : "";
  $("#csv-modal").hidden = false;
}

$("#csv-cancel").addEventListener("click", () => { $("#csv-modal").hidden = true; });
$("#csv-go").addEventListener("click", async () => {
  const mapping = {};
  document.querySelectorAll("[data-csv-field]").forEach((sel) => {
    if (sel.value !== "") mapping[sel.dataset.csvField] = +sel.value;
  });
  if (mapping.name == null && mapping.first == null && mapping.cust_id == null) return toast("Pick the column with the names or iRacing IDs", true);
  try {
    const saved = await saveEditor();
    const r = await api(`/api/leagues/${encodeURIComponent(saved.id)}/import-csv`, {
      method: "POST", body: { text: csvText, mapping: Object.keys(mapping).length ? mapping : { name: -1 }, class_role: $("#csv-role").value },
    });
    $("#csv-modal").hidden = true;
    openEditor(r.league);
    const m = r.summary;
    toast(`${m.added} added, ${m.updated} updated${m.teams ? `, ${m.teams} new team${m.teams === 1 ? "" : "s"}` : ""}${m.classes ? `, ${m.classes} new class${m.classes === 1 ? "" : "es"}` : ""}`);
  } catch (err) {
    toast(err.message, true);
  }
});

async function openLeague(id) {
  const league = await api(`/api/leagues/${encodeURIComponent(id)}`);
  openEditor(league);
  for (const sel of document.querySelectorAll(".league-picker")) sel.value = league.id;
}

// Each team's "Also in" list folds to a count; which are open is kept while
// the page is redrawn.
const teamShareOpen = new Set();

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
    const others = drivers.map((d, j) => [d, j]).filter(([d]) => !sameTeam(d.team, t.name)).sort(byName(([d]) => d.name));
    return `<div class="team-card" style="--team:${esc(t.color || "#3a4150")}">
      <div class="team-card-head">
        <div class="team-logos">
          <label class="team-logo big" title="${t.logo ? "Replace the full logo" : "Upload the full logo"}">
            ${t.logo ? `<img src="${esc(logoSrc(t.logo))}" alt="">` : "+ Full logo"}
            <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-team-logo="${i}" hidden>
          </label>
          <label class="team-logo small" title="${t.logo_small ? "Replace the small logo" : "Upload a small logo (a badge or icon): overlays and boards can be set to show it instead"}">
            ${t.logo_small ? `<img src="${esc(logoSrc(t.logo_small))}" alt="">` : "+ Small"}
            <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-team-logo-small="${i}" hidden>
          </label>
        </div>
        <div class="team-fields">
          <input data-team="${i}" data-key="name" value="${esc(t.name)}" placeholder="Team name" aria-label="Team name">
          <div class="row">
            <input data-team="${i}" data-key="short" class="narrow" maxlength="8" value="${esc(t.short || "")}" placeholder="Short" aria-label="Short name">
            <input type="color" data-team="${i}" data-key="color" value="${esc(t.color || "#3a4150")}" aria-label="Team colour" title="Team colour">
            ${t.color ? `<button class="btn subtle" data-team-nocolor="${i}" title="Use the class colour instead">No colour</button>` : ""}
            ${t.logo ? `<button class="btn subtle" data-team-nologo="${i}">Remove full logo</button>` : ""}
            ${t.logo_small ? `<button class="btn subtle" data-team-nologo-small="${i}">Remove small logo</button>` : ""}
            <button class="btn icon danger" data-team-delete="${i}" title="Delete team">✕</button>
          </div>
          <label class="check small" title="Its drivers still score for themselves; the team just isn't in the team championship (standings, boards).">
            <input type="checkbox" data-team="${i}" data-key="no_standings" ${t.no_standings ? "checked" : ""}> Leave out of the team standings</label>
        </div>
      </div>
      <div class="chips team-members">${members.map(([d, j]) => `<span class="chip">${label(d)}
        <button class="clear" data-team-unassign="${j}" title="Take out of the team">✕</button></span>`).join("") || '<span class="hint">No drivers yet</span>'}</div>
      <select data-team-add="${i}" aria-label="Add a driver to ${esc(t.name)}">
        <option value="">+ Add driver…</option>
        ${others.map(([d, j]) => `<option value="${j}">${label(d)}${d.team ? ` (${esc(d.team)})` : ""}</option>`).join("")}
      </select>
      ${otherLeagues.length ? `<details class="team-shared-box" data-team-name="${esc(t.name)}" ${teamShareOpen.has(t.name) ? "open" : ""}>
        <summary title="The other leagues this team is in (open to change)">Also in ${(t.shared || []).filter((id) => otherLeagues.some((l) => l.id === id)).length} of ${otherLeagues.length} leagues</summary>
        <div class="team-shared"><span class="hint" title="Tick a league to put the team, and its drivers who race there too, in that league as well (drivers who join it later are put in the team by themselves). ✕ takes the team out of that league.">Tick to add:</span>
        ${otherLeagues.map((l) => {
    const on = (t.shared || []).includes(l.id);
    return `<label class="chip ${on ? "active" : ""}" title="${on ? `Untick: stop keeping ${esc(l.name)}'s copy in step` : `Tick: put the team in ${esc(l.name)} too`}">
          <input type="checkbox" data-team-share="${i}" value="${esc(l.id)}" ${on ? "checked" : ""} hidden>${esc(l.name)}${on
    ? `<button class="clear" data-team-remove-from="${esc(l.id)}" data-team-i="${i}" title="Take ${esc(t.name)} out of ${esc(l.name)}">✕</button>` : ""}</label>`;
  }).join("")}</div></details>` : ""}
    </div>`;
  }).join("") : '<p class="hint">No teams yet: add one, or fill in the Team column in the League builder roster.</p>';
  const free = drivers.map((d, j) => [d, j]).filter(([d]) => !String(d.team || "").trim());
  $("#team-free").innerHTML = free.length ? free.map(([d]) => `<span class="chip">${label(d)}</span>`).join("")
    : '<span class="hint">Everyone is in a team.</span>';
}

document.addEventListener("toggle", (e) => {
  const box = e.target;
  if (!box.classList || !box.classList.contains("team-shared-box")) return;
  if (box.open) teamShareOpen.add(box.dataset.teamName);
  else teamShareOpen.delete(box.dataset.teamName);
}, true);

document.querySelectorAll(".league-picker").forEach((sel) => sel.addEventListener("change", (e) => {
  if (!e.target.value) return;
  if ((champ.dirty || editorUnsaved()) && !confirm("Leave without saving the changes to this league?")) {
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
  if (el.dataset.teamLogo != null || el.dataset.teamLogoSmall != null) {
    const small = el.dataset.teamLogoSmall != null;
    const team = teams[+(small ? el.dataset.teamLogoSmall : el.dataset.teamLogo)];
    if (!el.files.length) return;
    try {
      await uploadImage(`${small ? "team_small" : "team"}:${team.name}`, el.files[0]);
      toast(`${small ? "Small logo" : "Logo"} added to ${team.name}`);
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
    if (el.value !== "") {
      const d = ui.editing.drivers[+el.value];
      const was = d.team;
      d.team = teams[+el.dataset.teamAdd].name;
      teamSwitch(d, was, d.team).then(() => { renderTeams(); renderRoster(); });
    }
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
    // Renaming moves the team's drivers with it (and the races raced for it).
    for (const d of ui.editing.drivers || []) if (sameTeam(d.team, team.name)) d.team = name;
    for (const r of allResults()) if (r.team && sameTeam(r.team, team.name)) r.team = name;
    team.name = name;
    renderRoster();
  } else {
    team[key] = el.type === "checkbox" ? el.checked : el.value.trim();
  }
  renderTeams();
});

$("#team-cards").addEventListener("click", async (e) => {
  const teams = editorTeams();
  const b = e.target.closest("button");
  if (!b) return;
  const d = b.dataset;
  if (d.teamRemoveFrom != null) {
    e.preventDefault();  // not the chip's tick box
    const team = teams[+d.teamI];
    const other = (ui.leagueList || []).find((l) => l.id === d.teamRemoveFrom);
    const name = other ? other.name : d.teamRemoveFrom;
    if (!confirm(`Take ${team.name} out of ${name}? Its drivers there are left without a team. ${ui.editing.name} keeps it.`)) return;
    try {
      // Saved first, so nothing changed here is lost.
      await saveEditor();
      const r = await api(`/api/leagues/${encodeURIComponent(ui.editing.id)}/remove-team-from`, { method: "POST", body: { team: team.name, league: d.teamRemoveFrom } });
      openEditor(r.league);
      toast(`${team.name} taken out of ${name}`);
    } catch (err) {
      toast(err.message, true);
    }
    return;
  }
  if (d.teamUnassign != null) {
    const dr = ui.editing.drivers[+d.teamUnassign];
    const was = dr.team;
    dr.team = "";
    await teamSwitch(dr, was, "");
  }
  else if (d.teamNocolor != null) teams[+d.teamNocolor].color = "";
  else if (d.teamNologo != null) teams[+d.teamNologo].logo = null;
  else if (d.teamNologoSmall != null) teams[+d.teamNologoSmall].logo_small = null;
  else if (d.teamDelete != null) {
    const team = teams[+d.teamDelete];
    if (!confirm(`Delete ${team.name}? Its drivers stay in the league without a team.`)) return;
    for (const dr of ui.editing.drivers || []) if (sameTeam(dr.team, team.name)) dr.team = "";
    for (const r of allResults()) if (r.team && sameTeam(r.team, team.name)) r.team = "";
    teams.splice(+d.teamDelete, 1);
  } else return;
  renderTeams();
  renderRoster();
});

// -- a driver changing team mid-season ----------------------------------------

// Every race result of the league being edited.
function allResults() {
  const c = ui.editing && ui.editing.championship;
  return c ? (c.rounds || []).flatMap((rd) => rd.results || []) : [];
}

// Pick one of ``options`` ([value, label, primary]) in a dialog, with ``html``
// (fields) above them: {value, form}, or null (closed).
function choose(title, text, options, html = "") {
  return new Promise((resolve) => {
    const modal = $("#choice-modal");
    $("#choice-title").textContent = title;
    $("#choice-text").textContent = text;
    $("#choice-form").innerHTML = html;
    const box = $("#choice-options");
    box.innerHTML = options.map(([v, label, primary]) => `<button class="btn ${primary ? "primary" : ""}" data-choice="${esc(v)}">${esc(label)}</button>`).join("");
    const done = (v) => {
      modal.hidden = true;
      box.onclick = modal.onclick = null;
      resolve(v === null ? null : { value: v, form: $("#choice-form") });
    };
    box.onclick = (e) => {
      const b = e.target.closest("[data-choice]");
      if (b) done(b.dataset.choice);
    };
    modal.onclick = (e) => { if (e.target === modal) done(null); };
    modal.hidden = false;
    box.querySelector("button").focus();
  });
}

// Another league's settings into this one (LeagueStore.copy_settings): pick
// the league and what to bring over; drivers and results stay as they are.
const COPY_PARTS = [
  ["rules", "Points & rules (points systems, drop rounds, bonuses, class points)", true],
  ["classes", "Classes (colours, logos, how drivers are matched; same-named ones updated)", true],
  ["teams", "Teams (names, short names, colours, logos; same-named ones updated)", false],
  ["branding", "League logo, banners, sponsors and calendar graphic", false],
  ["calendar", "Calendar: the rounds, without results (only into a league with no results yet)", false],
  ["options", "Options (drivers with no class hidden, (P) name tags)", true],
];
$("#btn-copy-settings").addEventListener("click", async () => {
  const me = ui.editing;
  if (!me || !me.id) return toast("Save this league first", true);
  let leagues = ui.leagueList || [];
  try {
    leagues = (await api("/api/leagues")).leagues;  // as they are now
  } catch (e) { /* the list the pickers have */ }
  const others = leagues.filter((l) => l.id !== me.id).sort(byName());
  if (!others.length) return toast("There's no other league to copy from yet", true);
  const html = `<label class="field">From <select id="copy-from">${others.map((l) => `<option value="${esc(l.id)}">${esc(l.name)}</option>`).join("")}</select></label>
    <div class="copy-parts">${COPY_PARTS.map(([k, label, on]) => `<label class="check"><input type="checkbox" data-copy-part="${k}" ${on ? "checked" : ""}> ${esc(label)}</label>`).join("")}</div>
    <p class="hint">Drivers, results and penalties stay as they are. Unsaved changes here are lost: save first.</p>`;
  const r = await choose(`Copy settings into ${me.name}`, "Bring another league's settings into this one.", [["copy", "Copy", true], ["cancel", "Cancel"]], html);
  if (!r || r.value !== "copy") return;
  const from = r.form.querySelector("#copy-from").value;
  const parts = [...r.form.querySelectorAll("[data-copy-part]:checked")].map((b) => b.dataset.copyPart);
  if (!parts.length) return toast("Tick at least one thing to copy", true);
  try {
    await api(`/api/leagues/${encodeURIComponent(me.id)}/copy-settings`, { method: "POST", body: { from, parts } });
    await openLeague(me.id);
    const name = (others.find((l) => l.id === from) || {}).name || from;
    toast(`Copied from ${name}`);
  } catch (err) {
    toast(err.message, true);
  }
});

// A driver moved from one team to another (or out of one) after racing this
// season: their points so far stay with the team they raced for, or all go
// to their team now. Each result keeps the team it was raced for ("" = their
// team now), which the teams' championship counts by.
async function teamSwitch(d, from, to) {
  from = String(from || "").trim();
  to = String(to || "").trim();
  if (!from || sameTeam(from, to)) return;
  const key = driverKey(d);
  const results = allResults().filter((r) => r.driver === key);
  if (!results.length) return;
  const name = d.name || "This driver";
  const races = racesOf(key);
  // The race they first drove for the new team: the ones before it stay with the old team.
  const pickHtml = `<label class="ov-field">First race for ${esc(to || "no team")}
    <select id="switch-from"><option value="">The next race (every race so far stays with ${esc(from)})</option>
    ${races.map(({ rd, n }) => `<option value="${esc(rd.id)}">${esc(roundLabel(rd, n))}</option>`).join("")}</select></label>`;
  const pick = await choose(`${name}: ${from} → ${to || "no team"}`,
    `${name} has ${races.length} race${races.length > 1 ? "s" : ""} this season. In the teams' championship, the races before their first one for ${to || "no team"} count for ${from}; that one and every race after it for ${to || "no team"}.`, [
      ["apply", "Apply", true],
      ["move", to ? `All their points go to ${to}` : "All their points go with them (no team for now)"],
    ], pickHtml);
  if (pick === null) return;
  const first = pick.value === "apply" ? pick.form.querySelector("#switch-from").value : races[0] && races[0].rd.id;
  const at = first ? races.findIndex(({ rd }) => rd.id === first) : races.length;
  races.forEach(({ result }, i) => {
    if (i >= at) result.team = "";  // the team they're in now
    else if (!result.team || sameTeam(result.team, to)) result.team = from;  // earlier races raced for another team keep it
  });
  toast(at === 0 ? `${name}'s points all go to ${to || "no team"}: save to keep it`
    : at >= races.length ? `${name}'s points so far stay with ${from}: save to keep it`
      : `${name}: ${at} race${at > 1 ? "s" : ""} for ${from}, the rest for ${to || "no team"}: save to keep it`);
}

// A driver moved to another class after racing this season: like a team
// switch, their points so far stay in the class they raced in, or all go to
// the new one (each result keeps the class it was raced in).
async function classSwitch(d, from, to) {
  if (!from || !to || from === "-" || to === "-" || from === to) return;  // "Auto" or no main class: nothing to move
  const key = driverKey(d);
  const races = racesOf(key).filter(({ result }) => result.class_id === from);
  if (!races.length) return;
  const name = d.name || "This driver";
  const [was, now] = [champClassName(from), champClassName(to)];
  const pickHtml = `<label class="ov-field">First race in ${esc(now)}
    <select id="switch-from"><option value="">The next race (every race so far stays in ${esc(was)})</option>
    ${races.map(({ rd, n }) => `<option value="${esc(rd.id)}">${esc(roundLabel(rd, n))}</option>`).join("")}</select></label>`;
  const pick = await choose(`${name}: ${was} → ${now}`,
    `${name} has ${races.length} race${races.length > 1 ? "s" : ""} in ${was} this season. In the championships, the races before their first one in ${now} count for ${was}; that one and every race after it for ${now}.`, [
      ["apply", "Apply", true],
      ["move", `All their points go to ${now}`],
    ], pickHtml);
  if (pick === null) return;
  const first = pick.value === "apply" ? pick.form.querySelector("#switch-from").value : races[0] && races[0].rd.id;
  const at = first ? races.findIndex(({ rd }) => rd.id === first) : races.length;
  races.forEach(({ result }, i) => {
    if (i >= at) result.class_id = to;
  });
  toast(at === 0 ? `${name}'s points all go to ${now}: save to keep it`
    : at >= races.length ? `${name}'s points so far stay in ${was}: save to keep it`
      : `${name}: ${at} race${at > 1 ? "s" : ""} in ${was}, the rest in ${now}: save to keep it`);
}

// A driver's races this season, in round order: [{rd, n (round number), result}].
function racesOf(key) {
  const c = ui.editing && ui.editing.championship;
  if (!c) return [];
  return (c.rounds || []).map((rd, i) => ({ rd, n: i + 1, result: (rd.results || []).find((r) => r.driver === key) }))
    .filter((x) => x.result);
}
const roundLabel = (rd, n) => `R${n} · ${[rd.event, rd.name].filter(Boolean).join(" · ")}${rd.date ? ` (${rd.date})` : ""}`;

// Teams by race: which team each of a driver's races counts for in the teams' championship.
async function teamHistory(d) {
  const key = driverKey(d);
  const races = racesOf(key);
  if (!races.length) return;
  const teams = editorTeams().map((t) => t.name);
  const html = `<div class="team-history">${races.map(({ rd, n, result }, i) => `<label class="ov-field">${esc(roundLabel(rd, n))}
    <select data-race="${i}"><option value="">Their team now${d.team ? ` (${esc(d.team)})` : ""}</option>
    ${[...new Set([...teams, result.team].filter(Boolean))].map((t) => `<option value="${esc(t)}" ${result.team && sameTeam(result.team, t) ? "selected" : ""}>${esc(t)}</option>`).join("")}
    </select></label>`).join("")}</div>`;
  const pick = await choose(`${d.name || "Driver"}: teams by race`, "Which team each race counts for in the teams' championship.",
    [["apply", "Apply", true], ["cancel", "Cancel"]], html);
  if (!pick || pick.value !== "apply") return;
  pick.form.querySelectorAll("[data-race]").forEach((sel) => { races[+sel.dataset.race].result.team = sel.value; });
  toast("Teams by race changed: save to keep it");
}

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
  const cardHtml = (c, i) => {
    const mode = c.logo_bg === "keep" ? "keep" : /^#/.test(c.logo_bg || "") ? "pick" : "auto";
    return `<div class="class-card ${isSecondary(c) ? "secondary" : ""}" data-class="${i}">
      <div class="class-preview"></div>
      <div class="class-fields">
        <label>Name <input data-cfield="name" value="${esc(c.name)}" placeholder="e.g. Pro"></label>
        <label>Colour <input type="color" data-cfield="color" value="${esc(c.color)}"></label>
        <label title="Car class: shown on the overlays, joined by the car. Category: Pro, Semi-Pro, Rookie…, picked per driver, for its own championships">Kind
          <select data-cfield="role">
            <option value="main" ${isSecondary(c) ? "" : "selected"}>Car class (on the overlays)</option>
            <option value="secondary" ${isSecondary(c) ? "selected" : ""}>Category (Pro, Am…: points)</option>
          </select></label>
        ${isSecondary(c) ? `<label title="Its short name on the tower (when the tower shows categories)">Short tag
            <input data-cfield="tag" value="${esc(c.tag || "")}" placeholder="${esc((c.name || "").slice(0, 4).toUpperCase() || "PRO")}" maxlength="6" class="short"></label>
          <label class="grow" title="Drivers whose name starts with this tag, e.g. (P) Dave Price, are put in it without picking (leave empty to pick by hand)">Name tag (optional)
            <input data-cfield="name_tag" value="${esc(c.name_tag ? `(${c.name_tag})` : "")}" placeholder="e.g. (P)" maxlength="10" class="short"></label>`
          : `<label class="grow">iRacing classes <input data-cfield="match" value="${esc((c.match || []).join(", "))}" placeholder="e.g. GT3, GT4 (optional)"></label>`}
        <button class="btn icon danger" data-remove-class="${i}" title="Remove class">✕</button>
      </div>
      ${isSecondary(c) ? categoryScopeHtml(c, i) : ""}
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
  };
  const list = classes.map((c, i) => [c, i]);
  const mains = list.filter(([c]) => !isSecondary(c));
  const cats = list.filter(([c]) => isSecondary(c));
  $("#class-list").innerHTML = `
    <div class="class-section-head"><h3 class="section-title">Car classes</h3>
      <span class="hint">What the overlays show. Drivers join one by the car they drive (iRacing classes), a name tag, or by hand.</span></div>
    ${mains.length ? mains.map(([c, i]) => cardHtml(c, i)).join("") : '<p class="hint">No car classes yet: drivers are grouped by their iRacing car class.</p>'}
    <div class="row"><button class="btn subtle" data-add-class="main">+ Add car class</button></div>
    <div class="class-section-head"><h3 class="section-title">Categories</h3>
      <span class="hint">Pro, Semi-Pro, Am, Rookie… set once, picked per driver (Drivers list, <i>Category</i>). Each has a
        championship of its own in every car class (LMP2 · Pro, GT3 · Pro), or one for the whole field.</span></div>
    ${cats.map(([c, i]) => cardHtml(c, i)).join("")}
    <div class="row"><button class="btn subtle" data-add-class="secondary">+ Add category</button>
      ${cats.length ? "" : `<button class="btn subtle" data-class-preset="pro-sp" title="Adds Pro and Semi-Pro, each scored in every car class">Pro / Semi-Pro</button>
      <button class="btn subtle" data-class-preset="pro-am" title="Adds Pro and Am, each scored in every car class">Pro / Am</button>`}</div>
    ${championshipsSummary(classes)}`;
  classes.forEach((_, i) => renderClassPreview(i));
}

// A category's championships: one in each car class (those ticked), or one for the whole field.
function categoryScopeHtml(c, i) {
  const mains = (ui.editing.classes || []).filter((x) => !isSecondary(x));
  const perClass = c.scope === "class";
  const inside = c.in || [];
  return `<div class="class-fields category-scope">
    <span class="field-label">Championship</span>
    <span class="seg" role="group" aria-label="Its championship">
      <button type="button" class="${perClass ? "active" : ""}" data-cscope="class" data-class-i="${i}">One per car class</button>
      <button type="button" class="${perClass ? "" : "active"}" data-cscope="field" data-class-i="${i}">One for the whole field</button></span>
    ${perClass && mains.length ? `<span class="hint">in</span>${mains.map((m) => `<label class="check chip-check"><input type="checkbox" data-cfield="in" data-main="${esc(m.id)}"
      ${!inside.length || inside.includes(m.id) ? "checked" : ""}> ${esc(m.name || "Unnamed")}</label>`).join("")}` : ""}
  </div>`;
}

// The championships the classes and categories make (which run is ticked under Season & points).
function championshipsSummary(classes) {
  const mains = classes.filter((c) => !isSecondary(c));
  const cats = classes.filter(isSecondary);
  if (!cats.length) return "";
  const names = [];
  for (const m of mains) {
    for (const c of cats) if (c.scope === "class" && (!(c.in || []).length || c.in.includes(m.id))) names.push(`${m.name || "Unnamed"} · ${c.name || "Unnamed"}`);
  }
  for (const c of cats) if (c.scope !== "class" || !mains.length) names.push(`${c.name || "Unnamed"} (whole field)`);
  return `<div class="champ-summary"><b>Championships these make</b>${mains.length ? ` <span class="hint">(and ${mains.map((m) => esc(m.name || "Unnamed")).join(", ")} as a whole)</span>` : ""}
    <div class="row">${names.map((n) => `<span class="chip">${esc(n)}</span>`).join("")}</div>
    <span class="hint">Turn any of them off under <i>Season &amp; points</i>. Results already in are scored again to these.</span></div>`;
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
  if (field === "in") {
    // The car classes a category is scored in (all ticked: all of them, new ones too).
    const ticked = [...card.querySelectorAll('[data-cfield="in"]')].filter((b) => b.checked).map((b) => b.dataset.main);
    if (!ticked.length) {
      e.target.checked = true;
      return toast("A category needs at least one car class (or one for the whole field)", true);
    }
    const all = (ui.editing.classes || []).filter((x) => !isSecondary(x)).length;
    c.in = ticked.length === all ? [] : ticked;
    return renderClasses();
  }
  if (field === "name_tag") {
    c.name_tag = v.replace(/[()]/g, "").trim();
    return;
  }
  if (field === "role") {
    // Drivers picked for it move to the matching column.
    c.role = v;
    if (v === "secondary" && !c.scope) c.scope = "class";
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
  const scope = e.target.closest("[data-cscope]");
  if (scope) {
    ui.editing.classes[+scope.dataset.classI].scope = scope.dataset.cscope;
    return renderClasses();
  }
  const add = e.target.closest("[data-add-class]");
  if (add) return addClass(add.dataset.addClass);
  const preset = e.target.closest("[data-class-preset]");
  if (preset) {
    const pairs = preset.dataset.classPreset === "pro-am"
      ? [["Pro", "PRO", "P", "#e8eaef"], ["Am", "AM", "AM", "#8d95a6"]]
      : [["Pro", "PRO", "P", "#e8eaef"], ["Semi-Pro", "SP", "SP", "#8d95a6"]];
    for (const [name, tag, nameTag, color] of pairs) addClass("secondary", { name, tag, name_tag: nameTag, color }, false);
    renderClasses();
    renderRoster();
    return toast("Categories added: pick each driver's in the Drivers list (or use name tags)");
  }
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

// A new car class (role "main") or category ("secondary": scored in each car class to start with).
function addClass(role, fields = {}, render = true) {
  const used = new Set(ui.editing.classes.map((c) => c.color));
  const color = CLASS_PALETTE.find((c) => !used.has(c)) || CLASS_PALETTE[ui.editing.classes.length % CLASS_PALETTE.length];
  // Client-side id so roster picks work before the first save.
  const c = { id: `class-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`, name: "", color, match: [], logo: null,
    logo_bg: "auto", logo_tolerance: 18, logo_fill: "edges", role,
    ...(role === "secondary" ? { scope: "class", in: [], tag: "", name_tag: "" } : {}), ...fields };
  // Car classes before the categories (the order the standings list them in).
  const at = role === "main" ? ui.editing.classes.findIndex(isSecondary) : -1;
  if (at >= 0) ui.editing.classes.splice(at, 0, c);
  else ui.editing.classes.push(c);
  if (!render) return;
  renderClasses();
  renderRoster();
  const card = document.querySelector(`.class-card[data-class="${ui.editing.classes.indexOf(c)}"] input`);
  if (card) card.focus();
}

function readEditor() {
  const p = ui.editing;
  p.name = $("#edit-name").value.trim();
  p.strip_class_prefix = $("#edit-strip-class").checked;
  p.hide_unclassed = $("#edit-hide-unclassed").checked;
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
// The team a driver was in before it's typed over (for a mid-season switch).
$("#roster-rows").addEventListener("focusin", (e) => {
  if (e.target.dataset.field === "team") e.target.dataset.was = ui.editing.drivers[+e.target.dataset.row].team || "";
  if (e.target.dataset.field === "class_id") e.target.dataset.was = ui.editing.drivers[+e.target.dataset.row].class_id || "";
});
$("#roster-rows").addEventListener("change", async (e) => {
  if (e.target.dataset.field === "team") {
    const d = ui.editing.drivers[+e.target.dataset.row];
    await teamSwitch(d, e.target.dataset.was, d.team);
    e.target.dataset.was = d.team || "";
    return renderTeams();
  }
  if (e.target.dataset.field === "class_id") {
    const d = ui.editing.drivers[+e.target.dataset.row];
    await classSwitch(d, e.target.dataset.was, d.class_id);
    e.target.dataset.was = d.class_id || "";
    return;
  }
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
  const tick = e.target.closest("[data-tick]");
  if (tick) {
    // Shift-click: every driver between this one and the last ticked, as this one.
    const order = [...document.querySelectorAll("#roster-rows [data-tick]")].map((b) => +b.dataset.tick);
    const here = order.indexOf(+tick.dataset.tick);
    const from = e.shiftKey && rosterLastTick != null ? order.indexOf(rosterLastTick) : -1;
    const span = from >= 0 ? order.slice(Math.min(from, here), Math.max(from, here) + 1) : [+tick.dataset.tick];
    for (const i of span) {
      const d = ui.editing.drivers[i];
      if (tick.checked) rosterTicks.add(d);
      else rosterTicks.delete(d);
    }
    rosterLastTick = +tick.dataset.tick;
    return renderRoster();
  }
  const history = e.target.closest("[data-team-history]");
  if (history) return teamHistory(ui.editing.drivers[+history.dataset.teamHistory]);
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
$("#roster-tick-all").addEventListener("change", (e) => {
  const shown = [...document.querySelectorAll("#roster-rows [data-tick]")].map((b) => ui.editing.drivers[+b.dataset.tick]);
  for (const d of shown) {
    if (e.target.checked) rosterTicks.add(d);
    else rosterTicks.delete(d);
  }
  renderRoster();
});
$("#roster-tools").addEventListener("click", (e) => {
  if (e.target.closest("[data-roster-nocat]")) {
    rosterNoCat = !rosterNoCat;
    return renderRoster();
  }
  if (e.target.closest("[data-bulk-untick]")) {
    rosterTicks.clear();
    return renderRoster();
  }
  const cat = e.target.closest("[data-bulk-cat]");
  if (cat) {
    const n = rosterTicks.size;
    for (const d of rosterTicks) d.class2_id = cat.dataset.bulkCat;
    const c = (ui.editing.classes || []).find((x) => x.id === cat.dataset.bulkCat);
    rosterTicks.clear();
    renderRoster();
    renderClasses();
    toast(`${n} driver${n === 1 ? "" : "s"} set to ${c ? c.name : "no category"}: save the league to keep it`);
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
  if (e.target.closest("[data-archive-toggle]")) {
    leagueArchiveOpen = !leagueArchiveOpen;
    return loadLeagues();
  }
  const dup = e.target.closest("[data-duplicate]");
  if (dup) {
    e.stopPropagation();
    try {
      const r = await api(`/api/leagues/${encodeURIComponent(dup.dataset.duplicate)}/duplicate`, { method: "POST", body: {} });
      await loadLeagues();
      openEditor(r.league);
      toast(`Made "${r.league.name}": rename it and save`);
    } catch (err) {
      toast(err.message, true);
    }
    return;
  }
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
      if (editorUnsaved() && !confirm("Leave without saving the changes to this league?")) return;
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

// The Licence card on the Home page: the optional Apex Labs key. Once a key is added (it comes
// from signing in with Discord) it's hidden, APEX-••••-••••-••••-••••, until Show is pressed, so
// it isn't on screen while streaming. A new key starts hidden again.
const licKey = { key: "", shown: false };

function maskKey(key) {
  return key.split("-").map((part, i) => (i === 0 && part === "APEX" ? part : "•".repeat(part.length))).join("-");
}

function showLicenceKey() {
  const shown = licKey.shown && !!licKey.key;
  $("#lic-key-shown").textContent = shown ? licKey.key : maskKey(licKey.key);
  $("#lic-key-shown").classList.toggle("masked", !shown);
  $("#lic-show").textContent = shown ? "Hide" : "Show";
  $("#lic-show").title = shown ? "Hide the key" : "Show the full key";
  $("#lic-show").setAttribute("aria-pressed", shown ? "true" : "false");
}

function renderLicence(st) {
  if (!st) return;
  let text = "No key added";
  if (st.valid) text = `<b>${esc(st.tier_name || "Licensed")}</b> · registered to ${esc(st.user || "you")}`;
  else if (st.has_key) text = "Key added, not confirmed yet";
  $("#lic-status").innerHTML = text;
  $("#lic-add-row").hidden = !!st.has_key;
  $("#lic-have-row").hidden = !st.has_key;
  if ((st.key || "") !== licKey.key) licKey.shown = false;
  licKey.key = st.key || "";
  showLicenceKey();
  $("#lic-get").hidden = !!st.has_key;
  $("#lic-manage").hidden = !st.has_key;
  if (st.manage_url) $("#lic-manage").href = st.manage_url;
  $("#lic-error").hidden = !st.error;
  $("#lic-error").textContent = st.error || "";
}

async function licenceAction(path, body = {}, button = null) {
  if (button) button.disabled = true;
  try {
    const st = await api(`/api/licence/${path}`, { method: "POST", body });
    renderLicence(st);
    return st;
  } catch (err) {
    toast(err.message, true);
    return null;
  } finally {
    if (button) button.disabled = false;
  }
}

$("#lic-save").addEventListener("click", async (e) => {
  const key = $("#lic-key").value.trim();
  if (!key) return toast("Paste your key first", true);
  const st = await licenceAction("set", { key }, e.currentTarget);
  if (st) {
    $("#lic-key").value = "";
    toast(st.valid ? `Key added: ${st.tier_name}` : "Key added");
  }
});
$("#lic-key").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#lic-save").click(); });
$("#lic-show").addEventListener("click", () => {
  licKey.shown = !licKey.shown;
  showLicenceKey();
});
$("#lic-check").addEventListener("click", async (e) => {
  const st = await licenceAction("check", {}, e.currentTarget);
  if (st && st.valid && !st.error) toast("Key checked");
});
$("#lic-remove").addEventListener("click", async (e) => {
  const st = await licenceAction("remove", {}, e.currentTarget);
  if (st) toast("Key removed from this PC");
});
api("/api/licence").then(renderLicence).catch(() => {});

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
  // Several versions behind: what's changed in each of them, newest first.
  const behind = status.latest.behind || 0;
  $("#update-behind").hidden = behind < 2;
  $("#update-behind").textContent = behind > 1 ? `${behind} updates since your version: what's new in each, newest first.` : "";
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

checkForUpdate();

// A drop-down (⚙ View) closes when you click anywhere else.
document.addEventListener("click", (e) => {
  for (const d of document.querySelectorAll("details.view-menu[open]")) if (!d.contains(e.target)) d.open = false;
});

// A button that opens a widget's settings (data-open-ws="key").
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-open-ws]");
  if (b) openWidgetSettings(b.dataset.openWs, b.dataset.openWsSection || null);
});

// ---- Search (Ctrl+K): a tab, a setting, a driver to watch, or something to do --
let cmdkItems = [];
let cmdkPick = 0;
function cmdkAll() {
  const items = [];
  document.querySelectorAll(".tabs .tab").forEach((t) => items.push({ kind: "Tab", label: t.textContent.replace(/\s+/g, " ").trim(), run: () => showPage(t.dataset.tab) }));
  for (const [group, list] of hotkeyActions()) {
    for (const [, label, fn] of list) items.push({ kind: group.replace(/ \(.*\)$/, ""), label, run: fn });
  }
  for (const d of (ui.snap && ui.snap.drivers) || []) {
    if (d.car_idx == null || !d.name) continue;
    items.push({ kind: "Watch", label: `#${d.number} ${d.name}`, sub: d.team || "", run: () => cmd("watch", { car_idx: d.car_idx }) });
  }
  for (const w of WIDGETS) {
    for (const sec of wsSections(w.key)) {
      for (const f of sec.fields) {
        if (f[2] === "note") continue;
        items.push({ kind: "Setting", label: String(f[1]).replace(/<[^>]+>/g, ""), sub: `${w.name}${w.general ? "" : ` › ${sec.tab}`} › ${sec.title}`,
          run: () => {
            wsQuery = "";
            if ($("#ws-search")) $("#ws-search").value = "";
            wsWidget = w.key;
            wsTab = sec.tab;
            wsReveal = f[0];
            showPage("widget-settings");
            wsRedraw();
          } });
      }
    }
  }
  return items;
}
function cmdkRender() {
  const words = $("#cmdk-q").value.toLowerCase().split(/\s+/).filter(Boolean);
  const all = cmdkAll();
  cmdkItems = words.length
    ? all.filter((it) => { const t = `${it.label} ${it.sub || ""} ${it.kind}`.toLowerCase(); return words.every((w) => t.includes(w)); }).slice(0, 60)
    : all.filter((it) => it.kind === "Tab");
  cmdkPick = Math.min(cmdkPick, Math.max(0, cmdkItems.length - 1));
  $("#cmdk-list").innerHTML = cmdkItems.length ? cmdkItems.map((it, i) => `<button type="button" role="option" class="cmdk-item ${i === cmdkPick ? "on" : ""}" data-cmdk="${i}" aria-selected="${i === cmdkPick}">
      <span class="k">${esc(it.kind)}</span><span class="l">${esc(it.label)}${it.sub ? `<small>${esc(it.sub)}</small>` : ""}</span></button>`).join("")
    : '<p class="hint" style="padding:12px 16px;margin:0">Nothing found. Try another word: a driver\'s name, "replay", "standings"…</p>';
  const on = $("#cmdk-list .cmdk-item.on");
  if (on) on.scrollIntoView({ block: "nearest" });
}
function cmdkOpen() {
  $("#cmdk").hidden = false;
  $("#cmdk-q").value = "";
  cmdkPick = 0;
  cmdkRender();
  $("#cmdk-q").focus();
}
function cmdkClose() { $("#cmdk").hidden = true; }
function cmdkGo(i) {
  const it = cmdkItems[i];
  if (!it) return;
  cmdkClose();
  it.run();
}
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
    e.preventDefault();
    e.stopPropagation();
    if ($("#cmdk").hidden) cmdkOpen(); else cmdkClose();
  }
}, true);
$("#cmdk-open").addEventListener("click", cmdkOpen);
$("#cmdk-q").addEventListener("input", () => { cmdkPick = 0; cmdkRender(); });
$("#cmdk-q").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    cmdkPick = (cmdkPick + (e.key === "ArrowDown" ? 1 : -1) + cmdkItems.length) % Math.max(1, cmdkItems.length);
    cmdkRender();
  } else if (e.key === "Enter") {
    e.preventDefault();
    cmdkGo(cmdkPick);
  } else if (e.key === "Escape") cmdkClose();
});
$("#cmdk").addEventListener("click", (e) => {
  const b = e.target.closest("[data-cmdk]");
  if (b) return cmdkGo(+b.dataset.cmdk);
  if (e.target.id === "cmdk") cmdkClose();
});

// ---- League builder, Teams and Championship: Save, and "Unsaved changes" ----
// Changes are kept until Save (points & rules excepted: they save as they're
// changed). "Unsaved changes" shows by the Save button while there are some,
// and switching to another league asks first.
let editorSaved = null;  // the league as last saved (or opened)
function editorJson() {
  try {
    return ui.editing ? JSON.stringify(readEditor()) : null;
  } catch (e) {
    return null;
  }
}
function editorUnsaved() {
  const now = editorJson();
  return now !== null && editorSaved !== null && now !== editorSaved;
}
const openEditorBase = openEditor;
openEditor = function (profile) {  // a league opened (or reloaded after a save): that's what's saved
  openEditorBase(profile);
  editorSaved = editorJson();
  champ.dirty = false;
  $("#champ-dirty").hidden = true;
  showUnsaved();
};
function showUnsaved() {
  const unsaved = editorUnsaved();
  document.querySelectorAll("[data-unsaved]").forEach((el) => { el.hidden = !unsaved; });
}
setInterval(() => {
  const panel = document.querySelector(".panel.active");
  if (panel && ["tab-league", "tab-teams", "tab-championship"].includes(panel.id)) showUnsaved();
}, 700);
window.addEventListener("beforeunload", (e) => {
  if (!editorUnsaved()) return;
  e.preventDefault();
  e.returnValue = "";
});

// Move: ◀ ▶ ▲ ▼ nudge a widget 10 px at a time.
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-nudge]");
  if (!b) return;
  const form = b.closest(".ov-form");
  const input = b.parentElement.querySelector("input");
  if (!form || !input) return;
  const v = Math.max(+input.min, Math.min(+input.max, (+input.value || 0) + +b.dataset.by));
  input.value = v;
  b.blur();
  resetForms();
  cmd("overlay_settings", { overlay: input.dataset.section || form.dataset.overlay, values: { [b.dataset.nudge]: v } });
});

// Widget Settings: click part of the preview to open its settings (the tower's
// header, its columns, a driver's number…; a board's header, banner, rows).
const PREVIEW_PARTS = [
  [".fin-flag", "Behaviour", "Drivers"],
  [".tower-sponsor-slot, .tower-head, .head-box .head-text", "Content", "Header"],
  [".srow .num, .srow .stripe", "Look", "Drivers"],
  [".srow .c, .srow .r, .head-row", "Content", "Columns"],
  [".srow", "Content", "Drivers"],
  [".bhead, .banner, .sponsors, .league-logo", "Look", "Logo, banner & sponsors"],
];
function previewClick(e) {
  const w = WIDGET[wsWidget];
  if (!w || w.general) return;
  const secs = wsSections(w.key);
  let tab = "Position";
  let group = null;
  for (const [sel, t, g] of PREVIEW_PARTS) {
    if (e.target.closest && e.target.closest(sel) && secs.some((sec) => sec.tab === t && sec.group === g)) {
      tab = t;
      group = g;
      break;
    }
  }
  if (!secs.some((sec) => sec.tab === tab)) return;
  wsTab = tab;
  wsReveal = null;
  wsOpenSection = group ? (secs.find((sec) => sec.tab === tab && sec.group === group) || {}).title || null : null;
  wsSave();
  window.focus();  // keys (Ctrl+K…) back to the app, not the preview
  wsRedraw();
}
$("#ws-frame").addEventListener("load", () => {
  try {
    const doc = $("#ws-frame").contentDocument;
    doc.addEventListener("click", previewClick);
    doc.addEventListener("keydown", (e) => {  // Ctrl+K with the preview clicked
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        window.focus();
        cmdkOpen();
      }
    });
    const style = doc.createElement("style");
    style.textContent = "body { cursor: pointer; }";
    doc.head.appendChild(style);
  } catch (err) { /* another origin: no clicks */ }
});

// Championship › Your own tracks and layouts: add one, take one off.
$("#mt-add").addEventListener("click", async () => {
  const track = $("#mt-track").value.trim();
  if (!track) return toast("Type the track's name", true);
  await rememberTrack(track, $("#mt-config").value);
  $("#mt-config").value = "";
  if (champ.view === "rounds") renderChampRounds();
});
$("#mt-list").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-mt-remove]");
  if (!b) return;
  const [track, config] = JSON.parse(b.dataset.mtRemove);
  try {
    const r = await api("/api/tracks", { method: "POST", body: { track, config, remove: true } });
    trackList.groups = r.tracks;
    trackList.status = r;
    $("#track-names").innerHTML = r.tracks.map((x) => `<option value="${esc(x.track)}"></option>`).join("");
    renderTrackStatus();
    if (champ.view === "rounds") renderChampRounds();
  } catch (err) {
    toast(err.message, true);
  }
});
