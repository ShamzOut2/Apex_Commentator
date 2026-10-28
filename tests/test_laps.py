import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from apex.config import DEFAULTS
from apex.core import App
from apex.laps import LapTracker, colour, sector_starts
from apex.league import LeagueStore
from apex.overlays import OverlaySettings, normalise
from apex.sources import TRK_OFF_TRACK, TRK_ON_TRACK, MockSource


@dataclass
class F:
    """Just the frame fields the lap tracker reads (one car, index 0)."""
    session_time: float
    pct: list
    session_num: int = 0
    surface: list = field(default_factory=lambda: [TRK_ON_TRACK])
    on_pit: list = field(default_factory=lambda: [False])
    last_lap: list = field(default_factory=lambda: [-1.0])


def drive(tracker, laps, start_t=0.0, start_pct=0.9, dt=0.1, sector_s=(30.0, 30.0, 30.0), off_at=None, last_lap=None):
    """Drive one car round a 3-sector lap (starts 0, 1/3, 2/3) with the given sector times."""
    t, pct = start_t, start_pct
    while pct < 1.0:  # roll up to the line at the pace of the last sector
        tracker.update(F(t, [pct]), lambda i: "A")
        t += dt
        pct += dt / (sector_s[2] * 3)
    pct = round(pct - 1.0, 9)
    for lap in range(laps):
        for n, s in enumerate(sector_s):
            end = (n + 1) / 3
            while pct < end - 1e-9:
                surface = [TRK_OFF_TRACK] if off_at is not None and abs(pct - off_at) < 0.01 else [TRK_ON_TRACK]
                ll = [last_lap if last_lap is not None and lap > 0 else -1.0]
                tracker.update(F(t, [pct % 1.0], surface=surface, last_lap=ll), lambda i: "A")
                t += dt
                pct += dt / (s * 3)
        pct = round(pct - 1.0, 9)
    tracker.update(F(t, [pct % 1.0], last_lap=[last_lap or -1.0]), lambda i: "A")
    return t


class LapTrackerTests(unittest.TestCase):
    def test_sector_starts(self):
        info = {"SplitTimeInfo": {"Sectors": [{"SectorNum": 0, "SectorStartPct": 0.0},
                                              {"SectorNum": 1, "SectorStartPct": 0.4}]}}
        self.assertEqual(sector_starts(info), (0.0, 0.4))
        self.assertEqual(sector_starts({}), (0.0, 1 / 3, 2 / 3))

    def test_colours(self):
        self.assertEqual(colour(30.0, None, 0.2), "purple")
        self.assertEqual(colour(29.9, 30.0, 0.2), "purple")
        self.assertEqual(colour(30.15, 30.0, 0.2), "green")
        self.assertEqual(colour(30.3, 30.0, 0.2), "yellow")

    def test_times_sectors_and_laps(self):
        lt = LapTracker()
        t = drive(lt, 2, sector_s=(30.0, 31.0, 29.0))
        car = lt.cars[0]
        self.assertEqual(car.laps, 2)
        self.assertAlmostEqual(car.best_lap, 90.0, delta=0.05)
        for got, want in zip(car.best_sectors, (30.0, 31.0, 29.0)):
            self.assertAlmostEqual(got, want, delta=0.05)
        st = lt.state(0, t)
        self.assertEqual(st["state"], "finished")
        self.assertAlmostEqual(st["delta"], 0.0, delta=0.05)
        self.assertEqual(len(st["sectors"]), 3)
        # Hidden after 5 s: then the new lap shows.
        self.assertEqual(lt.state(0, t + 6)["state"], "running")

    def test_faster_lap_is_purple_with_negative_delta(self):
        lt = LapTracker()
        drive(lt, 1, sector_s=(30.0, 30.0, 30.0))
        t = drive(lt, 1, start_t=lt.cars[0].t, start_pct=lt.cars[0].pct, sector_s=(29.0, 30.1, 31.0))
        last = lt.state(0, t)
        self.assertLess(abs(last["delta"]), 0.2)
        self.assertEqual([s["colour"] for s in last["sectors"]], ["purple", "green", "yellow"])

    def test_off_track_lap_is_invalid_and_not_a_best(self):
        lt = LapTracker()
        t = drive(lt, 1, sector_s=(25.0, 25.0, 25.0), off_at=0.5)
        self.assertFalse(lt.state(0, t)["valid"])
        self.assertIsNone(lt.best(0))

    def test_out_lap_is_not_timed(self):
        lt = LapTracker()
        lt.update(F(0.0, [0.95], on_pit=[True]), lambda i: "A")
        lt.update(F(0.5, [0.01], on_pit=[True]), lambda i: "A")
        self.assertIsNone(lt.cars[0].lap)

    def test_iracing_lap_time_is_adopted(self):
        lt = LapTracker()
        drive(lt, 1, sector_s=(30.0, 30.0, 30.0), last_lap=90.123)
        self.assertEqual(lt.cars[0].last["lap_time"], 90.123)
        self.assertEqual(lt.best(0), 90.123)
        self.assertEqual(lt.cars[0].lap["ref_lap"], 90.123)  # the next lap's target too

    def test_new_session_resets(self):
        lt = LapTracker()
        drive(lt, 1)
        lt.update(F(5.0, [0.2], session_num=1), lambda i: "A")
        self.assertIsNone(lt.best(0))


class OverlaySettingsTests(unittest.TestCase):
    def test_normalise_clamps_and_rejects(self):
        s = normalise({"laps": {"count": 99, "reference": "nope", "green_s": "0.3"}, "standings": {"mode": "class"}})
        self.assertEqual(s["laps"]["count"], 12)
        self.assertEqual(s["laps"]["reference"], "personal")
        self.assertEqual(s["laps"]["green_s"], 0.3)
        self.assertEqual(s["standings"]["mode"], "class")

    def test_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overlays.json"
            OverlaySettings(path).update("standings", {"rows": 10})
            self.assertEqual(OverlaySettings(path).get()["standings"]["rows"], 10)


class QualifyingOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = 0.0
        self.source = MockSource(seed=3, session="qualify", clock=lambda: self.t)
        self.app = App(self.source, dict(DEFAULTS), LeagueStore(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def run_for(self, seconds):
        for _ in range(int(seconds * 10)):
            self.t += 0.1
            self.app.tick()

    def test_standings_blank_until_laps_then_by_lap_time(self):
        self.run_for(5)
        ov = self.app.build_snapshot()["overlays"]
        self.assertEqual(ov["session_kind"], "qualify")
        self.assertEqual(ov["standings"], [])
        self.assertTrue(ov["laps"]["active"])
        self.run_for(240)
        standings = self.app.build_snapshot()["overlays"]["standings"]
        self.assertGreater(len(standings), 5)
        times = [e["best"] for e in standings]
        self.assertEqual(times, sorted(times))
        self.assertIsNone(standings[0]["gap"])
        self.assertAlmostEqual(standings[1]["gap"], times[1] - times[0], places=3)

    def test_trackers_and_spectated_car(self):
        self.run_for(120)
        laps = self.app.build_snapshot()["overlays"]["laps"]
        self.assertEqual(laps["sectors"], 3)
        self.assertEqual(laps["camera"]["car_idx"], self.source.cam_car_idx)
        self.assertTrue(laps["trackers"])
        self.assertNotIn(self.source.cam_car_idx, [t["car_idx"] for t in laps["trackers"]])

    def test_settings_command_works_offline(self):
        self.app.command("overlay_settings", {"overlay": "laps", "values": {"count": 6}})
        self.assertEqual(self.app.overlays.get()["laps"]["count"], 6)

    def test_race_has_no_lap_tracker(self):
        app = App(MockSource(seed=3, clock=lambda: self.t), dict(DEFAULTS), LeagueStore(self.tmp.name))
        app.tick()
        ov = app.build_snapshot()["overlays"]
        self.assertFalse(ov["laps"]["active"])
        self.assertEqual(len(ov["standings"]), 18)
