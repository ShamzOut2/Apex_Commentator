import tempfile
import unittest

from apex.pits import PitTracker
from tests.test_app import make_app


class TrackerTests(unittest.TestCase):
    def test_a_stop(self):
        p = PitTracker()
        # (time, on pit road, in its box) for car 5
        for t, pit, box in ((10, False, False), (11, True, False), (18, True, True), (25.5, True, True),
                            (26, True, False), (33, False, False)):
            p.update(0, t, [(5, pit, box, True)])
        [s] = p.state(33, hold_s=8)
        self.assertEqual((s["lane_s"], s["box_s"], s["out"], s["in_box"]), (22.0, 8.0, True, False))
        self.assertEqual(p.state(42, hold_s=8), [])  # gone after hold_s

    def test_running_times_and_drive_through(self):
        p = PitTracker()
        p.update(0, 100, [(1, True, False, True), (2, True, False, True)])
        p.update(0, 104, [(1, True, True, True), (2, True, False, True)])
        p.update(0, 106, [(1, True, True, True), (2, True, False, True)])
        a, b = p.state(106)
        self.assertEqual((a["lane_s"], a["box_s"], a["in_box"], a["out"]), (6.0, 2.0, True, False))
        self.assertIsNone(b["box_s"])  # not in a box (a drive-through)

    def test_new_session_or_rewind_starts_again(self):
        p = PitTracker()
        p.update(0, 50, [(1, True, False, True)])
        p.update(0, 20, [(1, False, False, True)])  # back in a replay
        self.assertEqual(p.state(20), [])
        p.update(0, 30, [(1, True, False, True)])
        p.update(1, 5, [(1, True, False, True)])   # the next session
        self.assertEqual(p.state(5)[0]["lane_s"], 0.0)


class OverlayTests(unittest.TestCase):
    def test_a_stop_in_the_demo_race(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, src = make_app(tmp, minutes=2.5)
            i = 4  # car 5 comes in now
            t = src.session_time
            src.pit_from[i], src.pit_until[i] = t, t + 22
            seen = []
            for _ in range(240):  # 24 s
                src.clock.t += 0.1
                app.tick()
                stops = app.build_snapshot()["overlays"]["pits"]["stops"]
                mine = next((s for s in stops if s["car_idx"] == i + 1), None)
                if mine:
                    seen.append(mine)
            self.assertTrue(seen)
            self.assertTrue(any(s["in_box"] for s in seen))
            last = seen[-1]
            self.assertTrue(last["out"])
            self.assertAlmostEqual(last["lane_s"], 22.0, delta=0.3)
            self.assertAlmostEqual(last["box_s"], 8.0, delta=0.3)
            self.assertTrue(last["name"])
            # A card's own time limit: gone after 10 s in the pit lane, also after the exit.
            app.command("overlay_settings", {"overlay": "pits", "values": {"show_s": 10}})
            self.assertFalse([s for s in app.build_snapshot()["overlays"]["pits"]["stops"] if s["car_idx"] == i + 1])
            app.command("overlay_settings", {"overlay": "pits", "values": {"show_s": 0, "hold_s": 0}})
            self.assertFalse([s for s in app.build_snapshot()["overlays"]["pits"]["stops"] if s["car_idx"] == i + 1])
            app.command("overlay_settings", {"overlay": "pits", "values": {"hold_s": 30, "count": 1}})
            self.assertEqual(len(app.build_snapshot()["overlays"]["pits"]["stops"]), 1)
            app.command("overlay_settings", {"overlay": "pits", "values": {"who": "camera"}})
            stops = app.build_snapshot()["overlays"]["pits"]["stops"]
            self.assertTrue(all(s["camera"] for s in stops))


if __name__ == "__main__":
    unittest.main()
