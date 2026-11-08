"""The on-track battle and track map widgets' data."""

import tempfile
import unittest
from types import SimpleNamespace

from apex.config import DEFAULTS
from apex.core import App
from apex.league import LeagueStore
from apex.sources import MockSource


def entry(idx, pos, interval, cls="iracing:GT3", class_pos=None, class_interval=None, down=0):
    return {"car_idx": idx, "name": f"Driver {idx}", "nickname": "", "number": str(idx), "team": "", "team_logo": None,
            "class_key": cls, "paint": None, "pos": pos, "class_pos": class_pos or pos, "interval": interval,
            "class_interval": class_interval if class_interval is not None else interval, "laps_down": down,
            "class_laps_down": down, "in_world": True, "on_pit": False}


def frame(cam, t=100.0):
    return SimpleNamespace(cam_car_idx=cam, timeline=lambda: (2, t))


class DuelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(MockSource(seed=1), dict(DEFAULTS), LeagueStore(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def duel(self, entries, cam, t=100.0):
        return self.app._duel_snapshot({"standings": entries}, frame(cam, t), True)

    def test_the_cars_within_the_gap_either_side(self):
        # 1 -- 3.0 s -- 2 -- 0.6 -- 3 (camera) -- 0.8 -- 4 -- 2.5 -- 5
        entries = [entry(1, 1, None), entry(2, 2, 3.0), entry(3, 3, 0.6), entry(4, 4, 0.8), entry(5, 5, 2.5)]
        d = self.duel(entries, 3)
        self.assertTrue(d["active"])
        self.assertEqual([r["car_idx"] for r in d["rows"]], [2, 3, 4])
        self.assertEqual(d["pos"], 2)  # Battle for P2
        self.assertEqual([r["interval"] for r in d["rows"]], [None, 0.6, 0.8])
        self.assertEqual([r["cam"] for r in d["rows"]], [False, True, False])
        # One car each side at most (the default), whatever the gap: a train of four shows three.
        entries = [entry(1, 1, None), entry(2, 2, 0.5), entry(3, 3, 0.5), entry(4, 4, 0.5)]
        self.assertEqual([r["car_idx"] for r in self.duel(entries, 2)["rows"]], [1, 2, 3])

    def test_no_battle_then_it_holds_a_moment_and_goes(self):
        close = [entry(1, 1, None), entry(2, 2, 0.4)]
        apart = [entry(1, 1, None), entry(2, 2, 2.4)]
        self.assertTrue(self.duel(close, 2, t=100.0)["active"])
        held = self.duel(apart, 2, t=101.0)  # broken up a second ago: still up (hold_s 3)
        self.assertEqual((held["active"], [r["car_idx"] for r in held["rows"]]), (True, [1, 2]))
        self.assertFalse(self.duel(apart, 2, t=110.0)["active"])

    def test_by_hand_it_shows_the_cars_either_side_anyway(self):
        self.app.overlays.update("duel", {"auto": False})
        d = self.duel([entry(1, 1, None), entry(2, 2, 4.0), entry(3, 3, 6.0)], 2)
        self.assertEqual([r["car_idx"] for r in d["rows"]], [1, 2, 3])
        self.assertFalse(d["active"])

    def test_only_cars_in_the_same_class_on_the_same_lap(self):
        entries = [entry(1, 1, None, "a", 1), entry(2, 2, 0.3, "b", 1, None), entry(3, 3, 0.4, "a", 2, 0.7)]
        d = self.duel(entries, 3)  # class a: 1 and 3, 0.7 s apart on track (car 2 of class b between them)
        self.assertEqual([r["car_idx"] for r in d["rows"]], [1, 3])
        self.assertEqual(d["rows"][1]["interval"], 0.7)
        self.assertTrue(d["multiclass"])
        lapped = [entry(1, 1, None), entry(2, 2, 0.3, down=1)]
        self.assertFalse(self.duel(lapped, 2)["active"])


class TrackMapTests(unittest.TestCase):
    def test_every_car_on_track_with_its_class_colours(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = {"t": 0.0}
            app = App(MockSource(seed=4, clock=lambda: clock["t"]), dict(DEFAULTS), LeagueStore(tmp))
            for _ in range(300):
                clock["t"] += 0.1
                app.tick()
            snap = app.build_snapshot()
            tm = snap["overlays"]["trackmap"]
            on_track = [r for r in snap["drivers"] if r["in_world"] and r["pct"] is not None and not r.get("hidden")]
            self.assertEqual(len(tm["cars"]), len(on_track))
            colors = {c["key"]: c["color"] for c in snap["classes"]}
            for car, r in zip(sorted(tm["cars"], key=lambda c: c["id"]), sorted(on_track, key=lambda r: r["car_idx"])):
                self.assertEqual(car["pct"], r["pct"])
                self.assertEqual(car["main"], colors[r["class_key"]])
                self.assertEqual(car["second"], car["main"])  # no league: no secondary class
            self.assertIsNone(tm["map"])  # no track map store in the tests
            self.assertIsNone(app.trackmap_points())


class PerLeagueSettingsTests(unittest.TestCase):
    def test_each_league_its_own_brought_in_as_its_picked(self):
        from pathlib import Path

        from apex.overlays import OverlaySettings
        with tempfile.TemporaryDirectory() as tmp:
            o = OverlaySettings(Path(tmp) / "overlays.json")
            o.use_league("jwb")
            o.update("standings", {"rows": 12, "visible": True})
            # A league with none of its own yet starts from these.
            self.assertFalse(o.use_league("vcr"))
            self.assertEqual(o.get()["standings"]["rows"], 12)
            o.update("standings", {"rows": 25, "visible": False})
            # Back to JWB: its own (what's on screen stays as it is).
            self.assertTrue(o.use_league("jwb"))
            self.assertEqual((o.get()["standings"]["rows"], o.get()["standings"]["visible"]), (12, False))
            self.assertTrue(o.use_league("vcr"))
            self.assertEqual(o.get()["standings"]["rows"], 25)
            # Kept on disk: the app started again, on VCR, has JWB's too.
            again = OverlaySettings(Path(tmp) / "overlays.json")
            again.use_league("vcr")
            self.assertEqual(again.get()["standings"]["rows"], 25)
            again.use_league("jwb")
            self.assertEqual(again.get()["standings"]["rows"], 12)
            # Copying another league's into this one; a duplicate starts with the same.
            again.copy_from("vcr")
            self.assertEqual(again.get()["standings"]["rows"], 25)
            again.copy_league("vcr", "vcr-copy")
            self.assertTrue(again.has_league("vcr-copy"))
            with self.assertRaises(ValueError):
                again.copy_from("nobody")

    def test_the_app_switches_them_with_the_league(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LeagueStore(tmp)
            a = store.save({"name": "JWB", "drivers": []})
            b = store.save({"name": "VCR", "drivers": []})
            app = App(MockSource(seed=1), dict(DEFAULTS), store)
            store.set_active(a["id"])
            app.build_snapshot()
            app.command("overlay_settings", {"overlay": "standings", "values": {"rows": 9}})
            store.set_active(b["id"])
            snap = app.build_snapshot()
            app.command("overlay_settings", {"overlay": "standings", "values": {"rows": 30}})
            store.set_active(a["id"])
            snap = app.build_snapshot()
            self.assertEqual(snap["overlays"]["settings"]["standings"]["rows"], 9)
            self.assertEqual([lg["name"] for lg in snap["overlay_leagues"]], ["VCR"])


if __name__ == "__main__":
    unittest.main()
