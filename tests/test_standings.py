import tempfile
import unittest

from apex.config import DEFAULTS
from apex.core import App, _session_limit
from apex.league import LeagueStore
from apex.sources import MockSource


class StandingsOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = 0.0

    def tearDown(self):
        self.tmp.cleanup()

    def app(self, **mock):
        source = MockSource(seed=4, clock=lambda: self.t, **mock)
        return App(source, dict(DEFAULTS), LeagueStore(self.tmp.name)), source

    def run_for(self, app, seconds):
        for _ in range(int(seconds * 10)):
            self.t += 0.1
            app.tick()

    def test_session_limit(self):
        self.assertEqual(_session_limit("30"), 30)
        self.assertEqual(_session_limit("1200.0000 sec"), 1200)
        self.assertIsNone(_session_limit("unlimited"))

    def test_reveal_fills_in_as_drivers_complete_a_lap(self):
        app, source = self.app(race_laps=5)
        app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": True}})
        self.run_for(app, 30)
        ov = app.build_snapshot()["overlays"]
        self.assertEqual(ov["standings"], [])  # nobody has done a lap: header only
        self.assertEqual((ov["progress"]["mode"], ov["progress"]["lap"], ov["progress"]["laps_total"]), ("laps", 1, 5))
        # Run until the leader has crossed the line but not the whole field.
        for _ in range(3000):
            self.t += 0.1
            app.tick()
            done = sum(1 for n in source.mock_laps if n >= 1)
            if 0 < done < source.num_cars:
                break
        shown = app.build_snapshot()["overlays"]["standings"]
        self.assertTrue(0 < len(shown) < source.num_cars)
        self.assertTrue(all(e["laps_completed"] >= 1 for e in shown))
        self.assertEqual([e["pos"] for e in shown], list(range(1, len(shown) + 1)))
        self.assertEqual(app.build_snapshot()["overlays"]["progress"]["lap"], 2)

    def test_without_reveal_the_race_shows_everyone(self):
        app, source = self.app(race_laps=5)
        self.run_for(app, 5)
        self.assertEqual(len(app.build_snapshot()["overlays"]["standings"]), source.num_cars)

    def test_qualifying_header_counts_time_down(self):
        app, _ = self.app(session="qualify")
        self.run_for(app, 10)
        pr = app.build_snapshot()["overlays"]["progress"]
        self.assertEqual(pr["mode"], "time")
        self.assertAlmostEqual(pr["time_remain"], 1190, delta=2)

    def test_reveal_in_qualifying_lists_drivers_without_a_time_last(self):
        app, source = self.app(session="qualify")
        app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": True}})
        self.run_for(app, 200)
        source.offtrack_until = [self.t + 1000] * source.num_cars  # every lap from now on is invalid
        shown = app.build_snapshot()["overlays"]["standings"]
        timed = [e for e in shown if e["best"]]
        self.assertEqual(shown[:len(timed)], timed)
        self.assertTrue(all(e["gap"] is None for e in shown[len(timed):]))

    def test_header_choice(self):
        app, _ = self.app(race_laps=5)
        app.command("overlay_settings", {"overlay": "standings", "values": {"header_info": "time"}})
        self.run_for(app, 2)
        self.assertEqual(app.build_snapshot()["overlays"]["progress"]["mode"], "time")
