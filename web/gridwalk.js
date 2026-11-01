"use strict";

// Grid walk: the starting grid two cars at a time, seen from a camera standing
// by the track, looking up the grid at an angle. The road, its kerbs, the grass,
// the wall with its catch fence and the grandstand behind it are flat planes in
// one 3D scene: each is drawn flat (textures, painted lines and numbers) and
// put in perspective with a CSS matrix3d worked out from the same camera, so
// everything foreshortens together. The cars (their pictures from the
// thumbnails folder, else a drawing in their livery colours) stand in their
// painted grid boxes, scaled for how far away they are. The cars ahead on the
// grid wait further up the road; moving on to the next pair, the camera glides
// back down the grid to it. Follows the walk the server keeps, so the control
// panel and any number of OBS sources stay in step.

const stage = $("#stage");
fitStage(stage);

let snap = null;
let shownKey = "";
let progress = null;
const DEFAULT_CLASS = { key: "", name: "", color: "#8b93a3", logo: null };
const classFor = (classes, e) => classes.get(e.class_key) || DEFAULT_CLASS;

// --- the world, in metres ------------------------------------------------------
// x: along the road, the way the cars point; y: across it, 0 at the near edge
// (the camera's side), ROAD_W at the far one; z: up.
const ROAD_W = 13;
const LANE = { far: 9.1, near: 3.9 };    // the odd places (pole's side) on the far lane
const SLOT_GAP = 7;                      // metres from one car to the next one behind (a TV grid, drawn snug)
const BOX = { len: 5.6, wid: 2.9 };      // a painted grid box
const WALL_Y = ROAD_W + 4.5;             // the wall, beyond a grass verge
const PIT_WALL_Y = -5;                   // the pit wall on the camera's side, the pit lane behind it
const STAND_Y = WALL_Y + 16;             // the grandstand, behind the fence
const PX = 30;                           // texture pixels a metre on the planes
const X_BACK = 90, X_AHEAD = 110;        // how much of the world, from the pair

// Where grid slot n (1 = pole) is: its box front, on its lane.
const slotX = (n) => -(n - 1) * SLOT_GAP;
const slotY = (n) => (n % 2 ? LANE.far : LANE.near);

// The camera: high up on the near side, a little ahead of the pair, looking
// down across the road at it with a long lens, so the grid runs gently
// downhill from left to right across the screen, the front of the grid on the
// right. az: degrees round from straight across the road towards the front of
// the grid; el: degrees down; dist: metres from the middle of the pair.
const CAM = { az: 12, el: 36, dist: 40, f: 3500, ahead: 0, lookY: 6.4, cx: 900, cy: 560 };
try {  // ?cam=az,el,dist,f,ahead,lookY: for trying out other angles
  const q = new URLSearchParams(location.search).get("cam");
  if (q) q.split(",").map(Number).forEach((v, i) => { if (isFinite(v)) CAM[["az", "el", "dist", "f", "ahead", "lookY"][i]] = v; });
} catch (e) { /* no override */ }

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => { const l = Math.hypot(...a); return [a[0] / l, a[1] / l, a[2] / l]; };

function camera(x0) {
  const mid = x0 - BOX.len / 2 - SLOT_GAP / 2;
  const target = [mid + CAM.ahead, CAM.lookY, 0.5];
  const az = CAM.az * Math.PI / 180, el = CAM.el * Math.PI / 180;
  const pos = [target[0] + CAM.dist * Math.cos(el) * Math.sin(az), target[1] - CAM.dist * Math.cos(el) * Math.cos(az),
    target[2] + CAM.dist * Math.sin(el)];
  const fwd = norm(sub(target, pos));
  const right = norm(cross(fwd, [0, 0, 1]));
  const up = cross(right, fwd);
  return { pos, fwd, right, up };
}

// A world point on screen: [x, y, depth] (depth <= 0: behind the camera).
function project(cam, p) {
  const d = sub(p, cam.pos);
  const z = dot(d, cam.fwd);
  return [CAM.cx + CAM.f * dot(d, cam.right) / z, CAM.cy - CAM.f * dot(d, cam.up) / z, z];
}

// The CSS matrix3d that puts a flat element in perspective: its pixel (s, t)
// is the world point o + s·u + t·v. Screen x, y and w are linear in s and t,
// so it's exact (and the browser clips what's behind the camera).
function planeMatrix(cam, o, u, v) {
  const d = sub(o, cam.pos);
  const row = (k) => [dot(u, k), dot(v, k), dot(d, k)];
  const [Ru, Rv, R0] = row(cam.right);
  const [Uu, Uv, U0] = row(cam.up);
  const [Fu, Fv, F0] = row(cam.fwd);
  const { f, cx, cy } = CAM;
  const X = [cx * Fu + f * Ru, cx * Fv + f * Rv, cx * F0 + f * R0];
  const Y = [cy * Fu - f * Uu, cy * Fv - f * Uv, cy * F0 - f * U0];
  const W = [Fu, Fv, F0];
  const m = [X[0], Y[0], 0, W[0], X[1], Y[1], 0, W[1], 0, 0, 1, 0, X[2], Y[2], 0, W[2]];
  return `matrix3d(${m.map((n) => +n.toFixed(6)).join(",")})`;
}

// --- textures, drawn once ---------------------------------------------------------
const textures = {};
function noiseTexture(name, size, paint) {
  if (textures[name]) return textures[name];
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  paint(g, size);
  return (textures[name] = c.toDataURL("image/png"));
}
const rand = (() => { let s = 7; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })();

function speckle(g, size, base, spread, flecks) {
  const img = g.createImageData(size, size);
  for (let i = 0; i < size * size; i++) {
    const n = (rand() - 0.5) * spread;
    const fleck = rand() < flecks ? 40 + rand() * 50 : 0;
    img.data[i * 4] = base[0] + n + fleck;
    img.data[i * 4 + 1] = base[1] + n + fleck;
    img.data[i * 4 + 2] = base[2] + n + fleck;
    img.data[i * 4 + 3] = 255;
  }
  g.putImageData(img, 0, 0);
}

const asphalt = () => noiseTexture("asphalt", 256, (g, n) => {
  speckle(g, n, [64, 66, 70], 34, 0.012);
  // A few darker patches: repairs and wear.
  for (let i = 0; i < 18; i++) {
    g.fillStyle = `rgba(20,22,26,${0.04 + rand() * 0.06})`;
    g.beginPath();
    g.ellipse(rand() * n, rand() * n, 10 + rand() * 40, 6 + rand() * 20, rand() * 3, 0, 7);
    g.fill();
  }
});
const grass = () => noiseTexture("grass", 256, (g, n) => {
  speckle(g, n, [58, 102, 46], 30, 0);
  for (let i = 0; i < 2600; i++) {  // blades
    g.fillStyle = rand() < 0.5 ? "rgba(120,170,80,.35)" : "rgba(25,55,20,.35)";
    g.fillRect(rand() * n, rand() * n, 1, 2 + rand() * 3);
  }
});
const concrete = () => noiseTexture("concrete", 128, (g, n) => speckle(g, n, [168, 170, 172], 22, 0.004));
// Rows of seats with people in them.
const crowd = () => noiseTexture("crowd", 512, (g, n) => {
  g.fillStyle = "#3b4048";
  g.fillRect(0, 0, n, n);
  const colours = ["#d9dde3", "#c0392b", "#2e86de", "#f1c40f", "#27ae60", "#1b1e24", "#e67e22", "#8e44ad", "#ecf0f1", "#7f8c8d"];
  for (let row = 0; row < n; row += 16) {
    g.fillStyle = "#2a2e35";
    g.fillRect(0, row + 12, n, 4);  // the step
    for (let x = 0; x < n; x += 6 + rand() * 4) {
      if (rand() < 0.22) continue;  // an empty seat
      g.fillStyle = colours[Math.floor(rand() * colours.length)];
      g.fillRect(x, row + 4 + rand() * 2, 4, 7);
      g.fillStyle = "#e0b896";
      g.fillRect(x + 0.5, row + 1 + rand() * 2, 3, 3);
    }
  }
});

// --- the planes -------------------------------------------------------------------
// A flat element in the world: on the ground (s along the road, t towards the
// camera from y = yFar) or standing up (s along the road, t down from z = top).
// Built once; placeScene() puts it in perspective for where the camera is.
function ground(x0, x1, yFar, yNear, cls, inner = "", style = "") {
  const w = Math.round((x1 - x0) * PX), h = Math.round((yFar - yNear) * PX);
  return `<div class="plane ${cls}" data-plane="g,${x0},${yFar}" style="width:${w}px;height:${h}px;${style}">${inner}</div>`;
}
function upright(x0, x1, y, top, bottom, cls, inner = "", style = "") {
  const w = Math.round((x1 - x0) * PX), h = Math.round((top - bottom) * PX);
  return `<div class="plane ${cls}" data-plane="u,${x0},${y},${top}" style="width:${w}px;height:${h}px;${style}">${inner}</div>`;
}

function planeTransform(cam, spec) {
  const [kind, x0, y, top] = spec.split(",");
  return kind === "g"
    ? planeMatrix(cam, [+x0, +y, 0], [1 / PX, 0, 0], [0, -1 / PX, 0])
    : planeMatrix(cam, [+x0, +y, +top], [1 / PX, 0, 0], [0, 0, -1 / PX]);
}

// What's painted on the road, in its own pixels (x0: the road's start).
// In front of each box, its number and, under it, the car's qualifying gap
// (pole: its lap time), as painted for a TV grid.
function paint(x0, slots, pole, entries) {
  const at = (x, y) => [Math.round((x - x0) * PX), Math.round((ROAD_W - y) * PX)];
  const out = [];
  for (const n of slots) {
    const [l, t] = at(slotX(n) - BOX.len, slotY(n) + BOX.wid / 2);
    // The box: the line across the front, and down both sides, open at the back.
    out.push(`<div class="box" style="left:${l}px;top:${t}px;width:${BOX.len * PX}px;height:${BOX.wid * PX}px"></div>`);
    const [nl, nt] = at(slotX(n) + 0.7, slotY(n) + 1.45);
    const e = entries[n - 1];
    const qual = e && look.track_qual !== false ? qualText(e, look.qual_shown) : "";
    out.push(`<div class="slot-num" style="left:${nl}px;top:${nt}px">${n}${qual ? `<small>${esc(qual)}</small>` : ""}</div>`);
  }
  if (pole) {  // the start line, just ahead of pole
    const [l] = at(slotX(1) + 9, 0);
    out.push(`<div class="start-line" style="left:${l}px"></div>`);
  }
  return out.join("");
}

// --- the cars ---------------------------------------------------------------------
function carArt(e, cfg) {
  if (e.car_image) return `<img src="${esc(e.car_image)}" alt="" class="${cfg.flip_cars ? "flip" : ""}">`;
  return carSvg(e.car_design, e.number);  // no picture: a drawing in its livery colours
}

// A car standing in its box: the bottom of the picture at the middle of the
// box, as wide as a car is long at that distance.
function carPlace(cam, n) {
  const x = slotX(n) - BOX.len / 2, y = slotY(n);
  const [sx, sy, z] = project(cam, [x, y, 0]);
  // Pixels a metre there, at the size set (all the cars, then the row's own).
  const row = n % 2 ? "top" : "bottom";  // the far lane (P1, P3...) is the top row on screen
  const scale = (CAM.f / z) * ((look.car_scale || 100) / 100) * ((look[`car_scale_${row}`] || 100) / 100);
  return { sx: sx + (look[`car_${row}_x`] || 0), sy: sy + (look[`car_${row}_y`] || 0), z, w: 4.9 * scale, h: 2.2 * scale };
}

let look = {};  // the grid walk's settings, as last drawn

// --- the driver panels ------------------------------------------------------------
// Their qualifying, as picked (qual_shown): the gap to their class pole, the
// interval to the car ahead of them in class, or the lap time. The class
// pole shows its lap time with a gap or an interval.
function qualText(e, how = "gap") {
  if (how === "none" || !e.qual_time) return "";
  if (how === "gap" && e.qual_gap) return `+${e.qual_gap.toFixed(3)}`;
  if (how === "interval" && e.qual_int) return `+${e.qual_int.toFixed(3)}`;
  return fmtLap(e.qual_time);
}

// The grid place, as the driver card shows a position: overall, in class, or both.
function placeHtml(e, cfg, cls) {
  const which = cfg.position_shown || "overall";
  const name = cfg.pos_class_name !== false && cls.name ? esc(cls.name) : "";
  if (which === "class" && e.class_pos) return `<span class="p">P${e.class_pos}</span>${name ? `<span class="cp">${name}</span>` : ""}`;
  if (which === "both" && e.class_pos) return `<span class="p">P${e.grid_pos}</span><span class="cp">P${e.class_pos}${name ? ` ${name}` : ""}</span>`;
  return `<span class="p">P${e.grid_pos}</span>`;
}

// Each driver's card, in the style of the driver-on-camera card (driver.html):
// the grid place on the class colour, the car number, the name with the
// nickname under it, the team with its logo, the qualifying time, the car badge.
function infoHtml(e, i, cls, cfg, multiclass) {
  const status = cfg.show_status === false ? "" : !e.in_session ? "NOT IN SESSION" : !e.in_world ? "NOT ON TRACK" : "";
  const qual = qualText(e, cfg.qual_shown);
  // Their class colour (main or secondary, as set), or none.
  const color = paintFor(e, cls, cfg.class_colors) || "";
  const nick = cfg.show_nickname !== false && e.nickname && cfg.name_format !== "nickname" ? e.nickname : "";
  const logo = cfg.show_class !== false && (multiclass || cls.logo) && classLogo(cls, rerender);  // the class logo, laid on its colour
  const klass = cfg.show_class === false ? "" : logo ? `<span class="klass has-logo" style="background:${esc(color)}"><img class="klass-logo" src="${esc(logo.url)}" alt="${esc(cls.name)}"></span>`
    : multiclass && cls.name ? `<span class="klass" style="background:${esc(color)};color:${inkFor(color)}">${esc(cls.name)}</span>` : "";
  const teamLogo = cfg.show_logo !== false && e.team_logo ? `<img class="team-logo" src="${esc(e.team_logo)}" alt="">` : "";
  const teamName = cfg.show_team !== false && e.team ? `<span class="team-name">${esc(e.team)}</span>` : "";
  const team = teamLogo || teamName ? `<div class="team">${teamLogo}${teamName}</div>` : "";
  const number = cfg.show_number === false || !e.number ? ""
    : color ? `<span class="num" style="background:${esc(color)};color:${inkFor(color)}">${esc(e.number)}</span>` : `<span class="num plain">${esc(e.number)}</span>`;
  return `<div class="gw-info ${i ? "rear" : "front"}" style="--cls:${esc(color || "var(--accent)")}">
      ${cfg.show_position !== false ? `<div class="pos" style="color:${color ? inkFor(color) : "#fff"}">${placeHtml(e, cfg, cls)}</div>` : ""}
      <div class="who">${number}
        <div class="names"><div class="name">${esc(formatName(e, cfg.name_format))}${klass}</div>
          ${nick ? `<div class="nick">“${esc(nick)}”</div>` : ""}${team}</div></div>
      ${qual || status ? `<div class="qual">${qual ? `<span class="t">${esc(qual)}</span>` : ""}${status ? `<span class="status">${status}</span>` : ""}</div>` : ""}
      ${cfg.show_make !== false && e.make_logo ? `<span class="make"><img src="${esc(e.make_logo)}" alt="${esc(e.make)}"></span>` : ""}
    </div>`;
}

// --- the scene --------------------------------------------------------------------
// The scene for the camera anywhere from x0 to x1 (box fronts), showing the
// grid from slot ``first`` (and the cars ahead of it).
function sceneHtml(x0, x1, first, entries, cfg) {
  const a = Math.min(x0, x1) - X_BACK, b = Math.max(x0, x1) + X_AHEAD;
  const league = (snap.league && snap.league.name) || "";
  const boards = Array.from({ length: Math.ceil((b - a) / 9) }, (_, i) =>
    `<span class="${i % 3 === 1 ? "alt" : ""}">${esc(league || "STARTING GRID")}</span>`).join("");
  // The slots in view wherever the camera is between x0 and x1: some ahead
  // (to the right) and some behind (to the left).
  const [lo, hi] = [x0, x1].map((x) => 1 - Math.round(x / SLOT_GAP)).sort((u, v) => u - v);
  const slots = [];
  for (let n = Math.max(1, lo - 14); n <= hi + 13; n++) slots.push(n);
  // The pair, and the cars either side unless they're hidden (then, gliding
  // from one pair to the next, the last pair fades as the camera moves).
  const pairOf = (n) => n === first || n === first + 1;
  const going = (n) => !pairOf(n) && (n === lo || n === lo + 1 || n === hi || n === hi + 1) && x0 !== x1;
  const cars = slots.filter((n) => n >= lo - 8 && n <= Math.min(entries.length, hi + 9))
    .filter((n) => cfg.neighbours !== "hide" || pairOf(n) || going(n));
  const art = cars.map((n) => `<div class="gw-car ${pairOf(n) ? "focus" : "other"} ${cfg.neighbours === "hide" && !pairOf(n) ? "going" : ""}" data-slot="${n}">${carArt(entries[n - 1], cfg)}</div>`).join("");
  const shadows = cars.map((n) => {
    const l = Math.round((slotX(n) - BOX.len + 0.2 - a) * PX), t = Math.round((ROAD_W - slotY(n) - 1.15) * PX);
    return `<i class="shadow ${cfg.neighbours === "hide" && !pairOf(n) ? "going" : ""}" data-shadow="${n}" style="left:${l}px;top:${t}px;width:${(BOX.len - 0.4) * PX}px;height:${2.3 * PX}px"></i>`;
  }).join("");
  return `<div class="scene">
    <div class="sky"></div>
    ${upright(a, b, STAND_Y, 15, 0, "stand", "", `background-image:url(${crowd()})`)}
    ${upright(a, b, STAND_Y - 0.5, 17, 14.5, "roof")}
    ${ground(a, b, STAND_Y, WALL_Y, "verge far", "", `background-image:url(${grass()})`)}
    ${ground(a, b, WALL_Y, ROAD_W, "verge", "", `background-image:url(${grass()})`)}
    ${ground(a, b, PIT_WALL_Y, -24, "pitlane", `<div class="pit-lines"></div>`, `background-image:url(${asphalt()})`)}
    ${ground(a, b, -2.5, PIT_WALL_Y, "verge near", "", `background-image:url(${grass()})`)}
    ${ground(a, b, ROAD_W + 1.1, ROAD_W, "kerb far")}
    ${ground(a, b, 0, -1.1, "kerb near")}
    ${ground(a, b, -1.1, -2.5, "apron", "", `background-image:url(${asphalt()})`)}
    ${ground(a, b, ROAD_W, 0, "road", `<div class="rubber"></div>${paint(a, slots, slots.includes(1), entries)}${shadows}`,
      `background-image:url(${asphalt()})`)}
    ${upright(a, b, WALL_Y, 1.1, 0, "wall", `<div class="ads">${boards}</div>`, `background-image:url(${concrete()})`)}
    ${upright(a, b, WALL_Y, 4.6, 1.1, "fence")}
    ${art}
    ${upright(a, b, PIT_WALL_Y, 1, 0, "wall pit-wall", "", `background-image:url(${concrete()})`)}
    <div class="haze"></div>
  </div>`;
}

// Put the scene in perspective for the camera at x (a box front).
function placeScene(root, x) {
  const cam = camera(x);
  root.querySelectorAll("[data-plane]").forEach((el) => { el.style.transform = planeTransform(cam, el.dataset.plane); });
  const cars = [...root.querySelectorAll(".gw-car")].map((el) => ({ el, p: carPlace(cam, +el.dataset.slot) }));
  for (const { el, p } of cars) {
    el.hidden = p.z < 2;  // behind the camera
    if (el.hidden) continue;
    const st = el.style;
    st.left = `${(p.sx - p.w / 2).toFixed(1)}px`;
    st.top = `${(p.sy - p.h * 0.86).toFixed(1)}px`;
    st.width = `${p.w.toFixed(1)}px`;
    st.height = `${p.h.toFixed(1)}px`;
    st.setProperty("--haze", Math.min(0.55, Math.max(0, (p.z - CAM.dist - 6) / 120)).toFixed(2));
    st.zIndex = String(1000 - Math.round(p.z));  // the near ones stand in front
    // A row moved off its boxes: its shadow comes with it (under the car), not left on the road.
    const row = +el.dataset.slot % 2 ? "top" : "bottom";
    st.setProperty("--rot", `${look[`car_${row}_rotate`] || 0}deg`);  // turned to line up with its box
    const moved = !!(look[`car_${row}_x`] || look[`car_${row}_y`]);
    el.classList.toggle("own-shadow", moved);
    const road = root.querySelector(`[data-shadow="${el.dataset.slot}"]`);
    if (road) road.hidden = moved;
  }
}

function walkHtml(g, pair, entries, classes, cfg, multiclass, x0) {
  const row = Math.floor(g.index / 2) + 1;
  const title = (snap.league && snap.league.name) || "Starting grid";
  const track = snap.session && snap.session.track;
  return `<div class="walk">
    <div id="scene">${sceneHtml(x0, x0, g.index + 1, entries, cfg)}</div>
    <div class="gw-title"><span class="t1">${esc(title)}</span>${track ? `<span class="t2">${esc(track)}</span>` : ""}
      <span class="t3">STARTING GRID · ROW ${row}</span><div class="progress"><i id="progress"></i></div></div>
    ${pair.map((e, i) => infoHtml(e, i, classFor(classes, e), cfg, multiclass)).join("")}
  </div>`;
}

// Gliding from one pair to the next: the scene is redrawn for a camera moving
// down the grid, then the new drivers' panels come in.
let glide = null;
let cameraX = null;
const GLIDE_MS = 1300;
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

function glideTo(target, build) {
  if (glide) cancelAnimationFrame(glide.raf);
  const from = cameraX;
  if (from == null || Math.abs(target - from) > SLOT_GAP * 6 || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    cameraX = target;
    placeScene(build(target, target), target);
    return;
  }
  const root = build(from, target);
  const draw = (x) => placeScene(root, x);
  const t0 = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - t0) / GLIDE_MS);
    cameraX = from + (target - from) * ease(t);
    draw(cameraX);
    glide = t < 1 ? { raf: requestAnimationFrame(step) } : null;
  };
  glide = { raf: requestAnimationFrame(step) };
}

function rerender() {
  shownKey = "";
  render();
}

function render() {
  const g = snap && snap.gridwalk;
  if (!g) return;
  const cfg = (snap.overlays && snap.overlays.settings.gridwalk) || {};
  look = cfg;
  document.body.style.setProperty("--card-k", String((cfg.card_scale || 100) / 100));
  const entries = g.entries || [];
  const classes = new Map((snap.classes || []).map((c) => [c.key, c]));
  const pair = entries.slice(g.index, g.index + 2);
  progress = { elapsed: g.elapsed, interval: g.interval, running: g.running && g.visible && g.autoplay !== false, at: performance.now() };
  const show = g.visible && pair.length > 0;
  setPanels(cfg);
  setSize(cfg, true, true);
  // Only rebuild when what's on screen changes, so the animations play once.
  const key = JSON.stringify([show, g.index, pair, entries.slice(Math.max(0, g.index - 8), g.index).map((e) => [e.key, e.car_image, e.car_design]),
    pair.map((e) => classes.get(e.class_key) || null), cfg.flip_cars, cfg.name_format, cfg.show_nickname, cfg.neighbours,
    ["car_scale", "show_position", "position_shown", "pos_class_name", "show_number", "show_team", "show_logo", "show_make",
      "show_class", "class_colors", "qual_shown", "track_qual", "logo_scale", "car_scale_top", "car_scale_bottom",
      "car_top_x", "car_top_y", "car_bottom_x", "car_bottom_y", "card_scale", "show_status", "car_top_rotate", "car_bottom_rotate"].map((k) => cfg[k]),
    snap.league && snap.league.name, snap.session && snap.session.track]);
  if (key === shownKey) return;
  const samePair = shownKey && JSON.parse(shownKey)[1] === g.index && JSON.parse(shownKey)[0] === show;
  shownKey = key;
  stage.classList.toggle("hidden", !show);
  if (!show) {
    cameraX = null;  // next time it comes on, it starts at its pair
    return;          // the last pair stays while it fades out
  }
  const multiclass = new Set(entries.map((e) => e.class_key)).size > 1;
  const target = slotX(g.index + 1);
  if (samePair || cameraX == null || !stage.querySelector(".walk")) {
    if (glide) cancelAnimationFrame(glide.raf);
    glide = null;
    cameraX = target;
    stage.innerHTML = walkHtml(g, pair, entries, classes, cfg, multiclass, target);
    placeScene($("#scene"), target);
    return;
  }
  // A new pair: the old panels go, the camera glides, the new panels come in.
  stage.querySelectorAll(".gw-info").forEach((el) => el.classList.add("leaving"));
  const html = walkHtml(g, pair, entries, classes, cfg, multiclass, target);
  const holder = document.createElement("div");
  holder.innerHTML = html;
  const panels = [...holder.querySelectorAll(".gw-info")];
  panels.forEach((p) => p.remove());
  const walk = stage.querySelector(".walk");
  walk.querySelector(".gw-title").outerHTML = holder.querySelector(".gw-title").outerHTML;
  glideTo(target, (from, to) => {
    const root = $("#scene");
    root.innerHTML = sceneHtml(from, to, g.index + 1, entries, cfg);
    return root;
  });
  setTimeout(() => {
    walk.querySelectorAll(".gw-info.leaving").forEach((el) => el.remove());
    panels.forEach((p) => walk.appendChild(p));
  }, GLIDE_MS * 0.7);
}

function tickProgress() {
  const bar = document.getElementById("progress");
  if (bar && progress) {
    const extra = progress.running ? (performance.now() - progress.at) / 1000 : 0;
    bar.style.width = `${Math.min(100, ((progress.elapsed + extra) / progress.interval) * 100)}%`;
  }
  requestAnimationFrame(tickProgress);
}
requestAnimationFrame(tickProgress);

stage.classList.add("hidden");
followSnapshots((s) => {
  snap = s;
  render();
});
