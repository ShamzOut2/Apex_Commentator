"""A car towed (or reset) to the pits mid-race isn't put up the order by it."""

import tempfile
import unittest
from dataclasses import replace

from apex.config import DEFAULTS
from apex.core import App, TowWatch
from apex.league import LeagueStore
from apex.sources import MockSource, TRK_IN_PIT_STALL, TRK_NOT_IN_WORLD
from tests.test_app import FakeClock


class TowTests(unittest.TestCase):
    def race_with_a_tow(self, tow_at=150.0):
        """The demo race; at ``tow_at`` the car in P8 is towed: gone for 2 s, then
        in its pit box with iRacing counting it a lap up (ahead of the leader)."""
        clock = FakeClock()
        src = MockSource(seed=7, clock=clock)
        read = src.read
        state = {"car": None, "lap": None}

        def towed_read():
            f = read()
            if f is None or f.session_time < tow_at:
                return f
            if state["car"] is None:
                order = sorted((p, i) for i, p in enumerate(f.position) if p)
                state["car"] = order[7][1]
                state["lap"] = max(f.lap) + 1  # a lap up on the leader
            car = state["car"]
            lap, pct, surface, on_pit, done = list(f.lap), list(f.pct), list(f.surface), list(f.on_pit), list(f.laps_completed)
            if f.session_time < tow_at + 2.0:
                surface[car], pct[car], lap[car] = TRK_NOT_IN_WORLD, -1.0, -1
            else:
                surface[car], pct[car], lap[car], on_pit[car] = TRK_IN_PIT_STALL, 0.97, state["lap"], True
                done[car] = state["lap"] - 1
            return replace(f, lap=lap, pct=pct, surface=surface, on_pit=on_pit, laps_completed=done)

        src.read = towed_read
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = App(src, dict(DEFAULTS), LeagueStore(tmp.name))
        for _ in range(int((tow_at + 10) * 10)):
            clock.t += 0.1
            app.tick()
        return app, state["car"]

    def test_towed_car_stays_where_iracing_has_it(self):
        app, car = self.race_with_a_tow()
        snap = app.build_snapshot()
        row = next(r for r in snap["drivers"] if r["car_idx"] == car)
        self.assertTrue(row["towed"])
        self.assertNotEqual(row["pos"], 1)  # not at the top for having been put a lap up
        self.assertEqual(row["pos"], row["official_pos"])
        self.assertIsNone(row["gap"])
        leader = next(r for r in snap["drivers"] if r["pos"] == 1)
        self.assertFalse(leader.get("towed"))

    def test_back_to_normal_over_the_line(self):
        w = TowWatch()
        key = ("sub", 2)
        w.update(key, True, 10.0, {1: (5.30, 5, True)}, 4000)
        w.update(key, True, 10.1, {1: (5.31, 5, True)}, 4000)
        self.assertEqual(w.towed, {})  # driving: nothing
        w.update(key, True, 10.2, {1: (-1, 5, False)}, 4000)  # gone (being towed)
        w.update(key, True, 15.0, {1: (6.95, 6, True)}, 4000)  # in its box, iRacing a lap on
        self.assertEqual(w.towed, {1: 6})
        w.update(key, True, 40.0, {1: (6.98, 6, True)}, 4000)  # out of the box
        self.assertIn(1, w.towed)
        w.update(key, True, 41.0, {1: (7.01, 7, True)}, 4000)  # over the line under its own power
        self.assertEqual(w.towed, {})
        # A jump forward further than a car drives: put there (a reset).
        w.update(key, True, 41.1, {1: (7.50, 7, True)}, 4000)
        self.assertIn(1, w.towed)
        # A new session: afresh.
        w.update(("sub", 3), True, 0.0, {1: (0.1, 0, True)}, 4000)
        self.assertEqual(w.towed, {})


if __name__ == "__main__":
    unittest.main()
