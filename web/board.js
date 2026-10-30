"use strict";

// Full-screen boards. The server says which board is on screen and sends its
// rows (see apex/boards.py); this page only draws them. Each board's columns
// follow its settings in the Boards tab.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
let shown = "";
let boardKey = "";  // which board: it fades in when this changes, not on every update

const fmtPts = (v) => (v == null ? "" : Number.isInteger(v) ? String(v) : v.toFixed(1));
const makeChip = (m) => (m ? `<span class="make">${m.logo ? `<img src="${esc(m.logo)}" alt="${esc(m.name)}">` : ""}</span>${m.withName ? `<span class="make-name">${esc(m.name)}</span>` : ""}` : "");
const ROW_SPACE = 820;  // px for table rows under the header (less with a horizontal banner)

// The car number, in the driver's class colour.
const numberChip = (r) => (r.number ? `<span class="num" style="${r.class_color ? `background:${esc(r.class_color)};color:${inkFor(r.class_color)}` : ""}">${esc(r.number)}</span>` : "");

// [label, width, class, cell(row)] for each column a board shows.
function columns(b) {
  const s = b.settings;
  const cols = [];
  const add = (on, label, width, cls, cell) => on && cols.push([label, width, cls, cell]);
  if (b.kind === "championship") {
    add(true, "Pos", "70px", "p r", (r) => r.pos);
    add(s.show_number, "#", "80px", "c", numberChip);
    add(true, "Driver", "auto", "", (r) => esc(r.name));
    add(s.show_team, "Team", "auto", "muted", (r) => `${s.show_logo && r.team_logo ? `<img class="logo" src="${esc(r.team_logo)}" alt="">` : ""}${esc(r.team)}`);
    add(s.show_make, "Car", "110px", "c", (r) => makeChip(r.make && { name: r.make, logo: r.make_logo }));
    b.round_names.forEach((name, i) => add(true, name, "70px", "rd", (r) => {
      const x = r.rounds[i];
      return x && x.played ? `<span class="${x.dropped ? "rd dropped" : ""}">${fmtPts(x.points)}</span>` : "–";
    }));
    add(s.show_wins, "Wins", "80px", "r muted", (r) => r.wins || "");
    add(s.show_penalty, "Pen", "80px", "r down", (r) => (r.penalty ? `−${fmtPts(r.penalty)}` : ""));
    add(true, "Pts", "100px", "r pts", (r) => fmtPts(r.points));
    add(s.show_gap, s.show_ahead ? "To leader" : "Gap", s.show_ahead ? "140px" : "100px", "r muted", (r) => (r.behind ? `−${fmtPts(r.behind)}` : ""));
    add(s.show_ahead, "To ahead", "140px", "r muted", (r) => (r.ahead != null ? `−${fmtPts(r.ahead)}` : ""));
  } else if (b.kind === "teams") {
    add(true, "Pos", "70px", "p r", (r) => r.pos);
    add(true, "Team", "auto", "", (r) => `<span class="team-cell">${s.show_color && r.color ? `<span class="team-stripe" style="background:${esc(r.color)}"></span>` : ""}${s.show_logo && r.team_logo ? `<img class="logo" src="${esc(r.team_logo)}" alt="">` : ""}<span class="team-name">${esc(r.team)}</span></span>`);
    add(s.show_drivers, "Drivers", "auto", "muted team-drivers", (r) => esc(r.drivers.join(" · ")));
    b.round_names.forEach((name, i) => add(true, name, "70px", "rd", (r) => (r.rounds[i] == null ? "–" : fmtPts(r.rounds[i]))));
    add(s.show_wins, "Wins", "80px", "r muted", (r) => r.wins || "");
    add(s.show_penalty, "Pen", "80px", "r down", (r) => (r.penalty_points ? `−${fmtPts(r.penalty_points)}` : ""));
    add(true, "Pts", "110px", "r pts", (r) => fmtPts(r.points));
    add(s.show_gap, s.show_ahead ? "To leader" : "Gap", s.show_ahead ? "140px" : "110px", "r muted", (r) => (r.behind ? `−${fmtPts(r.behind)}` : ""));
    add(s.show_ahead, "To ahead", "140px", "r muted", (r) => (r.ahead != null ? `−${fmtPts(r.ahead)}` : ""));
  } else if (b.kind === "makes") {
    add(true, "Pos", "70px", "p r", (r) => r.pos);
    add(true, "Manufacturer", "auto", "", (r) => (s.show_logo ? makeChip({ name: r.make, logo: r.make_logo, withName: true }) : esc(r.make)));
    add(s.show_wins, "Wins", "100px", "r muted", (r) => r.wins || "");
    add(true, "Pts", "120px", "r pts", (r) => fmtPts(r.points));
    add(s.show_gap, "Gap", "120px", "r muted", (r) => (r.behind ? `−${fmtPts(r.behind)}` : ""));
  } else if (b.kind === "results") {
    add(true, "Pos", "70px", "p r", (r) => (r.rank ?? (r.status || "").toUpperCase()));
    add(s.show_gained, "", "90px", "c", (r) => (r.gained ? `<span class="${r.gained > 0 ? "up" : "down"}">${r.gained > 0 ? "▲" : "▼"}${Math.abs(r.gained)}</span>` : ""));
    add(s.show_number, "#", "80px", "c", numberChip);
    add(true, "Driver", "auto", "", (r) => esc(r.name));
    add(s.show_team, "Team", "auto", "muted", (r) => `${s.show_logo && r.team_logo ? `<img class="logo" src="${esc(r.team_logo)}" alt="">` : ""}${esc(r.team)}`);
    add(s.show_make, "Car", "110px", "c", (r) => makeChip(r.make && { name: r.make, logo: r.make_logo }));
    add(s.show_laps, "Laps", "80px", "r muted", (r) => r.laps ?? "");
    add(s.show_fastest, "Fastest", "140px", "r", (r) => (r.fastest_lap ? `<span class="${r.has_fastest ? "fl" : "muted"}">${fmtLap(r.fastest_lap)}</span>` : ""));
    add(s.show_status, "", "90px", "c", (r) => (r.status !== "finished" || r.short ? `<span class="st">${r.short ? "DNF" : esc(r.status.toUpperCase())}</span>` : ""));
    add(s.show_points, "Pts", "90px", "r pts", (r) => (r.points == null ? "" : `+${fmtPts(r.points)}`));
  }
  return cols;
}

function tableHtml(cols, rows) {
  return `<table class="btable"><colgroup>${cols.map((c) => `<col style="width:${c[1]}">`).join("")}</colgroup>
    <thead><tr>${cols.map((c) => `<th class="${c[2].replace(/\b(pts|p|muted|down)\b/g, "")}">${c[0]}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r, i) => `<tr class="${(r.pos || r.rank) <= 3 ? "top3" : ""}" style="--i:${i}">${cols.map((c) => `<td class="${c[2]}">${c[3](r)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function dateText(r) {
  if (!r.date) return "";
  const d = new Date(`${r.date}T${r.time || "12:00"}`);
  if (isNaN(d)) return r.date;
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

function calendarHtml(b) {
  const s = b.settings;
  if (!b.rows.length) return '<div class="empty-board">No rounds in the calendar yet.</div>';
  return `<div class="cal">${b.rows.map((r, i) => `<div class="round ${r.done ? "done" : ""} ${r.next ? "next" : ""}" style="--i:${i}">
      <div class="rn">Round ${r.round}${r.multiplier !== 1 ? ` · ×${r.multiplier} points` : ""}<span class="tag">${r.next ? "Next" : r.done ? "Done" : ""}</span></div>
      <div class="tr">${esc(r.track || r.name)}</div>
      ${s.show_config && r.config ? `<div class="cf">${esc(r.config)}</div>` : ""}
      <div class="when">${[s.show_date && dateText(r), s.show_time && r.time, s.show_length && r.length].filter(Boolean).map(esc).join(" · ")}</div>
      ${s.show_winners && r.winners.length ? `<div class="wins">${r.winners.map((w) => `<span style="${w.color ? `background:${esc(w.color)};color:${inkFor(w.color)}` : ""}">🏆 ${esc(r.winners.length === 1 ? "" : `${w.group_name}: `)}${esc(w.name)}</span>`).join("")}</div>` : ""}
    </div>`).join("")}</div>`;
}

function render(snap) {
  const b = snap.board;
  setBackground(b && b.settings, !!b);
  if (!b) {
    if (shown !== "none") {
      leave();  // fade the board out
      if (PREVIEW) stage.insertAdjacentHTML("beforeend", '<div class="preview-hint">No board on screen</div>');
    }
    shown = "none";
    boardKey = "";
    return;
  }
  let body;
  if (b.kind === "calendar" && b.image) body = `<div class="cal-image"><img src="${esc(b.image)}" alt="Season calendar"></div>`;
  else if (b.kind === "calendar") body = calendarHtml(b);
  else if (!b.rows.length) body = '<div class="empty-board">Nothing to show yet: no results in this championship.</div>';
  else {
    // Long lists go into two columns rather than shrinking past readable.
    const space = ROW_SPACE - (b.banner && b.banner.orientation === "horizontal" ? 150 : 0)
      - (b.sponsors && (b.sponsors.place === "top" || b.sponsors.place === "bottom") ? 110 : 0);
    const cols = columns(b);
    const split = b.rows.length > 20 ? 2 : 1;
    const per = Math.ceil(b.rows.length / split);
    const rowH = Math.max(30, Math.min(48, Math.floor(space / per)));
    const parts = [];
    for (let i = 0; i < split; i++) parts.push(b.rows.slice(i * per, (i + 1) * per));
    body = `<div class="bbody" style="--row-h:${rowH}px;--row-font:${Math.round(rowH * 0.52)}px">${parts.map((p) => tableHtml(cols, p)).join("")}</div>`;
  }
  // Banner and sponsor logos go round the edges: top / bottom across, left / right down the side.
  const edge = (place) => {
    const parts = [];
    if (b.banner && b.banner.place === place) parts.push(`<div class="banner ${b.banner.orientation}"><img src="${esc(b.banner.url)}" alt=""></div>`);
    if (b.sponsors && b.sponsors.place === place) {
      parts.push(`<div class="sponsors">${b.sponsors.logos.map((l) => `<img src="${esc(l.url)}" alt="${esc(l.name)}">`).join("")}</div>`);
    }
    if (!parts.length) return "";
    // The banner sits on the outside, sponsors next to the table.
    if (place === "bottom" || place === "right") parts.reverse();
    return `<div class="edge ${place === "top" || place === "bottom" ? "across" : "down"} ${place}">${parts.join("")}</div>`;
  };
  const sub = b.subtitle
    ? `<span class="sub"><span class="chip" style="${b.accent ? `background:${esc(b.accent)};color:${inkFor(b.accent)}` : "background:rgba(255,255,255,.12)"}">${esc(b.subtitle)}</span></span>` : "";
  const key = [b.kind, b.title, b.subtitle].join("|");
  const steady = key === boardKey;
  boardKey = key;
  const html = `<div class="board ${b.kind}" style="${b.accent ? `--accent-c:${esc(b.accent)}` : ""}">
    ${edge("left")}
    <div class="center">
      ${edge("top")}
      <div class="main">
        <div class="bhead">${b.league_logo ? `<img class="league-logo" src="${esc(b.league_logo)}" alt="">` : ""}<span class="t1">${esc(b.title)}</span>${sub}<span class="league">${esc(b.league)}</span></div>
        ${body}
      </div>
      ${edge("bottom")}
    </div>
    ${edge("right")}</div>`;
  if (html !== shown) {
    shown = html;
    if (steady) {
      // Same board with new numbers: swap them in without animating again.
      const cur = stage.querySelector(".board:not(.leaving)");
      if (cur) cur.outerHTML = html.replace('class="board ', 'class="board steady ');
      else stage.innerHTML = html;
    } else {
      // Another board: the old one fades out as the new one comes in over it.
      leave();
      stage.querySelectorAll(".preview-hint").forEach((el) => el.remove());
      stage.insertAdjacentHTML("beforeend", html);
    }
  }
}

// Fade out whatever board is on screen, then remove it.
function leave() {
  stage.querySelectorAll(".preview-hint").forEach((el) => el.remove());
  for (const old of stage.querySelectorAll(".board:not(.leaving)")) {
    old.classList.add("leaving");
    setTimeout(() => old.remove(), 600);
  }
}

followSnapshots(render);
