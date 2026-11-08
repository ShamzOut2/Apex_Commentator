"""Live timing for spectators: a website anyone can open, without seeing
the host's IP address or anything else about them.

Two parts:

* **SpectatorServer**: a small web server of its own, separate from the app's,
  listening on this PC only (127.0.0.1). It serves the spectators' page
  (``web/live/``), the live timing feed (``/feed``, server-sent events), the
  track outline (``/map.json``) and the logos on the page (``/img/<token>``),
  and nothing else: none of the app's own pages, data or controls. The feed
  is built field by field (``App._spectator_section``): names, car numbers,
  teams, classes, places, gaps, laps, sectors, tyres and where each car is
  on the lap. No iRacing IDs, notes, file paths, or anything the app knows
  about the host.
* **Tunnel**: Cloudflare's ``cloudflared`` connects out from this PC to
  Cloudflare and gives the page a public address (a free
  ``https://….trycloudflare.com`` link, new each time, or the host's own
  address with a Cloudflare tunnel token). Spectators connect to Cloudflare,
  never to this PC: they can't see its address. ``cloudflared`` is
  downloaded from Cloudflare's own releases the first time it's needed.
"""

import json
import os
import platform
import re
import shutil
import stat
import subprocess
import threading
import time
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 8191
HEARTBEAT_S = 15.0
PAGE_FILES = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
              "/live.css": ("live.css", "text/css; charset=utf-8"), "/live.js": ("live.js", "text/javascript; charset=utf-8"),
              "/favicon.png": ("favicon.png", "image/png")}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml"}
# Every answer: no caching, no address of the page passed on, not framed by
# other sites, and the page may only load from itself.
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SpectatorServer:
    """The spectators' page and its live feed, on 127.0.0.1 only (see the module notes)."""

    def __init__(self, page_dir, port=DEFAULT_PORT, host="127.0.0.1"):
        self.page_dir = Path(page_dir)
        self.port = int(port)
        self.host = host
        self.viewers = 0
        self._feed = (0, b"null")
        self._map = (None, b"null")
        self._images = {}
        self._changed = threading.Condition()
        self._server = None
        self._stopped = threading.Event()

    # -- what it serves, from the app ----------------------------------------------

    def update(self, section, track_map=None, images=None):
        """The live timing now (a dict made only of what spectators may see),
        the track outline ({id, points} or None) and the logos it names ({token: path})."""
        body = json.dumps(section, separators=(",", ":")).encode("utf-8")
        with self._changed:
            if images is not None:
                self._images = dict(images)
            map_id = track_map["id"] if track_map else None
            if map_id != self._map[0]:
                self._map = (map_id, json.dumps({"id": map_id, "points": track_map["points"]} if track_map else None,
                                                separators=(",", ":")).encode("utf-8"))
            if body != self._feed[1]:
                self._feed = (self._feed[0] + 1, body)
                self._changed.notify_all()

    def _wait(self, version, timeout):
        with self._changed:
            self._changed.wait_for(lambda: self._feed[0] != version or self._stopped.is_set(), timeout)
            return self._feed

    # -- the server --------------------------------------------------------------------

    @property
    def running(self):
        return self._server is not None

    @property
    def url(self):
        return f"http://{self.host}:{self.port}/"

    def start(self):
        if self._server:
            return self
        spec = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "Apex-Live"
            sys_version = ""

            def log_message(self, fmt, *args):  # quiet: spectators' addresses aren't logged either
                pass

            def _head(self, status, ctype, length=None):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                if length is not None:
                    self.send_header("Content-Length", str(length))
                for k, v in SECURITY_HEADERS.items():
                    self.send_header(k, v)
                self.end_headers()

            def _send(self, status, ctype, body):
                self._head(status, ctype, len(body))
                if self.command != "HEAD":
                    self.wfile.write(body)

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                path = self.path.split("?", 1)[0].split("#", 1)[0]
                if path in PAGE_FILES:
                    name, ctype = PAGE_FILES[path]
                    try:
                        return self._send(HTTPStatus.OK, ctype, (spec.page_dir / name).read_bytes())
                    except OSError:
                        return self._send(HTTPStatus.NOT_FOUND, "text/plain", b"Not found")
                if path == "/map.json":
                    return self._send(HTTPStatus.OK, "application/json", spec._map[1])
                if path == "/feed":
                    return spec._serve_feed(self)
                m = re.fullmatch(r"/img/([0-9a-f]{16})", path)
                if m:
                    file = spec._images.get(m.group(1))
                    ctype = IMAGE_TYPES.get(Path(file).suffix.lower()) if file else None
                    if file and ctype:
                        try:
                            return self._send(HTTPStatus.OK, ctype, Path(file).read_bytes())
                        except OSError:
                            pass
                return self._send(HTTPStatus.NOT_FOUND, "text/plain", b"Not found")

            def _refuse(self):
                self._send(HTTPStatus.METHOD_NOT_ALLOWED, "text/plain", b"Read only")

            do_POST = do_PUT = do_DELETE = do_PATCH = _refuse  # noqa: N815 - nothing can be changed from outside

        self._stopped.clear()
        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, name="spectators", daemon=True).start()
        return self

    def _serve_feed(self, handler):
        handler._head(HTTPStatus.OK, "text/event-stream")
        handler.connection.settimeout(60)
        with self._changed:
            self.viewers += 1
        version = -1
        try:
            while not self._stopped.is_set():
                new, body = self._wait(version, HEARTBEAT_S)
                if new == version:
                    handler.wfile.write(b": still here\n\n")  # keeps the connection open through Cloudflare
                else:
                    version = new
                    handler.wfile.write(b"data: " + body + b"\n\n")
                handler.wfile.flush()
        except OSError:
            pass
        finally:
            with self._changed:
                self.viewers -= 1

    def stop(self):
        self._stopped.set()
        with self._changed:
            self._changed.notify_all()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self.viewers = 0


# -- the public address: a Cloudflare tunnel ----------------------------------------------

RELEASES = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
QUICK_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def cloudflared_asset():
    """The cloudflared download for this PC, or None (not one Cloudflare publishes a plain binary for)."""
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "386" if machine in ("x86", "i386", "i686") else "amd64"
    if os.name == "nt":
        return f"cloudflared-windows-{arch}.exe"
    if platform.system() == "Linux":
        return f"cloudflared-linux-{arch}"
    return None


class Tunnel:
    """``cloudflared`` running for the spectators' page: a quick link, or the
    host's own Cloudflare tunnel (``token``) for an address that stays the same."""

    def __init__(self, bin_dir, local_url, token="", public_url="", fetch=None, popen=None):
        self.bin_dir = Path(bin_dir)
        self.local_url = local_url
        self.token = token.strip()
        self.public_url = public_url.strip()   # with a token: the address it's set up for (to show), else found
        self.status = "starting"               # starting | downloading | online | error | stopped
        self.error = ""
        self._fetch = fetch or self._download
        self._popen = popen or subprocess.Popen
        self._proc = None
        self._stop = threading.Event()

    # -- cloudflared itself ---------------------------------------------------------------

    def binary(self):
        """cloudflared: on the PATH, already downloaded, or downloaded now."""
        found = shutil.which("cloudflared")
        if found:
            return found
        asset = cloudflared_asset()
        if asset is None:
            raise RuntimeError("Install cloudflared from Cloudflare (it isn't downloaded by itself on this system)")
        path = self.bin_dir / ("cloudflared.exe" if asset.endswith(".exe") else "cloudflared")
        if not path.exists():
            self.status = "downloading"
            data = self._fetch(RELEASES + asset)
            if len(data) < 1_000_000:
                raise RuntimeError("The cloudflared download didn't look right")
            self.bin_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            tmp.replace(path)
        return str(path)

    @staticmethod
    def _download(url):
        req = urllib.request.Request(url, headers={"User-Agent": "Apex-Commentator"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()

    # -- running it ----------------------------------------------------------------------

    def start(self):
        self._stop.clear()
        threading.Thread(target=self._run, name="tunnel", daemon=True).start()
        return self

    def _command(self, exe):
        base = [exe, "tunnel", "--no-autoupdate"]
        if self.token:
            # The host's own tunnel (set up on Cloudflare to point at the local address).
            return base + ["run", "--token", self.token]
        return base + ["--url", self.local_url]

    def _run(self):
        tries = 0
        while not self._stop.is_set():
            try:
                exe = self.binary()
                self.status, self.error = "starting", ""
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self._proc = self._popen(self._command(exe), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, creationflags=flags)
                for raw in self._proc.stdout:
                    line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
                    found = QUICK_URL.search(line)
                    if found and not self.token:
                        self.public_url, self.status, tries = found.group(0), "online", 0
                    elif self.token and "Registered tunnel connection" in line:
                        self.status, tries = "online", 0
                    if self._stop.is_set():
                        break
                self._proc.wait()
                if not self._stop.is_set():
                    self.status, self.error = "error", "The tunnel stopped: starting it again"
            except Exception as e:  # noqa: BLE001 - shown in the app; tried again
                self.status, self.error = "error", str(e)
            if self._stop.wait(min(60, 5 * 2 ** min(tries, 4))):
                break
            tries += 1
        self.status = "stopped"

    def stop(self):
        self._stop.set()
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if not self.token:
            self.public_url = ""  # a quick link is gone once the tunnel stops
        self.status = "stopped"
