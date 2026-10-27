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
// class colours and logos
// ---------------------------------------------------------------------------

function hexToRgb(hex) {
  const n = parseInt(String(hex).slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex([r, g, b]) {
  return "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
}

// Black or white, whichever reads better on the class colour.
function inkFor(hex) {
  const [r, g, b] = hexToRgb(hex).map((v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4 ? "#111" : "#fff";
}

const ALPHA_CLEAR = 40;   // alpha below this counts as transparent background
const MAX_LOGO_PX = 512;  // logos are scaled down to this before processing

// Work out a logo's background from its border pixels: mostly transparent,
// or the most common colour (bucketed so JPEG noise doesn't split it).
function detectBackground(px, w, h) {
  const idx = [];
  const step = Math.max(1, Math.floor((2 * (w + h)) / 2000));
  for (let x = 0; x < w; x += step) idx.push(x, (h - 1) * w + x);
  for (let y = 0; y < h; y += step) idx.push(y * w, y * w + w - 1);
  let clear = 0;
  const buckets = new Map();
  for (const i of idx) {
    const o = i * 4;
    if (px[o + 3] < ALPHA_CLEAR) {
      clear++;
      continue;
    }
    const key = ((px[o] >> 4) << 8) | ((px[o + 1] >> 4) << 4) | (px[o + 2] >> 4);
    const b = buckets.get(key) || { n: 0, r: 0, g: 0, b: 0 };
    b.n++; b.r += px[o]; b.g += px[o + 1]; b.b += px[o + 2];
    buckets.set(key, b);
  }
  if (clear >= idx.length * 0.4 || !buckets.size) return { transparent: true, rgb: null };
  let best = null;
  for (const b of buckets.values()) if (!best || b.n > best.n) best = b;
  return { transparent: false, rgb: [best.r / best.n, best.g / best.n, best.b / best.n] };
}

// Replace the logo's background colour with the class colour. Background is
// either everything connected to the border ("edges") or every matching
// pixel ("all"). Anti-aliased fringe pixels are shifted by how much
// background they contain, so edges stay smooth.
function recolourBackground(px, w, h, bg, target, tolerance, fillAll) {
  const t = Math.max(0.02, tolerance / 100);
  const n = w * h;
  const dist = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    dist[i] = px[o + 3] < ALPHA_CLEAR ? 0
      : Math.hypot(px[o] - bg[0], px[o + 1] - bg[1], px[o + 2] - bg[2]) / 441.7;
  }
  const filled = new Uint8Array(n);
  if (fillAll) {
    for (let i = 0; i < n; i++) if (dist[i] <= t) filled[i] = 1;
  } else {
    const queue = new Int32Array(n);
    let head = 0, tail = 0;
    const seed = (i) => {
      if (!filled[i] && dist[i] <= t) {
        filled[i] = 1;
        queue[tail++] = i;
      }
    };
    for (let x = 0; x < w; x++) { seed(x); seed((h - 1) * w + x); }
    for (let y = 0; y < h; y++) { seed(y * w); seed(y * w + w - 1); }
    while (head < tail) {
      const i = queue[head++];
      const x = i % w;
      if (x > 0) seed(i - 1);
      if (x < w - 1) seed(i + 1);
      if (i >= w) seed(i - w);
      if (i < n - w) seed(i + w);
    }
  }
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    if (filled[i]) {
      px[o] = target[0]; px[o + 1] = target[1]; px[o + 2] = target[2]; px[o + 3] = 255;
      continue;
    }
    const x = i % w;
    const touches = (x > 0 && filled[i - 1]) || (x < w - 1 && filled[i + 1]) ||
      (i >= w && filled[i - w]) || (i < n - w && filled[i + w]);
    if (!touches) continue;
    const k = Math.min(1, Math.max(0, 1 - (dist[i] - t) / (t * 1.5)));
    const a = px[o + 3] / 255;
    for (let c = 0; c < 3; c++) {
      // Shift the background share to the target, then flatten any transparency onto it.
      const shifted = px[o + c] + k * (target[c] - bg[c]);
      px[o + c] = Math.min(255, Math.max(0, shifted * a + target[c] * (1 - a)));
    }
    px[o + 3] = 255;
  }
}

// Lay a transparent logo onto a solid class colour.
function fillTransparent(px, target) {
  for (let o = 0; o < px.length; o += 4) {
    const a = px[o + 3] / 255;
    for (let c = 0; c < 3; c++) px[o + c] = px[o + c] * a + target[c] * (1 - a);
    px[o + 3] = 255;
  }
}

async function processLogo(src, color, mode, tolerance, fill) {
  const img = new Image();
  img.src = src;
  await img.decode();
  let w = img.naturalWidth || 256, h = img.naturalHeight || 256;
  const scale = Math.min(1, MAX_LOGO_PX / Math.max(w, h));
  w = Math.max(1, Math.round(w * scale));
  h = Math.max(1, Math.round(h * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, w, h);
  const data = ctx.getImageData(0, 0, w, h);
  const detected = detectBackground(data.data, w, h);
  const result = { detected: detected.transparent ? "transparent" : rgbToHex(detected.rgb) };
  if (mode === "keep") return { ...result, url: src };
  const target = hexToRgb(color);
  if (/^#[0-9a-f]{6}$/i.test(mode)) {
    recolourBackground(data.data, w, h, hexToRgb(mode), target, tolerance, fill === "all");
  } else if (detected.transparent) {
    fillTransparent(data.data, target);
  } else {
    recolourBackground(data.data, w, h, detected.rgb, target, tolerance, fill === "all");
  }
  ctx.putImageData(data, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  return { ...result, url: URL.createObjectURL(blob) };
}

// Processed logos keyed by every setting that affects them. Rendering is
// synchronous: a miss starts processing and calls onReady when done.
const logoCache = new Map();
const LOGO_CACHE_MAX = 60;

function classLogo(cls, onReady) {
  if (!cls || !cls.logo) return null;
  const key = [cls.logo, cls.color, cls.logo_bg, cls.logo_tolerance, cls.logo_fill].join("|");
  const hit = logoCache.get(key);
  if (hit) return hit.url ? hit : null;
  logoCache.set(key, {});
  processLogo(cls.logo, cls.color, cls.logo_bg, cls.logo_tolerance, cls.logo_fill)
    .then((r) => logoCache.set(key, r))
    .catch(() => logoCache.set(key, { url: cls.logo, detected: null, failed: true }))
    .then(() => {
      while (logoCache.size > LOGO_CACHE_MAX) {
        const [oldKey, old] = logoCache.entries().next().value;
        if (old.url && old.url.startsWith("blob:")) URL.revokeObjectURL(old.url);
        logoCache.delete(oldKey);
      }
      if (onReady) onReady();
    });
  return null;
}

function classHeaderHtml(cls, detail, onReady) {
  const logo = classLogo(cls, onReady);
  return `<div class="class-head" style="background:${esc(cls.color)};color:${inkFor(cls.color)}">
    ${logo ? `<img class="class-logo" src="${esc(logo.url)}" alt="">` : cls.logo ? '<span class="class-logo pending"></span>' : ""}
    <span class="class-name">${esc(cls.name)}</span>${detail ? `<span class="class-detail">${esc(detail)}</span>` : ""}
  </div>`;
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
    <td><button class="btn icon danger" data-remove="${i}" title="Remove">✕</button></td></tr>`).join("");
}

// -- classes ------------------------------------------------------------------

const CLASS_PALETTE = ["#e8463c", "#2f80ed", "#27ae60", "#f2c94c", "#9b51e0", "#f2994a", "#56ccf2", "#eb5ea8"];

// The class as the overlay would show it, for the editor preview.
function previewClass(c) {
  return {
    name: c.name || "Unnamed class",
    color: c.color,
    logo: c.logo && ui.editing.id ? `/api/logos/${encodeURIComponent(ui.editing.id)}/${encodeURIComponent(c.logo)}` : null,
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
        <label class="btn">${c.logo ? "Replace" : "Upload"}<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" data-upload="${i}" hidden></label>
        ${c.logo ? `<button class="btn subtle" data-clear-logo="${i}">Remove</button>` : ""}
        <label ${c.logo ? "" : "hidden"}>Background
          <select data-cfield="bgmode">
            <option value="auto" ${mode === "auto" ? "selected" : ""}>Auto-detect</option>
            <option value="pick" ${mode === "pick" ? "selected" : ""}>Pick logo background</option>
            <option value="keep" ${mode === "keep" ? "selected" : ""}>Keep logo as is</option>
          </select>
        </label>
        <input type="color" data-cfield="bgcolor" value="${mode === "pick" ? esc(c.logo_bg) : "#ffffff"}" title="Logo background colour to replace" ${c.logo && mode === "pick" ? "" : "hidden"}>
        <label ${c.logo && mode !== "keep" ? "" : "hidden"} title="How different a pixel can be from the background and still be recoloured">Tolerance
          <input type="range" min="0" max="60" data-cfield="logo_tolerance" value="${c.logo_tolerance ?? 18}"></label>
        <label ${c.logo && mode !== "keep" ? "" : "hidden"} title="Also recolour background-coloured areas enclosed by the logo, like the inside of an O">
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
  if (hit && hit.failed) detected.textContent = "Couldn't read this logo";
  else if (hit && hit.detected) {
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
    // The class needs a saved id before it can own a logo.
    const saved = await saveEditor();
    const cls = saved.classes[i];
    const res = await fetch(`/api/leagues/${encodeURIComponent(saved.id)}/classes/${encodeURIComponent(cls.id)}/logo`, {
      method: "POST",
      headers: { "Content-Type": file.type || "application/octet-stream" },
      body: file,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.error || "Upload failed");
    openEditor(data.league);
    toast(`Logo added to ${cls.name}`);
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
$("#roster-rows").addEventListener("click", (e) => {
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
  openEditor({ id: "", name: "", league_id: null, source: "manual", classes: [], drivers: [] });
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
