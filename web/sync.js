"use strict";

// The co-commentator's FREE | SYNC switch on its own (sync.html): what the
// app's top bar pill does, in a small window kept on top of iRacing.

const pill = document.getElementById("pill");
const statusEl = document.getElementById("status");
let free = false;

async function send(action, params) {
  try {
    const r = await fetch("/api/cmd", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, params }) });
    return await r.json();
  } catch (e) {
    return null;
  }
}

pill.addEventListener("click", () => {
  free = !free;
  pill.classList.toggle("free", free);  // at once; the app confirms it
  send("follow_free", { on: free });
});

document.getElementById("close").addEventListener("click", async () => {
  const r = await send("sync_widget", { on: false });
  if (!r || !r.opened) window.close();  // a browser window
});

// Dragged by its handle (or the status text): the app moves the window. The
// window's own position comes from the app (in its units: on a scaled screen
// those can be the screen's pixels, not the page's), the mouse moves add to it.
let drag = null, pending = null, sending = false;
async function pump() {
  if (sending || !pending) return;
  const [x, y, save] = pending;
  pending = null;
  sending = true;
  await send("sync_widget_move", { x, y, save });
  sending = false;
  pump();
}
for (const el of document.querySelectorAll(".drag")) {
  el.addEventListener("pointerdown", async (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    el.setPointerCapture(e.pointerId);
    const start = { sx: e.screenX, sy: e.screenY };
    drag = start;
    const r = await send("sync_widget_move", {});
    if (drag !== start) return;  // already let go
    if (!r || !r.at) {
      drag = null;  // a browser window: it can't be moved from here
      return;
    }
    const [wx, wy] = r.at;
    // Window units per page pixel: 1, or the screen's scale when the app counts real pixels.
    const dpr = window.devicePixelRatio || 1;
    const k = Math.abs(wx - window.screenX) <= Math.abs(wx - window.screenX * dpr) ? 1 : dpr;
    Object.assign(start, { wx, wy, k, ready: true });
  });
  el.addEventListener("pointermove", (e) => {
    if (!drag || !drag.ready) return;
    pending = [Math.round(drag.wx + (e.screenX - drag.sx) * drag.k), Math.round(drag.wy + (e.screenY - drag.sy) * drag.k), false];
    pump();
  });
  const end = (e) => {
    if (!drag) return;
    if (drag.ready) {
      pending = [Math.round(drag.wx + (e.screenX - drag.sx) * drag.k), Math.round(drag.wy + (e.screenY - drag.sy) * drag.k), true];
      pump();
    }
    drag = null;
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", () => { drag = null; });
}

followSnapshots((s) => {
  const fo = (s.remote && s.remote.follow) || {};
  free = !!fo.free;
  pill.classList.toggle("free", free);
  pill.classList.toggle("off", !fo.on || fo.status !== "following");
  const host = fo.host;
  statusEl.textContent = !fo.on ? "Not following (Home tab)"
    : fo.status !== "following" ? (fo.status === "connecting" ? "Connecting…" : fo.error || "Not connected")
      : free ? "Your own camera" : host && host.car ? `Host: #${host.car} ${host.driver}${host.live === false ? " (replay)" : ""}` : "With the host";
});
