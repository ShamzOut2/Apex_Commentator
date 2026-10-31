"use strict";

// Shared by the control panel (app.js) and the broadcast pages.

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

// White stays as long as it keeps 3:1 contrast on the class colour (the
// large-text minimum); lighter colours get near-black instead.
function inkFor(hex) {
  const [r, g, b] = hexToRgb(hex).map((v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return 1.05 / (luminance + 0.05) >= 3 ? "#fff" : "#111";
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

// Layered SVGs (made by tools/logo_to_svg.py, or hand-made) mark their
// parts: data-apex-fill="class" takes the class colour exactly, and
// data-apex-fill="ink" stays white unless the class colour is too light for
// it. Returns null for any other image so it goes through pixel recolouring.
async function recolourLayeredSvg(src, color, keep) {
  if (!/\.svg$/i.test(src)) return null;
  const text = await (await fetch(src)).text();
  const doc = new DOMParser().parseFromString(text, "image/svg+xml");
  const layers = doc.querySelectorAll('[data-apex-fill="class"]');
  if (doc.querySelector("parsererror") || !layers.length) return null;
  if (keep) return { url: src, detected: "layered" };
  layers.forEach((el) => el.setAttribute("fill", color));
  const ink = inkFor(color) === "#fff" ? "#ffffff" : "#111111";
  doc.querySelectorAll('[data-apex-fill="ink"]').forEach((el) => el.setAttribute("fill", ink));
  const blob = new Blob([new XMLSerializer().serializeToString(doc)], { type: "image/svg+xml" });
  return { url: URL.createObjectURL(blob), detected: "layered" };
}

async function processLogo(src, color, mode, tolerance, fill) {
  const layered = await recolourLayeredSvg(src, color, mode === "keep");
  if (layered) return layered;
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
    ${logo ? `<img class="class-logo" src="${esc(logo.url)}" alt="${esc(cls.name)}" title="${esc(cls.name)}">`
      : `<span class="class-name">${esc(cls.name)}</span>`}${detail ? `<span class="class-detail">${esc(detail)}</span>` : ""}
  </div>`;
}

// ---------------------------------------------------------------------------
// team logos: never in a white box
// ---------------------------------------------------------------------------
// Team logos often come with a white (or near-white) box around them. Every
// page shows them without it: the plain light background touching the
// image's edges becomes see-through, and a logo that was dark on white turns
// light so it reads on the dark panels. Done once per logo, in the browser
// (OBS included), whatever page draws it.

const TEAM_LOGO = /^\/api\/logos\/[^/]+\/team-[^/]+$/;
const clearedLogos = new Map();  // src -> url to show, or a Promise of one

async function clearLogoBackground(src) {
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
  const px = data.data;
  const bg = detectBackground(px, w, h);
  // Already see-through, or a coloured badge: shown as it is.
  if (bg.transparent || Math.min(...bg.rgb) < 200) return src;
  const t = 0.12;
  const n = w * h;
  const dist = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    dist[i] = px[o + 3] < ALPHA_CLEAR ? 0 : Math.hypot(px[o] - bg.rgb[0], px[o + 1] - bg.rgb[1], px[o + 2] - bg.rgb[2]) / 441.7;
  }
  const gone = new Uint8Array(n);
  const queue = new Int32Array(n);
  let head = 0, tail = 0;
  const seed = (i) => {
    if (!gone[i] && dist[i] <= t) {
      gone[i] = 1;
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
  let solid = 0, dark = 0;
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    if (gone[i]) {
      px[o + 3] = 0;
      continue;
    }
    const x = i % w;
    const edge = (x > 0 && gone[i - 1]) || (x < w - 1 && gone[i + 1]) || (i >= w && gone[i - w]) || (i < n - w && gone[i + w]);
    if (edge) {
      // Anti-aliased edge: take out the share of white it was blended with.
      const k = Math.min(0.95, Math.max(0, 1 - (dist[i] - t) / (t * 1.5)));
      for (let c = 0; c < 3; c++) px[o + c] = Math.min(255, Math.max(0, (px[o + c] - k * bg.rgb[c]) / (1 - k)));
      px[o + 3] *= 1 - k;
    }
    if (px[o + 3] > 128) {
      solid++;
      if (px[o] * 0.3 + px[o + 1] * 0.59 + px[o + 2] * 0.11 < 90) dark++;
    }
  }
  // Dark on white (black lettering, say): light instead, or it would vanish.
  if (solid && dark / solid > 0.5) {
    for (let o = 0; o < px.length; o += 4) {
      const lum = px[o] * 0.3 + px[o + 1] * 0.59 + px[o + 2] * 0.11;
      if (px[o + 3] && lum < 110 && Math.max(px[o], px[o + 1], px[o + 2]) - Math.min(px[o], px[o + 1], px[o + 2]) < 60) {
        px[o] = px[o + 1] = px[o + 2] = 255 - lum * 0.5;
      }
    }
  }
  ctx.putImageData(data, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  return URL.createObjectURL(blob);
}

function showClearedLogo(img) {
  const src = img.getAttribute("src");
  if (!src || !TEAM_LOGO.test(src)) return;
  let hit = clearedLogos.get(src);
  if (typeof hit === "string") {
    if (hit !== src) img.src = hit;
    return;
  }
  if (!hit) {
    hit = clearLogoBackground(src).catch(() => src).then((url) => {
      clearedLogos.set(src, url);
      return url;
    });
    clearedLogos.set(src, hit);
  }
  img.style.visibility = "hidden";  // never flash the white box
  hit.then((url) => {
    if (img.getAttribute("src") === src && url !== src) img.src = url;
    img.style.visibility = "";
  });
}

// New logos are swapped as they're added, before they're painted.
new MutationObserver((changes) => {
  for (const change of changes) {
    for (const node of change.addedNodes) {
      if (node.nodeType !== 1) continue;
      if (node.tagName === "IMG") showClearedLogo(node);
      else node.querySelectorAll("img").forEach(showClearedLogo);
    }
  }
}).observe(document.documentElement, { childList: true, subtree: true });

// ---------------------------------------------------------------------------
// liveries: a stylised car and helmet in a driver's iRacing paint colours,
// used whenever no photo has been uploaded for them
// ---------------------------------------------------------------------------

let liveryIds = 0;

function designColors(design, fallback) {
  const c = (design && design.colors) || [];
  return [c[0] || fallback[0], c[1] || fallback[1], c[2] || fallback[2]];
}

// Accent shapes for a pattern number, drawn inside the clipped body/shell.
// iRacing has many patterns; these four families stand in for them.
function liveryAccents(pattern, w, h, c2, c3) {
  switch (Math.abs(pattern || 0) % 4) {
    case 0: // side band with pinstripe
      return `<rect x="0" y="${h * 0.52}" width="${w}" height="${h * 0.14}" fill="${c2}"/>
              <rect x="0" y="${h * 0.68}" width="${w}" height="${h * 0.04}" fill="${c3}"/>`;
    case 1: // diagonal split
      return `<polygon points="${w * 0.42},0 ${w},0 ${w},${h} ${w * 0.22},${h}" fill="${c2}"/>
              <polygon points="${w * 0.36},0 ${w * 0.42},0 ${w * 0.22},${h} ${w * 0.16},${h}" fill="${c3}"/>`;
    case 2: // twin stripes over the top
      return `<rect x="0" y="0" width="${w}" height="${h * 0.12}" fill="${c2}"/>
              <rect x="0" y="${h * 0.14}" width="${w}" height="${h * 0.06}" fill="${c3}"/>`;
    default: // contrasting nose and tail
      return `<rect x="0" y="0" width="${w * 0.24}" height="${h}" fill="${c2}"/>
              <rect x="${w * 0.78}" y="0" width="${w * 0.22}" height="${h}" fill="${c2}"/>
              <rect x="${w * 0.24}" y="0" width="${w * 0.02}" height="${h}" fill="${c3}"/>`;
  }
}

function carSvg(design, number, { mirror = false } = {}) {
  const id = `lv${++liveryIds}`;
  const [c1, c2, c3] = designColors(design, ["#d0d4da", "#1b76d1", "#111111"]);
  const body = "M18 96 L18 74 Q20 63 40 61 L122 56 Q150 30 204 27 L252 27 Q286 30 308 52 L362 61 Q387 66 391 84 L391 96 Z";
  return `<svg class="livery livery-car" viewBox="0 0 410 130" xmlns="http://www.w3.org/2000/svg" ${mirror ? 'style="transform:scaleX(-1)"' : ""}>
    <defs><clipPath id="${id}"><path d="${body}"/></clipPath></defs>
    <ellipse cx="205" cy="120" rx="190" ry="8" fill="rgba(0,0,0,.35)"/>
    <rect x="16" y="40" width="44" height="7" rx="2" fill="${c3}"/><rect x="34" y="46" width="5" height="16" fill="#222"/>
    <path d="${body}" fill="${c1}"/>
    <g clip-path="url(#${id})">${liveryAccents(design && design.pattern, 410, 100, c2, c3)}</g>
    <path d="${body}" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="2"/>
    <path d="M140 57 Q162 36 204 33 L250 33 Q276 36 294 54 Z" fill="#1d2633"/>
    <path d="M150 54 Q168 40 204 38 L222 38 L210 54 Z" fill="rgba(255,255,255,.18)"/>
    <rect x="18" y="92" width="373" height="6" fill="#151515"/>
    <circle cx="232" cy="74" r="17" fill="#fff" stroke="#111" stroke-width="2"/>
    <text x="232" y="81" text-anchor="middle" font-family="system-ui,sans-serif" font-weight="800" font-size="19" fill="#111"
      ${mirror ? 'transform="translate(464 0) scale(-1 1)"' : ""}>${esc(number)}</text>
    <g fill="#141414"><circle cx="96" cy="98" r="24"/><circle cx="318" cy="98" r="24"/></g>
    <g fill="#8a9099"><circle cx="96" cy="98" r="12"/><circle cx="318" cy="98" r="12"/></g>
    <g fill="#3a3f46"><circle cx="96" cy="98" r="5"/><circle cx="318" cy="98" r="5"/></g>
  </svg>`;
}

// ---------------------------------------------------------------------------
// broadcast pages
// ---------------------------------------------------------------------------

// Driver name in one of the overlay formats (see apex/overlays.py).
// The colour a driver is shown in (car number, bar, card): with a league
// active, their main or secondary class's (``which``, the overlay's
// class_colors setting), or null (no colour: a plain number, no bar) when
// they have none; without a league, the iRacing class colour.
function paintFor(e, cls, which) {
  if (!e || !e.paint) return cls.color;
  return (which === "secondary" ? e.paint.secondary : e.paint.main) || null;
}

function formatName(e, format) {
  const full = String(e.name || "").trim();
  const parts = full.split(/\s+/);
  const first = parts.length > 1 ? parts[0] : "";
  const last = parts.length > 1 ? parts.slice(1).join(" ") : full;
  switch (format) {
    case "initial_last": return first ? `${first[0]}. ${last}` : last;
    case "last_initial": return first ? `${last} ${first[0]}.` : last;
    case "last": return last;
    case "first": return first || last;
    case "abbrev": return last.replace(/[^\p{L}]/gu, "").slice(0, 3).toUpperCase();
    case "nickname": return e.nickname || full;
    default: return full;
  }
}

// Redraw a list and slide each row from where it was to its new place, so
// drivers swapping positions glide past each other. Rows carry data-key.
// Rows new to the list fade in. Works through redraws mid-slide: a row
// carries on from wherever it had got to.
function flipRows(container, selector, redraw, ms = 450, keyOf = (el) => el.dataset.key) {
  const before = new Map();
  container.querySelectorAll(selector).forEach((el) => before.set(keyOf(el), el.getBoundingClientRect().top));
  redraw();
  const moved = [];
  const hadRows = before.size > 0;
  container.querySelectorAll(selector).forEach((el) => {
    const top = before.get(keyOf(el));
    if (top === undefined) {
      if (hadRows) el.classList.add("row-enter");
      return;
    }
    const rect = el.getBoundingClientRect();
    const scale = el.offsetHeight ? rect.height / el.offsetHeight : 1;  // the stage is scaled to fit
    const dy = (top - rect.top) / (scale || 1);
    if (Math.abs(dy) < 1) return;
    el.style.transition = "none";
    el.style.transform = `translateY(${dy}px)`;
    moved.push(el);
  });
  if (!moved.length) return;
  container.getBoundingClientRect();  // apply the start positions before sliding
  for (const el of moved) {
    el.style.transition = `transform ${ms}ms cubic-bezier(.2, .8, .2, 1)`;
    el.style.transform = "";
  }
}

// An animation that keeps going across redraws: elements re-created mid-way
// start where the last one had got to (a negative animation-delay).
function ongoing(since, ms) {
  const elapsed = performance.now() - since;
  return elapsed < ms ? `animation-delay:-${Math.round(elapsed)}ms` : null;
}

// A stopwatch icon (fastest lap), coloured by CSS (currentColor).
const STOPWATCH = '<svg class="stopwatch" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M9 1h6v2H9zm10.03 6.39 1.42-1.42-1.41-1.41-1.42 1.42A8.96 8.96 0 0 0 12 4a9 9 0 1 0 9 9c0-2.12-.74-4.07-1.97-5.61zM12 20a7 7 0 1 1 0-14 7 7 0 0 1 0 14zm-1-12h2v6h-2z"/></svg>';

// A chequered flag on its pole (a driver who's finished): the cloth waves (CSS .fin-flag).
const FINISH_FLAG = '<svg class="fin-svg" viewBox="0 0 26 24" aria-hidden="true">'
  + '<defs><pattern id="fin-check" width="8" height="8" patternUnits="userSpaceOnUse">'
  + '<rect width="8" height="8" fill="#f4f4f4"/><rect width="4" height="4" fill="#111"/><rect x="4" y="4" width="4" height="4" fill="#111"/></pattern></defs>'
  + '<rect x="2" y="1.5" width="2" height="21.5" rx="1" fill="#cfd3d8"/>'
  + '<g class="fin-cloth"><rect x="4" y="2.5" width="20" height="13" fill="url(#fin-check)" stroke="rgba(0,0,0,.35)" stroke-width=".5"/></g></svg>';

// Fixed 1920x1080 stage, scaled to fit the browser source. setStageSize()
// then makes the whole stage bigger or smaller around the middle (boards,
// full screens, the grid walk).
let fitNow = () => {};
let stageSize = 1;
let stageOffset = [0, 0];  // an overlay moved from where it sits (offset_x / offset_y), in 1920×1080 px

function fitStage(stage) {
  const fit = () => {
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    stage.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`
      + (stageOffset[0] || stageOffset[1] ? ` translate(${stageOffset[0]}px, ${stageOffset[1]}px)` : "")
      + (stageSize !== 1 ? ` translate(960px, 540px) scale(${stageSize}) translate(-960px, -540px)` : "");
  };
  fitNow = fit;
  addEventListener("resize", fit);
  fit();
  if (new URLSearchParams(location.search).has("preview")) document.body.classList.add("preview");
  // Straight on the user's screen (see desktop.py): no soft shadows, which
  // can't be see-through there and would show as dark smudges.
  const desk = new URLSearchParams(location.search).get("desktop");
  if (desk) {
    document.body.classList.add("desktop");
    reportDeskParts(desk);
  }
}

// On the user's own screen, the app cuts the overlay's window down to where
// the page draws (desktop.py), so nothing else of the screen is covered and
// the mouse goes straight through everywhere else. This tells it where:
// the visible parts below, in window pixels, whenever they change. Full-screen
// versions (?screen=1) are a whole screen.
const DESK_PARTS = {
  "/standings.html": "#tower, .fl-pill",
  "/laps.html": ".tracker",
  "/driver.html": "#slot > *",
  "/sponsors.html": ".sp",
  "/gridwalk.html": ".gw-title, .gw-track, .gw-info",
  "/board.html": "#stage > *",
  "/battle.html": ".battle:not(.out)",
  "/pits.html": ".pit-card",
};

function reportDeskParts(page) {
  const whole = new URLSearchParams(location.search).has("screen");
  const parts = DESK_PARTS[location.pathname];
  let sent = null;
  const shows = (el) => !el.checkVisibility || el.checkVisibility({ opacityProperty: true, visibilityProperty: true });
  const tick = () => {
    let rects = null;
    if (!whole && parts) {
      const k = devicePixelRatio || 1;
      const pad = 3;  // anti-aliased edges and the odd pixel of movement
      rects = [...document.querySelectorAll(parts)].filter(shows).map((el) => el.getBoundingClientRect())
        .filter((r) => r.width > 1 && r.height > 1)
        .map((r) => [Math.floor(r.left * k) - pad, Math.floor(r.top * k) - pad, Math.ceil(r.width * k) + 2 * pad, Math.ceil(r.height * k) + 2 * pad]);
    }
    const key = JSON.stringify(rects);
    if (key === sent) return;
    sent = key;
    fetch("/api/cmd", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "desktop_region", params: { page, rects } }) })
      .catch(() => { sent = null; });  // try again next time
  };
  setInterval(tick, 100);
  tick();
}

// The Background setting (a solid colour or an uploaded image, at the opacity
// set) means two things:
// - overlays (tower, lap tracker, sponsors, grid walk): the overlay's own
//   panels, nothing else (setPanels);
// - boards and full-screen pages, which are a whole screen: that screen's
//   backdrop (setBackground), shown only while there's something on screen.

// Custom background per column (cfg.col_opacity_on): every column (the
// cells marked data-opcol) gets a background of cfg.col_bg_color, at its own
// opacity (cfg.col_opacity "gap:60,laps:40", percent; columns left out 100).
// The text stays as it is. body.col-bg lets each page drop the background it
// would otherwise have behind the rows (standings.css).
let colOpacityCss = null;
function setColumnOpacity(cfg) {
  const on = !!(cfg && cfg.col_opacity_on);
  document.body.classList.toggle("col-bg", on);
  const color = on && /^#[0-9a-f]{6}$/i.test(cfg.col_bg_color || "") ? cfg.col_bg_color : "#0e1015";
  const css = on ? [`body.col-bg [data-opcol] { position: relative; isolation: isolate; }`,
    `body.col-bg [data-opcol]::before { content: ""; position: absolute; inset: 0; z-index: -1; pointer-events: none;
      background: ${color}; opacity: var(--colbg, 1); }`,
    ...String(cfg.col_opacity || "").split(",").map((p) => p.split(":"))
      .filter(([k, v]) => /^[a-z_]+$/.test(k || "") && /^\d+$/.test(v || ""))
      .map(([k, v]) => `[data-opcol="${k}"] { --colbg: ${Math.min(100, +v) / 100}; }`)].join("\n") : "";
  if (css === colOpacityCss) return;
  colOpacityCss = css;
  let el = document.getElementById("col-opacity");
  if (!el) {
    el = document.createElement("style");
    el.id = "col-opacity";
    document.head.appendChild(el);
  }
  el.textContent = css;
}

// The Size setting (scale, percent). Overlays: their own elements grow or
// shrink from where they sit (CSS zoom via --ov-size, in each page's CSS).
// Boards and full screens: the whole stage, around the middle.
function setSize(cfg, whole = false, moved = !whole) {
  const k = ((cfg && cfg.scale) || 100) / 100;
  document.body.style.setProperty("--ov-size", String(whole ? 1 : k));
  const stage = whole ? k : 1;
  // Overlays (not boards or full screens) can be moved: offset_x / offset_y.
  const off = moved && cfg ? [+cfg.offset_x || 0, +cfg.offset_y || 0] : [0, 0];
  if (stage !== stageSize || off[0] !== stageOffset[0] || off[1] !== stageOffset[1]) {
    stageSize = stage;
    stageOffset = off;
    fitNow();
  }
}

// Overlays: their panels take the colour, or show the image inside them
// (overlay.css / gridwalk.css: body.panel-image). Everything else stays
// see-through.
function setPanels(cfg) {
  const mode = cfg ? cfg.bg : "default";
  const st = document.body.style;
  const op = (cfg && cfg.bg_opacity != null ? cfg.bg_opacity : 100) / 100;
  const image = mode === "image" && cfg.bg_image;
  document.body.classList.toggle("custom-panels", mode === "color" || !!image);
  document.body.classList.toggle("panel-image", !!image);
  if (mode === "color") {
    const [r, g, b] = hexToRgb(cfg.bg_color);
    st.setProperty("--panel", `rgba(${r}, ${g}, ${b}, ${op})`);
  } else if (image) {
    st.setProperty("--panel", "transparent");
    st.setProperty("--panel-image", `url("/api/backgrounds/${encodeURIComponent(cfg.bg_image)}")`);
    st.setProperty("--panel-opacity", String(op));
  } else {
    st.removeProperty("--panel");
  }
}

// Boards and full-screen pages: the whole page's backdrop. Only while there's
// something on screen (visible), so an empty board source stays see-through.
// They drop their own backdrop for it (body.custom-bg, overlay.css).
let pageBg = null;

function setBackground(cfg, visible) {
  const mode = cfg ? cfg.bg : "default";
  const custom = mode === "color" || (mode === "image" && cfg.bg_image);
  if (!pageBg) {
    if (!custom) return;
    pageBg = document.createElement("div");
    pageBg.className = "page-bg";
    Object.assign(pageBg.style, { position: "fixed", inset: "0", zIndex: "-1", pointerEvents: "none", opacity: "0",
      transition: "opacity .5s ease", backgroundPosition: "center", backgroundSize: "cover", backgroundRepeat: "no-repeat" });
    document.body.prepend(pageBg);
  }
  document.body.classList.toggle("custom-bg", !!custom);
  if (custom) {
    pageBg.style.backgroundColor = mode === "color" ? cfg.bg_color : "transparent";
    pageBg.style.backgroundImage = mode === "image" ? `url("/api/backgrounds/${encodeURIComponent(cfg.bg_image)}")` : "none";
  }
  pageBg.style.opacity = custom && visible ? String((cfg.bg_opacity ?? 100) / 100) : "0";
}

// The app's live snapshots: onSnap(snapshot) for each, onDown() when the app
// can't be reached (it retries by itself). Pages in the same browser share one
// connection (stream-worker.js): a browser allows only 6 to the same address,
// and clicks need one too. Where shared workers aren't available, the page
// has its own.
function liveStream(onSnap, onDown = () => {}) {
  if (typeof SharedWorker === "function") {
    try {
      const worker = new SharedWorker("/stream-worker.js", { name: "apex-live" });
      worker.port.onmessage = (m) => {
        if (m.data.type === "snapshot") onSnap(JSON.parse(m.data.data));
        else onDown();
      };
      worker.port.start();
      addEventListener("pagehide", () => worker.port.postMessage("bye"));
      return;
    } catch (e) { /* not allowed here: a stream of its own */ }
  }
  const stream = new EventSource("/api/stream");
  stream.onmessage = (m) => onSnap(JSON.parse(m.data));
  stream.onerror = onDown;
}

// Follow the app's live snapshot; reload after an app update so OBS picks up
// new graphics.
function followSnapshots(onSnap) {
  let version = null;
  liveStream((snap) => {
    if (version && snap.version && snap.version !== version) return location.reload();
    version = version || snap.version;
    onSnap(snap);
  });
}
