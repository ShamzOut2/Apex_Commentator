import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from apex.config import DEFAULTS
from apex.core import App
from apex.laps import LapTracker, colour, group_sectors, sector_starts
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
    lap: list = field(default_factory=lambda: [-1])


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

    def test_group_sectors(self):
        track = (0.0, 0.1, 0.22, 0.35, 0.47, 0.6, 0.71, 0.84)
        self.assertEqual(group_sectors(track, 3), (0.0, 0.35, 0.71))
        self.assertEqual(group_sectors(track, 2), (0.0, 0.47))
        self.assertEqual(group_sectors(track, 0), track)
        self.assertEqual(group_sectors((0.0, 0.5), 3), (0.0, 0.5))

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

    def test_a_hair_backwards_doesnt_lose_the_lap(self):
        # iRacing's position for other cars can step back a little now and then
        # (its smoothing of their position over the network), also at the line.
        lt = LapTracker()
        t, pct, step = 0.0, 0.95, 0.1 / 90
        jitter = 0
        while pct < 3.2:
            jitter += 1
            back = 0.003 if jitter % 7 == 0 else 0.0  # a step back from the last position
            lt.update(F(t, [(pct - back) % 1.0]), lambda i: "A")
            t += 0.1
            pct += step
        car = lt.cars[0]
        self.assertEqual(car.laps, 2)  # both full laps timed
        self.assertAlmostEqual(car.best_lap, 90.0, delta=0.1)
        self.assertEqual(lt.state(0, t + 10)["state"], "running")  # and the third under way

    def test_faster_lap_is_purple_with_negative_delta(self):
        lt = LapTracker()
        drive(lt, 1, sector_s=(30.0, 30.0, 30.0))
        t = drive(lt, 1, start_t=lt.cars[0].t, start_pct=lt.cars[0].pct, sector_s=(29.0, 30.1, 31.0))
        last = lt.state(0, t)
        self.assertLess(abs(last["delta"]), 0.2)
        self.assertEqual([s["colour"] for s in last["sectors"]], ["purple", "green", "yellow"])
        # Each sector against what it was compared with (their best before), and how long ago it was done.
        self.assertEqual([round(s["delta"]) for s in last["sectors"]], [-1, 0, 1])
        self.assertLess(last["sectors"][2]["age"], 1.0)  # the last one: just now
        self.assertGreater(last["sectors"][0]["age"], 50)

    def test_off_track_lap_is_invalid_and_not_a_best(self):
        lt = LapTracker()
        t = drive(lt, 1, sector_s=(25.0, 25.0, 25.0), off_at=0.5)
        self.assertFalse(lt.state(0, t)["valid"])
        self.assertIsNone(lt.best(0))

    def test_an_invalid_lap_is_marked(self):
        lt = LapTracker()
        t = drive(lt, 1, sector_s=(25.0, 25.0, 25.0), off_at=0.5)  # off in the second sector
        st = lt.state(0, t)
        self.assertEqual(st["state"], "finished")
        self.assertEqual([s["mark"] for s in st["sectors"]], ["struck"] * 3)  # done: every sector struck through
        # On the way round: the sector it happened in struck, the rest greyed.
        lt = LapTracker()
        drive(lt, 0)
        t = lt.cars[0].t
        for i, pct in enumerate((0.15, 0.30, 0.40, 0.50, 0.55, 0.60, 0.70)):
            surface = [TRK_OFF_TRACK] if pct == 0.50 else [TRK_ON_TRACK]
            lt.update(F(t + 3 * (i + 1), [pct], surface=surface), lambda i: "A")
        # (The lap started at the line before 0.40; sector 1 ended at 1/3.)
        st = lt.state(0, t + 21, hide_s=0)
        self.assertEqual([s["mark"] for s in st["sectors"]], [None, "struck", "grey"])

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

    def test_a_hiccup_of_a_second_or_two_keeps_the_lap(self):
        tr = LapTracker()
        drive(tr, 1, sector_s=(30.0, 30.0, 30.0))
        t = tr.cars[0].t
        tr.update(F(t + 1.5, [0.05]), lambda i: "A")  # the app was busy for 1.5 s
        st = tr.state(0, t + 20, hide_s=0)
        self.assertEqual(st["state"], "running")

    def test_lap_counter_starts_a_lap_when_the_line_was_missed(self):
        tr = LapTracker()
        tr.update(F(0.0, [0.5], lap=[3]), lambda i: "A")
        tr.update(F(0.1, [0.501], lap=[3]), lambda i: "A")
        self.assertIsNone(tr.state(0, 0.1))  # joined mid-lap: nothing timed
        tr.update(F(0.2, [0.502], lap=[4]), lambda i: "A")  # iRacing says a new lap began
        self.assertEqual(tr.state(0, 0.3)["state"], "running")

    def test_a_replay_rewound_times_again(self):
        tr = LapTracker()
        t = drive(tr, 2)
        tr.update(F(5.0, [0.95]), lambda i: "A")  # back to the start of the session
        self.assertIsNone(tr.state(0, 5.0))
        t = drive(tr, 1, start_t=5.1, start_pct=0.96)
        self.assertIsNotNone(tr.state(0, tr.cars[0].t))

    def test_overall_reference_is_anyones_best(self):
        tr = LapTracker()
        classes = {0: "A", 1: "B"}
        # Car 1 (class B) sets a quick first sector; car 0 (class A) then a slower one.
        for t, p0, p1 in ((0.0, 0.95, 0.95), (1.0, 0.01, 0.01), (5.0, 0.15, 0.2), (9.0, 0.3, 0.36), (12.0, 0.36, 0.45)):
            tr.update(F(t, [p0, p1], surface=[TRK_ON_TRACK] * 2, on_pit=[False] * 2, last_lap=[-1.0] * 2, lap=[-1] * 2),
                      lambda i: classes[i])
        mine = tr.cars[0].lap["colours"][0]
        self.assertEqual(mine["session"], "purple")   # fastest in its class
        self.assertEqual(mine["overall"], "yellow")   # but not overall
        self.assertEqual(tr.state(0, 12.0, "overall")["sectors"][0]["colour"], "yellow")

    def run_two(self, tr, car0, car1, off0_at=None, classes=("A", "A")):
        times = (0, 1, 5, 6, 7, 10, 11, 13, 14)
        for t, p0, p1 in zip(times, car0, car1):
            surface = [TRK_OFF_TRACK if off0_at is not None and t >= off0_at else TRK_ON_TRACK, TRK_ON_TRACK]
            tr.update(F(t, [p0, p1], surface=surface, on_pit=[False] * 2, last_lap=[-1.0] * 2, lap=[-1] * 2),
                      lambda i: classes[i])

    def test_a_purple_beaten_by_someone_else_turns_green(self):
        tr = LapTracker()
        # Car 0 sets the first sector (~9.8 s); car 1, a lap behind on the road, then does it in ~7.3 s.
        self.run_two(tr, (.99, .01, .20, .25, .27, .33, .34, .36, .37), (.70, .75, .90, .99, .01, .20, .25, .30, .34))
        self.assertEqual(tr.cars[0].lap["colours"][0]["session"], "purple")  # purple when it was set
        for ref in ("session", "overall"):
            self.assertEqual(tr.state(0, 14, ref)["sectors"][0]["colour"], "green", ref)
            self.assertEqual(tr.state(1, 14, ref)["sectors"][0]["colour"], "purple", ref)
        self.assertEqual(tr.state(0, 14, "personal")["sectors"][0]["colour"], "purple")  # still their own best
        # In another class, car 1 only beats car 0 overall.
        tr = LapTracker()
        self.run_two(tr, (.99, .01, .20, .25, .27, .33, .34, .36, .37), (.70, .75, .90, .99, .01, .20, .25, .30, .34),
                     classes=("A", "B"))
        self.assertEqual(tr.state(0, 14, "session")["sectors"][0]["colour"], "purple")
        self.assertEqual(tr.state(0, 14, "overall")["sectors"][0]["colour"], "green")

    def test_an_invalidated_lap_s_sector_is_not_the_fastest(self):
        slow1 = (.98, .02, .10, .15, .18, .25, .27, .32, .34)  # car 1: the first sector in ~13.2 s
        fast0 = (.99, .01, .20, .25, .27, .33, .34, .36, .37)  # car 0: ~9.8 s, then off track at t = 13
        tr = LapTracker()
        self.run_two(tr, fast0, slow1)
        self.assertEqual(tr.state(1, 14, "session")["sectors"][0]["colour"], "yellow")  # slower than car 0's
        tr = LapTracker()
        self.run_two(tr, fast0, slow1, off0_at=13)
        self.assertFalse(tr.cars[0].lap["valid"])
        self.assertAlmostEqual(tr.sector_best(0, "A"), tr.cars[1].lap["splits"][0], places=3)
        for ref in ("session", "overall"):
            self.assertEqual(tr.state(1, 14, ref)["sectors"][0]["colour"], "purple", ref)
        # Car 1's sector was yellow when it was set (car 0's lap still clean); car 0
        # goes off later: car 1's is the fastest now, purple.
        tr = LapTracker()
        late = (.98, .02, .10, .15, .18, .25, .27, .34, .35)  # car 1 through the sector by t = 13
        self.run_two(tr, fast0, late, off0_at=14)
        self.assertEqual(tr.cars[1].lap["colours"][0]["session"], "yellow")
        self.assertEqual(tr.state(1, 14, "session")["sectors"][0]["colour"], "purple")

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
        # Timed drivers only (no "fill in as drivers complete a lap").
        self.app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": False}})

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

    def test_many_track_sectors_are_shown_as_three(self):
        source = MockSource(seed=3, session="qualify", clock=lambda: self.t, sectors=9)
        app = App(source, dict(DEFAULTS), LeagueStore(self.tmp.name))
        app.tick()
        self.assertEqual(len(app._track_sectors), 9)
        self.assertEqual(app.build_snapshot()["overlays"]["laps"]["sectors"], 3)
        app.command("overlay_settings", {"overlay": "laps", "values": {"sectors": 0}})
        self.assertEqual(app.build_snapshot()["overlays"]["laps"]["sectors"], 9)

    def test_settings_command_works_offline(self):
        self.app.command("overlay_settings", {"overlay": "laps", "values": {"count": 6}})
        self.assertEqual(self.app.overlays.get()["laps"]["count"], 6)

    def test_race_has_no_lap_tracker(self):
        app = App(MockSource(seed=3, clock=lambda: self.t), dict(DEFAULTS), LeagueStore(self.tmp.name))
        app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": False}})
        app.tick()
        ov = app.build_snapshot()["overlays"]
        self.assertFalse(ov["laps"]["active"])
        self.assertEqual(len(ov["standings"]), 18)
