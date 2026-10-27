import tempfile
import unittest

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
        self.assertEqual(p["drivers"], [{"cust_id": 12, "name": "A", "car_number": "", "nickname": "", "team": "", "notes": ""}])


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

    def test_bad_league_id(self):
        with self.assertRaises(LeagueError):
            self.store.fetch("abc")


if __name__ == "__main__":
    unittest.main()
