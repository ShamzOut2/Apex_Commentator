"""The commentator tools in the app: talking points, the catching overlay, a
driver's season, head to head and the race recap board (with their hotkeys)."""

import tempfile
import unittest

from apex.core import CommandError
from apex.league import driver_key, profile_from_session
from tests.test_app import make_app


class CommentatorToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, _ = make_app(cls.tmp.name, minutes=6)  # the demo race: four laps or so
        drivers = cls.app.build_snapshot()["drivers"]
        profile = profile_from_session(drivers, "Tools")
        cls.keys = [driver_key(d) for d in profile["drivers"]]
        k = cls.keys
        # Three rounds before this one: k[0] won two, k[1] one; k[2] never on the podium.
        order = [[k[0], k[1], k[3], k[2]], [k[1], k[0], k[3], k[2]], [k[0], k[3], k[1], k[2]]]
        rounds = [{"id": f"r{n}", "name": f"Round {n}", "results": [
            {"driver": d, "name": d, "position": i + 1, "laps": 10, "status": "finished"} for i, d in enumerate(o)]}
            for n, o in enumerate(order, start=1)] + [{"id": "r4", "name": "Round 4"}]
        profile["championship"] = {"rules": {"points": [25, 18, 15, 12, 10], "scoring": "overall"}, "rounds": rounds}
        cls.league = cls.app.leagues.save(profile)
        cls.app.leagues.set_active(cls.league["id"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def snap(self):
        return self.app.build_snapshot()

    def car_of(self, key):
        return next(r["car_idx"] for r in self.snap()["drivers"] if driver_key(r) == key)

    def test_talking_points(self):
        pts = self.snap()["talking"]
        self.assertTrue(pts, "the demo race gives something to say")
        for p in pts:
            self.assertTrue({"key", "kind", "text", "cars", "action", "age"} <= set(p))
            self.assertGreaterEqual(p["age"], 0)
        self.assertEqual(len({p["key"] for p in pts}), len(pts))
        # Each one puts up what it's about; the top one with its hotkey.
        for p in pts:
            self.app.command("talk_do", {"key": p["key"]})
        self.app.command("hotkey", {"action": "talk:top"})
        if self.snap()["board"]:
            self.app.command("board_hide", {})
        with self.assertRaises(CommandError):
            self.app.command("talk_do", {"key": "nothing:here"})

    def test_catching(self):
        self.app.command("hotkey", {"action": "catching:ahead"})
        cfg = self.app.overlays.get()["catching"]
        self.assertEqual((cfg["target"], cfg["visible"]), ("ahead", True))
        c = self.snap()["overlays"]["catching"]
        self.assertLess(c["ahead"]["pos"], c["behind"]["pos"])
        self.assertGreaterEqual(len(c["gaps"]), 2)  # laps both have done at the line
        self.assertIn(c["trend"], ("closing", "pulling", "steady"))
        # Two cars picked (the car ahead first, whatever order they're given in).
        rows = sorted((r for r in self.snap()["drivers"] if r["pos"]), key=lambda r: r["pos"])
        self.app.command("catching_pick", {"cars": [rows[4]["car_idx"], rows[2]["car_idx"]]})
        c = self.snap()["overlays"]["catching"]
        self.assertEqual((c["ahead"]["car_idx"], c["behind"]["car_idx"]), (rows[2]["car_idx"], rows[4]["car_idx"]))
        self.app.command("hotkey", {"action": "catching:toggle"})
        self.assertFalse(self.app.overlays.get()["catching"]["visible"])
        with self.assertRaises(CommandError):
            self.app.command("catching_pick", {"mode": "sideways"})

    def test_season_card(self):
        car = self.car_of(self.keys[0])
        before = self.snap()["overlays"]["season"]
        self.app.command("season_show", {"car_idx": car})
        s = self.snap()["overlays"]["season"]
        self.assertEqual(s["car_idx"], car)
        self.assertNotEqual(s["pick"], before and before["pick"])  # asked for again: it shows again
        self.assertEqual((s["season"]["wins"], s["season"]["podiums"], s["season"]["best"]), (2, 3, 1))
        self.assertEqual(s["season"]["form"], ["P1", "P2", "P1"])
        self.assertEqual(s["season"]["pos"], 1)
        # The driver on camera (hotkey season:camera), and off again.
        self.app.command("hotkey", {"action": "season:camera"})
        self.assertEqual(self.app.overlays.get()["season"]["driver"], "")
        self.app.command("hotkey", {"action": "season:toggle"})
        self.assertFalse(self.app.overlays.get()["season"]["visible"])

    def test_head_to_head(self):
        self.app.command("h2h_pick", {"drivers": [self.keys[0], self.keys[1]]})
        h = self.snap()["overlays"]["h2h"]
        self.assertEqual([d["driver"] for d in h["drivers"]], self.keys[:2])
        self.assertEqual(h["ahead"], [2, 1])  # k0 ahead in rounds 1 and 3, k1 in round 2
        self.assertEqual(h["drivers"][0]["season"]["wins"], 2)
        self.assertIsNotNone(h["drivers"][0]["today"])  # both in the session
        self.assertIsNotNone(h["gap"])
        with self.assertRaises(CommandError):
            self.app.command("h2h_pick", {"drivers": [self.keys[0], self.keys[0]]})
        self.app.command("hotkey", {"action": "h2h:camera"})  # the driver on camera and the car ahead
        self.assertEqual(len(self.app.overlays.get()["h2h"]["drivers"].split(",")), 2)
        self.app.command("hotkey", {"action": "h2h:toggle"})
        self.assertFalse(self.app.overlays.get()["h2h"]["visible"])

    def test_recap_board(self):
        self.app.command("hotkey", {"action": "board:recap:overall"})
        b = self.snap()["board"]
        self.assertEqual((b["kind"], b["title"]), ("recap", "Race recap"))
        r = b["recap"]
        self.assertGreaterEqual(r["chart"]["laps"], 3)
        self.assertLessEqual(len(r["chart"]["cars"]), self.app.overlays.get()["board_recap"]["chart_cars"])
        self.assertEqual(len(r["chart"]["cars"][0]["places"]), r["chart"]["laps"] + 1)  # the start, then each lap
        self.assertTrue(r["chart"]["cars"][0]["name"])
        if r["cleanest"]:
            self.assertIn("incidents", r["cleanest"])
        self.app.command("hotkey", {"action": "board:recap:overall"})  # again: off
        self.assertIsNone(self.snap()["board"])

    def test_new_overlays_everywhere_overlays_are(self):
        for k in ("catching", "season", "h2h"):
            self.assertIn(k, self.app.DESKTOP_PAGES)
            self.assertIn(k, self.app.TOGGLE_ALL)
            self.assertIn(k, self.app.DESKTOP_GROUPS["overlays"])
            self.app.command("hotkey", {"action": f"ov:{k}"})  # the usual on / off hotkey


class ClassOrOverallTests(unittest.TestCase):
    """Season and head to head by class or overall, in a league that scores
    only its classes: overall shows the overall finishes, without a place or
    points (there's no overall championship)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, _ = make_app(cls.tmp.name, minutes=3)
        profile = profile_from_session(cls.app.build_snapshot()["drivers"], "Classes")
        k = cls.keys = [driver_key(d) for d in profile["drivers"]]
        cls_of = {k[0]: "gt3", k[1]: "gt3", k[2]: "gt4", k[3]: "gt4"}
        for d in profile["drivers"]:
            d["class_id"] = cls_of.get(driver_key(d), "gt3")
        # Overall finishing orders; k0's class finishes are 1, 1, 2 and overall 2, 1, 2.
        order = [[k[2], k[0], k[1], k[3]], [k[0], k[2], k[1], k[3]], [k[1], k[0], k[3], k[2]]]
        rounds = [{"id": f"r{n}", "name": f"Round {n}", "results": [
            {"driver": d, "name": d, "position": i + 1, "laps": 10, "status": "finished", "class_id": cls_of[d]} for i, d in enumerate(o)]}
            for n, o in enumerate(order, start=1)]
        profile["championship"] = {"rules": {"points": [25, 18, 15, 12], "scoring": "class"}, "rounds": rounds}
        cls.app.leagues.set_active(cls.app.leagues.save(profile)["id"])
        cls.car = next(r["car_idx"] for r in cls.app.build_snapshot()["drivers"] if driver_key(r) == k[0])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def season(self, champ):
        self.app.command("overlay_settings", {"overlay": "season", "values": {"champ": champ}})
        self.app.command("season_show", {"car_idx": self.car})
        return self.app.build_snapshot()["overlays"]["season"]

    def test_season_by_class_and_overall(self):
        s = self.season("class")
        self.assertEqual((s["by"], s["scored"], s["championship"]), ("class", True, "GT3"))
        self.assertEqual((s["season"]["pos"], s["season"]["wins"], s["season"]["form"]), (1, 2, ["P1", "P1", "P2"]))
        s = self.season("overall")
        self.assertEqual((s["by"], s["scored"]), ("overall", False))
        self.assertEqual((s["season"]["pos"], s["season"]["points"]), (None, None))  # no overall championship
        self.assertEqual((s["season"]["wins"], s["season"]["podiums"], s["season"]["form"]), (1, 3, ["P2", "P1", "P2"]))
        self.app.command("hotkey", {"action": "season:champ"})  # switched back
        self.assertEqual(self.app.overlays.get()["season"]["champ"], "class")

    def test_head_to_head_by_class_and_overall(self):
        k = self.keys
        self.app.command("overlay_settings", {"overlay": "h2h", "values": {"champ": "class"}})
        self.app.command("h2h_pick", {"drivers": [k[0], k[1]]})
        h = self.app.build_snapshot()["overlays"]["h2h"]
        self.assertEqual((h["by"], h["scored"], h["ahead"]), ("class", True, [2, 1]))
        self.assertIsNotNone(h["points_gap"])
        self.app.command("hotkey", {"action": "h2h:champ"})  # overall
        h = self.app.build_snapshot()["overlays"]["h2h"]
        self.assertEqual((h["by"], h["scored"], h["points_gap"]), ("overall", False, None))
        self.assertIsNone(h["drivers"][0]["season"]["pos"])
        self.assertEqual(h["drivers"][0]["season"]["wins"], 1)
        # Different classes, by class: compared overall (finishes only).
        self.app.command("hotkey", {"action": "h2h:champ"})
        self.app.command("h2h_pick", {"drivers": [k[0], k[2]]})
        h = self.app.build_snapshot()["overlays"]["h2h"]
        self.assertEqual((h["by"], h["scored"], h["ahead"]), ("overall", False, [2, 1]))


if __name__ == "__main__":
    unittest.main()
