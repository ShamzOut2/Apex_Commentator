import unittest

from apex.config import DEFAULTS
from apex.events import EventDetector
from apex.sources import Frame, STATE_RACING, TRK_OFF_TRACK, TRK_ON_TRACK, FLAG_CAUTION

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
        self.assertEqual(run(self.det, steps), [])

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


if __name__ == "__main__":
    unittest.main()
