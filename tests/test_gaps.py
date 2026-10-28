import tempfile
import unittest

from apex.config import DEFAULTS
from apex.core import App
from apex.gaps import GapTimer
from apex.league import LeagueStore
from apex.sources import MockSource

TRACK_M = 4000.0


class GapTimerTests(unittest.TestCase):
    def drive(self, timer, seconds, dt, cars, start=0.0):
        """cars: {car: (start metres, m/s)}; returns each car's progress and the time at the end."""
        t = start
        p, last = {}, start
        while t <= start + seconds + 1e-9:
            p = {car: (m0 + v * (t - start)) / TRACK_M for car, (m0, v) in cars.items()}
            timer.update(0, t, p)
            last = t
            t += dt
        self.now = last
        return p

    def test_gap_between_cars_at_the_same_point(self):
        timer = GapTimer()
        timer.set_track(TRACK_M)
        # Car 2 runs 100 m behind car 1 at 50 m/s: 2.0 s behind. Telemetry at an uneven 10 Hz.
        p = self.drive(timer, 20, 0.1, {1: (300.0, 50.0), 2: (200.0, 50.0)})
        self.assertAlmostEqual(timer.gap(2, 1, p[2], self.now), 2.0, delta=0.02)

    def test_gap_follows_a_car_closing_in(self):
        timer = GapTimer()
        timer.set_track(TRACK_M)
        cars = {1: (300.0, 50.0), 2: (200.0, 55.0)}  # 5 m/s faster: closes 100 m in 20 s
        p = self.drive(timer, 10, 0.05, cars)
        # Car 2 is 50 m behind, but car 1 passed that point 0.95 s before car 2 does.
        self.assertAlmostEqual(timer.gap(2, 1, p[2], self.now), 1.0, delta=0.06)

    def test_lapped_car_and_replays(self):
        timer = GapTimer()
        timer.set_track(TRACK_M)
        # Car 2 a lap and 500 m down at 50 m/s: 90 s behind.
        p = self.drive(timer, 100, 0.1, {1: (4500.0, 50.0), 2: (0.0, 50.0)})
        self.assertAlmostEqual(timer.gap(2, 1, p[2], self.now), 90.0, delta=0.05)
        # Watching a replay of earlier (8 s back): the gap where car 2 was then.
        self.assertAlmostEqual(timer.gap(2, 1, p[2] - 400.0 / TRACK_M, self.now - 8.0), 90.0, delta=0.05)
        self.assertIsNone(timer.gap(2, 1, 0.01, self.now))  # before anything was timed

    def test_a_stopped_car_keeps_losing_time(self):
        timer = GapTimer()
        timer.set_track(TRACK_M)
        p = self.drive(timer, 20, 0.1, {1: (300.0, 50.0), 2: (200.0, 50.0)})
        stopped_at = p[2]
        for i in range(1, 51):  # car 2 stops for 5 s
            timer.update(0, self.now + i * 0.1, {1: p[1] + i * 5.0 / TRACK_M, 2: stopped_at})
        self.assertAlmostEqual(timer.gap(2, 1, stopped_at, self.now + 5.0), 7.0, delta=0.05)

    def test_tows_and_sessions_start_afresh(self):
        timer = GapTimer()
        timer.set_track(TRACK_M)
        self.drive(timer, 5, 0.1, {1: (0.0, 50.0)})
        timer.update(0, 5.2, {1: 0.9})  # towed to the pits: a jump, no times noted for it
        self.assertLess(max(timer._passed[1]), 0.1 * timer.points)
        timer.update(1, 0.0, {1: 0.1})  # next session
        self.assertEqual(timer._passed, {})


class LiveGapTests(unittest.TestCase):
    def test_gaps_come_from_timing_not_iracings_lagging_value(self):
        clock = [0.0]
        src = MockSource(seed=2, clock=lambda: clock[0])
        app = App(src, dict(DEFAULTS), LeagueStore(tempfile.mkdtemp()))
        real_read = src.read

        def stale_read():
            f = real_read()
            f.f2_time = [0.0] * len(f.f2_time)  # iRacing's gap stuck
            return f

        src.read = stale_read
        for _ in range(30 * 120):
            clock[0] += 1 / 30
            app.tick()
        rows = [r for r in app.build_snapshot()["drivers"] if r["pos"]]
        gaps = [r["gap"] for r in rows[1:]]
        self.assertTrue(all(g is not None and g > 0 for g in gaps[:10]), gaps[:10])
        self.assertEqual(gaps[:10], sorted(gaps[:10]))  # in step with the order on track
