"use strict";

// One live connection to the app for every page open in this browser: the
// control panel, its preview panes, pop-outs and on-screen overlays. A browser
// allows only 6 open connections to the same address, and each page keeping
// its own stream open used them all up, so clicks (which need one too) never
// got through. Pages connect here (liveStream in common.js) and get every
// snapshot passed on.

const ports = new Set();
let stream = null;
let last = null;

function send(msg) {
  for (const port of ports) port.postMessage(msg);
}

function open() {
  stream = new EventSource("/api/stream");
  stream.onmessage = (m) => {
    last = m.data;
    send({ type: "snapshot", data: m.data });
  };
  stream.onerror = () => send({ type: "down" });
}

onconnect = (e) => {
  const port = e.ports[0];
  ports.add(port);
  port.onmessage = (m) => {
    if (m.data === "bye") ports.delete(port);  // the page is going
  };
  if (!stream) open();
  if (last) port.postMessage({ type: "snapshot", data: last });  // no waiting for the next one
};
