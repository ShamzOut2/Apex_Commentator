import json
import tempfile
import unittest
from pathlib import Path

from apex import transfer
from apex.backgrounds import Backgrounds
from apex.league import LeagueStore
from apex.overlays import OverlaySettings

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def res(driver, pos, cls, name=None):
    return {"driver": driver, "name": name or driver, "class_id": cls, "position": pos, "start_position": pos,
            "laps": 20, "laps_led": 0, "fastest_lap": 90.5 + pos, "incidents": 2, "status": "finished", "make": "BMW"}


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.store = LeagueStore(self.dir / "leagues")
        p = self.store.save({
            "name": "Sunday Cup",
            "classes": [{"id": "pro", "name": "PRO", "color": "#ff0000"}, {"id": "am", "name": "AM", "color": "#00ff00"}],
            "drivers": [{"cust_id": 1, "name": "Ann Lee", "car_number": "7", "team": "Red"},
                        {"cust_id": 2, "name": "Bo Kim", "car_number": "8", "team": "Blue"}],
            "championship": {"rules": {"points": [10, 6]}, "rounds": [
                {"id": "r1", "name": "Opener", "track": "Spa", "results": [res("cust:1", 1, "pro", "Ann Lee"), res("cust:2", 2, "am", "Bo Kim")]},
                {"id": "r2", "name": "Finale", "track": "Monza"}]},
        })
        p = self.store.save_image(p["id"], "team:Red", PNG)
        self.league = self.store.save_image(p["id"], "sponsor:Acme", PNG + b"1")

    def tearDown(self):
        self.tmp.cleanup()

    def test_league_round_trip_with_images_and_never_overwrites(self):
        data = transfer.export_league(self.store, self.league)
        fmt, kind, obj = transfer.read(data)
        self.assertEqual((fmt, kind), ("json", "league"))
        self.assertEqual(len(obj["images"]), 2)
        other = LeagueStore(self.dir / "elsewhere")  # another PC
        imported = transfer.import_league(other, obj)
        self.assertEqual(imported["name"], "Sunday Cup")
        self.assertTrue(other.logo_file(imported["id"], imported["sponsors"][0]["file"]))
        self.assertEqual(len(imported["championship"]["rounds"]), 2)
        again = transfer.import_league(self.store, obj)  # the same PC: a copy, the original untouched
        self.assertEqual(again["name"], "Sunday Cup (imported)")
        self.assertNotEqual(again["id"], self.league["id"])
        self.assertTrue(self.store.logo_file(again["id"], again["teams"][0]["logo"]))

    def test_teams_into_another_league(self):
        obj = transfer.read(transfer.export_teams(self.store, self.league))[2]
        target = self.store.save({"name": "Other", "drivers": [{"cust_id": 2, "name": "Bo Kim"}, {"cust_id": 9, "name": "Zed"}]})
        profile, info = transfer.import_teams(self.store, target, obj)
        self.assertEqual(sorted(t["name"] for t in profile["teams"]), ["Blue", "Red"])
        self.assertEqual({d["name"]: d["team"] for d in profile["drivers"]}, {"Bo Kim": "Blue", "Zed": ""})
        red = next(t for t in profile["teams"] if t["name"] == "Red")
        self.assertTrue(self.store.logo_file(profile["id"], red["logo"]))
        self.assertEqual(info["drivers"], 1)

    def test_championship_and_rounds(self):
        champ = transfer.read(transfer.export_championship(self.league))[2]
        target = self.store.save({"name": "Copy", "classes": [{"id": "x1", "name": "PRO"}]})
        profile, _ = transfer.import_championship(self.store, target, champ)
        r1 = profile["championship"]["rounds"][0]["results"]
        self.assertEqual([r["class_id"] for r in r1], ["x1", "am"])  # matched to this league's PRO by name
        # A round's results as CSV, edited in a spreadsheet, back into round 2.
        csv_text = transfer.round_csv(self.league, "r1").decode("utf-8-sig")
        self.assertTrue(csv_text.startswith("Pos,Driver,Cust ID,Class"))
        edited = csv_text.replace("Ann Lee", "Ann Lee").replace(",1,PRO,", ",1,PRO,")
        fmt, rows = transfer.expect(edited.encode(), "round", csv_ok=True)
        profile, info = transfer.import_round(self.store, self.league, "r2", fmt, rows)
        r2 = profile["championship"]["rounds"][1]["results"]
        self.assertEqual(info["results"], 2)
        self.assertEqual([(r["driver"], r["class_id"], r["position"], r["fastest_lap"]) for r in r2],
                         [("cust:1", "pro", 1, 91.5), ("cust:2", "am", 2, 92.5)])
        with self.assertRaises(transfer.TransferError):
            transfer.import_round(self.store, profile, "nope", fmt, rows)
        with self.assertRaises(transfer.TransferError):
            transfer.expect(transfer.export_teams(self.store, self.league), "championship")

    def test_iracing_event_result_export(self):
        # iRacing's own export: the event above the results table.
        text = (
            'Start Time,Track,Series,Hosted Session Name\n'
            '"2026-10-08T18:00:29Z","Fuji International Speedway - No Chicane","Hosted iRacing","Sunday Cup"\n\n\n'
            '"League Name","League ID"\n"Sunday Cup","7015"\n\n'
            '"Fin Pos","Car ID","Car","Car Class ID","Car Class","Team ID","Cust ID","Name","Start Pos","Car #","Out ID",'
            '"Out","Interval","Laps Led","Qualify Time","Average Lap Time","Fastest Lap Time","Fast Lap#","Laps Comp","Inc"\n'
            '"1","156","Mercedes-AMG GT3 2020","4091","PRO","2","2","Bo Kim","2","8","0","Running","-00.000","13","",'
            '"1:35.101","1:34.597","9","13","3"\n'
            '"2","206","Aston Martin Vantage GT3 EVO","4091","GT3 2025","1","1","Ann Lee","1","7","0","Running","-1:03.689","0","",'
            '"1:35.139","1:34.535","5","13","0"\n'
            '"3","132","BMW M4 GT3 EVO","4091","GT3 2025","9","9","Lapped Larry","3","9","0","Running","-1 L","0","",'
            '"1:43.842","1:36.171","4","12","12"\n'
            '"4","192","Supercars Chevrolet Camaro Gen 3","4070","Supercars","99","99","Safety Car","4","999","0","Running","-13 L","0","",'
            '"00.000","","","0","0"\n'
            '"5","132","BMW M4 GT3 EVO","4091","GT3 2025","3","3","Gone Early","5","10","32","Disconnected","-13 L","0","",'
            '"00.000","","","0","4"\n')
        drivers = [dict(d, class_id="pro") if d["cust_id"] == 2 else d for d in self.league["drivers"]]
        league = self.store.save(dict(self.league, classes=self.league["classes"] + [
            {"id": "gt3", "name": "GT3", "match": ["GT3 2025"]}],
            drivers=drivers + [{"cust_id": 3, "name": "Gone Early", "class_id": "am"},
                               {"cust_id": 99, "name": "Safety Car"}]))  # in the roster, given no class
        fmt, rows = transfer.expect(text.encode(), "round", csv_ok=True)
        profile, info = transfer.import_round(self.store, league, "r2", fmt, rows)
        rd = profile["championship"]["rounds"][1]
        got = [(r["driver"], r["position"], r["class_id"], r["laps"], r["fastest_lap"], r["status"], r["gap"], r["incidents"], r["make"])
               for r in rd["results"]]
        self.assertEqual(got, [
            ("cust:2", 1, "pro", 13, 94.597, "finished", 0.0, 3, "Mercedes-AMG"),     # the class picked for them
            ("cust:1", 2, "gt3", 13, 94.535, "finished", 63.689, 0, "Aston Martin"),  # by the class's iRacing classes
            ("cust:9", 3, "gt3", 12, 96.171, "finished", None, 12, "BMW"),             # not in the roster: its car class
            ("cust:3", 5, "am", 0, None, "dns", None, 4, "BMW")])  # the safety car (no class) left out
        self.assertEqual(info["results"], 4)
        self.assertAlmostEqual(rd["results"][0]["race_time"], 95.101 * 13, places=2)  # average lap x laps
        self.assertEqual((rd["track"], rd["config"]), ("Monza", ""))  # the round's own track kept
        empty = self.store.save(dict(profile, championship=dict(profile["championship"], rounds=[{"id": "r9", "name": "New"}])))
        rd9 = transfer.import_round(self.store, empty, "r9", fmt, rows)[0]["championship"]["rounds"][0]
        self.assertEqual((rd9["track"], rd9["config"], rd9["date"]), ("Fuji International Speedway", "No Chicane", "2026-10-08"))

    def test_standings_and_roster_csv(self):
        text = transfer.standings_csv(self.league).decode("utf-8-sig")
        self.assertIn("PRO championship", text)
        self.assertIn("Ann Lee", text)
        roster = transfer.drivers_csv(self.league).decode("utf-8-sig")
        self.assertTrue(roster.startswith("Name,Cust ID,Car #"))
        rows = transfer.read((roster + "New Guy,3,12,,Newbie,Green,,AM,,Ford\n").encode())[2]
        profile, info = transfer.import_drivers_csv(self.store, self.league, rows)
        self.assertEqual((info["added"], info["updated"]), (1, 2))
        new = next(d for d in profile["drivers"] if d["cust_id"] == 3)
        self.assertEqual((new["nickname"], new["team"], new["class_id"], new["car_make"]), ("Newbie", "Green", "am", "Ford"))

    def test_overlay_settings_with_backgrounds(self):
        bgs = Backgrounds(self.dir / "bg")
        name = bgs.save(PNG)
        mine = OverlaySettings()
        mine.update("standings", {"bg": "image", "bg_image": name, "rows": 7})
        data = transfer.export_overlays(mine.get(), bgs)
        theirs, their_bgs = OverlaySettings(), Backgrounds(self.dir / "bg2")
        info = transfer.import_overlays(theirs, their_bgs, json.loads(data))
        self.assertGreater(info["sections"], 5)
        self.assertEqual((theirs.get()["standings"]["rows"], theirs.get()["standings"]["bg_image"]), (7, name))
        self.assertTrue(their_bgs.file(name))

    def test_exports_are_named_and_never_overwritten(self):
        a = transfer.save_export(["Sunday Cup", "Teams"], "json", b"{}", folder=self.dir / "out")
        b = transfer.save_export(["Sunday Cup", "Teams"], "json", b"{}", folder=self.dir / "out")
        self.assertRegex(a.name, r"^Sunday Cup - Teams - \d{4}-\d\d-\d\d\.json$")
        self.assertTrue(b.name.endswith(" (2).json"))

    def test_not_an_export(self):
        with self.assertRaises(transfer.TransferError):
            transfer.read(b'{"hello": 1}')
        with self.assertRaises(transfer.TransferError):
            transfer.read(b"")
