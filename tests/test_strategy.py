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

    def pit(self, entry, lap, session_num=None, kind="stop"):
        """A visit to the pit lane in the race log: in on ``lap``, out (a
        ``kind`` of stop) on the next; kind None: still in the pit lane."""
        num = self.app._frame.timeline()[0] if session_num is None else session_num
        for typ, at in (("pit_in", lap), ("pit_out", lap + 1)):
            if typ == "pit_out" and kind is None:
                break
            ev = {"id": 10_000 + len(self.app.detector.events), "type": typ, "car_idx": entry["car_idx"], "car_number": entry["number"],
                  "driver": entry["name"], "session_num": num, "session_time": 1.0, "lap": at, "incidents": 0}
            if typ == "pit_out":
                ev.update(stop=kind, duration=30.0, position=1, from_position=1)
            self.app.detector.events.append(ev)

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
        self.assertEqual([[v["lap"] for v in r["stops"]] for r in s["rows"]], [[], [7, 19], []])
        self.assertEqual([r["stop_count"] for r in s["rows"]], [0, 2, 0])
        self.assertEqual(s["missing"], ["999"])
        self.assertEqual(s["scale"], 30)  # the race's length
        self.assertEqual(s["rows"][0]["done"], first["laps_completed"])
        # As picked; and the laps so far as the scale.
        self.app.command("overlay_settings", {"overlay": "strategy", "values": {"order": "picked", "scale_to": "so_far"}})
        s = self.app.build_snapshot()["overlays"]["strategy"]
        self.assertEqual([r["number"] for r in s["rows"]], [fifth["number"], first["number"], third["number"]])
        self.assertEqual(s["scale"] % 5, 0)
        self.assertGreater(s["scale"], s["lap"])

    def test_penalties_served_in_the_pit_lane(self):
        car = self.standings()[0]
        self.pit(car, 5, kind="drive_through")
        self.pit(car, 12)
        self.pit(car, 18, kind="stop_go")
        self.pit(car, 25, kind=None)  # in the pit lane now: not known yet, not counted yet
        self.app.command("overlay_settings", {"overlay": "strategy", "values": {"cars": car["number"]}})

        def now():
            snap = self.app.build_snapshot()
            row = snap["overlays"]["strategy"]["rows"][0]
            tower = next(e for e in snap["overlays"]["standings"] if e["car_idx"] == car["car_idx"])
            return [(v["lap"], v["kind"], v["counted"]) for v in row["stops"]], row["stop_count"], tower["pit_stops"]
        # The default: penalties shown on the scale, not counted (here or in the tower's Pits).
        visits, count, tower = now()
        self.assertEqual(visits, [(5, "drive_through", False), (12, "stop", True), (18, "stop_go", False), (25, None, False)])
        self.assertEqual((count, tower), (1, 1))
        # Not shown either.
        self.app.command("overlay_settings", {"overlay": "strategy", "values": {"show_penalties": False}})
        self.assertEqual([v[0] for v in now()[0]], [12, 25])
        # Counted as stops: everywhere.
        self.app.command("overlay_settings", {"overlay": "general", "values": {"penalty_stops": True}})
        visits, count, tower = now()
        self.assertEqual(visits[:3], [(5, "drive_through", True), (12, "stop", True), (18, "stop_go", True)])
        self.assertEqual((count, tower), (3, 3))

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
