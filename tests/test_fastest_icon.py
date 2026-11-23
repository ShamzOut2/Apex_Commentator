"""Who gets the tower's fastest lap stopwatch: a choice of three, kept as set."""

import tempfile
import unittest

from apex.overlays import DEFAULTS
from tests.test_app import make_app


class FastestIconTests(unittest.TestCase):
    def test_choices(self):
        self.assertEqual(DEFAULTS["standings"]["fastest_icon_for"], "classes")  # as it always was
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=0.2)
            for who in ("overall", "view", "classes"):
                app.command("overlay_settings", {"overlay": "standings", "values": {"fastest_icon_for": who}})
                self.assertEqual(app.overlays.get()["standings"]["fastest_icon_for"], who)
            app.command("overlay_settings", {"overlay": "standings", "values": {"fastest_icon_for": "everyone"}})
            self.assertIn(app.overlays.get()["standings"]["fastest_icon_for"], ("classes", "view", "overall"))


if __name__ == "__main__":
    unittest.main()
