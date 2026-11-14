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

    def test_a_replay_of_any_lap_and_going_back_keeps_the_timing(self):
        timer = GapTimer()
        timer.set_track(TRACK_M)
        # 10 laps, car 2 three seconds behind car 1 (150 m at 50 m/s).
        p = self.drive(timer, 800, 0.1, {1: (150.0, 50.0), 2: (0.0, 50.0)})
        early = 25.0  # a replay of lap 1: where car 2 was then
        self.assertAlmostEqual(timer.gap(2, 1, early * 50.0 / TRACK_M, early), 3.0, delta=0.05)
        # The replay going back in time doesn't throw the timing away.
        timer.update(0, early, {1: (150.0 + early * 50.0) / TRACK_M, 2: early * 50.0 / TRACK_M})
        self.assertAlmostEqual(timer.gap(2, 1, p[2], self.now), 3.0, delta=0.05)

    def test_gaps_across_what_wasnt_timed_during_a_replay(self):
        """Nothing timed for a while (a replay was on screen): back live, a
        car where the leader went round unseen still has its gap, taken across
        the stretch at the leader's pace, not none (which fell back to an
        estimate and made the gaps jump about for a lap after each replay)."""
        timer = GapTimer()
        timer.set_track(TRACK_M)
        cars = {1: (1000.0, 50.0), 2: (0.0, 50.0)}  # car 2 20 s behind
        self.drive(timer, 30, 0.1, cars)
        # 40 s of replay: no timing at all.
        p = self.drive(timer, 15, 0.1, {car: (m0 + v * 70, v) for car, (m0, v) in cars.items()}, start=70.0)
        # Car 2 (4250 m) is now where car 1 went round during the replay (at 65 s: nothing timed there).
        self.assertAlmostEqual(timer.gap(2, 1, p[2], self.now), 20.0, delta=0.3)

    def test_a_stopped_car_keeps_losing_time(self):
        timer = GapTimer()
        timer.set_track(TRACK_M)
        p = self.drive(timer, 20, 0.1, {1: (300.0, 50.0), 2: (200.0, 50.0)})
        stopped_at = p[2]
        for i in range(1, 51):  # car 2 stops for 5 s
            timer.update(0, self.now + i * 0.1, {1: p[1] + i * 5.0 / TRACK_M, 2: stopped_at})
        self.assertAlmostEqual(timer.gap(2, 1, stopped_at, self.now + 5.0), 7.0, delta=0.05)

    def test_steady_with_iracings_patchy_positions(self):
        """iRacing sends other cars' positions every few frames (the same
        distance again in between) and now and then puts one back a little:
        the gap stays steady and right, not jumping with each."""
        import random
        rnd = random.Random(3)
        timer = GapTimer()
        timer.set_track(TRACK_M)
        cars = {1: (300.0, 50.0), 2: (200.0, 50.0)}  # 2.0 s apart
        shown, t, gaps, off = {}, 0.0, [], {}
        for i in range(30 * 60):  # a minute at 30 frames a second
            t = i / 30
            true = {car: (m0 + v * t) / TRACK_M for car, (m0, v) in cars.items()}
            for car, p in true.items():
                if i % 3 == 0 or car not in shown:  # a new position every third frame
                    # Now and then one a little behind (8 m), the next one right again.
                    off[car] = not off.get(car) and rnd.random() < 0.15
                    shown[car] = p - (8.0 / TRACK_M if off[car] else 0.0)
            timer.update(0, t, dict(shown))
            if t > 20:
                gaps.append(timer.gap(2, 1, timer.position(2, shown[2], t), t))
        self.assertTrue(all(abs(g - 2.0) < 0.1 for g in gaps), (min(gaps), max(gaps)))
        self.assertLess(max(abs(a - b) for a, b in zip(gaps, gaps[1:])), 0.1)
        # Put back a little doesn't count as being there again later: car 1 got to
        # 1000 m at 14 s (the first time stands), so 2 s before 16 s.
        self.assertAlmostEqual(timer.gap(2, 1, 1000.0 / TRACK_M, 16.0), 2.0, delta=0.05)

    def test_tows_and_sessions_start_afresh(self):
        timer = GapTimer()
        timer.set_track(TRACK_M)
        self.drive(timer, 5, 0.1, {1: (0.0, 50.0)})
        timer.update(0, 5.2, {1: 0.9})  # towed to the pits: a jump, no times noted for it
        timed = [k for k, v in enumerate(timer._passed[1]) if v == v]  # NaN: not passed
        self.assertLess(max(timed), 0.1 * timer.points)
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
