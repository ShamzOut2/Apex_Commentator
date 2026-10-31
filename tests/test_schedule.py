import json
import tempfile
import threading
import unittest
import urllib.request
from datetime import date, timezone

from apex import boards, championship, ocr, schedule
from apex.server import make_server
from apex.tracks import TrackCatalogue
from tests.test_app import make_app

TRACKS = TrackCatalogue().grouped()
TODAY = date(2026, 10, 31)


def found(rounds):
    return [(r["track"], r["config"], r["date"], r["time"], r["length"]) for r in rounds]


def piece(text, x, y, w, h=20):
    return {"text": text, "x": x, "y": y, "w": w, "h": h}


class TrackTests(unittest.TestCase):
    def setUp(self):
        self.m = schedule.TrackMatcher(TRACKS)

    def test_names_nicknames_and_layouts(self):
        self.assertEqual(self.m.find("SPA-FRANCORCHAMPS")["track"], "Circuit de Spa-Francorchamps")
        self.assertEqual(self.m.find("Imola")["track"], "Autodromo Internazionale Enzo e Dino Ferrari")
        self.assertEqual(self.m.find("COTA")["track"], "Circuit of the Americas")
        # The longer nickname wins: Petit Le Mans is at Road Atlanta.
        self.assertEqual(self.m.find("PETIT LE MANS")["track"], "Road Atlanta")
        self.assertEqual(self.m.find("Le Mans")["track"], "Circuit des 24 Heures du Mans")
        # Road Atlanta, not Atlanta Motor Speedway; but plain Atlanta is the speedway.
        self.assertEqual(self.m.find("Road Atlanta")["track"], "Road Atlanta")
        self.assertEqual(self.m.find("Atlanta")["track"], "Atlanta Motor Speedway")
        self.assertEqual(self.m.find("Silverstone GP")["config"], "Grand Prix")
        self.assertEqual(self.m.find("Watkins Glen Boot")["config"], "Boot")
        # A slightly misread name still matches; generic words alone don't.
        self.assertEqual(self.m.find("Nurburgring Nordschliefe")["track"], "Nürburgring Nordschleife")
        self.assertIsNone(self.m.find("Road Course"))
        self.assertIsNone(self.m.find("Season 4 Calendar"))


class DetailTests(unittest.TestCase):
    def test_dates(self):
        d = lambda t, df=True: schedule.find_date(t, df)[:2] if schedule.find_date(t, df) else None  # noqa: E731
        self.assertEqual(d("Sun 8th November 2026"), (date(2026, 11, 8), True))
        self.assertEqual(d("15/11/26"), (date(2026, 11, 15), True))
        self.assertEqual(d("11/15/2026", False), (date(2026, 11, 15), True))
        self.assertEqual(d("Nov 22"), (date(2000, 11, 22), False))
        self.assertEqual(d("2026-12-06"), (date(2026, 12, 6), True))
        self.assertIsNone(d("19.30"))
        self.assertTrue(schedule.numeric_order(["1/24 7pm"]) is False)
        self.assertTrue(schedule.numeric_order(["24/1"]))

    def test_times_and_lengths(self):
        self.assertEqual(schedule.find_time("8PM GMT"), "20:00")
        self.assertEqual(schedule.find_time("7:30pm"), "19:30")
        self.assertEqual(schedule.find_time("12am"), "00:00")
        self.assertEqual(schedule.find_time("19.30"), "19:30")
        self.assertEqual(schedule.find_length("45 MINS"), "45 min")
        self.assertEqual(schedule.find_length("2 HOURS"), "2 h")
        self.assertEqual(schedule.find_length("1h30"), "90 min")
        self.assertEqual(schedule.find_length("30 laps"), "30 laps")


class CalendarTests(unittest.TestCase):
    def test_a_line_a_round(self):
        text = """GT3 Winter Championship 2026
Round 1 - Spa-Francorchamps - Sun 8th November - 8PM GMT - 60 min
Round 2 - Monza - 15/11/26 - 20:00 - 45 mins
Round 3 - Road Atlanta Full Course - Nov 22 - 7:30pm - 30 laps"""
        rounds = schedule.rounds_from_text(text, TRACKS, today=TODAY)
        self.assertEqual(found(rounds), [
            ("Circuit de Spa-Francorchamps", "", "2026-11-08", "20:00", "60 min"),
            ("Autodromo Nazionale Monza", "", "2026-11-15", "20:00", "45 min"),
            ("Road Atlanta", "Full Course", "2026-11-22", "19:30", "30 laps"),
        ])
        self.assertEqual([r["name"] for r in rounds], ["Round 1", "Round 2", "Round 3"])

    def test_blocks_and_month_first_dates(self):
        cards = "ROUND 1\nSILVERSTONE GP\nSUNDAY 10TH JANUARY\n8PM\n\nROUND 2\nLe Mans\n24 Jan\n8PM"
        self.assertEqual(found(schedule.rounds_from_text(cards, TRACKS, today=TODAY)), [
            ("Silverstone Circuit", "Grand Prix", "2027-01-10", "20:00", ""),  # no year: the coming January
            ("Circuit des 24 Heures du Mans", "", "2027-01-24", "20:00", ""),  # no layout named
        ])
        us = "Week 1: Daytona Road Course 1/10 7pm\nWeek 2: Watkins Glen 1/24 7pm"
        self.assertEqual([r["date"] for r in schedule.rounds_from_text(us, TRACKS, today=TODAY)], ["2027-01-10", "2027-01-24"])

    def test_a_scanned_table(self):
        # A table read column by column: each row's details stay with its track.
        pieces = [piece("TRACK", 138, 176, 93), piece("DATE", 495, 177, 70)]
        for i, (track, day, length) in enumerate((("Brands Hatch Indy", "8th", "45 MINS"), ("Zandvoort", "15th", "60 MINS"),
                                                  ("Watkins Glen", "22nd", "2 HOURS"))):
            y = 210 + 34 * i
            pieces += [piece(track, 138, y, 90 + 40 * (i % 2 == 0)), piece(f"Sun {day} Nov", 495, y, 160),
                       piece("8PM GMT", 770, y, 126), piece(length, 968, y, 107)]
        self.assertEqual(found(schedule.rounds_from_pieces(pieces, TRACKS, today=TODAY)), [
            ("Brands Hatch Circuit", "Indy", "2026-11-08", "20:00", "45 min"),
            ("Circuit Park Zandvoort", "", "2026-11-15", "20:00", "60 min"),
            ("Watkins Glen International", "", "2026-11-22", "20:00", "2 h"),
        ])

    def test_scanned_cards(self):
        # Cards side by side; a name over two lines; a track the list doesn't know.
        pieces = []
        for col, (num, lines, when) in enumerate((("1", ["DAYTONA"], "Saturday 16 January"),
                                                  ("2", ["HIDDEN VALLEY"], "Saturday 13 February"),
                                                  ("3", ["SPA-", "FRANCORCHAMPS"], "Saturday 13 March"))):
            x, y = 66 + 490 * col, 174
            pieces.append(piece(f"ROUND {num}", x, y, 114, 18))
            for line in lines:
                y += 40
                pieces.append(piece(line, x, y, 180, 29))
            pieces += [piece(when, x, y + 40, 220, 23), piece("6 Hours - 18:00", x, y + 70, 163, 17)]
        rounds = schedule.rounds_from_pieces(pieces, TRACKS, today=TODAY)
        self.assertEqual(found(rounds), [
            ("Daytona International Speedway", "", "2027-01-16", "18:00", "6 h"),
            ("Hidden Valley", "", "2027-02-13", "18:00", "6 h"),
            ("Circuit de Spa-Francorchamps", "", "2027-03-13", "18:00", "6 h"),
        ])
        self.assertEqual([r["unknown_track"] for r in rounds], [False, True, False])
        self.assertEqual([r["name"] for r in rounds], ["Round 1", "Round 2", "Round 3"])

    def test_ocr_lines_split_at_wide_gaps(self):
        words = [{"text": t, "x": x, "y": 10, "w": w, "h": 20} for t, x, w in
                 (("Brands", 0, 60), ("Hatch", 66, 50), ("Sun", 400, 30), ("8", 436, 10), ("Nov", 452, 30))]
        self.assertEqual([p["text"] for p in ocr.pieces([words])], ["Brands Hatch", "Sun 8 Nov"])

    def test_iracing_season(self):
        sessions = [
            {"launch_at": "2026-11-08T20:00:00Z", "session_name": "", "race_laps": 0, "race_length": 120,
             "track": {"track_name": "Circuit de Spa-Francorchamps", "config_name": "Endurance", "track_id": 163}},
            {"launch_at": "2026-11-01T19:30:00Z", "session_name": "Season opener", "race_laps": 25,
             "track": {"track_name": "Autodromo Nazionale Monza", "config_name": "Grand Prix"}},
        ]
        rounds = schedule.rounds_from_iracing(sessions, timezone.utc)
        self.assertEqual([(r["name"], r["date"], r["time"], r["length"], r["config"]) for r in rounds], [
            ("Season opener", "2026-11-01", "19:30", "25 laps", "Grand Prix"),
            ("Round 2", "2026-11-08", "20:00", "2 h", "Endurance"),
        ])

    def test_races_per_event(self):
        rounds = schedule.races_per_event([{"name": "Spa night", "track": "Spa"}], 3, "Heat")
        self.assertEqual([(r["event"], r["name"]) for r in rounds], [("Spa night", f"Heat {k}") for k in (1, 2, 3)])


class MeetingTests(unittest.TestCase):
    def test_calendar_board_shows_a_meeting_once(self):
        champ = {"rounds": [
            {"id": "a", "name": "Round 1", "track": "Monza"},
            {"id": "b", "event": "Spa night", "name": "Heat 1", "track": "Spa", "results": [
                {"driver": "x", "name": "X", "position": 1, "laps": 10}]},
            {"id": "c", "event": "Spa night", "name": "Heat 2", "track": "Spa"},
        ]}
        cal = championship.calendar({"name": "L", "drivers": [], "classes": [],
                                     "championship": championship.normalise(champ)})
        self.assertEqual([r["event"] for r in cal], ["", "Spa night", "Spa night"])
        rows = boards.meetings(cal)
        self.assertEqual([(r["name"], r["round"], r["last"], r["races"], r["done"]) for r in rows], [
            ("Round 1", 1, None, ["Round 1"], False), ("Spa night", 2, 3, ["Heat 1", "Heat 2"], False)])
        self.assertEqual([(w["race"], w["name"]) for w in rows[1]["winners"]], [("Heat 1", "X")])


class MeetingImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, cls.source = make_app(cls.tmp.name, minutes=1)
        cls.server = make_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.app.stop()
        cls.server.shutdown()
        cls.tmp.cleanup()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def test_every_race_of_the_event(self):
        app = self.app
        cars = sorted(app._drivers)[:3]
        with app._lock:
            sessions = app._session_meta["sessions"]
            sessions[0]["SessionName"] = "HEAT 1"
            # A second heat, already run: only iRacing's results are left of it.
            sessions[1] = {"SessionType": "Race", "SessionName": "HEAT 2", "ResultsPositions": [
                {"Position": i + 1, "CarIdx": car, "LapsComplete": 8, "LapsLed": 8 if i == 0 else 0,
                 "FastestTime": 90.5 + i, "Incidents": i, "ReasonOutStr": "Running"} for i, car in enumerate(cars)]}
        self.assertEqual([(r["num"], r["name"]) for r in app.race_sessions()], [(0, "HEAT 1"), (1, "HEAT 2")])
        league = app.leagues.save({"name": "Heats", "championship": {"rounds": [
            {"id": "h1", "event": "Night 1", "name": "Heat 1"}, {"id": "h2", "event": "Night 1", "name": "Heat 2"}]}})
        r = self.post(f"/api/leagues/{league['id']}/championship/import-meeting", {"round_ids": ["h1", "h2"]})
        self.assertEqual([(x["race"], x["round"]) for x in r["imported"]], [("HEAT 1", "Heat 1"), ("HEAT 2", "Heat 2")])
        h1, h2 = r["league"]["championship"]["rounds"]
        self.assertEqual(len(h1["results"]), len(app._drivers))
        sub = app._session_meta["subsession"]
        self.assertEqual((h1["session"], h2["session"]), (f"{sub}:0", f"{sub}:1"))
        self.assertEqual([(x["position"], x["laps"], x["fastest_lap"], x["status"]) for x in h2["results"]],
                         [(i + 1, 8, 90.5 + i, "finished") for i in range(3)])
        self.assertEqual(h2["results"][0]["laps_led"], 8)


if __name__ == "__main__":
    unittest.main()
