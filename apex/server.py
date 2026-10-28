"""Tiny HTTP server (standard library only).

* ``GET  /``                     the overlay UI (files in ``web/``)
* ``GET  /api/state``            current snapshot
* ``GET  /api/stream``           Server-Sent Events stream of snapshots
* ``POST /api/cmd``              ``{"action": "...", "params": {...}}`` spectate/replay commands
* ``/api/leagues...``            league builder
* ``POST /api/leagues/<id>/classes/<class>/logo``  upload a class logo (raw image body)
* ``POST /api/leagues/<id>/images?target=...``     upload a class/team/car/helmet image
* ``GET  /api/logos/<id>/<file>``  serve a class logo
* ``GET  /api/logo-library``     the built-in class logos (``web/logos/``)
* ``GET  /api/update``           update status; ``POST /api/update/{check,skip,install}``
"""

import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import championship
from .core import CommandError
from .league import LOGO_TYPES, MAX_IMAGE_BYTES, LeagueError, logo_library, profile_from_session
from .paths import WEB_DIR
from .updater import UpdateError, request_restart

MAX_BODY = 2 * 1024 * 1024
# Explicit types: the Windows registry sometimes maps .js to text/plain.
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):
    server_version = "ApexCommentator"
    app = None  # set by make_server

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    # -- helpers ------------------------------------------------------------

    def _send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message, status=HTTPStatus.BAD_REQUEST):
        self._send_json({"ok": False, "error": message}, status)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("Request too large")
        if not length:
            return {}
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        return data

    def _path(self):
        return unquote(urlparse(self.path).path).rstrip("/") or "/"

    # -- routing ------------------------------------------------------------

    def do_GET(self):
        path = self._path()
        if path == "/api/state":
            return self._send_json(self.app.build_snapshot())
        if path == "/api/stream":
            return self._stream()
        if path == "/api/config":
            cfg = self.app.cfg
            return self._send_json({
                "replay_preroll_s": cfg["replay_preroll_s"],
                "replay_auto_return_s": cfg["replay_auto_return_s"],
                "api_configured": bool(self.app.leagues.client and self.app.leagues.client.configured),
            })
        if path == "/api/update":
            updater = getattr(self.app, "updater", None)
            return self._send_json(updater.status() if updater else {"enabled": False})
        if path == "/api/logo-library":
            return self._send_json({"logos": logo_library()})
        if path.startswith("/api/logos/"):
            return self._logo(path)
        if path == "/api/leagues":
            return self._send_json({"leagues": self.app.leagues.list(), "active": self.app.leagues.active_id})
        if path.startswith("/api/leagues/") and path.endswith("/championship"):
            profile = self.app.leagues.get(path.split("/")[3])
            if profile is None:
                return self._error("League not found", HTTPStatus.NOT_FOUND)
            return self._send_json({
                "bonuses": championship.BONUSES,
                "championship": championship.normalise(profile.get("championship")),
                "standings": championship.standings(profile),
            })
        if path.startswith("/api/leagues/"):
            profile = self.app.leagues.get(path.split("/", 3)[3])
            if profile is None:
                return self._error("League not found", HTTPStatus.NOT_FOUND)
            return self._send_json(profile)
        return self._static(path)

    def do_POST(self):
        path = self._path()
        parts = path.split("/")
        if len(parts) == 7 and parts[:3] == ["", "api", "leagues"] and parts[4] == "classes" and parts[6] == "logo":
            return self._upload_image(parts[3], f"class:{parts[5]}")
        if len(parts) == 5 and parts[:3] == ["", "api", "leagues"] and parts[4] == "images":
            target = parse_qs(urlparse(self.path).query).get("target", [""])[0]
            return self._upload_image(parts[3], target)
        try:
            body = self._body()
        except ValueError as e:
            return self._error(f"Bad request: {e}")
        if path.startswith("/api/update/"):
            return self._update_action(path.rsplit("/", 1)[1], body)
        try:
            if path == "/api/cmd":
                params = body.get("params") or {}
                if not isinstance(params, dict):
                    return self._error("params must be an object")
                result = self.app.command(str(body.get("action", "")), params)
                return self._send_json({"ok": True, **result})
            if path == "/api/leagues":
                return self._send_json({"ok": True, "league": self.app.leagues.save(body)})
            if path == "/api/leagues/fetch":
                return self._send_json({"ok": True, "league": self.app.leagues.fetch(body.get("league_id", ""))})
            if path == "/api/leagues/active":
                profile = self.app.leagues.set_active(body.get("id") or None)
                self.app.publish()
                return self._send_json({"ok": True, "active": profile["id"] if profile else None})
            if path.startswith("/api/leagues/") and path.endswith("/import-session"):
                drivers = self.app.build_snapshot().get("drivers") or []
                if not drivers:
                    return self._error("No drivers in the current session")
                league, added = self.app.leagues.import_session(path.split("/")[3], drivers)
                self.app.publish()
                return self._send_json({"ok": True, "league": league, "added": added})
            if path.startswith("/api/leagues/") and path.endswith("/championship/import"):
                return self._import_round(path.split("/")[3], str(body.get("round_id") or ""))
            if path == "/api/leagues/from-session":
                drivers = self.app.build_snapshot().get("drivers") or []
                if not drivers:
                    return self._error("No drivers in the current session")
                name = str(body.get("name") or "").strip() or "Session roster"
                return self._send_json({"ok": True, "league": self.app.leagues.save(profile_from_session(drivers, name))})
        except (CommandError, LeagueError) as e:
            return self._error(str(e))
        except (TypeError, ValueError) as e:
            return self._error(f"Invalid parameters: {e}")
        return self._error("Not found", HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        path = self._path()
        if path.startswith("/api/leagues/"):
            self.app.leagues.delete(path.split("/", 3)[3])
            self.app.publish()
            return self._send_json({"ok": True})
        return self._error("Not found", HTTPStatus.NOT_FOUND)

    # -- endpoints ----------------------------------------------------------

    def _import_round(self, profile_id, round_id):
        """Fill a championship round with the current session's results."""
        app = self.app
        with app._lock:
            if not app._drivers or app._frame is None:
                return self._error("Not connected to a session")
            if not app._is_race(app._frame):
                return self._error("Results can only be imported from a race session")
            profile = app.leagues.get(profile_id)
            if profile is None:
                return self._error("League not found", HTTPStatus.NOT_FOUND)
            rounds = profile.setdefault("championship", championship.normalise({}))["rounds"]
            rd = next((r for r in rounds if r["id"] == round_id), None)
            if rd is None:
                return self._error("Save the round first")
            results, added = app.session_results(profile, add_missing=True)
            # Too little of the race covered: a DNF (and no points).
            rd["results"] = championship.apply_distance_rule(results, championship.normalise_rules(profile["championship"].get("rules")))
            rd["session"] = app.session_key() or ""
            if not rd["track"]:
                rd["track"] = app._session_meta.get("track", "")
            league = app.leagues.save(profile)
        app.publish()
        return self._send_json({"ok": True, "league": league, "added": added, "count": len(results)})

    def _stream(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        version = -1
        try:
            while not self.app._stop.is_set():
                new_version, snap = self.app.wait_snapshot(version)
                if new_version == version:
                    self.wfile.write(b": keep-alive\n\n")
                else:
                    version = new_version
                    self.wfile.write(b"data: " + json.dumps(snap).encode("utf-8") + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _update_action(self, action, body):
        updater = getattr(self.app, "updater", None)
        if updater is None or not updater.enabled:
            return self._error("Update checks are turned off")
        if action == "check":
            return self._send_json({"ok": True, **updater.check()})
        if action == "skip":
            updater.skip(str(body.get("version") or ""))
            return self._send_json({"ok": True})
        if action == "install":
            try:
                version = updater.install()
            except UpdateError as e:
                return self._error(str(e))
            # An installer reopens the app itself; a file update needs a relaunch.
            request_restart(relaunch=not updater.installer_mode)
            return self._send_json({"ok": True, "version": version, "restarting": True})
        return self._error("Not found", HTTPStatus.NOT_FOUND)

    def _upload_image(self, league_id, target):
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_IMAGE_BYTES:
            return self._error("Image must be between 1 byte and 8 MB")
        data = self.rfile.read(length)
        try:
            league = self.app.leagues.save_image(league_id, target, data)
        except LeagueError as e:
            return self._error(str(e))
        self.app.publish()
        return self._send_json({"ok": True, "league": league})

    def _logo(self, path):
        parts = path.split("/")
        target = self.app.leagues.logo_file(parts[3], parts[4]) if len(parts) == 5 else None
        if target is None:
            return self._error("Not found", HTTPStatus.NOT_FOUND)
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", LOGO_TYPES[target.suffix.lstrip(".")])
        self.send_header("Content-Length", str(len(data)))
        # Names are content-addressed, so they can be cached for good.
        self.send_header("Cache-Control", "max-age=31536000, immutable")
        # Uploaded SVGs must never run script if opened directly.
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path):
        rel = "index.html" if path == "/" else path.lstrip("/")
        web = WEB_DIR.resolve()
        target = (web / rel).resolve()
        if web not in target.parents or not target.is_file():
            return self._error("Not found", HTTPStatus.NOT_FOUND)
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", CONTENT_TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


def make_server(app, host, port):
    handler = type("BoundHandler", (Handler,), {"app": app})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def serve_in_thread(server):
    t = threading.Thread(target=server.serve_forever, name="http", daemon=True)
    t.start()
    return t
