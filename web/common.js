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

function helmetSvg(design, { mirror = false } = {}) {
  const id = `lv${++liveryIds}`;
  const [c1, c2, c3] = designColors(design, ["#f2f2f2", "#d7263d", "#111111"]);
  const shell = "M28 128 Q14 52 92 30 Q166 14 184 86 L186 124 Q152 140 100 144 L40 144 Q30 140 28 128 Z";
  return `<svg class="livery livery-helmet" viewBox="0 0 200 160" xmlns="http://www.w3.org/2000/svg" ${mirror ? 'style="transform:scaleX(-1)"' : ""}>
    <defs><clipPath id="${id}"><path d="${shell}"/></clipPath></defs>
    <path d="${shell}" fill="${c1}"/>
    <g clip-path="url(#${id})">${liveryAccents(((design && design.pattern) || 0) + 1, 200, 160, c2, c3)}</g>
    <path d="${shell}" fill="none" stroke="rgba(0,0,0,.4)" stroke-width="2.5"/>
    <path d="M106 62 Q160 56 182 80 L183 100 Q150 98 108 98 Q98 80 106 62 Z" fill="#1d2633" stroke="#0c0f14" stroke-width="2"/>
    <path d="M116 66 Q150 62 170 74 L150 76 Q128 74 116 78 Z" fill="rgba(255,255,255,.25)"/>
    <rect x="96" y="58" width="12" height="44" rx="5" fill="${c3}"/>
    <path d="M60 30 Q100 16 140 24" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="5" stroke-linecap="round"/>
  </svg>`;
}

// A 3/4 front view for the "grid on track" style, where cars stand on an
// angled road. Built from a tiny projection: s runs nose-ward along the car,
// t across it (0 = near side), h up from the ground.
function car34Svg(design, number) {
  const id = `lv${++liveryIds}`;
  const [c1, c2, c3] = designColors(design, ["#d0d4da", "#1b76d1", "#111111"]);
  // Matches the "grid on track" road: the car points down-right, its far side up-right.
  const P = (s, t, h) => [40 + s * 470 + t * 70, 186 + s * 68 - t * 88 - h * 100];
  const poly = (...pts) => pts.map((p) => P(...p).map((v) => v.toFixed(1)).join(",")).join(" ");
  const wheel = (s, t, r = 1) => {
    const [x, y] = P(s, t, 0.13);
    return `<ellipse cx="${x}" cy="${y}" rx="${30 * r}" ry="${36 * r}" fill="#121212"/>
      <ellipse cx="${x + 3}" cy="${y}" rx="${18 * r}" ry="${23 * r}" fill="#7d838c"/>
      <ellipse cx="${x + 4}" cy="${y}" rx="${7 * r}" ry="${9 * r}" fill="#2f3339"/>`;
  };
  // Near side of the body, slightly tucked in at both ends.
  const side = poly([0.02, 0, 0.13], [0, 0, 0.5], [0.06, 0, 0.56], [0.94, 0, 0.5], [1, 0, 0.36], [1, 0, 0.18], [0.97, 0, 0.13]);
  // Rectangle (w 470 x h 100) -> the side face, for painting the livery on it.
  const [ox, oy] = P(0, 0, 0.56);
  const sideMap = `matrix(1 ${(68 / 470).toFixed(4)} 0 ${(0.43 * 100 / 100).toFixed(4)} ${ox} ${oy})`;
  const [nx, ny] = P(0.52, 0, 0.33);
  return `<svg class="livery livery-car34" viewBox="0 0 640 300" xmlns="http://www.w3.org/2000/svg">
    <defs><clipPath id="${id}"><polygon points="${side}"/></clipPath></defs>
    <polygon points="${poly([-0.04, -0.05, 0], [1.05, -0.05, 0], [1.05, 1.08, 0], [-0.04, 1.08, 0])}" fill="rgba(0,0,0,.38)"/>
    ${wheel(0.8, 1, 0.92)}${wheel(0.2, 1, 0.92)}
    <polygon points="${poly([0, 0, 0.5], [0, 1, 0.5], [0.94, 1, 0.5], [0.94, 0, 0.5])}" fill="${c1}"/>
    <polygon points="${poly([0.94, 0, 0.5], [0.94, 1, 0.5], [1, 1, 0.36], [1, 0, 0.36])}" fill="${c1}"/>
    <polygon points="${poly([0.94, 0, 0.5], [0.94, 1, 0.5], [1, 1, 0.36], [1, 0, 0.36])}" fill="rgba(255,255,255,.12)"/>
    <polygon points="${poly([1, 0, 0.36], [1, 1, 0.36], [1, 1, 0.16], [1, 0, 0.16])}" fill="${c2}"/>
    <polygon points="${poly([1, 0.06, 0.33], [1, 0.3, 0.33], [1, 0.3, 0.26], [1, 0.06, 0.26])}" fill="#e9eef5"/>
    <polygon points="${poly([1, 0.7, 0.33], [1, 0.94, 0.33], [1, 0.94, 0.26], [1, 0.7, 0.26])}" fill="#e9eef5"/>
    <polygon points="${poly([1, 0.02, 0.15], [1, 0.98, 0.15], [1.03, 0.98, 0.1], [1.03, 0.02, 0.1])}" fill="#151515"/>
    <polygon points="${poly([0.28, 0.12, 0.5], [0.4, 0.16, 0.86], [0.62, 0.16, 0.86], [0.75, 0.12, 0.5])}" fill="#1b2430"/>
    <polygon points="${poly([0.4, 0.16, 0.86], [0.62, 0.16, 0.86], [0.62, 0.84, 0.86], [0.4, 0.84, 0.86])}" fill="${c1}"/>
    <polygon points="${poly([0.4, 0.16, 0.86], [0.62, 0.16, 0.86], [0.62, 0.84, 0.86], [0.4, 0.84, 0.86])}" fill="rgba(255,255,255,.14)"/>
    <polygon points="${poly([0.62, 0.16, 0.86], [0.75, 0.12, 0.5], [0.75, 0.88, 0.5], [0.62, 0.84, 0.86])}" fill="#253244"/>
    <polygon points="${poly([0.64, 0.24, 0.8], [0.72, 0.22, 0.56], [0.72, 0.4, 0.56], [0.64, 0.4, 0.8])}" fill="rgba(255,255,255,.2)"/>
    <polygon points="${side}" fill="${c1}"/>
    <g clip-path="url(#${id})"><g transform="${sideMap}">${liveryAccents(design && design.pattern, 470, 100, c2, c3)}</g></g>
    <polygon points="${side}" fill="none" stroke="rgba(0,0,0,.3)" stroke-width="2"/>
    <polygon points="${poly([0.02, 0, 0.17], [0.97, 0, 0.17], [0.97, 0, 0.13], [0.02, 0, 0.13])}" fill="#151515"/>
    ${wheel(0.2, 0)}${wheel(0.8, 0)}
    <polygon points="${poly([0, 0.04, 0.5], [0.03, 0.04, 0.78], [0.05, 0.04, 0.78], [0.04, 0.04, 0.5])}" fill="#202020"/>
    <polygon points="${poly([0, 0.96, 0.5], [0.03, 0.96, 0.78], [0.05, 0.96, 0.78], [0.04, 0.96, 0.5])}" fill="#202020"/>
    <polygon points="${poly([-0.03, 0, 0.78], [0.08, 0, 0.8], [0.08, 1, 0.8], [-0.03, 1, 0.78])}" fill="${c3}"/>
    <polygon points="${poly([-0.03, 0, 0.78], [0.08, 0, 0.8], [0.08, 0, 0.74], [-0.03, 0, 0.72])}" fill="#151515"/>
    <g transform="${sideMap.replace(/ [\d.]+ [\d.]+\)$/, ` ${nx} ${ny})`)}">
      <ellipse cx="0" cy="0" rx="26" ry="26" fill="#fff" stroke="#111" stroke-width="2"/>
      <text x="0" y="9" text-anchor="middle" font-family="system-ui,sans-serif" font-weight="900" font-size="26" fill="#111">${esc(number)}</text>
    </g>
  </svg>`;
}

// ---------------------------------------------------------------------------
// broadcast pages
// ---------------------------------------------------------------------------

// Driver name in one of the overlay formats (see apex/overlays.py).
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

// A stopwatch icon (fastest lap), coloured by CSS (currentColor).
const STOPWATCH = '<svg class="stopwatch" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M9 1h6v2H9zm10.03 6.39 1.42-1.42-1.41-1.41-1.42 1.42A8.96 8.96 0 0 0 12 4a9 9 0 1 0 9 9c0-2.12-.74-4.07-1.97-5.61zM12 20a7 7 0 1 1 0-14 7 7 0 0 1 0 14zm-1-12h2v6h-2z"/></svg>';

// Fixed 1920x1080 stage, scaled to fit the browser source.
function fitStage(stage) {
  const fit = () => {
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    stage.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
  };
  addEventListener("resize", fit);
  fit();
  if (new URLSearchParams(location.search).has("preview")) document.body.classList.add("preview");
}

// Follow the app's live snapshot; reload after an app update so OBS picks up
// new graphics.
function followSnapshots(onSnap) {
  const stream = new EventSource("/api/stream");
  let version = null;
  stream.onmessage = (msg) => {
    const snap = JSON.parse(msg.data);
    if (version && snap.version && snap.version !== version) return location.reload();
    version = version || snap.version;
    onSnap(snap);
  };
}
