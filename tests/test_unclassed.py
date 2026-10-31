import tempfile
import unittest

from apex.league import profile_from_session
from tests.test_app import make_app


class UnclassedTests(unittest.TestCase):
    def test_drivers_with_no_class_are_left_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=2)
            drivers = app.build_snapshot()["drivers"]
            league = profile_from_session(drivers, "Classes")
            # GT3 is a class; GT4 cars match none. One GT4 driver has a secondary class.
            league["classes"] = [{"id": "gt3", "name": "GT3", "color": "#ff0000", "match": ["GT3"]},
                                 {"id": "rookie", "name": "Rookie", "color": "#00ff00", "role": "secondary"}]
            gt4 = [d for d in drivers if d["car_class"] == "GT4"]
            rookie = gt4[0]
            for d in league["drivers"]:
                d["class_id"] = ""
                if d["cust_id"] == rookie["cust_id"]:
                    d["class2_id"] = "rookie"
            league = app.leagues.save(league)
            app.leagues.set_active(league["id"])
            snap = app.build_snapshot()
            hidden = {d["car_idx"] for d in snap["drivers"] if d["hidden"]}
            self.assertEqual(hidden, {d["car_idx"] for d in gt4[1:]})
            shown = {e["car_idx"] for e in snap["overlays"]["standings"]}
            self.assertFalse(shown & hidden)
            self.assertIn(rookie["car_idx"], shown)  # a secondary class is enough
            self.assertEqual(len(snap["drivers"]), len(drivers))  # the Timing tab still has everyone
            self.assertFalse({e["car_idx"] for e in snap["gridwalk"]["entries"]} & hidden)
            results, _ = app.session_results(app.leagues.get(league["id"]))
            cust = {d["cust_id"] for d in gt4[1:]}
            self.assertFalse({r["driver"] for r in results} & {f"cust:{c}" for c in cust})
            # Turned off in the league: everyone again.
            league["hide_unclassed"] = False
            app.leagues.save(league)
            app.leagues.set_active(league["id"])
            self.assertFalse(any(d["hidden"] for d in app.build_snapshot()["drivers"]))


if __name__ == "__main__":
    unittest.main()
