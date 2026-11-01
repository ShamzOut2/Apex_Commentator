import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

from apex.config import DEFAULTS
from apex.core import App, CommandError, parse_track_length
from apex.league import LeagueStore
from apex.server import make_server
from apex.sources import MockSource, RPY_SRCH_TO_END


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make_app(tmpdir, minutes=6):
    clock = FakeClock()
    source = MockSource(seed=7, clock=clock)
    app = App(source, dict(DEFAULTS), LeagueStore(tmpdir))
    for _ in range(int(minutes * 60 * 10)):
        clock.t += 0.1
        app.tick()
    return app, source


def wait_for(predicate, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, cls.source = make_app(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.source.commands.clear()

    def test_track_length(self):
        self.assertAlmostEqual(parse_track_length("4.01 km"), 4010)
        self.assertAlmostEqual(parse_track_length("2.5 mi"), 4023.36)

    def test_snapshot(self):
        snap = self.app.build_snapshot()
        self.assertTrue(snap["connected"])
        drivers = snap["drivers"]
        self.assertEqual(len(drivers), 18)  # pace car excluded
        # Without a league, classes come straight from iRacing.
        self.assertEqual([c["key"] for c in snap["classes"]], ["iracing:GT3", "iracing:GT4"])
        self.assertEqual(snap["classes"][0]["color"], "#ffda59")
        self.assertEqual([d["pos"] for d in drivers], list(range(1, 19)))
        gaps = [d["gap"] for d in drivers]
        self.assertEqual(gaps, sorted(gaps))
        self.assertTrue(snap["events"])
        self.assertTrue(any(e["type"] == "overtake" for e in snap["events"]))
        json.dumps(snap)  # must be serialisable

    def test_watch_uses_car_number(self):
        d = self.app.build_snapshot()["drivers"][3]
        self.app.command("watch", {"car_idx": d["car_idx"], "group": 9})
        self.assertEqual(self.source.commands[-1], ("cam_switch_num", d["number"], 9, 0))
        self.app.tick()  # the camera change shows up in the next telemetry frame
        self.assertEqual(self.app.build_snapshot()["camera"]["car_idx"], d["car_idx"])

    def test_step_car(self):
        order = [d["car_idx"] for d in self.app.build_snapshot()["drivers"]]
        self.app.command("watch", {"car_idx": order[5]})
        self.app.tick()
        self.app.command("step_car", {"direction": -1})
        self.app.tick()
        self.assertEqual(self.app.build_snapshot()["camera"]["car_idx"], order[4])

    def test_replay_event_seeks_then_switches_camera_then_plays(self):
        ev = self.app.detector.events[-1]
        result = self.app.command("replay_event", {"event_id": ev["id"]})
        self.assertTrue(wait_for(lambda: len(self.source.commands) >= 4))
        target_ms = int(max(0, ev["session_time"] - DEFAULTS["replay_preroll_s"]) * 1000)
        number = self.app._drivers[ev["car_idx"]]["number"]
        self.assertEqual(self.source.commands, [
            ("replay_set_play_speed", 0, False),
            ("replay_search_session_time", ev["session_num"], target_ms),
            ("cam_switch_num", number, self.app._group(None), 0),
            ("replay_set_play_speed", 1, False),
        ])
        self.assertEqual(result["replaying"], ev["driver"])
        self.app.tick()
        self.assertFalse(self.app.build_snapshot()["replay"]["live"])
        self.app.command("live", {})
        self.assertEqual(self.source.commands[-2], ("replay_search", RPY_SRCH_TO_END))
        self.app.tick()
        self.assertTrue(self.app.build_snapshot()["replay"]["live"])

    def test_replay_driver_without_events(self):
        events = self.app.detector.events
        quiet = [i for i in self.app._drivers if not any(e["car_idx"] == i for e in events)]
        if quiet:
            with self.assertRaises(CommandError):
                self.app.command("replay_driver", {"car_idx": quiet[0]})
        with self.assertRaises(CommandError):
            self.app.command("replay_event", {"event_id": 10 ** 9})

    def test_grid_walk(self):
        g = self.app.build_snapshot()["gridwalk"]
        entries = g["entries"]
        self.assertEqual(len(entries), 18)
        self.assertEqual(g["source"], "qualifying")
        self.assertEqual([e["grid_pos"] for e in entries], list(range(1, 19)))
        # The mock's grid follows its qualifying order.
        self.assertEqual([e["car_idx"] for e in entries], [i + 1 for i in self.source.qual_order])
        self.assertTrue(all(e["car_design"] for e in entries))
        self.assertTrue(all(e["car_image"] is None and not e["has_thumb"] for e in entries))  # no pictures folder
        self.assertEqual(g["thumbs"]["folder"], "")
        self.assertEqual(entries[0]["team"], self.source.drivers[entries[0]["car_idx"]]["TeamName"])
        # Qualifying gaps are to each class's pole, which shows a gap of zero.
        seen = set()
        for e in entries:
            self.assertEqual(e["qual_time"], self.source.qual_time[e["car_idx"] - 1])
            self.assertEqual(e["qual_gap"] == 0, e["class_key"] not in seen)
            self.assertGreaterEqual(e["qual_gap"], 0)
            seen.add(e["class_key"])
        self.app.command("gridwalk_start", {})
        self.app.command("gridwalk_next", {})
        g = self.app.build_snapshot()["gridwalk"]
        self.assertEqual((g["visible"], g["running"], g["index"]), (True, True, 2))
        self.app.command("gridwalk_move", {"key": entries[1]["key"], "direction": -1})
        g = self.app.build_snapshot()["gridwalk"]
        self.assertEqual((g["entries"][0]["key"], g["source"]), (entries[1]["key"], "manual"))
        self.app.command("gridwalk_reset_order", {})
        self.app.command("gridwalk_hide", {})
        with self.assertRaises(CommandError):
            self.app.command("gridwalk_settings", {"interval": "nope"})

    def test_logging_follows_live_and_replay_without_duplicates(self):
        app, source = self.app, self.source
        source.step(0.1)
        app.tick()
        self.assertEqual(app.detection, "live")
        logged = len(app.detector.events)
        # Rewind 60s in the live race: what's on screen was already logged.
        source.replay_search_session_time(0, int((source.session_time - 60) * 1000))
        app.tick()
        self.assertEqual(app.detection, "paused")
        for _ in range(50):
            source.step(0.1)
            app.tick()
        self.assertEqual(len(app.detector.events), logged)
        self.assertEqual(app.detection, "paused")
        source.replay_search(1)  # back to live
        source.step(0.1)
        app.tick()
        self.assertEqual(app.detection, "live")

    def test_unknown_action_and_bad_car(self):
        with self.assertRaises(CommandError):
            self.app.command("self_destruct", {})
        with self.assertRaises(CommandError):
            self.app.command("watch", {"car_idx": 999})


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, cls.source = make_app(cls.tmp.name, minutes=1)
        cls.server = make_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.app.stop()
        cls.server.shutdown()
        cls.tmp.cleanup()

    def request(self, path, body=None, method=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_points_rules_apply_as_soon_as_theyre_changed(self):
        """Drop rounds (and every other rule) count straight away: the
        standings, boards and overlays don't wait for the championship's Save."""
        def res(order):
            return [{"driver": f"cust:{d}", "name": f"D{d}", "class_id": "gt3", "position": i, "status": "finished"}
                    for i, d in enumerate(order, 1)]
        league = self.app.leagues.save({"name": "Drop test", "drivers": [{"cust_id": d, "name": f"D{d}"} for d in (1, 2, 3)],
                                        "classes": [{"id": "gt3", "name": "GT3", "color": "#fff"}],
                                        "championship": {"rounds": [{"id": "a", "name": "R1", "results": res([1, 2, 3])},
                                                                    {"id": "b", "name": "R2", "results": res([3, 2, 1])}]}})
        status, r = self.request(f"/api/leagues/{league['id']}/championship/rules", {"rules": {"drop_rounds": 1}, "live_round": "b"})
        self.assertEqual(status, 200)
        saved = self.app.leagues.get(league["id"])["championship"]
        self.assertEqual((saved["rules"]["drop_rounds"], saved["live_round"], len(saved["rounds"])), (1, "b", 2))
        top = r["standings"]["groups"][0]["drivers"][0]
        self.assertLess(top["points"], top["gross"])  # a round dropped

    def test_state_and_index(self):
        status, snap = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(snap["connected"])
        with urllib.request.urlopen(self.base + "/", timeout=5) as r:
            self.assertIn(b"Apex Commentator", r.read())
        with urllib.request.urlopen(self.base + "/app.js", timeout=5) as r:
            self.assertEqual(r.headers["Content-Type"], "text/javascript")

    def test_static_traversal_blocked(self):
        status, _ = self.request("/../apex/config.py")
        self.assertEqual(status, 404)
        status, _ = self.request("/%2e%2e/config.example.json")
        self.assertEqual(status, 404)

    def test_command_endpoint(self):
        car = self.request("/api/state")[1]["drivers"][0]["car_idx"]
        status, body = self.request("/api/cmd", {"action": "watch", "params": {"car_idx": car}})
        self.assertEqual((status, body["ok"]), (200, True))
        status, body = self.request("/api/cmd", {"action": "watch", "params": {"car_idx": car, "bogus": 1}})
        self.assertEqual(status, 400)
        status, body = self.request("/api/cmd", {"action": "nope"})
        self.assertEqual(status, 400)
        self.assertIn("Unknown action", body["error"])

    def test_league_from_session_roundtrip(self):
        status, body = self.request("/api/leagues/from-session", {"name": "Test League"})
        self.assertEqual(status, 200)
        league = body["league"]
        league["drivers"][0]["nickname"] = "Rocket"
        self.assertEqual(self.request("/api/leagues", league)[0], 200)
        self.assertEqual(self.request("/api/leagues/active", {"id": league["id"]})[0], 200)
        snap = self.request("/api/state")[1]
        self.assertEqual(snap["league"]["name"], "Test League")
        nicknames = [d["league"]["nickname"] for d in snap["drivers"] if d["league"]]
        self.assertIn("Rocket", nicknames)
        self.assertEqual(self.request("/api/leagues/fetch", {"league_id": "123"})[0], 404)  # no iRacing login any more
        # Session-built leagues get one class per iRacing class, coloured like iRacing.
        self.assertEqual(sorted(c["name"] for c in league["classes"]), ["GT3", "GT4"])
        names = {c["key"]: c for c in snap["classes"]}
        self.assertEqual(set(names), {"league:gt3", "league:gt4"})
        for cls_key in names:
            in_class = [d["class_pos"] for d in snap["drivers"] if d["class_key"] == cls_key]
            self.assertEqual(in_class, list(range(1, len(in_class) + 1)))
        self.assertEqual(self.request(f"/api/leagues/{league['id']}", method="DELETE")[0], 200)

    def test_grid_walk_league_details(self):
        status, body = self.request("/api/leagues/from-session", {"name": "Grid League"})
        league = body["league"]
        first = league["drivers"][0]
        first["nickname"] = "Rocket"
        league["drivers"].append({"name": "Absent Andy", "car_number": "404", "team": "Ghost GP"})
        league = self.request("/api/leagues", league)[1]["league"]
        png = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
        for target in (f"car:cust:{first['cust_id']}", f"team:{first['team']}"):
            req = urllib.request.Request(f"{self.base}/api/leagues/{league['id']}/images?target={urllib.parse.quote(target)}",
                                         data=png, method="POST", headers={"Content-Type": "image/png"})
            urllib.request.urlopen(req, timeout=5).close()
        self.request("/api/leagues/active", {"id": league["id"]})
        self.request("/api/cmd", {"action": "gridwalk_settings", "params": {"include_absent": True}})
        entries = self.request("/api/state")[1]["gridwalk"]["entries"]
        mine = next(e for e in entries if e["name"] == first["name"])
        self.assertEqual(mine["nickname"], "Rocket")
        self.assertTrue(mine["car_image"].startswith(f"/api/logos/{league['id']}/car-"))
        self.assertTrue(mine["team_logo"].startswith(f"/api/logos/{league['id']}/team-"))
        absent = entries[-1]
        self.assertEqual((absent["name"], absent["in_session"], absent["grid_pos"]), ("Absent Andy", False, len(entries)))
        with urllib.request.urlopen(self.base + mine["car_image"], timeout=5) as r:
            self.assertEqual(r.read(), png)
        self.request("/api/cmd", {"action": "gridwalk_settings", "params": {"include_absent": False}})
        self.request(f"/api/leagues/{league['id']}", method="DELETE")

    def test_logo_upload_and_serve(self):
        league = self.request("/api/leagues", {"name": "Logo League", "classes": [{"name": "Pro", "color": "#e8463c"}]})[1]["league"]
        png = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
        req = urllib.request.Request(f"{self.base}/api/leagues/{league['id']}/classes/pro/logo", data=png,
                                     method="POST", headers={"Content-Type": "image/png"})
        with urllib.request.urlopen(req, timeout=5) as r:
            logo = json.load(r)["league"]["classes"][0]["logo"]
        with urllib.request.urlopen(f"{self.base}/api/logos/{league['id']}/{logo}", timeout=5) as r:
            self.assertEqual(r.read(), png)
            self.assertEqual(r.headers["Content-Type"], "image/png")
            self.assertIn("default-src 'none'", r.headers["Content-Security-Policy"])
        req = urllib.request.Request(f"{self.base}/api/leagues/{league['id']}/classes/pro/logo", data=b"nope",
                                     method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(self.request(f"/api/logos/{league['id']}/..%2F..%2Fx.png")[0], 404)
        self.request(f"/api/leagues/{league['id']}", method="DELETE")
        self.assertEqual(self.request(f"/api/leagues/{league['id']}")[0], 404)


if __name__ == "__main__":
    unittest.main()


class PollerTests(unittest.TestCase):
    def test_an_error_doesnt_stop_the_updates(self):
        """An error building a snapshot used to end the poller for good (every
        overlay frozen until a restart): it carries on now."""
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            app = App(MockSource(seed=3), dict(DEFAULTS, poll_hz=60, push_hz=30), LeagueStore(tmp))
            real, fails = app.build_snapshot, {"n": 3}

            def flaky():
                if fails["n"]:
                    fails["n"] -= 1
                    raise KeyError("odd data")
                return real()

            app.build_snapshot = flaky
            log = io.StringIO()
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(io.StringIO()):
                app.start()
                try:
                    self.assertTrue(wait_for(lambda: app._version >= 3, timeout=5.0))
                finally:
                    app.stop()
            self.assertEqual(fails["n"], 0)
            self.assertIn("publish error", log.getvalue())
            # Logged in full once, not every time round.
            self.assertEqual(log.getvalue().count("publish error"), 1)
            # The stream's payload: encoded once, the same bytes for every page.
            v, data = app.wait_payload(-1, timeout=0.1)
            self.assertIs(app.wait_payload(-1, timeout=0.1)[1], data)
            self.assertEqual(json.loads(data)["connected"], app._snapshot["connected"])


class LogTests(unittest.TestCase):
    def test_a_big_log_is_trimmed_to_its_latest_lines(self):
        from pathlib import Path

        from apex.desktop import trim_log

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "apex.log"
            log.write_text("".join(f"line {i}\n" for i in range(1000)))
            trim_log(log, most=100_000)  # small enough: left alone
            self.assertTrue(log.read_text().startswith("line 0\n"))
            trim_log(log, most=1000, keep=200)
            text = log.read_text()
            self.assertTrue(text.endswith("line 999\n"))
            self.assertLessEqual(len(text), 200)
            self.assertTrue(text.startswith("line "))  # from a line's start
            trim_log(Path(tmp) / "none.log")  # no log yet: nothing to do


class DataDelayTests(unittest.TestCase):
    def test_the_race_shows_a_second_late_settings_straight_away(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            app = App(MockSource(seed=3), dict(DEFAULTS), LeagueStore(tmp))
            now = {"t": 100.0}

            def snap(i):
                return {"connected": True, "session": {"time": i}, "drivers": [i], "camera": {"car_idx": i},
                        "overlays": {"standings": [i], "settings": {"n": i}}, "league": {"n": i}}

            with mock.patch("apex.core.time.monotonic", lambda: now["t"]):
                seen = []
                for i in range(20):  # 8 a second
                    seen.append(app._delay(snap(i)))
                    now["t"] += 0.125
                last = seen[-1]
                # Race data from 1 s (8 snapshots) back; settings and the league as they are now.
                self.assertEqual((last["session"]["time"], last["drivers"], last["overlays"]["standings"]), (11, [11], [11]))
                self.assertEqual((last["overlays"]["settings"], last["league"]), ({"n": 19}, {"n": 19}))
                self.assertEqual(seen[0]["session"]["time"], 0)  # just started: the oldest there is
                app.command("data_delay", {"seconds": 0})
                self.assertEqual(app._delay(snap(50))["session"]["time"], 50)  # 0: straight away
                with self.assertRaises(Exception):
                    app.command("data_delay", {"seconds": "soon"})
