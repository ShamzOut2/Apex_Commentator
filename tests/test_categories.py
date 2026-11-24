"""Categories (Pro, Semi-Pro...) inside each car class (LMP2 · Pro, GT3 · Pro),
championships a league doesn't run, and ending a championship (locked, in
the archive)."""

import tempfile
import unittest

from apex import boards
from apex import championship as ch
from apex.league import LeagueEnded, LeagueError, LeagueStore, normalise_profile
from tests.test_championship import profile, res

CLASSES = [{"id": "lmp2", "name": "LMP2", "color": "#2f7bff"}, {"id": "gt3", "name": "GT3", "color": "#22b573"},
           {"id": "pro", "name": "Pro", "role": "secondary", "scope": "class", "tag": "PRO", "name_tag": "(P)"},
           {"id": "sp", "name": "Semi-Pro", "role": "secondary", "scope": "class", "tag": "SP", "name_tag": "SP"}]
# LMP2: A (Pro) 1st, B (Semi-Pro) 2nd, C (Pro) 3rd, D (Semi-Pro) 4th. GT3: E (Pro) 1st, F (Semi-Pro) 2nd.
DRIVERS = [{"cust_id": i, "name": n, "class2_id": c2} for i, n, c2 in
           ((1, "A", "pro"), (2, "B", "sp"), (3, "C", "pro"), (4, "D", "sp"), (5, "E", "pro"), (6, "F", "sp"))]
ROUND = {"id": "r1", "results": [res("cust:1", 1, "lmp2"), res("cust:2", 2, "lmp2"), res("cust:3", 3, "lmp2"),
                                 res("cust:4", 4, "lmp2"), res("cust:5", 5, "gt3"), res("cust:6", 6, "gt3")]}
RULES = {"points": [25, 18, 15, 12], "classified_pct": 0}


def groups(p):
    return {g["key"]: g for g in ch.standings(p)["groups"]}


def points(g):
    return [(r["driver"], r["points"]) for r in g["drivers"]]


class CategoryTests(unittest.TestCase):
    def test_a_championship_per_category_in_each_car_class(self):
        g = groups(profile(RULES, [ROUND], classes=CLASSES, drivers=DRIVERS))
        self.assertEqual(list(g), ["lmp2", "gt3", "lmp2/pro", "lmp2/sp", "gt3/pro", "gt3/sp"])
        self.assertEqual(g["lmp2/pro"]["name"], "LMP2 · Pro")
        self.assertEqual((g["lmp2/pro"]["color"], g["lmp2/pro"]["car_class"], g["lmp2/pro"]["category"]), ("#2f7bff", "lmp2", "pro"))
        # Ranked among the Pros in LMP2: C was 3rd in LMP2, 2nd Pro.
        self.assertEqual(points(g["lmp2/pro"]), [("cust:1", 25), ("cust:3", 18)])
        self.assertEqual(points(g["lmp2/sp"]), [("cust:2", 25), ("cust:4", 18)])
        self.assertEqual(points(g["gt3/sp"]), [("cust:6", 25)])
        # The car class championships are as they were.
        self.assertEqual(points(g["lmp2"]), [("cust:1", 25), ("cust:2", 18), ("cust:3", 15), ("cust:4", 12)])

    def test_points_from_their_car_class(self):
        rules = dict(RULES, secondary_scoring={"pro": "class"})
        g = groups(profile(rules, [ROUND], classes=CLASSES, drivers=DRIVERS))
        self.assertEqual(points(g["lmp2/pro"]), [("cust:1", 25), ("cust:3", 15)])
        self.assertEqual(g["lmp2/pro"]["basis"], "The points its drivers score in their own class")
        # Even when the car classes themselves aren't scored (overall only).
        g = groups(profile(dict(rules, scoring="overall"), [ROUND], classes=CLASSES, drivers=DRIVERS))
        self.assertEqual(points(g["lmp2/pro"]), [("cust:1", 25), ("cust:3", 15)])

    def test_a_category_points_table_in_every_car_class(self):
        rules = dict(RULES, class_points={"sp": [10, 5]})
        g = groups(profile(rules, [ROUND], classes=CLASSES, drivers=DRIVERS))
        self.assertEqual(points(g["lmp2/sp"]), [("cust:2", 10), ("cust:4", 5)])
        self.assertEqual(points(g["gt3/sp"]), [("cust:6", 10)])

    def test_only_in_some_car_classes(self):
        classes = [dict(c, **({"in": ["lmp2"]} if c["id"] == "sp" else {})) for c in CLASSES]
        g = groups(profile(RULES, [ROUND], classes=classes, drivers=DRIVERS))
        self.assertIn("lmp2/sp", g)
        self.assertNotIn("gt3/sp", g)

    def test_championships_switched_off(self):
        # Car classes off: only their categories run.
        rules = dict(RULES, hidden=["lmp2", "gt3", "gt3/sp"])
        g = groups(profile(rules, [ROUND], classes=CLASSES, drivers=DRIVERS))
        self.assertEqual(list(g), ["lmp2/pro", "lmp2/sp", "gt3/pro"])

    def test_whole_field_categories_as_before(self):
        # Saved before categories had a scope: one for the whole field.
        classes = [{k: v for k, v in c.items() if k != "scope"} for c in CLASSES]
        p = profile(RULES, [ROUND], classes=classes, drivers=DRIVERS)
        self.assertEqual(p["classes"][2]["scope"], "field")
        g = groups(p)
        self.assertEqual(points(g["pro"]), [("cust:1", 25), ("cust:3", 18), ("cust:5", 15)])
        self.assertNotIn("lmp2/pro", g)

    def test_rounds_scored_before_rescore(self):
        """Rounds saved before the league had categories score in them as soon
        as it has them: standings are worked out from the results each time."""
        before = profile(RULES, [ROUND], classes=CLASSES[:2], drivers=[{k: v for k, v in d.items() if k != "class2_id"} for d in DRIVERS])
        self.assertEqual(list(groups(before)), ["lmp2", "gt3"])
        after = normalise_profile(dict(before, classes=CLASSES, drivers=DRIVERS))
        self.assertEqual(points(groups(after)["lmp2/pro"]), [("cust:1", 25), ("cust:3", 18)])

    def test_round_results_and_boards(self):
        p = dict(profile(RULES, [ROUND], classes=CLASSES, drivers=DRIVERS), id="cats")
        rows = ch.round_results(p, p["championship"]["rounds"][0], "lmp2/sp")
        self.assertEqual([(r["driver"], r["rank"], r["points"]) for r in rows], [("cust:2", 1, 25), ("cust:4", 2, 18)])
        opts = boards.options(p)
        self.assertIn({"key": "gt3/pro", "name": "GT3 · Pro", "color": "#22b573", "secondary": True}, opts["classes"])
        self.assertIn("lmp2/pro", [g["key"] for g in opts["groups"]])
        self.assertEqual(boards._group_info(p, "lmp2/pro")[:2], ("LMP2 · Pro", "#2f7bff"))

    def test_category_from_name_tag(self):
        drivers = [{"name": "(P) Dave Price"}, {"name": "(SP) Ben Gibbons"}, {"name": "(P) Ann Lee", "class2_id": "-"},
                   {"name": "No Tag"}]
        p = profile(RULES, classes=CLASSES, drivers=drivers)
        self.assertEqual([d["class2_id"] for d in p["drivers"]], ["pro", "sp", "-", ""])
        self.assertEqual(p["classes"][2]["name_tag"], "P")
        self.assertEqual(ch.secondary_classes(p), {"name:(p) dave price": "pro", "name:(sp) ben gibbons": "sp"})


class EndedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LeagueStore(self.tmp.name)
        self.league = self.store.save({"name": "Season 1", "classes": CLASSES, "drivers": DRIVERS,
                                       "championship": {"rules": RULES, "rounds": [ROUND]}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_ended_league_is_locked_and_archived(self):
        ended = self.store.end(self.league["id"])
        self.assertTrue(ended["ended"]["at"])
        self.assertTrue(next(x for x in self.store.list() if x["id"] == ended["id"])["ended"])
        with self.assertRaises(LeagueEnded):
            self.store.save(dict(ended, name="Changed"))
        with self.assertRaises(LeagueError):
            self.store.save(dict(ended, drivers=[]))
        self.assertEqual(self.store.get(ended["id"])["name"], "Season 1")
        # Standings stay as they ended.
        self.assertEqual(list(groups(self.store.get(ended["id"]))), ["lmp2", "gt3", "lmp2/pro", "lmp2/sp", "gt3/pro", "gt3/sp"])
        # Reopened: it can be changed again.
        self.store.reopen(ended["id"])
        self.assertEqual(self.store.save(dict(self.store.get(ended["id"]), name="Changed"))["name"], "Changed")

    def test_copy_from_an_ended_league(self):
        self.store.end(self.league["id"])
        nxt = self.store.save({"name": "Season 2"})
        got = self.store.copy_settings(nxt["id"], self.league["id"], ["rules", "classes"])
        self.assertEqual([c["name"] for c in got["classes"]], ["LMP2", "GT3", "Pro", "Semi-Pro"])
        self.assertEqual(got["classes"][2]["scope"], "class")
        # Not into it, though.
        with self.assertRaises(LeagueEnded):
            self.store.copy_settings(self.league["id"], nxt["id"], ["rules"])
        # A copy of it runs.
        copy = self.store.duplicate(self.league["id"], "Season 1 again")
        self.assertIsNone(copy["ended"])
        self.store.save(dict(copy, name="Season 1 again"))

    def test_a_save_cannot_end_or_reopen(self):
        saved = self.store.save(dict(self.league, ended={"at": "2026-01-01"}))
        self.assertIsNone(saved["ended"])


if __name__ == "__main__":
    unittest.main()
