"""Drivers' pronouns and second-account numbers on the overlays and boards."""

import tempfile
import unittest

from apex import boards
from apex.config import DEFAULTS
from apex.core import App
from apex.league import LeagueStore, clean_pronouns, normalise_profile, profile_from_session, strip_name_number
from apex.overlays import normalise as overlay_settings
from apex.sources import MockSource
from tests.test_app import FakeClock
from tests.test_boards import league


class NameNumberTests(unittest.TestCase):
    def test_the_number_on_the_end_comes_off(self):
        self.assertEqual(strip_name_number("Shamoy Samuel3"), "Shamoy Samuel")
        self.assertEqual(strip_name_number("Jo Bloggs 2"), "Jo Bloggs")
        self.assertEqual(strip_name_number("Max Verstappen33"), "Max Verstappen")
        for keep in ("Dave Price", "R2D2 Smith", "12345", "Jo O'Neil"):
            self.assertEqual(strip_name_number(keep), keep)

    def test_pronouns_kept_without_brackets(self):
        self.assertEqual(clean_pronouns("  (she/her) "), "she/her")
        self.assertEqual(clean_pronouns("they / them"), "they / them")
        p = normalise_profile({"name": "L", "drivers": [{"cust_id": 1, "name": "A", "pronouns": "(he/him)"}]})
        self.assertEqual(p["drivers"][0]["pronouns"], "he/him")


class OnStreamTests(unittest.TestCase):
    def test_overlays(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            app = App(MockSource(seed=7, clock=clock), dict(DEFAULTS), LeagueStore(tmp))
            for _ in range(30):
                clock.t += 0.1
                app.tick()
            prof = profile_from_session(app.build_snapshot()["drivers"], "L")
            prof["drivers"][0]["pronouns"] = "she/her"
            first = prof["drivers"][0]["cust_id"]
            app.leagues.set_active(app.leagues.save(prof)["id"])
            app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": False}})
            for _ in range(5):
                clock.t += 0.1
                app.tick()
            snap = app.build_snapshot()
            by_cust = {d["cust_id"]: d["car_idx"] for d in snap["drivers"]}
            entries = {e["car_idx"]: e for e in snap["overlays"]["standings"]}
            self.assertEqual(entries[by_cust[first]]["pronouns"], "she/her")
            self.assertTrue(all(e["pronouns"] == "" for idx, e in entries.items() if idx != by_cust[first]))
            # Numbers on the end of names: left off once it's ticked (Officials mode too: no league).
            self.assertEqual(app._stream_name("Shamoy Samuel3", "", None), ("Shamoy Samuel3", ""))
            app.command("overlay_settings", {"overlay": "general", "values": {"strip_name_numbers": True}})
            self.assertEqual(app._stream_name("Shamoy Samuel3", "", None), ("Shamoy Samuel", ""))
            self.assertEqual(app._stream_name("(P) Shamoy Samuel3", "", {"strip_class_prefix": True})[0], "Shamoy Samuel")

    def test_boards(self):
        lg = league()
        lg["drivers"][0]["pronouns"] = "they/them"   # cust:1
        lg["drivers"][1]["name"] = "(P) Driver 22"     # cust:2, a second account's number
        settings = overlay_settings({})
        board = {"kind": "championship", "params": {"group": "overall"}}
        rows = {r["number"]: r for r in boards.build(lg, board, settings)["rows"]}
        self.assertEqual((rows["1"]["pronouns"], rows["3"]["pronouns"]), ("they/them", ""))
        self.assertEqual(rows["2"]["name"], "Driver 22")
        settings = overlay_settings({"general": {"strip_name_numbers": True}})
        rows = {r["number"]: r for r in boards.build(lg, board, settings)["rows"]}
        self.assertEqual(rows["2"]["name"], "Driver")
        results = boards.build(lg, {"kind": "results", "params": {"group": "overall", "round": "r1"}}, settings)["rows"]
        self.assertEqual({r["driver"]: r["pronouns"] for r in results}["cust:1"], "they/them")


if __name__ == "__main__":
    unittest.main()
