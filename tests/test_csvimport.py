import json
import tempfile
import threading
import unittest
import urllib.request

from apex import csvimport
from apex.league import LeagueStore
from apex.server import make_server
from tests.test_app import make_app

SHEET = """CustomerID,First name,Last name,Full name,Abbreviation,Carnumber,Color 1,Team Name,Team color,Country,Bio,Social media
1485589,Adam,Antczak,Adam Antczak,A. Antczak,77,,Kukasz Crew,,,SILVER,
228974,Adam,Siennicki,Adam Siennicki,A. Siennicki,73,,Kukasz Crew E-Sport,,,GOLD,
1069108,Jason,Raaff,Jason Raaff,J. Raaff,021,,CSA Racing Team Pasop (Blue),#1a6bff,,SILVER,
1117125,Adam,Konig,Adam Konig,A. Konig,,,Kukasz Crew E-Sport,,,GOLD,
424227,Dave,Collier,Dave Collier,D. Collier,16,,DC Motorsport,,,BRONZE,
"""


class GuessTests(unittest.TestCase):
    def test_columns(self):
        headers, rows = csvimport.read(SHEET)
        m = {f: headers[i] for f, i in csvimport.guess(headers, rows).items()}
        self.assertEqual(m["cust_id"], "CustomerID")
        self.assertEqual(m["name"], "Full name")
        self.assertEqual(m["number"], "Carnumber")
        self.assertEqual(m["team"], "Team Name")
        self.assertEqual(m["team_color"], "Team color")
        self.assertEqual(m["class"], "Bio")  # no Class heading: the column of a few words in every row

    def test_semicolons_and_headings(self):
        text = "﻿iRacing ID;Driver;Car No;Team;Class\n12;Ann Bee;5;Red;Pro\n13;Cy Dee;6;Blue;Am\n"
        headers, rows = csvimport.read(text)
        m = {f: headers[i] for f, i in csvimport.guess(headers, rows).items()}
        self.assertEqual((m["cust_id"], m["name"], m["number"], m["team"], m["class"]),
                         ("iRacing ID", "Driver", "Car No", "Team", "Class"))
        with self.assertRaises(csvimport.CsvError):
            csvimport.read("just a heading\n")


class ApplyTests(unittest.TestCase):
    def test_into_a_league(self):
        headers, rows = csvimport.read(SHEET)
        mapping = csvimport.guess(headers, rows)
        profile = {"name": "NXTGEN", "classes": [{"id": "gold", "name": "Gold", "color": "#ffcc00", "role": "secondary"}],
                   "teams": [{"name": "kukasz crew", "color": "#ff0000"}],
                   "drivers": [{"name": "A Antczak", "cust_id": 1485589, "car_number": "1", "nickname": "Ant"}]}
        summary = csvimport.apply(profile, rows, mapping, "secondary")
        self.assertEqual(summary, {"added": 4, "updated": 1, "teams": 3, "classes": 2, "skipped": 0})
        by_id = {d["cust_id"]: d for d in profile["drivers"]}
        adam = by_id[1485589]
        self.assertEqual((adam["name"], adam["car_number"], adam["nickname"], adam["team"], adam["class2_id"]),
                         ("Adam Antczak", "77", "Ant", "kukasz crew", "silver"))  # the league's team, as it's named there
        self.assertEqual(by_id[1069108]["car_number"], "021")  # leading zeros kept
        self.assertNotIn("car_number", {k for k, v in by_id[1117125].items() if v})  # no number in the sheet
        self.assertEqual(by_id[228974]["class2_id"], "gold")  # the league's own Gold class
        self.assertEqual([(c["name"], c["color"], c["role"]) for c in profile["classes"][1:]],
                         [("Silver", "#b8bec6", "secondary"), ("Bronze", "#cd7f32", "secondary")])
        pasop = next(t for t in profile["teams"] if t["name"].startswith("CSA"))
        self.assertEqual(pasop["color"], "#1a6bff")
        # As main classes instead: the same names, made as main classes.
        p2 = {"name": "X"}
        csvimport.apply(p2, rows, mapping, "main")
        self.assertEqual({d["class_id"] for d in p2["drivers"]}, {"silver", "gold", "bronze"})


class EndpointTests(unittest.TestCase):
    def test_preview_and_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=0.1)
            server = make_server(app, "127.0.0.1", 0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_address[1]}"

            def post(path, body):
                req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    return json.load(r)
            try:
                league = app.leagues.save({"name": "NXTGEN"})
                p = post("/api/csv/preview", {"text": SHEET})
                self.assertEqual((p["rows"], p["classes"]), (5, ["BRONZE", "GOLD", "SILVER"]))
                r = post(f"/api/leagues/{league['id']}/import-csv", {"text": SHEET, "mapping": p["mapping"], "class_role": "main"})
                self.assertEqual(r["summary"]["added"], 5)
                saved = LeagueStore(app.leagues.dir).get(league["id"])
                self.assertEqual(len(saved["drivers"]), 5)
                self.assertEqual(sorted(c["name"] for c in saved["classes"]), ["Bronze", "Gold", "Silver"])
            finally:
                server.shutdown()
                server.server_close()
                app.stop()


if __name__ == "__main__":
    unittest.main()


class PaintTests(unittest.TestCase):
    def test_main_and_secondary_colours(self):
        from apex.core import App
        league = {"classes": [{"id": "gt3", "color": "#ff0000"}, {"id": "gold", "color": "#d4af37", "role": "secondary"}]}
        both = {"class_key": "league:gt3", "league": {"class2_id": "gold"}}
        self.assertEqual(App._paint(both, league), {"main": "#ff0000", "secondary": "#d4af37"})
        # No main class in the league (iRacing's class): no colour; nor without a secondary.
        self.assertEqual(App._paint({"class_key": "iracing:GT3", "league": {"class2_id": "gold"}}, league),
                         {"main": None, "secondary": "#d4af37"})
        self.assertEqual(App._paint({"class_key": "league:gt3", "league": None}, league), {"main": "#ff0000", "secondary": None})
        self.assertIsNone(App._paint(both, None))  # no league: iRacing's colours
