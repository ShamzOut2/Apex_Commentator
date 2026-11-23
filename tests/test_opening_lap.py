"""The opening lap's order (by lap distance, not iRacing's lap count), the
leader's gap after a pass for the lead, the camera outside the data delay,
and on-screen overlays fading out before their windows close."""

import tempfile
import time
import unittest
from types import SimpleNamespace

from apex.core import OpeningLap
from tests.test_app import make_app


def run(opening, frames, green=0.0, key=("s", 1)):
    """``frames``: [(t, {car: raw laps + distance})] -> the order at each."""
    orders = []
    for t, cars in frames:
        got = {idx: opening(key, green, t, True, idx, raw) for idx, raw in cars.items()}
        orders.append((sorted(got, key=lambda i: -got[i]), got))
    return orders


class OpeningLapTests(unittest.TestCase):
    def grid_start(self, lap_before, lap_after):
        """Three cars on the grid behind the line (A ahead), driving round
        together; iRacing calls them on lap ``lap_before`` until they cross the
        line, ``lap_after`` after it."""
        start = {"A": 0.97, "B": 0.95, "C": 0.93}
        frames = []
        for step in range(0, 120):
            t = step * 0.25
            cars = {}
            for name, p0 in start.items():
                p = p0 + step * 0.006
                lap = lap_before if p < 1.0 else lap_after
                cars[name] = lap + (p % 1.0)
            frames.append((t, cars))
        return frames

    def test_lap_counted_from_the_grid(self):
        # iRacing already calls the grid lap 1, and keeps lap 1 over the line: taken
        # as it came, a car still behind the line (1.9x) was ahead of one over it (1.0x).
        orders = run(OpeningLap(), self.grid_start(1, 1))
        self.assertTrue(all(o == ["A", "B", "C"] for o, _ in orders), [o for o, _ in orders if o != ["A", "B", "C"]][:3])

    def test_lap_up_at_the_line(self):
        orders = run(OpeningLap(), self.grid_start(0, 1))
        self.assertTrue(all(o == ["A", "B", "C"] for o, _ in orders))

    def test_no_jump_when_the_lap_count_is_taken_again(self):
        # Half a lap on, iRacing's count (lap 2 here) is used again, less the lap it's apart.
        orders = run(OpeningLap(), self.grid_start(1, 2))
        values = [got["A"] for _, got in orders]
        steps = [b - a for a, b in zip(values, values[1:])]
        self.assertTrue(all(0 <= s < 0.01 for s in steps), max(steps))
        self.assertAlmostEqual(values[-1], 1 + (0.97 + 119 * 0.006) % 1.0, places=6)
        self.assertTrue(all(o == ["A", "B", "C"] for o, _ in orders))

    def test_not_at_the_green_as_iracing_has_it(self):
        o = OpeningLap()
        self.assertEqual(o(("s", 1), 0.0, 30.0, True, "late", 1.97), 1.97)  # out of the garage later
        self.assertEqual(o(("s", 1), None, 1.0, True, "A", 1.97), 1.97)     # the green not seen (app started mid-race)
        self.assertEqual(o(("s", 1), 0.0, 1.0, False, "A", 1.97), 1.97)     # not racing
        self.assertEqual(o(("s", 1), 0.0, 1.0, True, "A", -1), -1)          # not on track


class LeaderGapTests(unittest.TestCase):
    def test_new_leader_has_no_gap_of_its_own(self):
        """A pass for the lead mid-lap: iRacing still calls the old leader the
        leader until the line, so its gap for the new one is to them. The
        leader's gap is 0 whatever it says (intervals are taken from it)."""
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=0.2)
            rows = [{"car_idx": 1, "pos": 1, "progress": 3.50, "class_key": "c", "gap": 0.8, "class_gap": None, "best_lap": 90.0},
                    {"car_idx": 2, "pos": 2, "progress": 3.49, "class_key": "c", "gap": 0.0, "class_gap": None, "best_lap": 90.0}]
            app._live_gaps(rows, SimpleNamespace(timeline=lambda: (0, 500.0)))
            self.assertEqual(rows[0]["gap"], 0.0)
            self.assertGreater(rows[1]["gap"], 0.0)


class DelayTests(unittest.TestCase):
    def test_camera_isnt_delayed(self):
        """The race is shown data_delay_s behind; which car's on camera is as it is now."""
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=0.2)
            app.settings.set("data_delay_s", 5.0)
            old = {"connected": True, "camera": {"car_idx": 1}, "drivers": ["then"], "overlays": {"settings": {}}}
            app._delay(old)
            out = app._delay({"connected": True, "camera": {"car_idx": 7}, "drivers": ["now"], "overlays": {"settings": {}}})
            self.assertEqual((out["camera"]["car_idx"], out["drivers"]), (7, ["then"]))


class DesktopCloseTests(unittest.TestCase):
    def test_fades_then_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=0.2)

            class Fake:
                up = {}

                def show(self, page, path, name, screen):
                    self.up[page] = screen
                    return True

                def hide(self, page=None):
                    self.up = {} if page is None else {k: v for k, v in self.up.items() if k != page}

                def on_screen(self):
                    return dict(self.up)

                def screens(self):
                    return []

            app.desktop = fake = Fake()
            app.DESK_CLOSE_S = 0.05
            app.command("desktop_show", {"page": "standings"})
            app.command("desktop_hide", {"page": "standings"})
            d = app.build_snapshot()["desktop"]
            self.assertEqual((d["on_screen"], d["closing"], fake.up), ({}, ["standings"], {"standings": 0}))
            time.sleep(0.3)
            self.assertEqual((fake.up, app.build_snapshot()["desktop"]["closing"]), ({}, []))
            # Put up again while it's fading out: it stays.
            app.command("desktop_show", {"page": "standings"})
            app.command("desktop_hide", {"page": "standings"})
            app.command("desktop_show", {"page": "standings"})
            time.sleep(0.3)
            self.assertEqual(fake.up, {"standings": 0})


if __name__ == "__main__":
    unittest.main()
