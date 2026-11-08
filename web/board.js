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

// A Background colour or image fills the whole screen behind the board, the
// image at its own size whatever the board's Size (setBackground in
// common.js, in render), rather than a panel round the table like the overlays.

// The car number, in the driver's class colour.
const numberChip = (r) => (r.number ? `<span class="num" style="${r.class_color ? `background:${esc(bgc(r.class_color))};color:${inkFor(r.class_color)}` : ""}">${esc(r.number)}</span>` : "");

// Places 1-3: gold, silver and bronze (the board's podium setting), else the accent colour.
let podium = true;
function podiumClass(r) {
  const place = r.pos || r.rank;
  if (!(place <= 3)) return "";
  return podium ? `top3 p${place}` : "top3";
}

// 1:23:45.678 / 23:45.678
function fmtRaceTime(t) {
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = (t % 60).toFixed(3).padStart(6, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

// [label, width, class, cell(row), key] for each column a board shows (the
// key is what Custom opacity per column calls it).
function columns(b) {
  const s = b.settings;
  const cols = [];
  const add = (on, key, label, width, cls, cell) => on && cols.push([label, width, cls, cell, key]);
  // The team logo and the team name: columns of their own, the logo before or after the name.
  const logoCol = (on) => add(on, "logo", "", "90px", "c lg", (r) => (r.team_logo ? `<img class="logo" src="${esc(r.team_logo)}" alt="">` : ""));
  const teamCols = (nameOn, nameCell) => {
    if (s.team_logo_side !== "last") logoCol(s.show_logo);
    add(nameOn, "team", "Team", "auto", nameCell ? "" : "muted", nameCell || ((r) => esc(r.team)));
    if (s.team_logo_side === "last") logoCol(s.show_logo);
  };
  if (b.kind === "championship") {
    add(true, "pos", "Pos", "70px", "p r", (r) => r.pos);
    add(s.show_number, "number", "#", "80px", "c", numberChip);
    add(true, "driver", "Driver", "auto", "", (r) => esc(formatName(r, s.name_format)));
    teamCols(s.show_team);
    add(s.show_make, "car", "Car", "110px", "c", (r) => makeChip(r.make && { name: r.make, logo: r.make_logo }));
    b.round_names.forEach((name, i) => add(true, "rounds", name, "70px", "rd", (r) => {
      const x = r.rounds[i];
      return x && x.played ? `<span class="${x.dropped ? "rd dropped" : ""}">${fmtPts(x.points)}</span>` : "–";
    }));
    add(s.show_wins, "wins", "Wins", "80px", "c muted", (r) => r.wins || "");
    add(s.show_penalty, "penalty", "Pen", "80px", "r down", (r) => (r.penalty ? `−${fmtPts(r.penalty)}` : ""));
    add(true, "points", "Pts", "100px", "r pts", (r) => fmtPts(r.points));
    add(s.show_gap, "gap", s.show_ahead ? "To leader" : "Gap", s.show_ahead ? "140px" : "100px", "r muted", (r) => (r.behind ? `−${fmtPts(r.behind)}` : ""));
    add(s.show_ahead, "ahead", "To ahead", "140px", "r muted", (r) => (r.ahead != null ? `−${fmtPts(r.ahead)}` : ""));
  } else if (b.kind === "teams") {
    add(true, "pos", "Pos", "70px", "p r", (r) => r.pos);
    teamCols(true, (r) => `<span class="team-cell">${s.show_color && r.color ? `<span class="team-stripe" style="background:${esc(bgc(r.color))}"></span>` : ""}<span class="team-name">${esc(r.team)}</span></span>`);
    add(s.show_drivers, "drivers", "Drivers", "auto", "muted team-drivers", (r) => esc((r.people || r.drivers.map((name) => ({ name }))).map((p) => formatName(p, s.name_format)).join(" · ")));
    b.round_names.forEach((name, i) => add(true, "rounds", name, "70px", "rd", (r) => (r.rounds[i] == null ? "–" : fmtPts(r.rounds[i]))));
    add(s.show_wins, "wins", "Wins", "80px", "c muted", (r) => r.wins || "");
    add(s.show_penalty, "penalty", "Pen", "80px", "r down", (r) => (r.penalty_points ? `−${fmtPts(r.penalty_points)}` : ""));
    add(true, "points", "Pts", "110px", "r pts", (r) => fmtPts(r.points));
    add(s.show_gap, "gap", s.show_ahead ? "To leader" : "Gap", s.show_ahead ? "140px" : "110px", "r muted", (r) => (r.behind ? `−${fmtPts(r.behind)}` : ""));
    add(s.show_ahead, "ahead", "To ahead", "140px", "r muted", (r) => (r.ahead != null ? `−${fmtPts(r.ahead)}` : ""));
  } else if (b.kind === "makes") {
    add(true, "pos", "Pos", "70px", "p r", (r) => r.pos);
    add(true, "make", "Manufacturer", "auto", "", (r) => (s.show_logo ? makeChip({ name: r.make, logo: r.make_logo, withName: true }) : esc(r.make)));
    add(s.show_wins, "wins", "Wins", "100px", "c muted", (r) => r.wins || "");
    add(true, "points", "Pts", "120px", "r pts", (r) => fmtPts(r.points));
    add(s.show_gap, "gap", "Gap", "120px", "r muted", (r) => (r.behind ? `−${fmtPts(r.behind)}` : ""));
  } else if (b.kind === "results") {
    add(true, "pos", "Pos", "70px", "p r", (r) => (r.rank ?? (r.status || "").toUpperCase()));
    add(s.show_gained, "gained", "", "90px", "c", (r) => (r.gained ? `<span class="${r.gained > 0 ? "up" : "down"}">${r.gained > 0 ? "▲" : "▼"}${Math.abs(r.gained)}</span>` : ""));
    add(s.show_number, "number", "#", "80px", "c", numberChip);
    add(true, "driver", "Driver", "auto", "", (r) => esc(formatName(r, s.name_format)));
    teamCols(s.show_team);
    add(s.show_make, "car", "Car", "110px", "c", (r) => makeChip(r.make && { name: r.make, logo: r.make_logo }));
    add(s.show_laps, "laps", "Laps", "80px", "r muted", (r) => r.laps ?? "");
    add(s.show_fastest, "fastest", "Fastest", "140px", "r", (r) => (r.fastest_lap ? `<span class="${r.has_fastest ? "fl" : "muted"}">${fmtLap(r.fastest_lap)}</span>` : ""));
    // Gap to the winner and to the car ahead; a DNF / DNS / DSQ shows there instead.
    const gapCell = (r, t, laps) => (r.out ? `<span class="st">${esc(r.out)}</span>`
      : laps ? `+${laps} ${laps === 1 ? "Lap" : "Laps"}` : t != null ? `+${secs(t, false)}` : "");
    // The winner's Gap: their laps, or their race time (where it's known).
    // The winner's Gap and Int: their whole race time (everyone else's gaps
    // are from it), else their laps.
    const how = s.winner_cell || "time";
    const winnerCell = (r) => (how === "time" && r.race_time ? fmtRaceTime(r.race_time)
      : r.laps ? `${r.laps} ${r.laps === 1 ? "Lap" : "Laps"}` : "");
    const lead = (r) => (r.winner && !r.out ? `<span class="lead">${winnerCell(r)}</span>` : null);
    add(s.show_gap, "gap", "Gap", "150px", "r muted", (r) => lead(r) ?? gapCell(r, r.gap, r.gap_laps));
    add(s.show_interval, "interval", "Int", "150px", "r muted", (r) => lead(r) ?? gapCell(r, r.interval, r.interval_laps));
    add(s.show_points, "points", "Pts", "90px", "r pts", (r) => (r.points == null ? "" : `+${fmtPts(r.points)}`));
  } else if (b.kind === "qualifying") {
    add(true, "pos", "Pos", "70px", "p r", (r) => r.rank ?? "");
    add(s.show_number, "number", "#", "80px", "c", numberChip);
    add(true, "driver", "Driver", "auto", "", (r) => esc(formatName(r, s.name_format)));
    teamCols(s.show_team);
    add(s.show_make, "car", "Car", "110px", "c", (r) => makeChip(r.make && { name: r.make, logo: r.make_logo }));
    add(s.show_laps, "laps", "Laps", "80px", "r muted", (r) => r.laps ?? "");
    add(s.show_best, "best", "Best lap", "150px", "r", (r) => (r.fastest_lap ? `<span class="${r.rank === 1 ? "fl" : ""}">${fmtLap(r.fastest_lap)}</span>` : ""));
    // Pole: their lap in the Gap and Int (everyone else's gaps are to it).
    const pole = (r) => (r.gap == null && r.fastest_lap && !r.out ? `<span class="lead">${fmtLap(r.fastest_lap)}</span>` : null);
    add(s.show_gap, "gap", "Gap", "130px", "r muted", (r) => pole(r) ?? (r.gap != null ? `+${secs(r.gap, false)}` : ""));
    add(s.show_interval, "interval", "Int", "130px", "r muted", (r) => pole(r) ?? (r.interval != null ? `+${secs(r.interval, false)}` : ""));
  } else if (b.kind === "grid") {
    add(true, "pos", "Grid", "80px", "p r", (r) => r.pos);
    add(s.show_class_pos && b.overall, "class_pos", "Cls", "70px", "c muted", (r) => r.class_pos);
    add(s.show_number, "number", "#", "80px", "c", numberChip);
    add(true, "driver", "Driver", "auto", "", (r) => esc(formatName(r, s.name_format)));
    teamCols(s.show_team);
    add(s.show_make, "car", "Car", "110px", "c", (r) => makeChip(r.make && { name: r.make, logo: r.make_logo }));
    // Qualifying times and gaps only on a grid that's from qualifying.
    const fromQual = gridFromQual(b);
    add(s.show_qual && fromQual, "qual", "Qualifying", "150px", "r", (r) => (r.qual_time ? fmtLap(r.qual_time) : ""));
    // Each class's pole: their lap in the Gap (the others' gaps are to it).
    add(s.show_gap && fromQual, "gap", "Gap", "130px", "r muted", (r) => (r.qual_gap != null ? `+${secs(r.qual_gap, false)}`
      : r.qual_time ? `<span class="lead">${fmtLap(r.qual_time)}</span>` : ""));
    add(s.show_from && b.grid_from === "previous race", "from", "Finished", "120px", "c muted", (r) => (r.from ? `P${r.from}` : ""));
  }
  return cols;
}

// A grid from qualifying (reversed or not), not from a race's finish or the grid walk's own order.
const gridFromQual = (b) => !b.grid_from || b.grid_from === "qualifying";

// The starting grid row by row: rows not shown yet keep their place, unseen
// (so nothing moves as they come); the row (or rows) just shown comes in.
let lastReveal = { base: "", n: 0 };
function markReveal(b) {
  if (b.kind !== "grid" || b.reveal == null) {
    lastReveal = { base: "", n: 0 };
    return;
  }
  const base = [b.kind, b.title, b.subtitle].join("|");
  const before = lastReveal.base === base ? lastReveal.n : 0;
  for (const r of b.rows) {
    const row = Math.ceil(r.pos / 2);  // the grid row (two cars)
    r._cls = r.hidden ? "unrevealed" : before && row > before && row <= b.reveal ? "reveal-in" : "";
  }
  lastReveal = { base, n: b.reveal };
}

// The starting grid as cars line up: two staggered columns, the odd places
// on the left a little ahead of the even ones on the right.
function gridLayoutHtml(b) {
  const s = b.settings;
  const slot = (r, i) => `<div class="gslot ${(r.pos || i + 1) % 2 ? "odd" : "even"} ${podiumClass(r)} ${r._cls || ""}" style="--i:${i}" data-pos="${esc(r.pos ?? "")}">
      <div class="gp">${r.pos}${s.show_class_pos && b.overall ? `<small>P${r.class_pos}</small>` : ""}</div>
      <div class="gbox" style="--cls:${esc(r.class_color || "#8b93a3")}">
        ${s.show_number ? numberChip(r) : ""}
        <div class="gname"><b>${esc(formatName(r, s.name_format))}</b>${s.show_team && r.team ? `<span>${esc(r.team)}</span>` : ""}</div>
        ${s.show_logo && r.team_logo ? `<img class="logo" src="${esc(r.team_logo)}" alt="">` : ""}
        ${s.show_make && r.make_logo ? makeChip({ name: r.make, logo: r.make_logo }) : ""}
        <div class="gq">${s.show_qual && gridFromQual(b) && r.qual_time ? `<span>${fmtLap(r.qual_time)}</span>` : ""}${s.show_gap && gridFromQual(b) && r.qual_gap != null ? `<span class="muted">+${secs(r.qual_gap, false)}</span>`
          : s.show_gap && !s.show_qual && gridFromQual(b) && r.qual_time ? `<span>${fmtLap(r.qual_time)}</span>` : ""}${s.show_from && b.grid_from === "previous race" && r.from ? `<span class="muted">Finished P${r.from}</span>` : ""}</div>
      </div></div>`;
  return `<div class="grid-layout">${b.rows.map(slot).join("")}</div>`;
}

function tableHtml(cols, rows) {
  return `<table class="btable"><colgroup>${cols.map((c) => `<col style="width:${c[1]}">`).join("")}</colgroup>
    <thead><tr>${cols.map((c) => `<th class="${c[2].replace(/\b(pts|p|muted|down)\b/g, "")}">${c[0]}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r, i) => `<tr class="${podiumClass(r)} ${r.kept ? "kept" : ""} ${r._cls || ""}" style="--i:${i}" data-pos="${esc(r.pos ?? "")}">${cols.map((c) => `<td class="${c[2]}" data-opcol="${c[4]}">${c[3](r)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const ordinal = (n) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th"}`;

// A round's date, in the style picked for the calendar board.
function dateText(r, format) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(r.date || "");
  if (!m) return r.date || "";
  const [y, mo, d] = [+m[1], +m[2], +m[3]];
  const weekday = DAYS[new Date(y, mo - 1, d).getDay()];
  const pad = (n) => String(n).padStart(2, "0");
  switch (format) {
    case "numeric": return `${pad(d)}/${pad(mo)}/${String(y).slice(-2)}`;               // 22/11/26
    case "day_month": return `${ordinal(d)} ${MONTHS[mo - 1]}`;                         // 22nd November
    case "full": return `${ordinal(d)} ${MONTHS[mo - 1]} ${y}`;                         // 22nd November 2026
    case "weekday": return `${weekday} ${ordinal(d)} ${MONTHS[mo - 1]}`;                // Sunday 22nd November
    default: return `${weekday.slice(0, 3)} ${d} ${MONTHS[mo - 1].slice(0, 3)}`;        // Sun 22 Nov
  }
}

// "Round 3", the round's own name, or both, as picked; a round without a
// name of its own is "Round 3" whatever's picked.
// A race meeting of several races is several rounds: "Rounds 4–6".
function roundTitle(r, how) {
  // The meeting's or round's own name (whatever it's called), unless it's just its number.
  const own = r.name && r.name.trim().toLowerCase() !== `round ${r.round}` ? r.name.trim() : "";
  const num = r.last ? `Rounds ${r.round}–${r.last}` : `Round ${r.round}`;
  if (how === "number" || !own) return num;
  return how === "name" ? own : `${num} · ${own}`;
}


// Each race of a card (one for a round, each heat for a race meeting): its
// name and length, and once it's run, each class's winner under it.
function racesHtml(r, s) {
  // Whose winners: the classes ticked (winner_groups: "" all, "none" none).
  const only = s.winner_groups ? new Set(s.winner_groups === "none" ? [] : s.winner_groups.split(",")) : null;
  const boxes = (r.sessions || []).map((x) => {
    const head = [s.show_race_name !== false && x.name, s.show_length && x.length].filter(Boolean);
    const shown = (x.winners || []).filter((w) => !only || only.has(w.group));
    const wins = s.show_winners && shown.length ? shown.map((w) => `<div class="rb-win">
        <span class="dot" style="background:${esc(bgc(w.color || "#8b93a3"))}"></span>${s.show_winner_class !== false && w.group_name ? `<span class="cls">${esc(w.group_name)}:</span> ` : "🏆 "}${esc(formatName(w, s.winner_name_format))}</div>`).join("") : "";
    if (!head.length && !wins) return "";
    return `<div class="race-box">${head.length ? `<div class="rb-head"><b>${esc(head[0])}</b>${head[1] ? ` <span class="len">${esc(head[1])}</span>` : ""}</div>` : ""}${wins}</div>`;
  }).filter(Boolean);
  return boxes.length ? `<div class="races">${boxes.join("")}</div>` : "";
}

function calendarHtml(b) {
  const s = b.settings;
  if (!b.rows.length) return '<div class="empty-board">No rounds in the calendar yet.</div>';
  return `<div class="cal">${b.rows.map((r, i) => `<div class="round ${r.done ? "done" : ""} ${r.next ? "next" : ""}" style="--i:${i}">
      <div class="rn"><span class="rt">${esc(roundTitle(r, s.round_title))}</span>${s.show_multiplier && r.multiplier !== 1 ? `<span class="mult">×${r.multiplier} points</span>` : ""}<span class="tag">${r.next ? "Next" : r.done ? "Done" : ""}</span></div>
      <div class="tr">${esc(r.track || "Track to be confirmed")}</div>
      ${s.show_config && r.config ? `<div class="cf">${esc(r.config)}</div>` : ""}
      <div class="when">${[s.show_date && dateText(r, s.date_format), s.show_time && r.time].filter(Boolean).map(esc).join(" · ")}</div>
      ${racesHtml(r, s)}
    </div>`).join("")}</div>`;
}

// The last board's settings: taken off screen, it fades out in its own
// background (yours, not the default one), the backdrop fading with it.
let lastSettings = null;

function render(snap) {
  const b = snap.board;
  if (b) {
    setSize(b.settings, true);
    lastSettings = b.settings;
  }
  const look = b ? b.settings : lastSettings;
  setBackground(look, !!b);
  // The whole board but its text at the opacity set (backdrop, rows, boxes, lines).
  document.body.style.setProperty("--bg-k", String(look && look.bg_opacity != null ? look.bg_opacity / 100 : 1));
  podium = !look || look.podium !== false;
  setColumnOpacity(look);
  setLogoScale(look);
  if (!b) {
    if (shown !== "none") {
      leave();  // fade the board out
      if (PREVIEW) stage.insertAdjacentHTML("beforeend", '<div class="preview-hint">No board on screen</div>');
    }
    shown = "none";
    boardKey = "";
    return;
  }
  markReveal(b);
  let body;
  if (b.kind === "calendar" && b.image) body = `<div class="cal-image"><img src="${esc(b.image)}" alt="Season calendar"></div>`;
  else if (b.kind === "calendar") body = calendarHtml(b);
  else if (!b.rows.length) {
    body = `<div class="empty-board">${b.kind === "grid" ? "No grid yet: drivers appear once they're in the session (qualifying, or the event's entry list)."
      : b.kind === "qualifying" ? "No qualifying times yet." : "Nothing to show yet: no results in this championship."}</div>`;
  } else if (b.kind === "grid" && b.settings.grid_layout === "grid") {
    // Fewer drivers on screen: bigger slots (and everything in them).
    const space = ROW_SPACE - (b.banner && b.banner.orientation === "horizontal" ? 150 : 0)
      - (b.sponsors && (b.sponsors.place === "top" || b.sponsors.place === "bottom") ? 110 : 0);
    const pairs = Math.max(1, Math.ceil(Math.max(b.rows.length, +b.settings.rows || 1) / 2));
    // Filling the page (grid_fill) as they come, however few; then the size picked by hand.
    const fit = Math.floor((space - 10 * (pairs - 1)) / (pairs + 0.6));
    const slotH = Math.round(Math.max(56, Math.min(b.settings.grid_fill !== false ? 400 : 130, fit)) * (+b.settings.grid_size || 100) / 100);
    // What's in them grows too, though not past what fits across (long names end in …).
    const k = Math.min(slotH / 74, 1.9);
    body = `<div class="scroll-box" style="--slot-h:${slotH}px;--slot-k:${k.toFixed(3)}">${gridLayoutHtml(b)}</div>`;
  } else {
    // Long lists go into two columns rather than shrinking past readable.
    const space = ROW_SPACE - (b.banner && b.banner.orientation === "horizontal" ? 150 : 0)
      - (b.sponsors && (b.sponsors.place === "top" || b.sponsors.place === "bottom") ? 110 : 0);
    const cols = columns(b);
    const split = b.rows.length > 20 ? 2 : 1;
    // The starting grid: fewer drivers on screen, bigger name plates.
    const per = b.kind === "grid" ? Math.ceil(Math.max(b.rows.length, Math.min(+b.settings.rows || 1, 40)) / split) : Math.ceil(b.rows.length / split);
    // The starting grid: rows fill the page (grid_fill), then the size picked by hand.
    const gridMax = b.settings.grid_fill !== false ? 150 : 80;
    const rowH = Math.round(Math.max(30, Math.min(b.kind === "grid" ? gridMax : 48, Math.floor(space / per)))
      * (b.kind === "grid" ? (+b.settings.grid_size || 100) / 100 : 1));
    // Bigger rows: the fixed-width columns grow with them.
    const grow = rowH / 48;
    if (grow > 1) for (const c of cols) if (/^\d+px$/.test(c[1])) c[1] = `${Math.round(parseInt(c[1], 10) * grow)}px`;
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
    ? `<span class="sub"><span class="chip" style="${b.accent ? `background:${esc(bgc(b.accent))};color:${inkFor(b.accent)}` : `background:${bgc("rgba(255,255,255,.12)")}`}">${esc(b.subtitle)}</span></span>` : "";
  // Scrolling (the grid row by row): the same board as it moves on, not a new page.
  const key = [b.kind, b.title, b.subtitle, b.scroll != null ? "scroll" : b.page].join("|");
  const scrolled = b.scroll != null && lastScroll != null && b.scroll > lastScroll && key === boardKey ? b.scroll - lastScroll : 0;
  lastScroll = b.scroll ?? null;
  const steady = key === boardKey;
  // Another page of the same board: the board (and its background) stays,
  // just the rows change, cascading in.
  const paging = !steady && boardKey && key.replace(/\|[^|]*$/, "") === boardKey.replace(/\|[^|]*$/, "");
  boardKey = key;
  const html = `<div class="board ${b.kind}" style="${b.accent ? `--accent-c:${esc(b.accent)}` : ""}">
    ${edge("left")}
    <div class="center">
      ${edge("top")}
      <div class="main">
        <div class="bhead">${b.league_logo ? `<img class="league-logo" src="${esc(b.league_logo)}" alt="">` : ""}<span class="t1">${esc(b.title)}</span>${sub}${b.settings.show_league !== false ? `<span class="league">${esc(b.league)}</span>` : '<span class="league"></span>'}${b.pages > 1 && b.settings.page_number ? `<span class="pageno">${b.page + 1} / ${b.pages}</span>` : ""}</div>
        ${body}
      </div>
      ${edge("bottom")}
    </div>
    ${edge("right")}</div>`;
  if (html !== shown) {
    shown = html;
    if (steady || paging) {
      // Same board with new numbers: swap them in without animating again.
      const cur = stage.querySelector(".board:not(.leaving)");
      const cls = steady ? 'class="board steady ' : 'class="board paging ';
      const before = scrolled && cur ? rowTops(cur, b.rows) : null;
      if (cur) cur.outerHTML = html.replace('class="board ', cls);
      else stage.innerHTML = html;
      if (before) scrollUp(before);
    } else {
      // Another board: the old one fades out as the new one comes in over it.
      leave();
      stage.querySelectorAll(".preview-hint").forEach((el) => el.remove());
      stage.insertAdjacentHTML("beforeend", html);
    }
  }
}

// Row by row, scrolling: where each driver's row was (by grid place), and
// copies of the rows (tables / grids) as they were, for the rows going off.
let lastScroll = null;
function rowTops(board, rows) {
  const tops = new Map();
  for (const el of board.querySelectorAll("[data-pos]")) tops.set(el.dataset.pos, el.getBoundingClientRect().top);
  const staying = new Set(rows.map((r) => String(r.pos)));
  const boardRect = board.getBoundingClientRect();
  const k = boardRect.height / board.offsetHeight || 1;  // the stage's scaling
  const ghosts = [];
  for (const box of board.querySelectorAll(".btable, .grid-layout")) {
    const r = box.getBoundingClientRect();
    const copy = box.cloneNode(true);
    let any = false;
    for (const el of copy.querySelectorAll("[data-pos]")) {
      if (staying.has(el.dataset.pos)) el.style.visibility = "hidden";
      else any = true;
    }
    copy.querySelectorAll("thead").forEach((h) => { h.style.visibility = "hidden"; });
    if (any) ghosts.push({ copy, left: (r.left - boardRect.left) / k, top: (r.top - boardRect.top) / k, width: r.width / k });
  }
  return { tops, ghosts, k };
}

// The rows still on screen glide up from where they were; the rows that went
// off the top slide up and fade away above them.
function scrollUp(before) {
  const board = stage.querySelector(".board:not(.leaving)");
  if (!board) return;
  let dy = 0;
  for (const el of board.querySelectorAll("[data-pos]")) {
    const was = before.tops.get(el.dataset.pos);
    if (was == null) continue;
    dy = (was - el.getBoundingClientRect().top) / before.k;
    if (Math.abs(dy) < 1) continue;
    el.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 650, easing: "cubic-bezier(.2, .8, .2, 1)" });
  }
  if (dy <= 0) return;
  for (const g of before.ghosts) {
    const wrap = document.createElement("div");
    wrap.className = "scroll-ghost";
    Object.assign(wrap.style, { position: "absolute", left: `${g.left}px`, top: `${g.top}px`, width: `${g.width}px`, pointerEvents: "none", zIndex: "2" });
    wrap.appendChild(g.copy);
    board.appendChild(wrap);
    wrap.animate([{ transform: "none", opacity: 1 }, { transform: `translateY(${-dy}px)`, opacity: 0 }],
      { duration: 650, easing: "cubic-bezier(.2, .8, .2, 1)" }).onfinish = () => wrap.remove();
  }
}

// Fade out whatever board is on screen, then remove it.
function leave() {
  stage.querySelectorAll(".preview-hint").forEach((el) => el.remove());
  for (const old of stage.querySelectorAll(".board:not(.leaving)")) {
    old.classList.add("leaving");
    setTimeout(() => old.remove(), 700);
  }
}

followSnapshots(render);
