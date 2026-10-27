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
  expanded: new Set(),   // car_idx with their event list open
  filter: "all",
  groupsKey: "",
  editing: null,         // league profile being edited
  activeLeague: null,
  groupByClass: true,
  library: [],           // built-in class logos
  libraryLoaded: false,
};

try {
  ui.groupByClass = localStorage.getItem("apex.groupByClass") !== "0";
} catch (e) { /* storage unavailable: keep default */ }

// ---------------------------------------------------------------------------
// live data stream
// ---------------------------------------------------------------------------

function connectStream() {
  const es = new EventSource("/api/stream");
  es.onmessage = (msg) => {
    ui.snap = JSON.parse(msg.data);
    // After an update the server restarts on the new version: load its UI.
    if (ui.version && ui.snap.version && ui.snap.version !== ui.version) return location.reload();
    ui.version = ui.version || ui.snap.version;
    $(".brand").title = `Apex Commentator v${ui.snap.version}`;
    render();
  };
  es.onerror = () => {
    $("#status-dot").classList.remove("on");
    $("#session-line").textContent = "Overlay server not reachable, retrying…";
  };
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

  if (!s.connected) {
    $("#session-line").textContent = s.source === "iracing" ? "Waiting for iRacing…" : "Not connected";
    $("#replay-badge").textContent = "—";
    $("#replay-badge").className = "badge";
    $("#driver-rows").innerHTML = "";
    rowEls.clear();
    $("#drivers-empty").hidden = false;
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

  renderCameraGroups(s.camera);
  renderDrivers(s);
  renderEvents(s);
}

function renderCameraGroups(cam) {
  const key = cam.groups.map((g) => `${g.num}:${g.name}`).join("|");
  const sel = $("#camera-group");
  if (key !== ui.groupsKey) {
    ui.groupsKey = key;
    sel.innerHTML = cam.groups.map((g) => `<option value="${g.num}">${esc(g.name)}</option>`).join("");
    // Quick buttons for the groups commentators reach for most.
    const favourites = ["TV1", "TV2", "TV3", "Chase", "Cockpit", "Blimp", "Chopper"];
    $("#camera-quick").innerHTML = cam.groups
      .filter((g) => favourites.includes(g.name))
      .map((g) => `<button class="chip" data-group="${g.num}">${esc(g.name)}</button>`)
      .join("");
  }
  if (document.activeElement !== sel) sel.value = String(cam.group);
  document.querySelectorAll("#camera-quick .chip").forEach((c) => c.classList.toggle("active", +c.dataset.group === cam.group));
}

function eventText(ev, withDriver = true) {
  const who = withDriver ? `<span class="num">${esc(ev.car_number)}</span> ${esc(ev.driver)}` : "";
  const pts = ev.incidents ? ` <b>${ev.incidents}x</b>` : "";
  switch (ev.type) {
    case "overtake":
      return `${who} passes <span class="num">${esc(ev.other_car_number)}</span> ${esc(ev.other_driver)}` +
        (ev.position ? ` for <b>P${ev.position}</b>` : "");
    case "offtrack":
      return `${who} off track${pts}`;
    case "slowdown":
      return `${who} slows ${ev.from_kph}→${ev.speed_kph} km/h${pts}`;
    default:
      return `${who} incident${pts}`;
  }
}

function kindLabel(ev) {
  const labels = { overtake: "PASS", offtrack: "OFF", slowdown: "SLOW", incident: "INC" };
  const cls = ev.incidents ? "kind has-points" : `kind ${ev.type}`;
  return `<span class="${cls}">${labels[ev.type] || ev.type}</span>`;
}

function eventItem(ev, withDriver = true) {
  return `<li>
    <span class="when">L${ev.lap} · ${fmtClock(ev.session_time)}</span>
    <span class="what">${kindLabel(ev)}${eventText(ev, withDriver)}</span>
    <button class="btn icon" data-act="watch" data-car="${ev.car_idx}" title="Watch live">👁</button>
    <button class="btn primary icon" data-act="replay-event" data-event="${ev.id}" title="Replay this moment">↺ Replay</button>
  </li>`;
}

// Rows are reconciled cell by cell rather than rebuilt, so buttons under the
// mouse are not replaced mid-click by the 4 Hz updates.
const rowEls = new Map();   // key -> <tr>

function patchRow(key, className, cells) {
  let tr = rowEls.get(key);
  if (!tr) {
    tr = document.createElement("tr");
    rowEls.set(key, tr);
  }
  if (tr.className !== className) tr.className = className;
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

function renderDrivers(s) {
  const rows = s.drivers;
  $("#driver-count").textContent = rows.length ? `(${rows.length})` : "";
  $("#drivers-empty").hidden = rows.length > 0;
  const isRace = (s.session.type || "").toLowerCase() === "race";
  const classes = s.classes || [];
  const classByKey = new Map(classes.map((c) => [c.key, c]));
  const grouped = ui.groupByClass && (classes.length > 1 || classes.some((c) => c.key.startsWith("league:")));
  $("#group-classes").checked = ui.groupByClass;

  // In grouped mode positions, gaps and intervals are within the class.
  const groups = grouped
    ? classes.map((c) => ({ cls: c, rows: rows.filter((r) => r.class_key === c.key) }))
    : [{ cls: null, rows }];
  const ordered = [];
  for (const { cls, rows: groupRows } of groups) {
    if (!groupRows.length) continue;
    if (cls) {
      const detail = `${groupRows.length} car${groupRows.length === 1 ? "" : "s"}`;
      ordered.push(patchRow(`h${cls.key}`, "class-row", [[classHeaderHtml(cls, detail, () => ui.snap && renderDrivers(ui.snap)), "", 11]]));
    }
    const fastest = Math.min(...groupRows.map((r) => r.best_lap || Infinity));
    const bestLapCar = groupRows.find((r) => r.best_lap && r.best_lap === fastest);
    const leaderGap = groupRows[0].gap;
    let prevGap = null;
    groupRows.forEach((r, i) => {
      let gap = "", int = "";
      if (isRace) {
        const g = r.gap != null && leaderGap != null ? r.gap - leaderGap : null;
        if (i === 0) gap = "Leader";
        else if (g != null && g > 0) gap = fmtDelta(g);
        if (i > 0 && prevGap != null && r.gap != null) int = fmtDelta(r.gap - prevGap);
        prevGap = r.gap;
      } else if (r.best_lap && isFinite(fastest)) {
        gap = r.best_lap === fastest ? "Fastest" : fmtDelta(r.best_lap - fastest);
      }
      const status = !r.in_world ? '<span class="tag out">OUT</span>'
        : r.on_pit ? '<span class="tag pit">PIT</span>'
        : r.surface === "off_track" ? '<span class="tag off">OFF</span>' : "";
      const lg = r.league;
      const team = (lg && lg.team) || r.team;
      const watching = s.camera.car_idx === r.car_idx;
      const open = ui.expanded.has(r.car_idx);
      const color = (classByKey.get(r.class_key) || {}).color || r.class_color || "var(--muted)";
      const pos = grouped ? r.class_pos : r.pos;
      ordered.push(patchRow(`d${r.car_idx}`, `${watching ? "watching" : ""} ${r.in_world ? "" : "gone"}`, [
        [String(pos ?? ""), "pos"],
        [`<span class="num" style="border-left-color:${esc(color)}">${esc(r.number)}</span>`],
        [`<span class="name">${esc(r.name)}</span>${lg && lg.nickname ? `<span class="nick">“${esc(lg.nickname)}”</span>` : ""}` +
          `${team ? `<span class="sub">${esc(team)}</span>` : ""}${lg && lg.notes ? `<span class="notes">${esc(lg.notes)}</span>` : ""}`],
        [String(r.lap ?? "")],
        [gap, "c-time"],
        [int, "c-time col-wide"],
        [fmtLap(r.last_lap), "c-time col-wide"],
        [fmtLap(r.best_lap), `c-time col-wide ${bestLapCar === r ? "best" : ""}`],
        [r.incidents == null ? "" : r.incidents + "x"],
        [status],
        [`<div class="actions">
          <button class="btn ${watching ? "primary" : ""}" data-act="watch" data-car="${r.car_idx}" title="Spectate this driver">👁 Watch</button>
          <button class="btn" data-act="replay-driver" data-car="${r.car_idx}" ${r.last_event_id ? "" : "disabled"} title="Replay this driver's latest incident/overtake">↺</button>
          <button class="btn ev-count" data-act="toggle" data-car="${r.car_idx}" ${r.event_count ? "" : "disabled"} title="Show this driver's events">${open ? "▴" : "▾"}${r.event_count || ""}</button>
        </div>`],
      ]));
      if (open) {
        const evs = s.events.filter((e) => e.car_idx === r.car_idx || e.other_car_idx === r.car_idx)
          .sort((a, b) => b.session_num - a.session_num || b.session_time - a.session_time);
        ordered.push(patchRow(`e${r.car_idx}`, "driver-events", [[
          `<ul class="events">${evs.length ? evs.map((e) => eventItem(e)).join("") : "<li>No events stored</li>"}</ul>`, "", 11,
        ]]));
      }
    });
  }
  const body = $("#driver-rows");
  const keep = new Set(ordered);
  for (const [key, tr] of rowEls) {
    if (!keep.has(tr)) {
      tr.remove();
      rowEls.delete(key);
    }
  }
  // Only move rows that are out of place (positions change rarely).
  ordered.forEach((tr, i) => {
    if (body.children[i] !== tr) body.insertBefore(tr, body.children[i] || null);
  });
}

function renderEvents(s) {
  const all = s.events;
  $("#event-count").textContent = all.length ? `(${all.length})` : "";
  const shown = all
    .filter((e) => ui.filter === "all" || (ui.filter === "overtake" ? e.type === "overtake" : e.type !== "overtake"))
    .sort((a, b) => b.session_num - a.session_num || b.session_time - a.session_time || b.id - a.id);
  $("#events-empty").hidden = shown.length > 0;
  const html = shown.map((e) => eventItem(e)).join("");
  const list = $("#event-list");
  if (list._html !== html) {
    list.innerHTML = html;
    list._html = html;
  }
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

$("#gw-interval").addEventListener("change", (e) => cmd("gridwalk_settings", { interval: +e.target.value }));
$("#gw-style").addEventListener("change", (e) => cmd("gridwalk_settings", { style: e.target.value }));
$("#gw-loop").addEventListener("change", (e) => cmd("gridwalk_settings", { loop: e.target.checked }));
$("#gw-absent").addEventListener("change", (e) => cmd("gridwalk_settings", { include_absent: e.target.checked }));
$("#gw-url").textContent = `${location.origin}/gridwalk.html`;

// ---------------------------------------------------------------------------
// interactions
// ---------------------------------------------------------------------------

function selectedGroup() {
  return +$("#camera-group").value || undefined;
}

document.addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (tab) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab.dataset.tab}`));
    if (tab.dataset.tab === "league") loadLeagues();
    return;
  }

  const filter = e.target.closest("#event-filter .chip");
  if (filter) {
    ui.filter = filter.dataset.filter;
    document.querySelectorAll("#event-filter .chip").forEach((c) => c.classList.toggle("active", c === filter));
    if (ui.snap && ui.snap.connected) renderEvents(ui.snap);
    return;
  }

  const quick = e.target.closest("#camera-quick .chip");
  if (quick) return cmd("camera_group", { group: +quick.dataset.group });

  const btn = e.target.closest("button[data-cmd]");
  if (btn) {
    const { cmd: action, ...rest } = btn.dataset;
    const params = {};
    for (const [k, v] of Object.entries(rest)) params[k] = isNaN(v) ? v : +v;
    if (["step_car", "watch_special"].includes(action)) params.group = selectedGroup();
    if (action === "clear_events" && !confirm("Clear all recorded events?")) return;
    return cmd(action, params);
  }

  const act = e.target.closest("button[data-act]");
  if (act) {
    const car = +act.dataset.car;
    switch (act.dataset.act) {
      case "watch":
        return cmd("watch", { car_idx: car, group: selectedGroup() });
      case "replay-driver":
        return cmd("replay_driver", { car_idx: car }, (r) => `Replaying ${r.replaying}`);
      case "replay-event":
        return cmd("replay_event", { event_id: +act.dataset.event }, (r) => `Replaying ${r.replaying}`);
      case "toggle":
        ui.expanded.has(car) ? ui.expanded.delete(car) : ui.expanded.add(car);
        if (ui.snap) renderDrivers(ui.snap);
        return;
    }
  }
});

$("#group-classes").addEventListener("change", (e) => {
  ui.groupByClass = e.target.checked;
  try {
    localStorage.setItem("apex.groupByClass", ui.groupByClass ? "1" : "0");
  } catch (err) { /* storage unavailable */ }
  if (ui.snap && ui.snap.connected) renderDrivers(ui.snap);
});

$("#btn-live").addEventListener("click", () => cmd("live", {}, "Back to live"));
$("#camera-group").addEventListener("change", (e) => cmd("camera_group", { group: +e.target.value }));

document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, select, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
  const keys = {
    l: () => cmd("live", {}, "Back to live"),
    r: () => cmd("replay_seconds", { seconds: 10 }),
    ArrowUp: () => cmd("step_car", { direction: -1, group: selectedGroup() }),
    ArrowDown: () => cmd("step_car", { direction: 1, group: selectedGroup() }),
  };
  const fn = keys[e.key] || keys[e.key.toLowerCase()];
  if (fn) {
    e.preventDefault();
    fn();
  }
});

// ---------------------------------------------------------------------------
// league builder
// ---------------------------------------------------------------------------

async function loadLeagues() {
  try {
    if (!ui.libraryLoaded) {
      ui.library = (await api("/api/logo-library")).logos;
      ui.libraryLoaded = true;
    }
    const [{ leagues, active }, cfg] = await Promise.all([api("/api/leagues"), api("/api/config")]);
    ui.activeLeague = active;
    $("#api-hint").textContent = cfg.api_configured
      ? "Pulls the roster from the iRacing Data API."
      : "iRacing API credentials aren't set (see README), so fetching won't work. You can still build a league from the current session or by hand.";
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
  $("#edit-league-id").value = profile.league_id ?? "";
  $("#btn-activate-league").textContent = profile.id && profile.id === ui.activeLeague ? "Active in overlay" : "Use in overlay";
  profile.classes = profile.classes || [];
  renderClasses();
  renderTeams();
  renderRoster();
  document.querySelectorAll("#league-list li").forEach((li) => li.classList.toggle("selected", li.dataset.league === profile.id));
}

const ROSTER_FIELDS = [["name", ""], ["cust_id", "c-id"], ["car_number", "c-num"], ["nickname", ""], ["team", ""], ["notes", ""]];

function renderRoster() {
  const drivers = ui.editing.drivers || [];
  const classes = ui.editing.classes || [];
  const classOptions = (selected) => `<option value="">Auto (by car)</option>` +
    classes.map((c) => `<option value="${esc(c.id)}" ${c.id === selected ? "selected" : ""}>${esc(c.name || "Unnamed")}</option>`).join("");
  $("#roster-rows").innerHTML = drivers.map((d, i) => `<tr>${ROSTER_FIELDS.map(([f]) =>
    `<td><input data-row="${i}" data-field="${f}" value="${esc(d[f] ?? "")}" aria-label="${f}"></td>`).join("")}
    <td><select data-row="${i}" data-field="class_id" aria-label="Class">${classOptions(d.class_id || "")}</select></td>
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

// -- teams --------------------------------------------------------------------

function editorTeams() {
  const teams = (ui.editing.teams = ui.editing.teams || []);
  const known = new Set(teams.map((t) => t.name.toLowerCase()));
  for (const d of ui.editing.drivers || []) {
    const name = String(d.team || "").trim();
    if (name && !known.has(name.toLowerCase())) {
      known.add(name.toLowerCase());
      teams.push({ name, logo: null });
    }
  }
  return teams;
}

function renderTeams() {
  const teams = editorTeams();
  $("#team-list").innerHTML = teams.length ? teams.map((t, i) => `<div class="team-row">
      <span class="team-logo">${t.logo ? `<img src="${esc(logoSrc(t.logo))}" alt="">` : ""}</span>
      <span class="team-name">${esc(t.name)}</span>
      <label class="btn">${t.logo ? "Replace logo" : "Upload logo"}<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-team="${i}" hidden></label>
      ${t.logo ? `<button class="btn subtle" data-clear-team="${i}">Remove</button>` : ""}
    </div>`).join("") : '<p class="hint">No teams yet: fill in the Team column below.</p>';
}

$("#team-list").addEventListener("change", async (e) => {
  const input = e.target.closest("[data-team]");
  if (!input || !input.files.length) return;
  const team = editorTeams()[+input.dataset.team];
  try {
    await uploadImage(`team:${team.name}`, input.files[0]);
    toast(`Logo added to ${team.name}`);
  } catch (err) {
    toast(err.message, true);
  }
});

$("#team-list").addEventListener("click", (e) => {
  const clear = e.target.closest("[data-clear-team]");
  if (clear) {
    editorTeams()[+clear.dataset.clearTeam].logo = null;
    renderTeams();
  }
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
  $("#class-list").innerHTML = classes.length ? classes.map((c, i) => {
    const mode = c.logo_bg === "keep" ? "keep" : /^#/.test(c.logo_bg || "") ? "pick" : "auto";
    return `<div class="class-card" data-class="${i}">
      <div class="class-preview"></div>
      <div class="class-fields">
        <label>Name <input data-cfield="name" value="${esc(c.name)}" placeholder="e.g. Pro"></label>
        <label>Colour <input type="color" data-cfield="color" value="${esc(c.color)}"></label>
        <label class="grow">iRacing classes <input data-cfield="match" value="${esc((c.match || []).join(", "))}" placeholder="e.g. GT3, GT4 (optional)"></label>
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
  const count = (ui.editing.drivers || []).filter((d) => d.class_id === c.id).length;
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
    ui.editing.drivers.forEach((d) => { if (d.class_id === removed.id) d.class_id = ""; });
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
  ui.editing.classes.push({ id: `class-${Date.now().toString(36)}`, name: "", color, match: [], logo: null, logo_bg: "auto", logo_tolerance: 18, logo_fill: "edges" });
  renderClasses();
  renderRoster();
  $("#class-list .class-card:last-child input").focus();
});

function readEditor() {
  const p = ui.editing;
  p.name = $("#edit-name").value.trim();
  p.league_id = $("#edit-league-id").value.trim() || null;
  return p;
}

$("#roster-rows").addEventListener("input", (e) => {
  const { row, field } = e.target.dataset;
  if (row != null) ui.editing.drivers[+row][field] = e.target.value;
});
$("#roster-rows").addEventListener("change", async (e) => {
  if (e.target.dataset.field === "team") return renderTeams();
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
$("#btn-add-driver").addEventListener("click", () => {
  ui.editing.drivers.push({ name: "", cust_id: "", car_number: "", nickname: "", team: "", notes: "", class_id: "" });
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

$("#fetch-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("#fetch-id").value.trim();
  if (!/^\d+$/.test(id)) return toast("Enter a numeric League ID", true);
  const btn = e.submitter;
  btn.disabled = true;
  btn.textContent = "Fetching…";
  try {
    const { league } = await api("/api/leagues/fetch", { method: "POST", body: { league_id: id } });
    toast(`Loaded ${league.name} (${league.drivers.length} drivers)`);
    await loadLeagues();
    openEditor(league);
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Fetch";
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

// Just enough markdown for release notes: headings, bullets, **bold**, `code`.
function notesHtml(md) {
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const out = [];
  let list = false;
  for (const raw of md.trim().split(/\r?\n/)) {
    const line = raw.trim();
    const bullet = line.match(/^[-*]\s+(.*)/);
    if (list && !bullet) {
      out.push("</ul>");
      list = false;
    }
    if (bullet) {
      if (!list) out.push("<ul>");
      list = true;
      out.push(`<li>${inline(bullet[1])}</li>`);
    } else if (/^#{1,6}\s/.test(line)) out.push(`<h4>${inline(line.replace(/^#+\s*/, ""))}</h4>`);
    else if (line) out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push("</ul>");
  return out.join("");
}

function closeUpdate() {
  $("#update-modal").hidden = true;
}

async function checkForUpdate(attempt = 0) {
  try {
    const status = await api("/api/update");
    if (!status.enabled) return;
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
