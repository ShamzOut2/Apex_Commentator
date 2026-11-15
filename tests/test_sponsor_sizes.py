"""Sponsor logo sizes: each sponsor's own scale, and the boards' sponsor logo size."""

import unittest

from apex import boards
from apex.league import normalise_sponsors
from apex.overlays import normalise as overlay_settings
from tests.test_boards import league


class SponsorSizeTests(unittest.TestCase):
    def test_each_sponsor_has_a_scale(self):
        out = normalise_sponsors([{"id": "a", "file": "sponsor-1.png", "name": "A"},
                                  {"id": "b", "file": "sponsor-2.png", "name": "B", "scale": 180},
                                  {"id": "c", "file": "sponsor-3.png", "name": "C", "scale": 999},
                                  {"id": "d", "file": "sponsor-4.png", "name": "D", "scale": "nope"}])
        self.assertEqual([s["scale"] for s in out], [100, 180, 250, 100])

    def test_sent_with_the_logos_and_boards_have_a_size(self):
        lg = league(sponsors=[{"id": "a", "file": "sponsor-1.png", "name": "A", "scale": 140}])
        self.assertEqual(boards.sponsors(lg, "")[0]["scale"], 140)
        settings = overlay_settings({"board_results": {"sponsors": "bottom", "sponsor_size": 150}})
        b = boards.build(lg, {"kind": "results", "params": {"group": "overall", "round": "r1"}}, settings)
        self.assertEqual((b["settings"]["sponsor_size"], b["sponsors"]["logos"][0]["scale"]), (150, 140))
        self.assertEqual(overlay_settings({"board_grid": {"sponsor_size": 1000}})["board_grid"]["sponsor_size"], 250)


if __name__ == "__main__":
    unittest.main()
