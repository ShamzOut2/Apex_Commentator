"use strict";

// Sponsor logos over the race: all together in a row, or one at a time.
// The logos come from the active league (League builder); place, size and
// which ones from the sponsors settings in the Overlays tab.

const stage = $("#stage");
fitStage(stage);
const PREVIEW = new URLSearchParams(location.search).has("preview");
let shownKey = "";
let timer = null;

function chosen(logos, ids) {
  if (!ids) return logos;
  const wanted = new Set(ids.split(","));
  return logos.filter((l) => wanted.has(l.id));
}

function render(snap) {
  const s = snap.overlays && snap.overlays.settings && snap.overlays.settings.sponsors;
  const logos = chosen((snap.league && snap.league.sponsors) || [], s ? s.sponsor_ids : "");
  const on = s && logos.length && (s.visible || PREVIEW);
  setBackground(s, !!on);
  const key = JSON.stringify([on, s, logos]);
  if (key === shownKey) return;
  shownKey = key;
  clearInterval(timer);
  if (!on) {
    stage.innerHTML = PREVIEW ? `<div class="sp-hint">${logos.length ? "" : "No sponsor logos in the active league"}</div>` : "";
    return;
  }
  const vertical = s.place === "left" || s.place === "right";
  const rotate = s.layout === "rotate" && logos.length > 1;
  stage.innerHTML = `<div class="sp ${esc(s.place)} ${vertical ? "vertical" : ""} ${rotate ? "rotate" : "row"} ${s.background ? "panel" : ""} ${s.visible ? "" : "hidden-preview"}"
      style="--sp-h:${s.size}px">
    ${s.title ? `<div class="sp-title">${esc(s.title)}</div>` : ""}
    <div class="sp-logos">${logos.map((l, i) => `<img class="${i === 0 ? "on" : ""}" src="${esc(l.url)}" alt="${esc(l.name)}">`).join("")}</div>
  </div>`;
  if (rotate) {
    const imgs = stage.querySelectorAll(".sp-logos img");
    let i = 0;
    timer = setInterval(() => {
      imgs[i].classList.remove("on");
      i = (i + 1) % imgs.length;
      imgs[i].classList.add("on");
    }, s.interval_s * 1000);
  }
}

followSnapshots(render);
