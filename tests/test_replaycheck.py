import csv
import tempfile
import unittest
from dataclasses import replace

from apex.config import DEFAULTS
from apex.core import App
from apex.league import LeagueStore
from apex.replaycheck import COLUMNS, ReplayCheck, ReplayProbe
from apex.sources import Frame, MockSource
from tests.test_app import FakeClock

ON_TRACK, RACING = 3, 4


def paused(t, pct, live=False, speed=0):
    """A frame with a replay on screen (paused: speed 0), the live clock at ``t``."""
    return Frame(session_time=t, session_state=RACING, replay_frames_from_end=0 if live else 6000,
                 replay_session_time=t - 100, replay_speed=speed, pct=list(pct), surface=[ON_TRACK] * len(pct))


class ProbeTests(unittest.TestCase):
    def test_cars_moving_with_the_replay_paused_are_live(self):
        probe = ReplayProbe()
        for k in range(45):  # over 2 s at 20 frames a second, every car going round
            probe.update(paused(10 + k * 0.05, [(0.1 * c + k * 0.001) % 1 for c in range(6)]), racing=True)
        self.assertEqual(probe.verdict, "live")

    def test_cars_standing_still_with_the_replay_paused_are_the_replays(self):
        probe = ReplayProbe()
        for k in range(70):
            probe.update(paused(10 + k * 0.05, [0.1 * c for c in range(6)]), racing=True)
        self.assertEqual(probe.verdict, "replay")

    def test_nothing_told_live_playing_or_not_racing(self):
        probe = ReplayProbe()
        for k in range(100):
            pct = [(0.1 * c + k * 0.001) % 1 for c in range(6)]
            probe.update(paused(10 + k * 0.05, pct, live=True), racing=True)          # live
            probe.update(paused(10 + k * 0.05, pct, speed=1), racing=True)            # replay playing
            probe.update(paused(10 + k * 0.05, [0.5] * 6), racing=False)              # not a race going on
        self.assertIsNone(probe.verdict)
        # The sim paused (the clock standing still): nothing either.
        for _ in range(100):
            probe.update(paused(50.0, [0.5] * 6), racing=True)
        self.assertIsNone(probe.verdict)


class CheckTests(unittest.TestCase):
    def test_a_row_a_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            check = ReplayCheck(tmp, clock=lambda: 1_700_000_000 + clock.t)
            self.assertFalse(check.write(Frame()))  # not on
            path = check.start([0, 2])
            frame = Frame(session_time=12.5, is_replay_playing=True, replay_frame_num=900, position=[2, 0, 1],
                          pct=[0.25, 0.0, 0.5], f2_time=[1.25, 0, 0], est_time=[30.0, 0, 60.0], on_pit=[False, False, True])
            for _ in range(25):  # 2.5 s, ten frames a second
                check.write(frame)
                clock.t += 0.1
            check.stop()
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            self.assertEqual(tuple(rows[0]), COLUMNS)
            self.assertEqual(len(rows) - 1, 3)  # at 0, 1 and 2 s
            row = dict(zip(rows[0], rows[1]))
            self.assertEqual((row["SessionTime"], row["IsReplayPlaying"], row["ReplayFrameNum"]), ("12.5", "1", "900"))
            self.assertEqual((row["CarIdxPosition"], row["CarIdxOnPitRoad"]), ("[2, 1]", "[0, 1]"))  # cars 0 and 2


class LiveInReplayTests(unittest.TestCase):
    """iRacing's car data live during replays: the race timed live underneath
    (gaps, intervals, places), the same as without the replay."""

    def run_pair(self, mode):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            clocks = (FakeClock(), FakeClock())
            sources = [MockSource(seed=7, clock=c) for c in clocks]
            apps = [App(s, dict(DEFAULTS), LeagueStore(d)) for s, d in zip(sources, (a, b))]
            apps[1].settings.set("replay_car_data", mode)
            # The second sees the same race, but from a minute in with a replay
            # paused on screen (iRacing's car data still the live race's).
            read = sources[1].read

            def in_replay():
                f = read()
                if f is None or f.session_time < 60:
                    return f
                return replace(f, replay_frames_from_end=6000, replay_session_time=30.0, replay_speed=0)
            sources[1].read = in_replay
            for _ in range(int(150 * 10)):
                for c, app in zip(clocks, apps):
                    c.t += 0.1
                    app.tick()
            snaps = [app.build_snapshot() for app in apps]
            return snaps, apps

    def test_gaps_live_in_a_replay(self):
        (live, replay), apps = self.run_pair("live")
        self.assertFalse(replay["replay"]["live"])           # still a replay on screen
        self.assertEqual(replay["detection"], "replay_live")
        order = lambda s: [(r["car_idx"], r["pos"], r["gap"]) for r in sorted(s["drivers"], key=lambda r: r["pos"] or 99)]  # noqa: E731
        self.assertEqual(order(replay), order(live))
        self.assertTrue(sum(1 for r in replay["drivers"] if r["gap"]) >= 5)

    def test_found_by_itself(self):
        (live, replay), apps = self.run_pair("auto")
        self.assertEqual(replay["replay_data"]["found"], "live")  # the cars went on moving with the replay paused
        self.assertEqual(apps[1].settings.get("replay_cars_found"), "live")
        order = lambda s: [(r["car_idx"], r["pos"], r["gap"]) for r in sorted(s["drivers"], key=lambda r: r["pos"] or 99)]  # noqa: E731
        self.assertEqual(order(replay), order(live))

    def test_the_replays_as_set(self):
        (live, replay), apps = self.run_pair("replay")
        self.assertEqual(replay["replay_data"]["found"], "replay")
        self.assertNotEqual(replay["detection"], "live")


if __name__ == "__main__":
    unittest.main()
