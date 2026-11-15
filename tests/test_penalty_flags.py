"""The flag by a driver on the tower for a penalty iRacing shows them."""

import tempfile
import unittest
from dataclasses import replace

from apex.config import DEFAULTS
from apex.core import App
from apex.league import LeagueStore
from apex.sources import FLAG_BLACK, FLAG_DISQUALIFY, FLAG_FURLED, FLAG_REPAIR, MockSource
from tests.test_app import FakeClock


class PenaltyFlagTests(unittest.TestCase):
    def test_black_meatball_warning_and_dq(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            src = MockSource(seed=7, clock=clock)
            read = src.read
            bits = {2: FLAG_BLACK, 3: FLAG_REPAIR, 4: FLAG_FURLED, 5: FLAG_DISQUALIFY | FLAG_REPAIR}

            def flagged():
                f = read()
                if f is None:
                    return f
                cf = list(f.car_flags) or [0] * len(f.pct)
                for i, b in bits.items():
                    cf[i] |= b
                return replace(f, car_flags=cf)
            src.read = flagged
            app = App(src, dict(DEFAULTS), LeagueStore(tmp))
            app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": False}})
            for _ in range(30):
                clock.t += 0.1
                app.tick()
            got = {e["car_idx"]: e["penalty"] for e in app.build_snapshot()["overlays"]["standings"]}
            self.assertEqual({i: got[i] for i in bits}, {2: "black", 3: "meatball", 4: "warning", 5: "dq"})  # the most serious
            self.assertTrue(all(p is None for i, p in got.items() if i not in bits))
            self.assertTrue(app.overlays.get()["standings"]["penalty_flags"])


if __name__ == "__main__":
    unittest.main()
