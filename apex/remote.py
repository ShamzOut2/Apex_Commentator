"""Dual commentary: one commentator's camera followed by another's app.

The host ticks *Let a co-commentator follow my camera*: a small server of its
own starts (CameraShare), separate from the app's (which only this PC can
reach and has no password), on DEFAULT_PORT, reachable from other computers
but only with the host's access code, and only for one thing: what the host's
iRacing is showing (the driver, the camera, live or a replay and where).

The co-commentator types the host's address and code into their own app
(CameraFollow): it keeps a connection to the host open and, whenever the
host's camera changes, puts their own iRacing on the same driver and camera,
the same replay (or back to live). It reconnects by itself when the
connection drops.
"""

import hmac
import json
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 8190
HEARTBEAT_S = 5.0      # the host sends the camera at least this often (the follower knows it's alive)
STALE_S = 15.0         # nothing from the host for this long: the follower reconnects
RETRY_S = (2, 4, 8, 15)


def new_code():
    """A six-digit access code."""
    return f"{secrets.randbelow(10 ** 6):06d}"


def local_addresses():
    """This PC's addresses on its networks (for the co-commentator to type in)."""
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))  # no packet is sent: just which address the PC would use
            out.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in out and not ip.startswith("127."):
                out.append(ip)
    except OSError:
        pass
    return out


class CameraShare:
    """The host's side: serves the camera to followers who have the code."""

    def __init__(self, port=DEFAULT_PORT, code=None, host="0.0.0.0"):
        self.port = int(port)
        self.host = host
        self.code = code or new_code()
        self.followers = 0
        self._state = None
        self._version = 0
        self._changed = threading.Condition()
        self._server = None
        self._stopped = threading.Event()
        self._addresses = (0.0, [])

    @property
    def addresses(self):
        """This PC's addresses (looked up again once a minute: it can be slow)."""
        at, found = self._addresses
        if time.monotonic() - at > 60:
            found = local_addresses()
            self._addresses = (time.monotonic(), found)
        return found

    # -- the camera, from the app ---------------------------------------------

    def update(self, state):
        """The host's camera now (a dict, or None when not in a session)."""
        with self._changed:
            if state != self._state:
                self._state = state
                self._version += 1
                self._changed.notify_all()

    def _wait(self, version, timeout):
        with self._changed:
            self._changed.wait_for(lambda: self._version != version or self._stopped.is_set(), timeout)
            return self._version, self._state

    # -- the server --------------------------------------------------------------

    def start(self):
        share = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # quiet
                pass

            def do_GET(self):
                url = urllib.parse.urlsplit(self.path)
                if url.path != "/follow":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                code = (urllib.parse.parse_qs(url.query).get("code") or [""])[0]
                if not hmac.compare_digest(code.encode(), share.code.encode()):
                    body = b'{"error": "Wrong code"}'
                    self.send_response(HTTPStatus.FORBIDDEN)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                share._serve(self)

        self._stopped.clear()
        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]  # the one it got (port 0: any free one)
        threading.Thread(target=self._server.serve_forever, name="camera-share", daemon=True).start()
        return self

    def _serve(self, handler):
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.connection.settimeout(30)
        with self._changed:
            self.followers += 1
        version = -1
        try:
            while not self._stopped.is_set():
                new, state = self._wait(version, HEARTBEAT_S)
                version = new
                # Every change, and the camera again every few seconds (it's alive).
                handler.wfile.write(b"data: " + json.dumps(state, separators=(",", ":")).encode() + b"\n\n")
                handler.wfile.flush()
        except OSError:
            pass
        finally:
            with self._changed:
                self.followers -= 1

    def stop(self):
        self._stopped.set()
        with self._changed:
            self._changed.notify_all()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


class CameraFollow:
    """The co-commentator's side: follows the host's camera with ``apply(state)``."""

    def __init__(self, address, code, apply, timeout=STALE_S):
        self.address = address
        self.code = code
        self.apply = apply
        self.timeout = timeout
        self.status = "connecting"   # connecting | following | error
        self.error = ""
        self.last = None             # the host's camera last received
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def url_for(address, code):
        """The follow address from what was typed: "192.168.1.20", "pc:8190", "http://…"."""
        address = str(address or "").strip()
        if not address:
            raise ValueError("Type in the host's address")
        if "://" not in address:
            address = f"http://{address}"
        parts = urllib.parse.urlsplit(address)
        if not parts.hostname:
            raise ValueError("That address doesn't look right")
        port = parts.port or DEFAULT_PORT
        host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
        return f"{parts.scheme or 'http'}://{host}:{port}/follow?code={urllib.parse.quote(str(code or '').strip())}"

    def start(self):
        self.url = self.url_for(self.address, self.code)
        self._thread = threading.Thread(target=self._run, name="camera-follow", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        tries = 0
        while not self._stop.is_set():
            try:
                self.status = "connecting"
                # Straight to the host (a co-commentator's PC on the same network
                # or VPN), never through a proxy the system may have.
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(self.url, timeout=self.timeout) as r:
                    tries = 0
                    self.status, self.error = "following", ""
                    for raw in r:
                        if self._stop.is_set():
                            return
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        state = json.loads(line[5:])
                        self.last = state
                        if state:
                            try:
                                self.apply(state)
                            except Exception as e:  # noqa: BLE001 - a bad command mustn't end the link
                                self.error = f"Couldn't follow: {e}"
                self.status, self.error = "error", "The host stopped sharing"
            except urllib.error.HTTPError as e:
                self.status = "error"
                self.error = "Wrong code" if e.code == 403 else f"The host answered {e.code}"
            except (OSError, ValueError) as e:
                self.status = "error"
                self.error = f"Can't reach the host ({getattr(e, 'reason', e)})"
            delay = RETRY_S[min(tries, len(RETRY_S) - 1)]
            tries += 1
            self._stop.wait(delay)
