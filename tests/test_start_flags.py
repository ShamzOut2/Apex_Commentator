"""The starting lights (lights.html) and the flag overlay's yellow sectors (flags.html)."""

import tempfile
import unittest
from dataclasses import replace

from apex.config import DEFAULTS
from apex.core import App
from apex.league import LeagueStore
from apex.sectorflags import SectorFlags, sector_of, sectors_text
from apex.sources import MockSource, STATE_PARADE_LAPS
from apex.startlights import ONE_LAP_TO_GREEN, START_GO, START_READY, START_SET, StartLights
from tests.test_app import FakeClock

KEY = (1, 0)


def lit(lights, t, **kw):
    args = dict(race=True, started=False, flags=0, leader=None)
    args.update(kw)
    out = lights.update(KEY, t, **args)
    return None if out is None else ("out" if out["out"] else out["lit"])


class LightsTests(unittest.TestCase):
    def test_standing_start(self):
        lights = StartLights()
        self.assertIsNone(lit(lights, 0.0))                      # nothing before iRacing's lights
        seen = [lit(lights, 10 + k * 0.5, flags=START_READY) for k in range(14)]
        self.assertEqual(seen[:3], [0, 0, 1])                     # dark lights, then a light a second
        self.assertEqual(max(seen), 5)
        self.assertEqual(lit(lights, 18.0, flags=START_SET), 5)  # all lit, held
        self.assertEqual(lit(lights, 19.0, flags=START_GO), "out")
        self.assertEqual(lit(lights, 21.5, started=True), "out")
        self.assertIsNone(lit(lights, 22.5, started=True))       # gone after 3 s

    def test_rolling_start_from_the_leaders_run_to_the_line(self):
        lights = StartLights()
        lap_s = 100.0
        seen = []
        for k in range(400):  # the lap to the green, 20 s at 10 a second, the line at 0.80 + 0.2
            t = k * 0.1
            progress = 0.80 + t / lap_s
            if progress >= 1.0:
                seen.append(lit(lights, t, started=True, leader=progress))
                continue
            seen.append(lit(lights, t, flags=ONE_LAP_TO_GREEN, leader=progress))
        counting = [s for s in seen[:200] if s is not None]
        self.assertTrue(seen[100] is None)                        # 10 s out: nothing yet
        self.assertEqual(counting[0], 0)
        self.assertEqual(sorted(set(counting)), [0, 1, 2, 3, 4, 5])
        self.assertEqual(counting, sorted(counting))              # never back a light
        self.assertEqual(seen[195], 5)                            # all lit before the line
        self.assertEqual(seen[200], "out")

    def test_by_hand_and_held_until_the_green(self):
        lights = StartLights()
        lights.count(50.0)
        self.assertEqual(lit(lights, 50.0, auto="hand"), 0)
        self.assertEqual(lit(lights, 52.5, auto="hand"), 2)
        self.assertEqual(lit(lights, 80.0, auto="hand"), 5)       # held lit
        self.assertEqual(lit(lights, 81.0, auto="hand", started=True), "out")

    def test_not_when_the_app_starts_mid_race_or_outside_a_race(self):
        lights = StartLights()
        self.assertIsNone(lit(lights, 500.0, started=True))
        self.assertIsNone(lit(lights, 10.0, race=False, flags=START_READY))
        self.assertIsNone(lit(lights, 10.0, flags=START_READY, auto="hand"))


class FlagTests(unittest.TestCase):
    def test_words(self):
        self.assertEqual(sectors_text([1], 3), "Sector 1")
        self.assertEqual(sectors_text([2, 1], 3), "Sectors 1 & 2")
        self.assertEqual(sectors_text([1, 2, 4], 5), "Sectors 1, 2 & 4")
        self.assertEqual(sectors_text([1, 2, 3], 3), "All Sectors")
        self.assertEqual(sector_of(0.5, (0.0, 0.33, 0.66)), 2)

    def flags_now(self, flags, t, cars=None, **kw):
        args = dict(starts=(0.0, 0.33, 0.66), cars=cars or {}, track_m=4000.0, auto=False, caution=False, racing=True)
        args.update(kw)
        return flags.update(KEY, t, **args)

    def test_by_hand_then_track_clear(self):
        flags = SectorFlags()
        self.assertIsNone(self.flags_now(flags, 0.0))  # nothing on: not on screen
        flags.toggle(1, 3)
        self.assertEqual(self.flags_now(flags, 1.0)["text"], "Sector 1")
        flags.toggle(2, 3)
        self.assertEqual(self.flags_now(flags, 2.0)["text"], "Sectors 1 & 2")
        flags.set_all(3)
        self.assertEqual(self.flags_now(flags, 3.0)["text"], "All Sectors")
        flags.clear()
        clear = self.flags_now(flags, 4.0)
        self.assertTrue(clear["clear"])
        self.assertEqual(clear["text"], "Track Clear")
        self.assertIsNone(self.flags_now(flags, 7.5))  # gone after 3 s

    def test_a_stopped_car_by_itself(self):
        flags = SectorFlags()
        stopped = (0.50, 3, False)
        out = None
        for k in range(40):  # 4 s: one car going round, one stood still in sector 2
            t = k * 0.1
            out = self.flags_now(flags, t, cars={1: ((0.10 + t * 0.01) % 1, 3, False), 2: stopped}, auto=True)
        self.assertEqual(out["sectors"], [2])
        # Going again: yellow for hold_s more.
        for k in range(40, 140):
            t = k * 0.1
            out = self.flags_now(flags, t, cars={1: ((0.10 + t * 0.01) % 1, 3, False), 2: ((0.50 + (t - 4) * 0.01) % 1, 3, False)}, auto=True,
                                 hold_s=5.0)
        self.assertTrue(out is None or out["clear"])
        # Not when it's in the pits, and nothing without auto.
        flags = SectorFlags()
        for k in range(40):
            out = self.flags_now(flags, k * 0.1, cars={2: (0.5, 3, True)}, auto=True)
        self.assertIsNone(out)
        self.assertEqual(self.flags_now(flags, 5.0, auto=True, caution=True)["text"], "All Sectors")


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = FakeClock()
        self.src = MockSource(seed=7, clock=self.clock)
        self.app = App(self.src, dict(DEFAULTS), LeagueStore(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def run_for(self, seconds):
        for _ in range(int(seconds * 10)):
            self.clock.t += 0.1
            self.app.tick()

    def test_flag_hotkeys(self):
        self.run_for(5)
        self.assertIsNone(self.app.build_snapshot()["overlays"]["flags"])
        self.assertEqual(self.app.command("hotkey", {"action": "flags:s2"}), {"sectors": [2]})
        self.app.command("hotkey", {"action": "flags:s3"})
        snap = self.app.build_snapshot()["overlays"]["flags"]
        self.assertEqual((snap["text"], snap["count"], len(snap["starts"])), ("Sectors 2 & 3", 3, 3))
        self.app.command("hotkey", {"action": "flags:all"})
        self.assertEqual(self.app.build_snapshot()["overlays"]["flags"]["text"], "All Sectors")
        self.app.command("hotkey", {"action": "flags:clear"})
        self.assertTrue(self.app.build_snapshot()["overlays"]["flags"]["clear"])
        self.assertIn("flags", self.app.TOGGLE_ALL)

    def test_lights_on_the_lap_to_the_green(self):
        # The demo race held on its parade lap (one to green) for a while, then racing.
        read = self.src.read

        def parade():
            f = read()
            if f is None or f.session_time > 20:
                return f
            return replace(f, session_state=STATE_PARADE_LAPS, session_flags=ONE_LAP_TO_GREEN)
        self.src.read = parade
        self.run_for(2)
        self.app.command("hotkey", {"action": "lights:count"})
        self.run_for(3.5)
        self.assertEqual(self.app.build_snapshot()["overlays"]["lights"]["lit"], 3)
        self.run_for(10)
        self.assertEqual(self.app.build_snapshot()["overlays"]["lights"]["lit"], 5)
        self.run_for(6)  # green at 20 s
        self.assertTrue(self.app.build_snapshot()["overlays"]["lights"]["out"])
        self.run_for(5)
        self.assertIsNone(self.app.build_snapshot()["overlays"]["lights"])


class TrackBoardTests(unittest.TestCase):
    def test_round_track_and_weather(self):
        from tests.test_boards import league
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            app = App(MockSource(seed=7, clock=clock), dict(DEFAULTS), LeagueStore(tmp))
            app.leagues.save(league())
            app.leagues.set_active("lg")
            for _ in range(20):
                clock.t += 0.1
                app.tick()
            app.command("board_show", {"kind": "track"})
            board = app.build_snapshot()["board"]
            info = board["track_info"]
            # The round this race counts as: the first without results (R2, "Finale").
            self.assertEqual((board["title"], board["subtitle"], board["league"]), ("Round 2", "Finale", "League"))
            self.assertEqual((info["track"], info["config"], info["city"], info["turns"]), ("Mock Raceway", "Grand Prix", "Braselton", 12))
            w = info["weather"]
            self.assertEqual((w["air"], w["track"], w["wind"], w["skies"], w["humidity"]), (22.4, 31.9, 3.2, "Partly Cloudy", 55.0))
            self.assertEqual(board["sponsors"], None)  # the league has none: no bar
            app.command("overlay_settings", {"overlay": "board_track", "values": {"title": "Season finale"}})
            self.assertEqual(app.build_snapshot()["board"]["title"], "Season finale")


if __name__ == "__main__":
    unittest.main()
