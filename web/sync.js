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
