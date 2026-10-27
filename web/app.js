"use strict";

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fmtLap(t) {
  if (!t || t <= 0) return "";
  const m = Math.floor(t / 60);
  const s = (t - m * 60).toFixed(3).padStart(6, "0");
  return m ? `${m}:${s}` : (+s).toFixed(3);
}

function fmtClock(t) {
  t = Math.max(0, Math.floor(t || 0));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  const mm = String(m).padStart(2, "0"), ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function fmtDelta(d) {
  if (d == null || !isFinite(d)) return "";
  return (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(1);
}

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
};

// ---------------------------------------------------------------------------
// live data stream
// ---------------------------------------------------------------------------

function connectStream() {
  const es = new EventSource("/api/stream");
  es.onmessage = (msg) => {
    ui.snap = JSON.parse(msg.data);
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
  const fastest = Math.min(...rows.map((r) => r.best_lap || Infinity));
  const bestLapCar = rows.find((r) => r.best_lap && r.best_lap === fastest);
  const ordered = [];
  let prevGap = null;
  for (const r of rows) {
    let gap = "", int = "";
    if (isRace) {
      if (r.pos === 1) gap = "Leader";
      else if (r.gap != null && r.gap > 0) gap = fmtDelta(r.gap);
      if (prevGap != null && r.gap != null && r.pos !== 1) int = fmtDelta(r.gap - prevGap);
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
    ordered.push(patchRow(`d${r.car_idx}`, `${watching ? "watching" : ""} ${r.in_world ? "" : "gone"}`, [
      [String(r.pos ?? ""), "pos"],
      [`<span class="num" style="border-left-color:${esc(r.class_color || "var(--muted)")}">${esc(r.number)}</span>`],
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
    const [{ leagues, active }, cfg] = await Promise.all([api("/api/leagues"), api("/api/config")]);
    ui.activeLeague = active;
    $("#api-hint").textContent = cfg.api_configured
      ? "Pulls the roster from the iRacing Data API."
      : "iRacing API credentials aren't set (see README), so fetching won't work. You can still build a league from the current session or by hand.";
    $("#league-list").innerHTML = leagues.length ? leagues.map((l) => `
      <li data-league="${esc(l.id)}" class="${ui.editing && ui.editing.id === l.id ? "selected" : ""}">
        <div><div>${esc(l.name)} ${l.active ? '<span class="badge live">ACTIVE</span>' : ""}</div>
        <div class="meta">${l.drivers} drivers${l.league_id ? ` · ID ${l.league_id}` : ""}</div></div>
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
  renderRoster();
  document.querySelectorAll("#league-list li").forEach((li) => li.classList.toggle("selected", li.dataset.league === profile.id));
}

const ROSTER_FIELDS = [["name", ""], ["cust_id", "c-id"], ["car_number", "c-num"], ["nickname", ""], ["team", ""], ["notes", ""]];

function renderRoster() {
  const drivers = ui.editing.drivers || [];
  $("#roster-rows").innerHTML = drivers.map((d, i) => `<tr>${ROSTER_FIELDS.map(([f]) =>
    `<td><input data-row="${i}" data-field="${f}" value="${esc(d[f] ?? "")}" aria-label="${f}"></td>`).join("")}
    <td><button class="btn icon danger" data-remove="${i}" title="Remove">✕</button></td></tr>`).join("");
}

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
$("#roster-rows").addEventListener("click", (e) => {
  const rm = e.target.closest("[data-remove]");
  if (rm) {
    ui.editing.drivers.splice(+rm.dataset.remove, 1);
    renderRoster();
  }
});
$("#btn-add-driver").addEventListener("click", () => {
  ui.editing.drivers.push({ name: "", cust_id: "", car_number: "", nickname: "", team: "", notes: "" });
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
  openEditor({ id: "", name: "", league_id: null, source: "manual", drivers: [] });
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

connectStream();
