"""The on-track battle and track map widgets' data."""

import tempfile
import unittest
from types import SimpleNamespace

from apex.config import DEFAULTS
from apex.core import App
from apex.league import LeagueStore
from apex.sources import MockSource


def entry(idx, pos, gap, cls="iracing:GT3", class_pos=None, down=0, pit=False):
    """A tower entry: ``gap`` seconds behind the leader (the leader: None)."""
    return {"car_idx": idx, "name": f"Driver {idx}", "nickname": "", "number": str(idx), "team": "", "team_logo": None,
            "class_key": cls, "paint": None, "pos": pos, "class_pos": class_pos or pos, "gap": gap, "laps_down": down,
            "class_laps_down": down, "in_world": True, "on_pit": pit}


def frame(cam, t=100.0):
    return SimpleNamespace(cam_car_idx=cam, timeline=lambda: (2, t))


class DuelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(MockSource(seed=1), dict(DEFAULTS), LeagueStore(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def duel(self, entries, cam, t=100.0, **cfg):
        if cfg:
            self.app.overlays.update("duel", cfg)
        return self.app._duel_snapshot({"standings": entries}, frame(cam, t), True)

    def test_the_driver_on_camera_and_the_cars_within_the_gap(self):
        # Leader, then 4.0 s, 7.5 s (camera), 9.0 s, 11.9 s, 20 s behind.
        entries = [entry(1, 1, None), entry(2, 2, 4.0), entry(3, 3, 7.5), entry(4, 4, 9.0), entry(5, 5, 11.9), entry(6, 6, 20.0)]
        d = self.duel(entries, 3, gap_s=5.0)
        self.assertTrue(d["active"])
        self.assertEqual([r["car_idx"] for r in d["rows"]], [2, 3, 4, 5])  # within 5 s of car 3 (not the leader, 7.5 s)
        self.assertEqual(d["pos"], 2)  # Battle for P2
        self.assertEqual([r["interval"] for r in d["rows"]], [None, 3.5, 1.5, 2.9])
        self.assertEqual([r["to_cam"] for r in d["rows"]], [-3.5, 0.0, 1.5, 4.4])
        self.assertEqual([r["cam"] for r in d["rows"]], [False, True, False, False])
        # At most N each way.
        self.assertEqual([r["car_idx"] for r in self.duel(entries, 3, behind=1)["rows"]], [2, 3, 4])
        # Not within a second of anyone: no battle.
        self.assertFalse(self.duel(entries, 6, gap_s=1.0, behind=2)["active"])

    def test_no_battle_then_it_holds_a_moment_and_goes(self):
        close = [entry(1, 1, None), entry(2, 2, 0.4)]
        apart = [entry(1, 1, None), entry(2, 2, 2.4)]
        self.assertTrue(self.duel(close, 2, t=100.0)["active"])
        held = self.duel(apart, 2, t=101.0)  # broken up a second ago: still up (hold_s 3)
        self.assertEqual((held["active"], [r["car_idx"] for r in held["rows"]]), (True, [1, 2]))
        self.assertFalse(self.duel(apart, 2, t=110.0)["active"])

    def test_its_class_or_overall(self):
        entries = [entry(1, 1, None, "a", 1), entry(2, 2, 0.3, "b", 1), entry(3, 3, 0.7, "a", 2)]
        d = self.duel(entries, 3)  # class a: 1 and 3, 0.7 s apart (car 2 of class b between them on track)
        self.assertEqual([r["car_idx"] for r in d["rows"]], [1, 3])
        self.assertEqual([r["pos"] for r in d["rows"]], [1, 2])  # class places
        self.assertTrue(d["multiclass"])
        d = self.duel(entries, 3, scope="overall")
        self.assertEqual([r["car_idx"] for r in d["rows"]], [1, 2, 3])
        self.assertEqual([r["pos"] for r in d["rows"]], [1, 2, 3])
        self.assertFalse(d["multiclass"])

    def test_not_a_lap_apart_or_in_the_pits(self):
        lapped = [entry(1, 1, None), entry(2, 2, 0.3, down=1)]
        self.assertFalse(self.duel(lapped, 2)["active"])
        pitting = [entry(1, 1, None), entry(2, 2, 0.3, pit=True), entry(3, 3, 0.9)]
        self.assertEqual([r["car_idx"] for r in self.duel(pitting, 3)["rows"]], [1, 3])


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
