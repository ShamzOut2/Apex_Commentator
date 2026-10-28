import math
import unittest

from apex.config import DEFAULTS
from apex.events import EventDetector
from apex.sources import (
    FLAG_BLACK, FLAG_CAUTION, FLAG_FURLED, FLAG_GREEN, Frame, STATE_RACING, TRK_OFF_TRACK, TRK_ON_TRACK,
)

TRACK_M = 4000.0
DRIVERS = {1: {"name": "Alice", "number": "1"}, 2: {"name": "Bob", "number": "2"}}


def frame(t, cars, flags=0, state=STATE_RACING):
    """cars: {idx: (lap, pct, surface, on_pit)}"""
    n = max(cars) + 1
    f = Frame(session_time=t, session_state=state, session_flags=flags)
    f.lap = [-1] * n
    f.pct = [-1.0] * n
    f.surface = [-1] * n
    f.on_pit = [False] * n
    for idx, (lap, pct, surface, pit) in cars.items():
        f.lap[idx], f.pct[idx], f.surface[idx], f.on_pit[idx] = lap, pct, surface, pit
    return f


def run(det, steps, is_race=True):
    out = []
    for f in steps:
        out += det.update(f, DRIVERS, TRACK_M, is_race)
    return out


class OvertakeTests(unittest.TestCase):
    def setUp(self):
        self.det = EventDetector(DEFAULTS)

    def sweep(self, b_offset_fn, seconds=6.0, dt=0.1, surf_b=TRK_ON_TRACK, pit_b=False, **kw):
        """Car 1 drives at a steady pace; car 2 sits at an offset given by b_offset_fn(t)."""
        steps = []
        t = 0.0
        while t < seconds:
            pa = 0.30 + t * 0.011
            pb = pa + b_offset_fn(t)
            steps.append(frame(100 + t, {
                1: (3, pa, TRK_ON_TRACK, False),
                2: (3, pb, surf_b, pit_b),
            }, **kw))
            t += dt
        return run(self.det, steps)

    def test_clean_pass_is_recorded_once_at_its_start(self):
        # Bob starts 0.5% behind and moves 0.5% ahead.
        events = self.sweep(lambda t: -0.005 + 0.002 * t)
        passes = [e for e in events if e["type"] == "overtake"]
        self.assertEqual(len(passes), 1)
        ev = passes[0]
        self.assertEqual((ev["car_idx"], ev["other_car_idx"]), (2, 1))
        self.assertEqual(ev["position"], 1)
        # The swap happens at t=2.5 s; the event is timestamped then, not when confirmed.
        self.assertAlmostEqual(ev["session_time"], 102.5, delta=0.15)

    def test_side_by_side_flicker_is_not_a_pass(self):
        events = self.sweep(lambda t: 0.0005 if int(t * 10) % 8 < 4 else -0.0005)
        self.assertEqual([e for e in events if e["type"] == "overtake"], [])

    def test_pass_on_pit_road_is_ignored(self):
        events = self.sweep(lambda t: -0.005 + 0.002 * t, pit_b=True)
        self.assertEqual([e for e in events if e["type"] == "overtake"], [])

    def test_no_passes_under_caution_or_outside_races(self):
        events = self.sweep(lambda t: -0.005 + 0.002 * t, flags=FLAG_CAUTION)
        self.assertEqual([e for e in events if e["type"] == "overtake"], [])
        det = EventDetector(DEFAULTS)
        steps = [frame(t / 10, {1: (3, 0.3 + t / 1000, TRK_ON_TRACK, False),
                                2: (3, 0.295 + t / 500, TRK_ON_TRACK, False)}) for t in range(60)]
        self.assertEqual(run(det, steps, is_race=False), [])

    def test_lap_counter_glitch_at_the_line_is_not_a_pass(self):
        # iRacing can bump CarIdxLap a tick before LapDistPct wraps, briefly
        # putting a car a whole lap ahead. That must not register as passes.
        steps = []
        for i in range(60):
            t = i * 0.1
            pa = (0.97 + t * 0.011) % 1.0
            pb = (0.965 + t * 0.011) % 1.0
            lap_a = 4 if 0.97 + t * 0.011 < 1.0 else 5
            lap_b = 4 if 0.965 + t * 0.011 < 1.0 else 5
            if 0.965 + t * 0.011 < 1.0 and 0.965 + (t + 0.1) * 0.011 >= 1.0:
                lap_b = 5  # glitch: lap bumped early
            steps.append(frame(t, {1: (lap_a, pa, TRK_ON_TRACK, False), 2: (lap_b, pb, TRK_ON_TRACK, False)}))
        self.assertEqual([e for e in run(self.det, steps) if e["type"] == "overtake"], [])


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.det = EventDetector(DEFAULTS)

    def test_spin_off_track_is_a_single_event_with_points_attached(self):
        steps = []
        pct = 0.1
        for i in range(80):
            t = i * 0.1
            spinning = 3.0 <= t < 5.0
            pct += 0.0001 if spinning else 0.001  # ~40 m/s, then ~4 m/s
            surface = TRK_OFF_TRACK if spinning else TRK_ON_TRACK
            steps.append(frame(200 + t, {1: (2, pct, surface, False)}))
        events = run(self.det, steps)
        self.assertEqual(len(events), 1)
        self.assertIn(events[0]["type"], ("offtrack", "slowdown"))

        # Incident points arrive a few seconds later via session info.
        drivers = {1: dict(DRIVERS[1], incidents=0)}
        self.det.update_incidents(steps[-1], drivers)
        drivers[1]["incidents"] = 4
        created = self.det.update_incidents(steps[-1], drivers)
        self.assertEqual(created, [])
        self.assertEqual(self.det.events[0]["incidents"], 4)

    def drive(self, speeds, dt=0.05, steer=None, yaw=None, start=0.1):
        """Car 1 at speeds[i] m/s each step (negative: backwards); steer / yaw: per step, or None."""
        steps, pct = [], start
        for i, v in enumerate(speeds):
            pct = (pct + v * dt / TRACK_M) % 1.0
            f = frame(300 + i * dt, {1: (2, pct, TRK_ON_TRACK, False)})
            f.steer = [0.0, steer[i] if steer else 0.0]
            if yaw is not None:
                f.player_car_idx, f.yaw = 1, yaw[i]
            steps.append(f)
        return run(self.det, steps)

    def test_braking_for_a_hairpin_is_not_a_spin(self):
        # 75 m/s down to 15 m/s at ~4 g for a hairpin, then back up, lap after lap.
        def speed_at(d):
            brake, apex, exit_ = 2000.0, 2077.0, 2107.0
            if brake <= d < apex:
                return math.sqrt(max(15.0 ** 2, 75.0 ** 2 - 2 * 35.0 * (d - brake)))
            if apex <= d < exit_:
                return 15.0
            if d >= exit_:
                return min(75.0, math.sqrt(15.0 ** 2 + 2 * 8.0 * (d - exit_)))
            return 75.0
        speeds, d, laps = [], 0.0, []
        for _ in range(6 * 1400):
            v = speed_at(d % TRACK_M)
            speeds.append(v)
            d += v * 0.05
        events = self.drive(speeds, start=0.0)
        self.assertEqual([e for e in events if e["type"] == "spin"], [])
        # Once the detector knows the corner, braking for it isn't even a slowdown.
        late = [e for e in events if e["session_time"] > 300 + 0.05 * len(speeds) * 0.5]
        self.assertEqual(late, [])

    def test_sliding_backwards_after_a_spin(self):
        speeds = [50.0] * 60 + [10.0] * 4 + [2.0] * 4 + [-8.0] * 12 + [0.0] * 20
        events = self.drive(speeds)
        self.assertEqual([(e["type"], e["spin"]) for e in events], [("spin", "backwards")])

    def test_snap_of_opposite_lock_within_the_window(self):
        speeds = [50.0] * 60 + [3.0] * 40
        steer = [0.3] * 58 + [-3.4] * 42  # 210 degrees of wheel in one sample, as it slows
        self.assertEqual([e["type"] for e in self.drive(speeds, steer=steer)], ["spin"])
        self.det = EventDetector(DEFAULTS)
        slow_turn = [0.3 - 3.7 * min(1.0, max(0.0, (i - 40) / 30)) for i in range(100)]  # the same, over 1.5 s
        self.assertEqual([e["type"] for e in self.drive(speeds, steer=slow_turn)], ["slowdown"])

    def test_heading_of_the_car_driven_on_this_pc(self):
        speeds = [50.0] * 60 + [3.0] * 40
        quick = [0.0] * 60 + [math.radians(20 * k) for k in range(1, 4)] + [math.radians(60)] * 37  # 60 deg in 0.15 s
        self.assertEqual([(e["type"], e["spin"]) for e in self.drive(speeds, yaw=quick)], [("spin", "yaw")])
        self.det = EventDetector(DEFAULTS)
        slow = [0.0] * 60 + [math.radians(min(60, 2 * k)) for k in range(1, 41)]  # 60 deg over 1.5 s: a corner
        self.assertEqual([e["type"] for e in self.drive(speeds, yaw=slow)], ["slowdown"])

    def test_incident_points_without_a_visible_moment_create_an_event(self):
        f = frame(500, {1: (5, 0.5, TRK_ON_TRACK, False)})
        drivers = {1: dict(DRIVERS[1], incidents=2)}
        self.assertEqual(self.det.update_incidents(f, drivers), [])  # baseline
        drivers[1]["incidents"] = 3
        created = self.det.update_incidents(f, drivers)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["type"], "incident")
        self.assertEqual(created[0]["incidents"], 1)
        self.assertLess(created[0]["session_time"], 500)

    def test_pit_road_slowdown_is_ignored(self):
        steps = []
        pct = 0.1
        for i in range(60):
            pct += 0.001 if i < 20 else 0.0002
            steps.append(frame(i * 0.1, {1: (2, pct, TRK_ON_TRACK, i >= 20)}))
        # Entering the pit lane is logged as a pit stop, not as a slowdown.
        self.assertEqual([e["type"] for e in run(self.det, steps)], ["pit_in"])

    def test_max_events_is_respected(self):
        det = EventDetector(dict(DEFAULTS, max_events=5))
        drivers = {1: dict(DRIVERS[1], incidents=0)}
        f = frame(0, {1: (1, 0.1, TRK_ON_TRACK, False)})
        det.update_incidents(f, drivers)
        for i in range(1, 12):
            f.session_time = i * 100
            drivers[1]["incidents"] = i
            det.update_incidents(f, drivers)
        self.assertEqual(len(det.events), 5)
        self.assertEqual(det.events[-1]["id"], 11)



class RaceEventTests(unittest.TestCase):
    """Pit stops, places lost after an off, penalties and fastest laps."""

    def setUp(self):
        self.det = EventDetector(DEFAULTS)
        self.drivers = {i: {"name": f"D{i}", "number": str(i), "car_class": "GT3"} for i in (1, 2, 3)}

    def race(self, seconds, car, dt=0.1, start=0.0):
        """Cars 2 and 3 lap steadily; car(t) gives car 1's (lap, pct, surface, on_pit, flags, best)."""
        events = []
        t = start
        while t < start + seconds:
            f = frame(t, {2: (5, (0.50 + t * 0.011) % 1, TRK_ON_TRACK, False),
                          3: (5, (0.45 + t * 0.011) % 1, TRK_ON_TRACK, False),
                          1: car(t)[:4]})
            f.car_flags = [0, car(t)[4], FLAG_GREEN, FLAG_GREEN]
            f.best_lap = [-1, car(t)[5], 90.0, 91.0]
            events += self.det.update(f, self.drivers, TRACK_M, True)
            t = round(t + dt, 3)
        return events

    def test_pit_stop_reports_time_and_places_lost(self):
        def car(t):
            if t < 2:      # leading, on track
                return (5, 0.60 + t * 0.011, TRK_ON_TRACK, False, FLAG_GREEN, 89.0)
            if t < 30:     # pit stop: crawls while the others pass
                return (5, 0.62 + (t - 2) * 0.001, TRK_ON_TRACK, True, FLAG_GREEN, 89.0)
            return (5, 0.65 + (t - 30) * 0.011, TRK_ON_TRACK, False, FLAG_GREEN, 89.0)
        events = [e for e in self.race(32, car) if e["type"].startswith("pit")]
        self.assertEqual([e["type"] for e in events], ["pit_in", "pit_out"])
        pit_out = events[1]
        self.assertAlmostEqual(pit_out["duration"], 28.0, delta=0.2)
        self.assertEqual((pit_out["from_position"], pit_out["position"]), (1, 3))

    def test_places_lost_after_going_off(self):
        def car(t):
            if t < 2:
                return (5, 0.60 + t * 0.011, TRK_ON_TRACK, False, FLAG_GREEN, 89.0)
            if t < 20:     # off and stuck while both others pass
                return (5, 0.62 + (t - 2) * 0.0005, TRK_OFF_TRACK, False, FLAG_GREEN, 89.0)
            return (5, 0.629 + (t - 20) * 0.011, TRK_ON_TRACK, False, FLAG_GREEN, 89.0)
        events = self.race(28, car)
        lost = [e for e in events if e["type"] == "position"]
        self.assertEqual(len(lost), 1)
        self.assertEqual((lost[0]["from_position"], lost[0]["position"], lost[0]["reason"]), (1, 3, "off"))
        self.assertAlmostEqual(lost[0]["session_time"], 2.0, delta=0.15)  # replays from the moment it went off

    def test_penalty_flags_are_logged_once(self):
        def car(t):
            flags = FLAG_GREEN | (FLAG_FURLED if t >= 1 else 0) | (FLAG_BLACK if t >= 2 else 0)
            return (5, 0.60 + t * 0.011, TRK_ON_TRACK, False, flags, 89.0)
        penalties = [e["penalty"] for e in self.race(4, car) if e["type"] == "penalty"]
        self.assertEqual(penalties, ["Warning", "Black flag"])

    def test_class_fastest_lap(self):
        def car(t):
            best = 89.0 if t < 1 else 88.5  # beats car 2's 90.0 and its own 89.0
            return (5, 0.60 + t * 0.011, TRK_ON_TRACK, False, FLAG_GREEN, best)
        laps = [e for e in self.race(2, car) if e["type"] == "fastest_lap"]
        # The laps already set when logging started aren't news; the improvement is.
        self.assertEqual([(e["car_idx"], e["lap_time"]) for e in laps], [(1, 88.5)])

    def test_time_jump_starts_afresh(self):
        def car(t):
            return (5, 0.60 + t * 0.011, TRK_ON_TRACK, False, FLAG_GREEN, 89.0)
        self.race(1, car)
        # Skip ahead 60s in a replay: cars have moved a lot, but nothing is logged for the gap.
        self.assertEqual([e for e in self.race(1, car, start=61) if e["type"] in ("overtake", "slowdown")], [])


if __name__ == "__main__":
    unittest.main()
