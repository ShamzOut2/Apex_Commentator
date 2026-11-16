"""The pit strategy overlay (strategy.html): the cars picked by number, the laps
each pitted on, where it is now, and the quick picks."""

import tempfile
import unittest

from apex.config import DEFAULTS
from apex.core import App, CommandError
from apex.league import LeagueStore
from apex.overlays import normalise
from apex.sources import MockSource
from tests.test_app import FakeClock


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = FakeClock()
        self.src = MockSource(seed=7, clock=self.clock, race_laps=30)
        self.app = App(self.src, dict(DEFAULTS), LeagueStore(self.tmp.name))
        self.app.overlays.update("standings", {"reveal": False})  # every car in the tower from the start
        self.run_for(140)

    def tearDown(self):
        self.tmp.cleanup()

    def run_for(self, seconds):
        for _ in range(int(seconds * 10)):
            self.clock.t += 0.1
            self.app.tick()

    def standings(self):
        return sorted(self.app.build_snapshot()["overlays"]["standings"], key=lambda e: e["pos"])

    def pit(self, entry, lap, session_num=None):
        """A pit stop in the race log: in on ``lap``."""
        num = self.app._frame.timeline()[0] if session_num is None else session_num
        self.app.detector.events.append({"id": 10_000 + len(self.app.detector.events), "type": "pit_in", "car_idx": entry["car_idx"],
                                         "car_number": entry["number"], "driver": entry["name"], "session_num": num,
                                         "session_time": 1.0, "lap": lap, "incidents": 0})

    def test_the_cars_picked_with_their_stops(self):
        self.assertIsNone(self.app.build_snapshot()["overlays"]["strategy"])  # none picked: nothing
        first, third, fifth = (self.standings()[i] for i in (0, 2, 4))
        self.pit(third, 7)
        self.pit(third, 19)
        self.pit(first, 4, session_num=99)  # another session's: not this race's
        cars = f"{fifth['number']},{first['number']},{third['number']},999"
        self.app.command("overlay_settings", {"overlay": "strategy", "values": {"cars": cars}})
        s = self.app.build_snapshot()["overlays"]["strategy"]
        # In running order, the stops' laps, and the car not in the race left out.
        self.assertEqual([r["number"] for r in s["rows"]], [first["number"], third["number"], fifth["number"]])
        self.assertEqual([r["stops"] for r in s["rows"]], [[], [7, 19], []])
        self.assertEqual(s["missing"], ["999"])
        self.assertEqual(s["scale"], 30)  # the race's length
        self.assertEqual(s["rows"][0]["done"], first["laps_completed"])
        # As picked; and the laps so far as the scale.
        self.app.command("overlay_settings", {"overlay": "strategy", "values": {"order": "picked", "scale_to": "so_far"}})
        s = self.app.build_snapshot()["overlays"]["strategy"]
        self.assertEqual([r["number"] for r in s["rows"]], [fifth["number"], first["number"], third["number"]])
        self.assertEqual(s["scale"] % 5, 0)
        self.assertGreater(s["scale"], s["lap"])

    def test_a_car_out_of_its_car_keeps_its_race_so_far(self):
        car = self.standings()[1]
        self.app.command("overlay_settings", {"overlay": "strategy", "values": {"cars": car["number"]}})
        done = self.app.build_snapshot()["overlays"]["strategy"]["rows"][0]["done"]
        self.assertGreater(done, 0)
        self.src.out[car["car_idx"] - 1] = True  # retires: out of the world
        self.run_for(2)
        row = self.app.build_snapshot()["overlays"]["strategy"]["rows"][0]
        self.assertEqual((row["done"] >= done, row["out"]), (True, True))

    def test_quick_picks_and_the_hotkey(self):
        with self.assertRaises(CommandError):  # nothing picked yet: nothing to show
            self.app.command("hotkey", {"action": "strategy:toggle"})
        order = self.standings()
        self.assertEqual(self.app.command("strategy_pick", {"mode": "top"})["cars"], [e["number"] for e in order[:5]])
        self.assertTrue(self.app.overlays.get()["strategy"]["visible"])
        leaders = self.app.command("hotkey", {"action": "strategy:leaders"})["cars"]
        self.assertEqual(leaders[0], order[0]["number"])
        self.assertEqual(len(leaders), len({e["class_key"] for e in order}))
        cam = next(e for e in order if e["car_idx"] == self.app._frame.cam_car_idx)
        self.assertEqual(self.app.command("strategy_pick", {"mode": "camera"})["cars"], [cam["number"]])
        around = self.app.command("strategy_pick", {"mode": "around"})["cars"]
        self.assertIn(cam["number"], around)
        self.assertLessEqual(len(around), 5)
        self.app.command("hotkey", {"action": "strategy:toggle"})
        self.assertFalse(self.app.overlays.get()["strategy"]["visible"])
        self.assertIn("strategy", self.app.TOGGLE_ALL)

    def test_cars_setting(self):
        s = normalise({"strategy": {"cars": " 95, 73,8,8,x!,007,1,2,3,4,5,6", "order": "nope", "panel_width": 5000}})["strategy"]
        self.assertEqual(s["cars"], "95,73,8,007,1,2,3,4")  # car numbers as they are, no repeats, eight at most
        self.assertEqual((s["order"], s["panel_width"]), ("position", 1840))


if __name__ == "__main__":
    unittest.main()
