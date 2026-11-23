"""Who gets the tower's fastest lap stopwatch: a choice of three, kept as set."""

import tempfile
import unittest
from pathlib import Path

from apex import boards, spectate
from apex.overlays import DEFAULTS
from tests.test_app import make_app

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


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


    def test_boards_know_the_class_and_the_overall_fastest(self):
        """A board's rows say whether each holds its class's fastest lap and the
        session's (a class's board too), for it to light as the stopwatch is set."""
        results = [{"driver": "a", "class_id": "gt3", "fastest_lap": 90.1, "status": "finished"},
                   {"driver": "b", "class_id": "gt3", "fastest_lap": 90.5, "status": "finished"},
                   {"driver": "c", "class_id": "gt4", "fastest_lap": 95.0, "status": "finished"},
                   {"driver": "d", "class_id": "gt4", "fastest_lap": 94.0, "status": "dsq"}]
        rows = [dict(r) for r in results if r["class_id"] == "gt4"]  # the GT4 board
        boards._mark_fastest(rows, results)
        self.assertEqual([(r["fl_class"], r["fl_overall"]) for r in rows], [(True, False), (False, False)])
        rows = [dict(r) for r in results]
        boards._mark_fastest(rows, results)
        self.assertEqual([r["driver"] for r in rows if r["fl_overall"]], ["a"])
        self.assertEqual([r["driver"] for r in rows if r["fl_class"]], ["a", "c"])

    def test_the_live_timing_page_is_told(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=0.5)
            app.spectators = spectate.SpectatorServer(WEB_DIR / "live", port=0)  # not started: just collecting
            app.command("overlay_settings", {"overlay": "standings", "values": {"fastest_icon_for": "overall"}})
            section = app.build_snapshot()["spectator"]
            self.assertEqual(section["flfor"], "overall")
            self.assertTrue(all("fl" in c and "cfl" in c for c in section["cars"]))


if __name__ == "__main__":
    unittest.main()
