"""After the chequered flag the tower (and timing screen) has the cars that
have finished in iRacing's official order, with its gaps: the app's own
timing at the line can't split a photo finish."""

import tempfile
import unittest

from apex.config import DEFAULTS
from apex.core import App
from apex.league import LeagueStore
from apex.sources import MockSource
from tests.test_app import FakeClock


class FinishOrderTests(unittest.TestCase):
    def test_a_photo_finish_as_iracing_has_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            src = MockSource(seed=7, clock=clock, race_laps=2)
            app = App(src, dict(DEFAULTS), LeagueStore(tmp))
            app.overlays.update("standings", {"reveal": False})
            for _ in range(6000):
                clock.t += 0.1
                app.tick()
                if len(app._race.finished) >= 4:
                    break
            self.assertGreaterEqual(len(app._race.finished), 4)

            def tower():
                snap = app.build_snapshot()
                return [(e["number"], e["pos"], e["gap"], e["class_gap"]) for e in
                        sorted(snap["overlays"]["standings"], key=lambda e: e["pos"])]
            before = tower()
            first, second, third = (next(r for r in app._live_rows[2] if r["number"] == n) for n, *_ in before[:3])
            # iRacing's results: the cars the app has 2nd and 3rd the other way
            # round, 0.016 s apart, 1.108 s and 1.124 s behind the winner.
            num = app._frame.session_num
            session = app._session_meta["sessions"][num]
            laps = max(p["LapsComplete"] for p in session["ResultsPositions"])
            others = [p for p in session["ResultsPositions"] if p["CarIdx"] not in (first["car_idx"], second["car_idx"], third["car_idx"])]
            session["ResultsPositions"] = [
                {"Position": 1, "CarIdx": first["car_idx"], "LapsComplete": laps, "Time": 1000.0},
                {"Position": 2, "CarIdx": third["car_idx"], "LapsComplete": laps, "Time": 1001.108},
                {"Position": 3, "CarIdx": second["car_idx"], "LapsComplete": laps, "Time": 1001.124},
            ] + [dict(p, Position=i) for i, p in enumerate(others, start=4)]
            after = tower()
            self.assertEqual([n for n, *_ in after[:3]], [first["number"], third["number"], second["number"]])
            self.assertEqual([(p, g) for _, p, g, _ in after[:3]], [(1, None), (2, 1.108), (3, 1.124)])
            # The rest where they were.
            self.assertEqual([n for n, *_ in after[3:]], [n for n, *_ in before[3:]])


class InstantFinishTests(unittest.TestCase):
    def test_iracings_live_position_the_moment_they_cross(self):
        """Before iRacing's results are in, its live position for each car
        (its scoring at the line) puts the finishers in order straight away;
        the gaps as timed stay in order with them."""
        from dataclasses import replace

        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            src = MockSource(seed=7, clock=clock, race_laps=2)
            app = App(src, dict(DEFAULTS), LeagueStore(tmp))
            app.overlays.update("standings", {"reveal": False})
            for _ in range(6000):
                clock.t += 0.1
                app.tick()
                if len(app._race.finished) >= 4:
                    break
            num = app._frame.session_num
            session = app._session_meta["sessions"][num]
            session["ResultsPositions"] = [dict(p, Time=-1) for p in session["ResultsPositions"]]  # not published yet
            before = sorted(app.build_snapshot()["overlays"]["standings"], key=lambda e: e["pos"])
            second, third = before[1], before[2]
            frame = app._frame
            position = list(frame.position)
            position[second["car_idx"]], position[third["car_idx"]] = position[third["car_idx"]], position[second["car_idx"]]
            with app._lock:
                app._frame = replace(frame, position=position)
            after = sorted(app.build_snapshot()["overlays"]["standings"], key=lambda e: e["pos"])
            self.assertEqual([e["number"] for e in after[:3]], [before[0]["number"], third["number"], second["number"]])
            self.assertLessEqual(after[1]["gap"], after[2]["gap"])  # gaps in order with the places


if __name__ == "__main__":
    unittest.main()
