import tempfile
import unittest
from pathlib import Path

from apex.league import (
    LeagueError, LeagueStore, mask_secret, merge_profiles, normalise_profile, profile_from_api,
)

API_LEAGUE = {
    "league_id": 4242,
    "league_name": "Thursday Night Thunder",
    "roster": [
        {"cust_id": 2, "display_name": "Zed Last", "car_number": "99", "nick_name": None},
        {"cust_id": 1, "display_name": "Amy First", "car_number": 7, "nick_name": "Ames"},
    ],
}


class MaskTests(unittest.TestCase):
    def test_matches_iracing_masking(self):
        # base64(sha256("MyPass" + "jane@example.com")), checked against a reference client.
        self.assertEqual(mask_secret("MyPass", " Jane@Example.com "), "FWb1HN/82wksm+/4HWSleKQbWSsIiqJIpx6ycAacRAY=")


class ProfileTests(unittest.TestCase):
    def test_profile_from_api(self):
        p = profile_from_api(API_LEAGUE)
        self.assertEqual(p["id"], "4242")
        self.assertEqual(p["name"], "Thursday Night Thunder")
        self.assertEqual([d["name"] for d in p["drivers"]], ["Amy First", "Zed Last"])
        self.assertEqual(p["drivers"][0]["car_number"], "7")
        self.assertEqual(p["drivers"][0]["nickname"], "Ames")

    def test_refresh_keeps_commentator_edits(self):
        old = profile_from_api(API_LEAGUE)
        old["drivers"][1]["notes"] = "Champion 2025"
        old["drivers"].append({"cust_id": None, "name": "Guest", "car_number": "5", "nickname": "", "team": "", "notes": ""})
        fresh = profile_from_api(dict(API_LEAGUE, roster=API_LEAGUE["roster"] + [
            {"cust_id": 3, "display_name": "New Person", "car_number": "3"}]))
        merged = merge_profiles(old, fresh)
        by_name = {d["name"]: d for d in merged["drivers"]}
        self.assertEqual(by_name["Zed Last"]["notes"], "Champion 2025")
        self.assertIn("New Person", by_name)
        self.assertIn("Guest", by_name)

    def test_normalise_validates(self):
        with self.assertRaises(LeagueError):
            normalise_profile({"name": ""})
        with self.assertRaises(LeagueError):
            normalise_profile({"name": "X", "league_id": "abc"})
        p = normalise_profile({"name": "My League!", "drivers": [{"name": " A ", "cust_id": "12"}, {"name": ""}]})
        self.assertEqual(p["id"], "my-league")
        self.assertEqual(p["drivers"], [{"cust_id": 12, "name": "A", "car_number": "", "nickname": "", "team": "", "notes": "", "class_id": "", "car_image": "", "helmet_image": "", "driver_number": ""}])

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

    def test_refresh_keeps_classes(self):
        old = normalise_profile(dict(profile_from_api(API_LEAGUE), classes=[{"name": "Am", "color": "#2f80ed"}]))
        old["drivers"][0]["class_id"] = "am"
        merged = merge_profiles(old, profile_from_api(API_LEAGUE))
        self.assertEqual([c["id"] for c in merged["classes"]], ["am"])
        self.assertEqual(merged["drivers"][0]["class_id"], "am")


class FakeClient:
    configured = True

    def league(self, league_id):
        return dict(API_LEAGUE, league_id=league_id)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LeagueStore(self.tmp.name, FakeClient())

    def tearDown(self):
        self.tmp.cleanup()

    def test_fetch_save_activate_lookup(self):
        p = self.store.fetch(" 4242 ")
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
        # Re-fetching keeps the edit.
        self.assertEqual(self.store.fetch(4242)["drivers"][0]["team"], "Apex Racing")
        self.store.delete("4242")
        self.assertEqual(self.store.list(), [])
        self.assertIsNone(self.store.active())

    def test_class_for_prefers_driver_pick_then_car_class(self):
        p = self.store.fetch(4242)
        p["classes"] = [{"name": "Pro", "color": "#e8463c", "match": ["GT3"]}, {"name": "Am", "color": "#2f80ed"}]
        p["drivers"][0]["class_id"] = "am"
        self.store.save(p)
        self.store.set_active("4242")
        amy = self.store.lookup(1, "7")
        self.assertEqual(self.store.class_for(amy, "GT3")["id"], "am")
        self.assertEqual(self.store.class_for(self.store.lookup(2, "99"), "gt3")["id"], "pro")
        self.assertIsNone(self.store.class_for(None, "GT4"))

    def test_logos(self):
        p = self.store.fetch(4242)
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
        p = self.store.fetch(4242)
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
        # Re-fetching keeps photos; dropping a photo deletes its file.
        refreshed = self.store.fetch(4242)
        self.assertEqual(refreshed["drivers"][0]["car_image"], amy["car_image"])
        self.assertTrue(self.store.logo_file("4242", amy["car_image"]))
        refreshed["drivers"][0]["car_image"] = ""
        self.store.save(refreshed)
        self.assertIsNone(self.store.logo_file("4242", amy["car_image"]))
        # Junk image references are dropped.
        junk = normalise_profile({"name": "L", "drivers": [{"name": "A", "car_image": "../../x.png"}],
                                  "teams": [{"name": "T", "logo": "../x.png"}, {"name": "t"}, {"name": ""}]})
        self.assertEqual(junk["drivers"][0]["car_image"], "")
        self.assertEqual(junk["teams"], [{"name": "T", "short": "", "color": "", "logo": None}])

    def test_import_session_merges_without_losing_edits(self):
        p = self.store.fetch(4242)
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

    def test_bad_league_id(self):
        with self.assertRaises(LeagueError):
            self.store.fetch("abc")


if __name__ == "__main__":
    unittest.main()
