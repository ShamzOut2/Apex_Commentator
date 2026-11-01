"""Tiny HTTP server (standard library only).

* ``GET  /``                     the overlay UI (files in ``web/``)
* ``GET  /api/state``            current snapshot
* ``GET  /api/stream``           Server-Sent Events stream of snapshots
* ``POST /api/cmd``              ``{"action": "...", "params": {...}}`` spectate/replay commands
* ``/api/leagues...``            league builder
* ``POST /api/leagues/<id>/classes/<class>/logo``  upload a class logo (raw image body)
* ``POST /api/leagues/<id>/images?target=...``     upload a class/team/car/helmet image
* ``GET  /api/logos/<id>/<file>``  serve a class logo
* ``GET  /api/thumbs/<file>``       a grid walk car picture from the thumbnails folder
* ``GET  /api/logo-library``     the built-in class logos (``web/logos/``)
* ``GET  /api/backgrounds``      uploaded overlay / board backgrounds; ``POST`` uploads one (raw image body)
* ``GET  /api/backgrounds/<file>``  serve one
* ``POST /api/export``           ``{"what", "league", "round"}``: save an export to the Exports folder
* ``POST /api/export/show``      ``{"path"}``: show an export in the file manager
* ``POST /api/import?what=...&league=...&round=...``  import a file (raw body)
* ``GET  /api/update``           update status; ``POST /api/update/{check,skip,install}``
* ``POST /api/calendar/scan?day_first=1``  a calendar image (raw PNG body) read into rounds
* ``POST /api/calendar/parse``     ``{"text", "day_first"}``: pasted calendar text into rounds
"""

import json
import mimetypes
import threading
from pathlib import Path
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import championship, ocr, schedule, transfer
from .core import CommandError
from .makes import catalogue as makes_catalogue
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
            })
        if path == "/api/update":
            updater = getattr(self.app, "updater", None)
            return self._send_json(updater.status() if updater else {"enabled": False})
        if path == "/api/tracks":
            query = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            if query:
                return self._send_json({"tracks": self.app.tracks.search(query), **self.app.tracks.status()})
            return self._send_json({"tracks": self.app.tracks.grouped(), **self.app.tracks.status()})
        if path == "/api/makes":
            return self._send_json({"makes": makes_catalogue()})
        if path == "/api/export/folder":
            return self._send_json({"folder": str(transfer.exports_dir())})
        if path == "/api/backgrounds":
            return self._send_json({"backgrounds": self.app.backgrounds.list()})
        if path.startswith("/api/backgrounds/"):
            return self._image_file(self.app.backgrounds.file(path.rsplit("/", 1)[1]))
        if path == "/api/logo-library":
            return self._send_json({"logos": logo_library()})
        if path.startswith("/api/logos/"):
            return self._logo(path)
        if path.startswith("/api/thumbs/"):
            return self._thumb(path[len("/api/thumbs/"):])
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
        if path == "/api/backgrounds":
            return self._upload_background()
        if path == "/api/import":
            return self._import()
        if path == "/api/calendar/scan":
            return self._scan_calendar()
        if len(parts) == 5 and parts[:3] == ["", "api", "leagues"] and parts[4] == "images":
            target = parse_qs(urlparse(self.path).query).get("target", [""])[0]
            return self._upload_image(parts[3], target)
        try:
            body = self._body()
        except ValueError as e:
            return self._error(f"Bad request: {e}")
        if path.startswith("/api/update/"):
            return self._update_action(path.rsplit("/", 1)[1], body)
        if path == "/api/export":
            return self._export(body)
        if path == "/api/export/show":
            return self._show_export(body)
        try:
            if path == "/api/cmd":
                params = body.get("params") or {}
                if not isinstance(params, dict):
                    return self._error("params must be an object")
                result = self.app.command(str(body.get("action", "")), params)
                return self._send_json({"ok": True, **result})
            if path == "/api/leagues":
                return self._send_json({"ok": True, "league": self.app.leagues.save(body)})
            if path == "/api/leagues/active":
                profile = self.app.leagues.set_active(body.get("id") or None)
                self.app.publish()
                return self._send_json({"ok": True, "active": profile["id"] if profile else None})
            if path == "/api/csv/preview":
                return self._csv_preview(body)
            if path.startswith("/api/leagues/") and path.endswith("/import-csv"):
                return self._csv_import(path.split("/")[3], body)
            if path.startswith("/api/leagues/") and path.endswith("/duplicate"):
                league = self.app.leagues.duplicate(path.split("/")[3], body.get("name"))
                return self._send_json({"ok": True, "league": league})
            if path.startswith("/api/leagues/") and path.endswith("/remove-team-from"):
                league = self.app.leagues.remove_team_from(path.split("/")[3], body.get("team"), str(body.get("league") or ""))
                self.app.publish()
                return self._send_json({"ok": True, "league": league})
            if path.startswith("/api/leagues/") and path.endswith("/import-session"):
                drivers = self.app.build_snapshot().get("drivers") or []
                if not drivers:
                    return self._error("No drivers in the current session")
                league, added = self.app.leagues.import_session(path.split("/")[3], drivers)
                self.app.publish()
                return self._send_json({"ok": True, "league": league, "added": added})
            if path == "/api/calendar/parse":
                rounds = schedule.rounds_from_text(str(body.get("text") or ""), self.app.tracks.grouped(),
                                                   day_first=body.get("day_first", True) is not False)
                return self._send_json({"ok": True, "rounds": rounds})
            if path.startswith("/api/leagues/") and path.endswith("/championship/import-meeting"):
                return self._import_meeting(path.split("/")[3], [str(r) for r in body.get("round_ids") or []])
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

    def _import_meeting(self, profile_id, round_ids):
        """Fill a race meeting's rounds with this event's race sessions, in
        order: heat 1 into its first race, heat 2 into the second, and so on."""
        app = self.app
        with app._lock:
            if not app._drivers or app._frame is None:
                return self._error("Not connected to a session")
            current = app._frame.session_num
            races = [r for r in app.race_sessions() if r["results"] or r["num"] == current]
            if not races:
                return self._error("This event has no race sessions with results yet")
            profile = app.leagues.get(profile_id)
            if profile is None:
                return self._error("League not found", HTTPStatus.NOT_FOUND)
            champ = profile.setdefault("championship", championship.normalise({}))
            rules = championship.normalise_rules(champ.get("rules"))
            by_id = {r["id"]: r for r in champ["rounds"]}
            rounds = [by_id[i] for i in round_ids if i in by_id]
            if not rounds:
                return self._error("Save the rounds first")
            done, added = [], 0
            for race, rd in zip(races, rounds):
                results, n = app.session_results(profile, add_missing=True, session_num=race["num"])
                rd["results"] = championship.apply_distance_rule(results, rules)
                rd["session"] = app.session_key(race["num"]) or ""
                if not rd["track"]:
                    rd["track"] = app._session_meta.get("track", "")
                added += n
                done.append({"round": rd["name"], "race": race["name"], "count": len(results)})
            league = app.leagues.save(profile)
        app.publish()
        return self._send_json({"ok": True, "league": league, "added": added, "imported": done,
                                "races": len(races), "rounds": len(rounds)})

    def _stream(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        version = -1
        # A page that's gone without closing its connection (a PC that went to
        # sleep, a browser that hung) doesn't keep this thread waiting on it
        # for ever: a write that can't go out in 30 s ends it.
        self.connection.settimeout(30)
        try:
            while not self.app._stop.is_set():
                new_version, data = self.app.wait_payload(version)
                if data is None:
                    self.wfile.write(b": keep-alive\n\n")
                else:
                    version = new_version
                    self.wfile.write(b"data: " + data + b"\n\n")
                self.wfile.flush()
        except OSError:  # gone: broken pipe, reset, aborted, timed out
            pass

    def _update_action(self, action, body):
        updater = getattr(self.app, "updater", None)
        if updater is None or not updater.enabled:
            return self._error("Update checks are turned off")
        if action == "check":
            return self._send_json({"ok": True, **updater.check()})
        if action == "token":
            return self._send_json({"ok": True, **updater.set_token(body.get("token"))})
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

    # -- export / import (see transfer.py) -------------------------------------

    def _league(self, league_id):
        profile = self.app.leagues.get(str(league_id or ""))
        if profile is None:
            raise transfer.TransferError("Pick a league first (and save it).")
        return profile

    def _export(self, body):
        what = body.get("what")
        try:
            if what == "overlays":
                parts, ext = ["Overlay settings"], "json"
                data = transfer.export_overlays(self.app.overlays.get(), self.app.backgrounds)
            else:
                p = self._league(body.get("league"))
                rid = body.get("round")
                label = None
                if rid:
                    n, rd = transfer._round(p, rid)
                    label = f"R{n} {rd['name']}" if rd["name"] and rd["name"] != f"Round {n}" else f"Round {n}"
                exports = {
                    "league": (["League"], "json", lambda: transfer.export_league(self.app.leagues, p)),
                    "teams": (["Teams"], "json", lambda: transfer.export_teams(self.app.leagues, p)),
                    "championship": (["Championship"], "json", lambda: transfer.export_championship(p)),
                    "standings": (["Championship standings"], "csv", lambda: transfer.standings_csv(p)),
                    "round": ([label, "Results"], "json", lambda: transfer.export_round(p, rid)),
                    "round_csv": ([label, "Results"], "csv", lambda: transfer.round_csv(p, rid)),
                    "drivers": (["Drivers"], "csv", lambda: transfer.drivers_csv(p)),
                }
                if what not in exports:
                    return self._error("Unknown export")
                parts, ext, make = exports[what]
                parts, data = [p["name"], *parts], make()
            path = transfer.save_export(parts, ext, data)
        except (transfer.TransferError, LeagueError) as e:
            return self._error(str(e))
        except OSError as e:
            return self._error(f"Couldn't save the export: {e}")
        return self._send_json({"ok": True, "path": str(path), "name": path.name, "folder": str(path.parent)})

    def _show_export(self, body):
        """Open the file manager at an export (on the PC the app runs on)."""
        folder = transfer.exports_dir().resolve()
        target = Path(str(body.get("path") or folder)).resolve()
        if target != folder and folder not in target.parents:
            return self._error("Not an export")
        from .desktop import reveal
        if not reveal(target):
            return self._error("Couldn't open the folder")
        return self._send_json({"ok": True})

    def _import(self):
        q = parse_qs(urlparse(self.path).query)
        what, league_id, round_id = (q.get(k, [""])[0] for k in ("what", "league", "round"))
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= transfer.MAX_IMPORT_BYTES:
            return self._error("Pick a file to import")
        data = self.rfile.read(length)
        store = self.app.leagues
        try:
            if what == "league":
                _, obj = transfer.expect(data, "league")
                profile, info = transfer.import_league(store, obj), {}
            elif what == "overlays":
                _, obj = transfer.expect(data, "overlays")
                profile, info = None, transfer.import_overlays(self.app.overlays, self.app.backgrounds, obj)
            else:
                p = self._league(league_id)
                if what == "teams":
                    profile, info = transfer.import_teams(store, p, transfer.expect(data, "teams")[1])
                elif what == "championship":
                    profile, info = transfer.import_championship(store, p, transfer.expect(data, "championship")[1])
                elif what == "round":
                    fmt, obj = transfer.expect(data, "round", csv_ok=True)
                    profile, info = transfer.import_round(store, p, round_id, fmt, obj)
                elif what == "drivers":
                    fmt, obj = transfer.expect(data, "drivers", csv_ok=True)
                    if fmt != "csv":
                        raise transfer.TransferError("The roster imports from a CSV file (like the Drivers export).")
                    profile, info = transfer.import_drivers_csv(store, p, obj)
                else:
                    return self._error("Unknown import")
        except (transfer.TransferError, LeagueError) as e:
            return self._error(str(e))
        self.app.publish()
        return self._send_json({"ok": True, "league": profile, "info": info})

    def _scan_calendar(self):
        """Read the text in a calendar image (sent as a PNG) and find the rounds in it."""
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= 4 * MAX_IMAGE_BYTES:
            return self._error("Image must be between 1 byte and 32 MB")
        data = self.rfile.read(length)
        day_first = parse_qs(urlparse(self.path).query).get("day_first", ["1"])[0] != "0"
        try:
            pieces = ocr.read(data)
        except ocr.OcrError as e:
            return self._error(str(e))
        rounds = schedule.rounds_from_pieces(pieces, self.app.tracks.grouped(), day_first=day_first)
        # The text as read, line by line, for pasting and correcting if the rounds are off.
        text = "\n".join(p["text"] for p in sorted(pieces, key=lambda p: (round(p["y"] / max(p["h"], 1)), p["x"])))
        return self._send_json({"ok": True, "rounds": rounds, "text": text})

    def _upload_background(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_IMAGE_BYTES:
            return self._error("Image must be between 1 byte and 8 MB")
        try:
            name = self.app.backgrounds.save(self.rfile.read(length))
        except (LeagueError, OSError) as e:
            return self._error(str(e))
        return self._send_json({"ok": True, "name": name, "backgrounds": self.app.backgrounds.list()})

    def _logo(self, path):
        parts = path.split("/")
        return self._image_file(self.app.leagues.logo_file(parts[3], parts[4]) if len(parts) == 5 else None)

    def _csv_preview(self, body):
        """A spreadsheet's columns and the guess at which is which (csvimport.py)."""
        from . import csvimport

        try:
            headers, rows = csvimport.read(body.get("text"))
        except csvimport.CsvError as e:
            raise LeagueError(str(e)) from None
        mapping = csvimport.guess(headers, rows)
        ci = mapping.get("class")
        classes = sorted({r[ci].strip() for r in rows if r[ci].strip()}) if ci is not None else []
        return self._send_json({"headers": headers, "mapping": mapping, "rows": len(rows), "sample": rows[:4],
                                "fields": list(csvimport.FIELDS), "classes": classes})

    def _csv_import(self, profile_id, body):
        """Drivers, teams and classes from a spreadsheet into a league, saved."""
        from . import csvimport

        profile = self.app.leagues.get(profile_id)
        if profile is None:
            return self._error("League not found", HTTPStatus.NOT_FOUND)
        try:
            headers, rows = csvimport.read(body.get("text"))
        except csvimport.CsvError as e:
            raise LeagueError(str(e)) from None
        given = body.get("mapping")
        mapping = {f: int(i) for f, i in (given.items() if isinstance(given, dict) else [])
                   if f in csvimport.FIELDS and str(i).lstrip("-").isdigit() and 0 <= int(i) < len(headers)}
        if not given:
            mapping = csvimport.guess(headers, rows)
        summary = csvimport.apply(profile, rows, mapping, body.get("class_role") or "main")
        league = self.app.leagues.save(profile)
        self.app.publish()
        return self._send_json({"ok": True, "league": league, "summary": summary})

    def _thumb(self, name):
        """A grid walk car picture from the user's thumbnails folder (thumbnails.py)."""
        from .thumbnails import EXTENSIONS

        target = self.app.thumbnails.path(name)
        if target is None:
            return self._error("Not found", HTTPStatus.NOT_FOUND)
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", EXTENSIONS[target.suffix.lower()])
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=86400")  # the URL changes with the file (?v=)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _image_file(self, target):
        """Send a stored image (logo or background), or 404."""
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
