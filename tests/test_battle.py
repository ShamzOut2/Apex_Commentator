import tempfile
import unittest

from apex.core import CommandError
from apex.league import profile_from_session
from apex.overlays import normalise
from tests.test_app import make_app


class BattleSettingsTests(unittest.TestCase):
    def test_drivers_kept_tidy(self):
        cfg = normalise({"battle": {"drivers": "cust:1, cust:2,cust:1,<script>,name:jo bloggs,cust:3,cust:4,cust:5,cust:6",
                                    "gap_to": "sideways"}})["battle"]
        self.assertEqual(cfg["drivers"], "cust:1,cust:2,name:jo bloggs,cust:3,cust:4")  # six at most, no repeats
        self.assertEqual(cfg["gap_to"], "first")
        self.assertFalse(cfg["visible"])


class BattleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app, self.source = make_app(self.tmp.name, minutes=2)
        drivers = self.app.build_snapshot()["drivers"]
        league = profile_from_session(drivers, "Season")
        league["championship"] = {"rules": {"points": [25, 18, 15, 12, 10, 8, 6, 4, 2, 1], "scoring": "overall"},
                                  "rounds": [{"id": "r1", "name": "Round 1"}]}
        self.league = self.app.leagues.save(league)
        self.app.leagues.set_active(self.league["id"])

    def tearDown(self):
        self.tmp.cleanup()

    def snap(self):
        return self.app.build_snapshot()

    def test_live_battle(self):
        snap = self.snap()
        self.assertIsNone(snap["overlays"]["battle"])  # nobody picked yet
        order = sorted((r for r in snap["drivers"] if r["pos"]), key=lambda r: r["pos"])
        keys = [f"cust:{r['cust_id']}" for r in order[:3]]
        # Picked in any order: shown in championship order.
        self.app.command("overlay_settings", {"overlay": "battle", "values": {"drivers": ",".join(reversed(keys)), "visible": True}})
        b = self.snap()["overlays"]["battle"]
        self.assertTrue(b["live"])
        self.assertEqual((b["group"], b["name"]), ("overall", "Overall"))
        self.assertEqual([r["driver"] for r in b["rows"]], keys)
        self.assertEqual([r["race_points"] for r in b["rows"]], [25, 18, 15])  # if it ended now
        self.assertEqual([r["pos"] for r in b["rows"]], [1, 2, 3])
        self.assertEqual([(r["gap_first"], r["gap_ahead"]) for r in b["rows"]], [(None, None), (7, 7), (10, 3)])
        self.assertTrue(all(r["name"] for r in b["rows"]))

    def test_quick_picks_from_the_car_on_camera(self):
        snap = self.snap()
        order = [r for r in sorted((r for r in snap["drivers"] if r["pos"]), key=lambda r: r["pos"])]
        key = lambda r: f"cust:{r['cust_id']}"  # noqa: E731
        with self.app._lock:
            self.source.cam_car_idx = order[3]["car_idx"]
        self.app.tick()
        self.snap()
        self.assertEqual(self.app.command("battle_pick", {"mode": "ahead"})["drivers"], [key(order[2]), key(order[3])])
        settings = self.app.overlays.get()["battle"]
        self.assertTrue(settings["visible"])
        self.assertEqual(self.app.command("hotkey", {"action": "battle:around"})["drivers"], [key(r) for r in order[2:5]])
        self.assertEqual(self.app.command("battle_pick", {"mode": "top"})["drivers"], [key(r) for r in order[:3]])
        # The leader on camera: it and the car behind.
        with self.app._lock:
            self.source.cam_car_idx = order[0]["car_idx"]
        self.app.tick()
        self.snap()
        self.assertEqual(self.app.command("battle_pick", {"mode": "ahead"})["drivers"], [key(order[0]), key(order[1])])
        with self.assertRaises(CommandError):
            self.app.command("battle_pick", {"mode": "sideways"})
        self.app.command("overlay_settings", {"overlay": "battle", "values": {"group": "nope"}})
        with self.assertRaises(CommandError):
            self.app.command("battle_pick", {"mode": "top"})


if __name__ == "__main__":
    unittest.main()
