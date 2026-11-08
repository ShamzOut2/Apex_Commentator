"""Live timing for spectators: what its server answers, what the feed holds
(nothing about the host), and the Cloudflare tunnel's public link."""

import io
import json
import re
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from apex import spectate
from apex.paths import WEB_DIR
from tests.test_app import make_app, wait_for


def get(url, method="GET"):
    req = urllib.request.Request(url, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = spectate.SpectatorServer(WEB_DIR / "live", port=0).start()
        self.base = f"http://127.0.0.1:{self.server.port}"

    def tearDown(self):
        self.server.stop()

    def test_only_the_page_its_feed_map_and_logos(self):
        status, headers, body = get(self.base + "/")
        self.assertEqual(status, 200)
        self.assertIn(b"live.js", body)
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertNotIn("Python", headers.get("Server", ""))
        for path in ("/api/state", "/api/leagues", "/index.html/../../apex/core.py", "/../config.json", "/overlays.json",
                     "/img/../../config.json", "/img/0123456789abcdef"):
            self.assertEqual(get(self.base + path)[0], 404, path)
        self.assertEqual(get(self.base + "/feed", "POST")[0], 405)  # nothing can be changed from outside

    def test_framed_only_by_this_pcs_app_and_its_preview_isnt_a_viewer(self):
        headers = get(self.base + "/")[1]
        self.assertIn("frame-ancestors http://localhost:* http://127.0.0.1:*;", headers["Content-Security-Policy"])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.server.update({"title": "Race", "cars": []})
        with opener.open(self.base + "/feed?preview=1", timeout=5) as r:
            r.readline()
            self.assertEqual(self.server.viewers, 0)

    def test_on_this_pc_only(self):
        self.assertEqual(self.server.host, "127.0.0.1")
        self.assertEqual(self.server._server.server_address[0], "127.0.0.1")

    def test_logos_by_token_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            logo = Path(tmp) / "team-1a2b3c4d.png"
            logo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
            self.server.update({"cars": []}, images={"0123456789abcdef": str(logo)})
            status, headers, body = get(self.base + "/img/0123456789abcdef")
            self.assertEqual((status, headers["Content-Type"]), (200, "image/png"))

    def test_feed_and_map(self):
        self.server.update({"title": "Race", "cars": []}, track_map={"id": "1:library", "points": [[0.1, 0.2]] * 60})
        self.assertEqual(json.loads(get(self.base + "/map.json")[2])["id"], "1:library")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(self.base + "/feed", timeout=5) as r:
            line = r.readline()
            self.assertTrue(line.startswith(b"data: "))
            self.assertEqual(json.loads(line[6:])["title"], "Race")
            self.assertEqual(self.server.viewers, 1)


class FeedTests(unittest.TestCase):
    def test_nothing_about_the_host_or_the_drivers_accounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=1.5)
            app.settings.set("spectate_token", "secret-token-value")
            app.settings.set("follow_code", "123456")
            app.spectators = spectate.SpectatorServer(WEB_DIR / "live", port=0)  # not started: just collecting
            section = app.build_snapshot()["spectator"]
            app.settings.set("spectate_token", "")
            app.settings.set("follow_code", "")
            text = json.dumps(section)
            self.assertTrue(section["cars"])
            allowed = {"id", "pos", "cpos", "pc", "num", "name", "abbr", "team", "logo", "cls", "gap", "int", "down", "lap",
                       "laps", "last", "best", "pct", "pit", "out", "fin", "tyre", "fl", "cfl", "sec", "now", "bsec"}
            for car in section["cars"]:
                self.assertLessEqual(set(car), allowed)
            for bad in ("cust", "notes", "secret-token-value", "123456", "127.0.0.1", "/api/", "\\\\", tmp):
                self.assertNotIn(bad, text, bad)
            self.assertIsNone(re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text))  # no IP addresses
            # It never goes to the app's own pages.
            app.publish()
            self.assertNotIn("spectator", app._snapshot)


    def test_every_driver_whatever_the_tower_shows(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=1.5)
            app.overlays.update("standings", {"rows": 3, "rows_last": 0, "mode": "class", "rows_class": 2})
            app.spectators = spectate.SpectatorServer(WEB_DIR / "live", port=0)
            snap = app.build_snapshot()
            everyone = {r["car_idx"] for r in snap["drivers"] if not r.get("hidden")}
            self.assertGreater(len(everyone), 3)
            self.assertEqual({c["id"] for c in snap["spectator"]["cars"]}, everyone)
            self.assertIsInstance(snap["spectator"]["clock"], float)


    def test_the_live_timing_tabs_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=1.5)
            app.spectators = spectate.SpectatorServer(WEB_DIR / "live", port=0)
            before = app.build_snapshot()["spectator"]
            self.assertTrue(any(c["team"] for c in before["cars"]))
            app.overlays.update("live", {"name_format": "last", "show_team": False, "show_logo": False, "title": "Sunday Cup",
                                         "show_sectors": False, "tracker": False, "map_label": "number", "accent_color": "#1E90FF"})
            app._spec = (0.0, None, None, {})
            section = app.build_snapshot()["spectator"]
            self.assertEqual(section["series"], "Sunday Cup")
            first = {c["id"]: c for c in before["cars"]}
            for car in section["cars"]:
                self.assertEqual((car["team"], car["logo"]), ("", None))
                self.assertEqual(car["name"], first[car["id"]]["name"].split()[-1])
            look = section["look"]
            self.assertEqual((look["accent"], look["label"], look["tracker"], look["sectors"], look["tyre"]),
                             ("#1e90ff", "number", False, False, True))

    def test_name_styles(self):
        from apex.core import App
        f = App._format_name
        self.assertEqual(f("Max Verstappen", "", "initial_last"), "M. Verstappen")
        self.assertEqual(f("Max Verstappen", "", "last_initial"), "Verstappen M.")
        self.assertEqual(f("Max Verstappen", "", "abbrev"), "VER")
        self.assertEqual(f("Max Verstappen", "Mad Max", "nickname"), "Mad Max")
        self.assertEqual(f("Max Verstappen", "", "nickname"), "Max Verstappen")
        self.assertEqual(f("Senna", "", "first"), "Senna")


class TunnelTests(unittest.TestCase):
    def test_quick_link_from_cloudflared(self):
        lines = [b"INF Requesting new quick Tunnel on trycloudflare.com...\n",
                 b'ERR failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": EOF\n',
                 b"INF |  https://brave-fox-123.trycloudflare.com  |\n"]

        class Proc:
            def __init__(self, cmd, **kw):
                Proc.cmd = cmd
                self.stdout = io.BytesIO(b"".join(lines))

            def wait(self, timeout=None):
                time.sleep(0.2)

            def poll(self):
                return None

            def terminate(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "cloudflared"
            t = spectate.Tunnel(tmp, "http://127.0.0.1:8191/", popen=Proc)
            t.binary = lambda: str(fake)
            t.start()
            self.assertTrue(wait_for(lambda: t.public_url == "https://brave-fox-123.trycloudflare.com"))
            self.assertIn("--url", Proc.cmd)
            self.assertEqual(Proc.cmd[Proc.cmd.index("--url") + 1], "http://127.0.0.1:8191/")
            t.stop()
            self.assertEqual(t.public_url, "")

    def test_cloudflares_own_address_in_an_error_isnt_the_link(self):
        line = 'ERR failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": EOF'
        self.assertIsNone(spectate.QUICK_URL.search(line))
        self.assertEqual(spectate.QUICK_URL.search("INF |  https://brave-fox-123.trycloudflare.com  |").group(0),
                         "https://brave-fox-123.trycloudflare.com")

    def test_own_tunnel_with_a_token(self):
        t = spectate.Tunnel("bin", "http://127.0.0.1:8191/", token="abc", public_url="https://timing.example.com")
        self.assertEqual(t._command("cloudflared")[-3:], ["run", "--token", "abc"])
        self.assertEqual(t.public_url, "https://timing.example.com")


if __name__ == "__main__":
    unittest.main()
