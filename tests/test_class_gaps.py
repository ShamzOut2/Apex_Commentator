"""Class gaps (the tower and timing screen by class): each car's time behind
its class leader, timed against the class leader, never below 0."""

import copy
import tempfile
import unittest
from dataclasses import replace

from apex.config import DEFAULTS
from apex.core import App, _rank
from apex.league import LeagueStore
from apex.sources import MockSource
from tests.test_app import FakeClock


class ClassGapTests(unittest.TestCase):
    def test_two_gaps_apart_never_below_zero(self):
        """The class leader's gap to the leader measured a moment apart from
        the car behind it can be the larger one: not a car "ahead" of it."""
        standings = [{"class_key": "a", "time": None}, {"class_key": "b", "time": 10.0},
                     {"class_key": "b", "time": 9.6}, {"class_key": "b", "time": 12.0, "class_time": 1.8}]
        _rank(standings, True)
        self.assertEqual([e["class_gap"] for e in standings], [None, None, 0.0, 1.8])

    def test_a_multiclass_race_live_and_in_a_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            src = MockSource(seed=7, clock=clock)
            app = App(src, dict(DEFAULTS), LeagueStore(tmp))
            app.overlays.update("standings", {"reveal": False})
            read, history, seen = src.read, [], 0

            def check():
                nonlocal seen
                snap = app.build_snapshot()
                entries = snap["overlays"]["standings"]
                for e in entries:
                    if e.get("class_gap") is not None:
                        self.assertGreaterEqual(e["class_gap"], 0.0, e)
                        seen += 1
                classes = {e["class_key"] for e in entries}
                return snap, classes

            for step in range(2400):  # 4 minutes of racing
                clock.t += 0.1
                f = read()
                history.append(copy.deepcopy(f))
                src.read = lambda f=f: f
                app.tick()
                if step % 10 == 0:
                    snap, classes = check()
            self.assertGreater(len(classes), 1)  # a race of more than one class
            self.assertGreater(seen, 100)
            # Timed against the class leader: how long ago they were where the car is.
            rows = [r for r in snap["drivers"] if r.get("class_gap") is not None and r["pos"]]
            self.assertTrue(rows)
            # A replay (iRacing's car data the replay's), the standings held live: still never below 0.
            app.command("replay_car_data", {"mode": "replay"})
            for step in range(600):
                clock.t += 0.1
                f = read()
                history.append(copy.deepcopy(f))
                old = history[-300]
                src.read = lambda f=f, old=old: replace(
                    f, replay_frames_from_end=1800, replay_session_time=old.session_time, replay_session_num=f.session_num,
                    lap=old.lap, laps_completed=old.laps_completed, pct=old.pct, position=old.position,
                    surface=old.surface, on_pit=old.on_pit, f2_time=old.f2_time)
                app.tick()
                if step % 10 == 0:
                    check()


if __name__ == "__main__":
    unittest.main()
