import json
import tempfile
import threading
import time
import unittest
import urllib.error
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
        status, body = self.request("/api/leagues/fetch", {"league_id": "123"})
        self.assertEqual(status, 400)  # no API client configured
        self.assertEqual(self.request(f"/api/leagues/{league['id']}", method="DELETE")[0], 200)
        self.assertEqual(self.request(f"/api/leagues/{league['id']}")[0], 404)


if __name__ == "__main__":
    unittest.main()
