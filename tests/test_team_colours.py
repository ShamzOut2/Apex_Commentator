"""The car number in the driver's team colour (class_colors "team")."""

import tempfile
import unittest

from apex.config import DEFAULTS
from apex.core import App
from apex.league import LeagueStore, profile_from_session
from apex.overlays import normalise
from apex.sources import MockSource
from tests.test_app import FakeClock


class TeamColourTests(unittest.TestCase):
    def test_a_choice_for_every_overlay_with_a_car_number(self):
        for section in ("standings", "driver", "pits", "gridwalk"):
            self.assertEqual(normalise({section: {"class_colors": "team"}})[section]["class_colors"], "team")

    def test_team_colour_sent_with_each_driver(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            app = App(MockSource(seed=7, clock=clock), dict(DEFAULTS), LeagueStore(tmp))
            for _ in range(30):
                clock.t += 0.1
                app.tick()
            prof = profile_from_session(app.build_snapshot()["drivers"], "L")
            prof["teams"] = [{"name": "Blue", "color": "#1e41ff"}]
            for d in prof["drivers"]:
                d["team"] = "Blue"
            app.leagues.set_active(app.leagues.save(prof)["id"])
            app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": False}})
            for _ in range(5):
                clock.t += 0.1
                app.tick()
            snap = app.build_snapshot()
            self.assertTrue(snap["overlays"]["standings"])
            self.assertTrue(all(e["team_color"] == "#1e41ff" for e in snap["overlays"]["standings"]))
            cars = snap["gridwalk"]["entries"]
            self.assertTrue(cars)
            self.assertTrue(all(c["team_color"] == "#1e41ff" for c in cars))


if __name__ == "__main__":
    unittest.main()
