import tempfile
import unittest

from apex import boards, championship as ch
from apex.config import DEFAULTS
from apex.core import App, CommandError
from apex.league import LeagueStore, normalise_profile
from apex.makes import catalogue, logo_for, make_for, slug
from apex.overlays import normalise as overlay_settings
from apex.sources import MockSource
from apex.tracks import TrackCatalogue


def res(driver, pos, cls, start=None, make="", laps=10, fl=None):
    return {"driver": driver, "name": driver.upper(), "class_id": cls, "position": pos, "start_position": start or pos,
            "laps": laps, "laps_led": 0, "fastest_lap": fl, "incidents": 0, "status": "finished", "make": make}


def league(**extra):
    return normalise_profile({
        "id": "lg", "name": "League", "strip_class_prefix": True,
        "classes": [{"id": "pro", "name": "PRO", "color": "#ff0000"}, {"id": "am", "name": "AM", "color": "#00ff00"}],
        "drivers": [{"cust_id": i, "name": f"({t}) Driver {i}", "car_number": str(i), "team": "Red" if i % 2 else "Blue",
                     "car_make": m} for i, t, m in ((1, "P", "Porsche"), (2, "P", "BMW"), (3, "AM", "Porsche"), (4, "AM", "BMW"))],
        "championship": {"rules": {"points": [10, 6, 4, 3], "scoring": "both", "classified_pct": 0}, "rounds": [
            {"id": "r1", "name": "Opener", "track": "Road Atlanta", "config": "Full Course", "date": "2026-11-01",
             "results": [res("cust:1", 1, "pro", start=2, fl=80.0), res("cust:3", 2, "am", start=1),
                         res("cust:2", 3, "pro", start=3), res("cust:4", 4, "am", start=4)]},
            {"id": "r2", "name": "Finale", "track": "Spa"}]},
        **extra,
    })


class MakesTests(unittest.TestCase):
    def test_make_from_car_names(self):
        self.assertEqual(make_for("Porsche 911 GT3 R (992)", "porsche992rgt3"), "Porsche")
        self.assertEqual(make_for("Corvette C8.R GTE"), "Chevrolet")
        self.assertEqual(make_for("FIA F4", "formulaf4"), "Tatuus")
        self.assertEqual(make_for("Something Unknown"), "")
        self.assertEqual(slug("Mercedes-AMG"), "mercedes-amg")

    def test_badges_ship_with_the_app(self):
        self.assertEqual(logo_for("Aston Martin"), "/makes/aston-martin.png")
        self.assertIsNone(logo_for("Skip Barber"))
        self.assertGreaterEqual(sum(1 for m in catalogue() if m["logo"]), 37)


class BannerTests(unittest.TestCase):
    def test_banners_are_saved_and_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LeagueStore(tmp)
            p = store.save({"name": "B"})
            png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
            p = store.save_image(p["id"], "banner:vertical", png)
            self.assertEqual(p["banners"][0]["orientation"], "vertical")
            again = store.get(p["id"])
            self.assertTrue(store.logo_file(p["id"], again["banners"][0]["file"]))


class TrackTests(unittest.TestCase):
    def test_builtin_list_and_layouts(self):
        tracks = TrackCatalogue()
        spa = next(g for g in tracks.grouped() if g["track"].startswith("Circuit de Spa"))
        self.assertIn("Endurance", [c["config"] for c in spa["configs"]])
        self.assertTrue(tracks.search("watkins boot"))

    def test_seen_tracks_are_remembered(self):
        with tempfile.TemporaryDirectory() as tmp:
            TrackCatalogue(f"{tmp}/t.json").remember(999, "Mock Raceway", "Grand Prix")
            hits = TrackCatalogue(f"{tmp}/t.json").search("mock raceway")
            self.assertEqual((hits[0]["id"], hits[0]["config"]), (999, "Grand Prix"))

    def test_official_list_needs_credentials(self):
        with self.assertRaises(ValueError):
            TrackCatalogue().refresh("now")


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.settings = overlay_settings({})

    def board(self, kind, group="", round=""):
        return boards.build(league(), {"kind": kind, "params": {"group": group, "round": round}}, self.settings)

    def test_championship_board(self):
        b = self.board("championship", "pro")
        self.assertEqual(b["subtitle"], "PRO")
        self.assertEqual([r["name"] for r in b["rows"]], ["Driver 1", "Driver 2"])  # class tag gone
        self.assertEqual(b["rows"][0]["make"], "Porsche")
        self.assertEqual(b["rows"][0]["class_color"], "#ff0000")
        # Driver 1 has 10, Driver 2 has 6 in PRO: 4 behind the leader and the car ahead.
        self.assertEqual((b["rows"][1]["behind"], b["rows"][1]["ahead"]), (4, 4))
        self.assertNotIn("ahead", b["rows"][0])

    def test_makes_board(self):
        rows = self.board("makes", "overall")["rows"]
        # Porsche: 10 + 6 overall; BMW: 4 + 3.
        self.assertEqual([(r["make"], r["points"]) for r in rows], [("Porsche", 16), ("BMW", 7)])

    def test_results_board_counts_places_within_the_class(self):
        b = self.board("results", "am")
        self.assertEqual([r["name"] for r in b["rows"]], ["Driver 3", "Driver 4"])
        self.assertEqual(b["rows"][0]["gained"], 0)  # started 1st of the AM cars, finished 1st
        self.assertEqual(b["title"], "Opener result")

    def test_calendar_board(self):
        rows = self.board("calendar")["rows"]
        self.assertTrue(rows[0]["done"] and rows[1]["next"])
        self.assertEqual(rows[0]["winners"][0]["group_name"], "Overall")
        self.assertEqual(rows[0]["winners"][0]["name"], "Driver 1")

    def test_teams_board(self):
        settings = overlay_settings({"board_teams": {"rounds": 2, "show_ahead": True}})
        b = boards.build(league(teams=[{"name": "Red", "color": "#ff0000"}]), {"kind": "teams", "params": {}}, settings)
        # Overall points (10, 6, 4, 3): Red = drivers 1 and 3, Blue = 2 and 4.
        self.assertEqual([(r["team"], r["points"], r["behind"], r["ahead"], r["wins"]) for r in b["rows"]],
                         [("Red", 16, 0, None, 1), ("Blue", 7, 9, 9, 0)])
        self.assertEqual(b["rows"][0]["drivers"], ["Driver 1", "Driver 3"])  # stream names, best scorer first
        self.assertEqual(b["rows"][0]["color"], "#ff0000")
        self.assertEqual((b["round_names"], b["rows"][0]["rounds"]), (["R1"], [16]))
        self.assertTrue(boards.options(league())["has_teams"])

    def test_sponsors(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LeagueStore(tmp)
            p = store.save({"name": "S"})
            png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
            p = store.save_image(p["id"], "sponsor:Acme Oil", png)
            p = store.save_image(p["id"], "sponsor:Brake Co", png + b"1")
            self.assertEqual([s["name"] for s in p["sponsors"]], ["Acme Oil", "Brake Co"])
            self.assertTrue(store.logo_file(p["id"], p["sponsors"][1]["file"]))
            first = p["sponsors"][0]["id"]
            self.assertEqual([s["name"] for s in boards.sponsors(p, first)], ["Acme Oil"])
            self.assertEqual(boards.sponsors(p, "none"), [])
        lg = league(sponsors=[{"id": "a1", "file": "sponsor-1.png", "name": "Acme"}, {"id": "b2", "file": "sponsor-2.png"}])
        settings = overlay_settings({"board_championship": {"sponsors": "bottom", "sponsor_ids": "b2"}})
        b = boards.build(lg, {"kind": "championship", "params": {}}, settings)
        self.assertEqual(b["sponsors"], {"place": "bottom", "logos": [{"id": "b2", "name": "", "url": "/api/logos/lg/sponsor-2.png"}]})
        self.assertIsNone(boards.build(lg, {"kind": "teams", "params": {}}, settings)["sponsors"])  # off by default

    def test_options_and_banner(self):
        opts = boards.options(league())
        self.assertEqual([g["name"] for g in opts["groups"]], ["Overall", "PRO", "AM"])
        lg = league(banners=[{"id": "b1", "file": "banner-horizontal-1.png", "orientation": "horizontal"},
                             {"id": "b2", "file": "banner-vertical-2.png", "orientation": "vertical"}],
                    logo="league-logo-1.png", calendar_image="league-calendar-image-1.png")
        settings = overlay_settings({"board_teams": {"banner": "right"}, "board_calendar": {"style": "image"}})
        b = boards.build(lg, {"kind": "teams", "params": {}}, settings)
        self.assertEqual((b["banner"]["place"], b["banner"]["orientation"]), ("right", "vertical"))
        self.assertEqual(b["league_logo"], "/api/logos/lg/league-logo-1.png")
        self.assertIsNone(self.board("teams")["banner"])  # off by default
        cal = boards.build(lg, {"kind": "calendar", "params": {}}, settings)
        self.assertEqual(cal["image"], "/api/logos/lg/league-calendar-image-1.png")
        self.assertTrue(cal["rows"])  # the rounds are still there for everything else

    def test_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(MockSource(seed=1, clock=lambda: 0.0), dict(DEFAULTS), LeagueStore(tmp))
            with self.assertRaises(CommandError):
                app.command("board_show", {"kind": "calendar"})  # no league yet
            app.leagues.save(league())
            app.leagues.set_active("lg")
            app.command("board_show", {"kind": "championship", "group": "overall"})
            snap = app.build_snapshot()
            self.assertEqual(snap["board"]["kind"], "championship")
            self.assertEqual(len(snap["board_options"]["groups"]), 3)
            app.command("board_hide", {})
            self.assertIsNone(app.build_snapshot()["board"])
            # Pop-outs: in the app window they open there; otherwise the page opens one itself.
            self.assertEqual(app.command("popout", {"page": "boards"}), {"opened": False})
            opened = []
            app.popout = lambda page, name: opened.append((page, name)) or True
            self.assertEqual(app.command("popout", {"page": "timing"}), {"opened": True})
            self.assertEqual(opened, [("timing", "Timing")])
            with self.assertRaises(CommandError):
                app.command("popout", {"page": "league"})

    def test_overlays_on_the_users_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(MockSource(seed=1, clock=lambda: 0.0), dict(DEFAULTS), LeagueStore(tmp))
            self.assertFalse(app.build_snapshot()["desktop"]["available"])
            with self.assertRaises(CommandError):  # in a browser: no app window to do it from
                app.command("desktop_show", {"page": "standings"})

            class Fake:
                def __init__(self):
                    self.up = {}
                    self.urls = []

                def screens(self):
                    return [{"index": 0, "width": 2560, "height": 1440, "x": 0, "y": 0},
                            {"index": 1, "width": 1920, "height": 1080, "x": 2560, "y": 0}]

                def show(self, page, path, name, screen):
                    self.up[page] = screen
                    self.urls.append(path)
                    return True

                def hide(self, page=None):
                    self.up = {} if page is None else {k: v for k, v in self.up.items() if k != page}

                def on_screen(self):
                    return dict(self.up)

            app.desktop = fake = Fake()
            app.command("desktop_show", {"page": "standings", "screen": 1})
            app.command("desktop_show", {"page": "board"})
            self.assertEqual(fake.urls, ["/standings.html?desktop=standings", "/board.html?desktop=board"])
            d = app.build_snapshot()["desktop"]
            self.assertEqual((d["available"], d["on_screen"], len(d["screens"])), (True, {"standings": 1, "board": 0}, 2))
            app.command("desktop_show", {"page": "standings_screen"})
            self.assertEqual(fake.urls[-1], "/standings.html?screen=1&desktop=standings_screen")
            app.command("desktop_hide", {"page": "board"})
            self.assertNotIn("board", app.build_snapshot()["desktop"]["on_screen"])
            app.command("desktop_hide", {})
            self.assertEqual(app.build_snapshot()["desktop"]["on_screen"], {})
            with self.assertRaises(CommandError):
                app.command("desktop_show", {"page": "index"})

    def test_round_keeps_calendar_fields(self):
        rd = ch.normalise({"rounds": [{"track": "Spa", "config": "Endurance", "time": "19:30", "length": "90 min"}]})["rounds"][0]
        self.assertEqual((rd["config"], rd["time"], rd["length"]), ("Endurance", "19:30", "90 min"))


class BackgroundTests(unittest.TestCase):
    def test_uploaded_backgrounds(self):
        from apex.backgrounds import Backgrounds
        from apex.league import LeagueError

        with tempfile.TemporaryDirectory() as tmp:
            store = Backgrounds(tmp)
            png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
            name = store.save(png)
            self.assertRegex(name, r"^bg-[0-9a-f]{12}\.png$")
            self.assertEqual(store.save(png), name)  # the same image once
            self.assertEqual(store.list(), [name])
            self.assertIsNotNone(store.file(name))
            self.assertIsNone(store.file("../" + name))
            with self.assertRaises(LeagueError):
                store.save(b"not an image")

    def test_every_overlay_and_board_has_a_background(self):
        settings = overlay_settings({
            "board_results": {"bg": "image", "bg_image": "bg-0123456789ab.jpg", "bg_opacity": 40},
            "laps": {"bg": "color", "bg_color": "#FF8800", "bg_opacity": 250},
            "sponsors": {"bg": "image", "bg_image": "../../secret.png"},
            "gridwalk": {"bg": "sparkles"},
        })
        for section in ("standings", "laps", "sponsors", "gridwalk", "board_championship", "board_teams",
                        "board_makes", "board_calendar", "board_results"):
            self.assertIn("bg", settings[section], section)
        self.assertEqual({k: settings["board_results"][k] for k in ("bg", "bg_image", "bg_opacity")},
                         {"bg": "image", "bg_image": "bg-0123456789ab.jpg", "bg_opacity": 40})
        self.assertEqual((settings["laps"]["bg_color"], settings["laps"]["bg_opacity"]), ("#ff8800", 100))
        self.assertEqual(settings["sponsors"]["bg_image"], "")  # not one of ours
        self.assertEqual(settings["gridwalk"]["bg"], "default")
        # Size: every overlay and board, 50-200 %.
        sized = overlay_settings({"standings": {"scale": 140}, "driver": {"scale": 10}, "board_teams": {"scale": 900}})
        self.assertEqual((sized["standings"]["scale"], sized["driver"]["scale"], sized["board_teams"]["scale"],
                          sized["laps"]["scale"]), (140, 50, 200, 100))
        # The board on screen carries its background settings to the page.
        b = boards.build(league(), {"kind": "results", "params": {}}, settings)
        self.assertEqual(b["settings"]["bg_opacity"], 40)
