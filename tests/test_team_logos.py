"""A team's full and small logos, and which one each overlay and board shows."""

import tempfile
import unittest

from apex import boards
from apex.league import LeagueStore
from apex.overlays import normalise as overlay_settings
from tests.test_boards import league

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x8d\xb4\x1c\x00\x00\x00\x00IEND\xaeB`\x82")


class TeamLogoTests(unittest.TestCase):
    def test_both_logos_kept_and_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LeagueStore(tmp)
            saved = store.save(league(teams=[{"name": "Red"}]))
            store.save_image(saved["id"], "team:Red", PNG)
            saved = store.save_image(saved["id"], "team_small:Red", PNG + b"x")
            red = next(t for t in saved["teams"] if t["name"] == "Red")
            self.assertTrue(red["logo"] and red["logo_small"] and red["logo"] != red["logo_small"])
            # Both files kept on the next save (nothing tidied away).
            saved = store.save(saved)
            for name in (red["logo"], red["logo_small"]):
                self.assertIsNotNone(store.logo_file(saved["id"], name))
            rows = boards.build(saved, {"kind": "championship", "params": {"group": "overall"}}, overlay_settings({}))["rows"]
            reds = [r for r in rows if r["team"] == "Red"]
            self.assertTrue(reds)
            self.assertTrue(all(r["team_logo"].endswith(red["logo"]) and r["team_logo_small"].endswith(red["logo_small"]) for r in reds))
            blues = [r for r in rows if r["team"] == "Blue"]
            self.assertTrue(all(r["team_logo_small"] is None for r in blues))

    def test_which_logo_is_a_setting_on_every_widget_with_team_logos(self):
        st = overlay_settings({"standings": {"team_logo_kind": "small"}, "driver": {"team_logo_kind": "nope"}})
        self.assertEqual((st["standings"]["team_logo_kind"], st["driver"]["team_logo_kind"]), ("small", "full"))
        for section in ("standings", "driver", "pits", "battle", "duel", "gridwalk", "laps",
                        "board_championship", "board_teams", "board_results", "board_qualifying", "board_grid"):
            self.assertEqual(st[section]["team_logo_kind"], "small" if section == "standings" else "full")


if __name__ == "__main__":
    unittest.main()
