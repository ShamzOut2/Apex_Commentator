import tempfile
import unittest
from pathlib import Path

from apex.league import LeagueError, LeagueStore, normalise_profile


class ProfileTests(unittest.TestCase):
    def test_normalise_validates(self):
        with self.assertRaises(LeagueError):
            normalise_profile({"name": ""})
        with self.assertRaises(LeagueError):
            normalise_profile({"name": "X", "league_id": "abc"})
        p = normalise_profile({"name": "My League!", "drivers": [{"name": " A ", "cust_id": "12"}, {"name": ""}]})
        self.assertEqual(p["id"], "my-league")
        self.assertEqual(p["drivers"], [{"cust_id": 12, "name": "A", "car_number": "", "nickname": "", "team": "", "notes": "", "class_id": "", "class2_id": "", "car_image": "", "helmet_image": "", "driver_number": "", "car_make": ""}])

    def test_normalise_classes(self):
        p = normalise_profile({"name": "L", "classes": [
            {"name": "Pro", "color": "#E8463C", "match": "GT3, ,GT3 Cup", "logo_bg": "#FFFFFF", "logo_tolerance": 999},
            {"name": "Pro", "color": "red", "logo": "../../etc/passwd", "logo_bg": "javascript:", "logo_fill": "all"},
        ], "drivers": [{"name": "A", "class_id": "pro"}, {"name": "B", "class_id": "ghost"}]})
        pro, pro2 = p["classes"]
        self.assertEqual((pro["id"], pro["color"], pro["match"]), ("pro", "#e8463c", ["GT3", "GT3 Cup"]))
        self.assertEqual((pro["logo_bg"], pro["logo_tolerance"], pro["logo_fill"]), ("#ffffff", 60, "edges"))
        self.assertEqual(pro2["id"], "pro-2")  # ids stay unique
        self.assertTrue(pro2["color"].startswith("#"))
        self.assertIsNone(pro2["logo"])
        self.assertEqual((pro2["logo_bg"], pro2["logo_fill"]), ("auto", "all"))
        self.assertEqual([d["class_id"] for d in p["drivers"]], ["pro", ""])
        with self.assertRaises(LeagueError):
            normalise_profile({"name": "L", "classes": [{"name": " "}]})


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LeagueStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def seed(self):
        """A league with two drivers, Amy (7) and Zed (99)."""
        return self.store.save({"id": "4242", "league_id": 4242, "name": "Thursday Night Thunder", "drivers": [
            {"cust_id": 1, "name": "Amy First", "car_number": "7", "nickname": "Ames"},
            {"cust_id": 2, "name": "Zed Last", "car_number": "99"}]})

    def test_duplicate(self):
        p = self.seed()
        p = self.store.save_image(p["id"], "sponsor:Acme", b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        copy = self.store.duplicate(p["id"])
        self.assertEqual((copy["id"], copy["name"]), ("thursday-night-thunder-copy", "Thursday Night Thunder (copy)"))
        self.assertIsNone(copy["league_id"])
        self.assertEqual([d["name"] for d in copy["drivers"]], ["Amy First", "Zed Last"])
        self.assertTrue(self.store.logo_file(copy["id"], copy["sponsors"][0]["file"]))  # images copied too
        again = self.store.duplicate(p["id"])
        self.assertEqual(again["name"], "Thursday Night Thunder (copy) 2")
        self.assertEqual(self.store.duplicate(p["id"], "Season 2")["id"], "season-2")
        self.assertEqual(len(self.get_all()), 4)
        self.assertEqual(self.store.get(p["id"])["name"], "Thursday Night Thunder")  # the original as it was

    def get_all(self):
        return self.store.list()

    def test_save_activate_lookup(self):
        p = self.seed()
        self.assertEqual(len(p["drivers"]), 2)
        self.assertEqual([l["id"] for l in self.store.list()], ["4242"])
        p["drivers"][0]["team"] = "Apex Racing"
        p["drivers"].append({"name": "No ID", "car_number": "55", "nickname": "Ghost"})
        self.store.save(p)
        self.assertIsNone(self.store.lookup(1, "7"))  # nothing active yet
        self.store.set_active("4242")
        self.assertEqual(self.store.lookup(1, "7")["team"], "Apex Racing")
        self.assertEqual(self.store.lookup(None, "55")["nickname"], "Ghost")
        self.assertIsNone(self.store.lookup(999, "1"))
        # Active league survives a restart.
        again = LeagueStore(self.tmp.name)
        self.assertEqual(again.active_id, "4242")
        self.assertEqual(self.store.get("4242")["drivers"][0]["team"], "Apex Racing")
        self.store.delete("4242")
        self.assertEqual(self.store.list(), [])
        self.assertIsNone(self.store.active())

    def test_class_for_prefers_driver_pick_then_car_class(self):
        p = self.seed()
        p["classes"] = [{"name": "Pro", "color": "#e8463c", "match": ["GT3"]}, {"name": "Am", "color": "#2f80ed"}]
        p["drivers"][0]["class_id"] = "am"
        self.store.save(p)
        self.store.set_active("4242")
        amy = self.store.lookup(1, "7")
        self.assertEqual(self.store.class_for(amy, "GT3")["id"], "am")
        self.assertEqual(self.store.class_for(self.store.lookup(2, "99"), "gt3")["id"], "pro")
        self.assertIsNone(self.store.class_for(None, "GT4"))

    def test_secondary_classes_never_show_on_overlays(self):
        p = self.seed()
        p["classes"] = [{"name": "Rookie", "match": ["GT3"], "role": "secondary"}, {"name": "Pro", "match": ["GT3"]}]
        p["drivers"][0].update(class_id="rookie", class2_id="rookie")   # Amy: Rookie can only be her secondary class
        p["drivers"][1].update(class_id="pro", class2_id="pro")         # Zed: Pro can't be his secondary one
        saved = self.store.save(p)
        self.assertEqual([c["role"] for c in saved["classes"]], ["secondary", "main"])
        amy, zed = sorted(saved["drivers"], key=lambda d: d["cust_id"])
        self.assertEqual((amy["class_id"], amy["class2_id"]), ("", "rookie"))
        self.assertEqual((zed["class_id"], zed["class2_id"]), ("pro", ""))
        self.store.set_active("4242")
        # Matching by car class or name tag skips the secondary class.
        self.assertEqual(self.store.class_for(self.store.lookup(1, "7"), "GT3")["id"], "pro")
        self.assertEqual(self.store.class_for(None, "", name="(R) Amy First"), None)
        self.assertEqual(self.store.lookup(1, "7")["class2_id"], "rookie")

    def test_logos(self):
        p = self.seed()
        p["classes"] = [{"name": "Pro", "color": "#e8463c"}]
        self.store.save(p)
        png = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
        saved = self.store.save_logo("4242", "pro", png)
        name = saved["classes"][0]["logo"]
        self.assertRegex(name, r"^pro-[0-9a-f]{8}\.png$")
        self.assertEqual(self.store.logo_file("4242", name).read_bytes(), png)
        self.assertIsNone(self.store.logo_file("4242", "../4242.json"))
        with self.assertRaises(LeagueError):
            self.store.save_logo("4242", "pro", b"<html>not an image</html>")
        with self.assertRaises(LeagueError):
            self.store.save_logo("4242", "nope", png)
        # Replacing the logo removes the old file; removing the class removes the rest.
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
        name2 = self.store.save_logo("4242", "pro", svg)["classes"][0]["logo"]
        self.assertTrue(name2.endswith(".svg"))
        self.assertIsNone(self.store.logo_file("4242", name))
        p = self.store.get("4242")
        p["classes"] = []
        self.store.save(p)
        self.assertIsNone(self.store.logo_file("4242", name2))

    def test_logo_library(self):
        from apex.league import logo_library, logo_url
        lib = {l["title"]: l for l in logo_library()}
        self.assertTrue({"PRO", "SEMI-PRO", "PRO-AM", "AM", "GOLD", "SILVER", "BRONZE"} <= set(lib))
        self.assertEqual(lib["PRO"]["id"], "lib:pro.svg")
        p = normalise_profile({"name": "L", "classes": [
            {"name": "Pro", "logo": "lib:pro.svg"},
            {"name": "X", "logo": "lib:missing.svg"},
            {"name": "Y", "logo": "lib:../web/index.html"},
        ]})
        self.assertEqual([c["logo"] for c in p["classes"]], ["lib:pro.svg", None, None])
        self.assertEqual(logo_url("my-league", "lib:pro.svg"), "/logos/pro.svg")
        self.assertEqual(logo_url("my-league", "pro-1a2b3c4d.png"), "/api/logos/my-league/pro-1a2b3c4d.png")
        # Library logos are not deleted as "unused uploads".
        self.store.save(dict(p, id="lib-test"))
        self.assertTrue((Path(__file__).resolve().parent.parent / "web" / "logos" / "pro.svg").is_file())

    def test_library_svgs_are_layered(self):
        from apex.league import LOGO_LIBRARY_DIR
        for path in LOGO_LIBRARY_DIR.glob("*.svg"):
            text = path.read_text(encoding="utf-8")
            self.assertIn('data-apex-fill="class"', text, path.name)
            self.assertIn('data-apex-fill="ink"', text, path.name)
            self.assertNotIn("<script", text.lower(), path.name)

    def test_driver_and_team_images(self):
        from apex.league import driver_key
        p = self.seed()
        p["drivers"][0]["team"] = "Apex Racing"
        p["drivers"].append({"name": "No ID", "car_number": "55"})
        self.store.save(p)
        png = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
        amy = self.store.save_image("4242", "car:cust:1", png)["drivers"][0]
        self.assertRegex(amy["car_image"], r"^car-cust-1-[0-9a-f]{8}\.png$")
        no_id = next(d for d in self.store.save_image("4242", "helmet:name:no id", png)["drivers"] if d["name"] == "No ID")
        self.assertEqual(driver_key(no_id), "name:no id")
        self.assertTrue(no_id["helmet_image"].startswith("helmet-name-no-id-"))
        team = self.store.save_image("4242", "team:apex racing", png)["teams"]
        self.assertEqual([t["name"] for t in team], ["apex racing"])
        self.store.set_active("4242")
        self.assertEqual(self.store.team_logo("Apex Racing"), team[0]["logo"])
        with self.assertRaises(LeagueError):
            self.store.save_image("4242", "car:cust:999", png)
        with self.assertRaises(LeagueError):
            self.store.save_image("4242", "wheel:cust:1", png)
        # Saving again keeps photos; dropping a photo deletes its file.
        refreshed = self.store.get("4242")
        self.assertEqual(refreshed["drivers"][0]["car_image"], amy["car_image"])
        self.assertTrue(self.store.logo_file("4242", amy["car_image"]))
        refreshed["drivers"][0]["car_image"] = ""
        self.store.save(refreshed)
        self.assertIsNone(self.store.logo_file("4242", amy["car_image"]))
        # Junk image references are dropped.
        junk = normalise_profile({"name": "L", "drivers": [{"name": "A", "car_image": "../../x.png"}],
                                  "teams": [{"name": "T", "logo": "../x.png"}, {"name": "t"}, {"name": ""}]})
        self.assertEqual(junk["drivers"][0]["car_image"], "")
        self.assertEqual(junk["teams"], [{"name": "T", "short": "", "color": "", "logo": None, "shared": []}])

    def test_teams_shared_between_leagues(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
        a = self.store.save({"id": "gt3", "name": "GT3 Cup", "drivers": [
            {"cust_id": 1, "name": "Amy", "team": "Apex Racing"}, {"cust_id": 2, "name": "Zed", "team": "Apex Racing"},
            {"name": "No ID", "team": "Apex Racing"}]})
        self.store.save({"id": "gt4", "name": "GT4 Cup", "drivers": [
            {"cust_id": 1, "name": "Amy"}, {"cust_id": 3, "name": "Cal", "team": "Other"}, {"name": "No ID"}]})
        a = self.store.save_image("gt3", "team:Apex Racing", png)
        team = next(t for t in a["teams"] if t["name"] == "Apex Racing")
        team.update(color="#ff0000", shared=["gt4", "gt3", "gone"])  # itself and unknown leagues are dropped
        a = self.store.save(a)
        self.assertEqual(next(t for t in a["teams"] if t["name"] == "Apex Racing")["shared"], ["gt4"])
        b = self.store.get("gt4")
        copy = next(t for t in b["teams"] if t["name"] == "Apex Racing")
        self.assertEqual((copy["color"], copy["shared"]), ("#ff0000", ["gt3"]))
        self.assertTrue(self.store.logo_file("gt4", copy["logo"]))  # the logo came along
        # Its drivers who are in the other league are in the team there too.
        self.assertEqual({d["name"]: d.get("team", "") for d in b["drivers"]}, {"Amy": "Apex Racing", "Cal": "Other", "No ID": "Apex Racing"})
        # Zed joins the GT4 league later: he's put in his team by himself.
        b["drivers"].append({"cust_id": 2, "name": "Zed"})
        b = self.store.save(b)
        self.assertEqual(next(d for d in b["drivers"] if d["name"] == "Zed")["team"], "Apex Racing")
        # Edits travel either way; and unsharing leaves the other league its copy.
        next(t for t in b["teams"] if t["name"] == "Apex Racing")["short"] = "APX"
        self.store.save(b)
        a = self.store.get("gt3")
        self.assertEqual(next(t for t in a["teams"] if t["name"] == "Apex Racing")["short"], "APX")
        next(t for t in a["teams"] if t["name"] == "Apex Racing")["shared"] = []
        self.store.save(a)
        copy = next(t for t in self.store.get("gt4")["teams"] if t["name"] == "Apex Racing")
        self.assertEqual((copy["shared"], copy["short"]), ([], "APX"))

    def test_import_session_merges_without_losing_edits(self):
        p = self.seed()
        p["drivers"][0]["nickname"] = "Ames"
        p["drivers"][0]["car_number"] = ""
        p["drivers"].append({"name": "Hand Added", "car_number": "55"})
        self.store.save(p)
        session = [
            {"cust_id": 1, "name": "Amy First", "number": "7", "team": "Apex Racing"},   # known: fill blanks
            {"cust_id": 77, "name": "Hand Added", "number": "55", "team": ""},          # matches the hand-added one
            {"cust_id": 9, "name": "New Person", "number": "9", "team": "Newcomers"},  # new
        ]
        league, added = self.store.import_session("4242", session)
        self.assertEqual(added, 1)
        by_name = {d["name"]: d for d in league["drivers"]}
        self.assertEqual((by_name["Amy First"]["nickname"], by_name["Amy First"]["car_number"],
                          by_name["Amy First"]["team"]), ("Ames", "7", "Apex Racing"))
        self.assertEqual(by_name["Hand Added"]["cust_id"], 77)
        self.assertEqual(by_name["New Person"]["team"], "Newcomers")
        self.assertEqual(self.store.import_session("4242", session)[1], 0)  # idempotent


if __name__ == "__main__":
    unittest.main()
