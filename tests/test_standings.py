import tempfile
import unittest

from apex.config import DEFAULTS
from apex.core import App, _session_limit
from apex.league import LeagueStore
from apex.sources import MockSource


class StandingsOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = 0.0

    def tearDown(self):
        self.tmp.cleanup()

    def app(self, **mock):
        source = MockSource(seed=4, clock=lambda: self.t, **mock)
        return App(source, dict(DEFAULTS), LeagueStore(self.tmp.name)), source

    def run_for(self, app, seconds):
        for _ in range(int(seconds * 10)):
            self.t += 0.1
            app.tick()

    def test_fastest_lap_holders_and_flash(self):
        app, source = self.app()
        app.command("overlay_settings", {"overlay": "standings", "values": {"fl_flash_s": 1000}})
        for _ in range(400):  # a few laps in, snapshots going out as in the app
            self.run_for(app, 1)
            ov = app.build_snapshot()["overlays"]
        st = ov["standings"]
        best = min(e["best_lap"] for e in st if e["best_lap"])
        holders = [e for e in st if e["fastest"]]
        self.assertEqual([e["best_lap"] for e in holders], [best])  # just the one overall
        for key in {e["class_key"] for e in st}:
            in_class = [e for e in st if e["class_key"] == key and e["best_lap"]]
            if in_class:
                marked = [e for e in in_class if e["class_fastest"]]
                self.assertEqual([e["best_lap"] for e in marked], [min(e["best_lap"] for e in in_class)])
        # A new fastest lap flashes, with its driver and time, for as long as set.
        flash = ov["fastest_flash"]
        self.assertIsNotNone(flash)
        self.assertEqual((flash["car_idx"], flash["lap_time"], flash["scope"]), (holders[0]["car_idx"], best, "overall"))
        app.command("overlay_settings", {"overlay": "standings", "values": {"fl_flash_s": 3}})
        app._fl_flash["at"] -= 4
        self.assertIsNone(app.build_snapshot()["overlays"]["fastest_flash"])
        app.command("overlay_settings", {"overlay": "standings", "values": {"fl_flash": False, "fl_flash_s": 30}})
        app._fl_flash["at"] += 4
        self.assertIsNone(app.build_snapshot()["overlays"]["fastest_flash"])

    def test_laps_set_before_the_app_started_dont_flash(self):
        app, source = self.app()
        self.run_for(app, 300)
        app._fl_session = None  # as if the app had just connected
        self.assertIsNone(app.build_snapshot()["overlays"]["fastest_flash"])

    def test_session_limit(self):
        self.assertEqual(_session_limit("30"), 30)
        self.assertEqual(_session_limit("1200.0000 sec"), 1200)
        self.assertIsNone(_session_limit("unlimited"))

    def test_reveal_fills_in_as_drivers_complete_a_lap(self):
        app, source = self.app(race_laps=5)
        app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": True}})
        self.run_for(app, 30)
        ov = app.build_snapshot()["overlays"]
        self.assertEqual(ov["standings"], [])  # nobody has done a lap: header only
        self.assertEqual((ov["progress"]["mode"], ov["progress"]["lap"], ov["progress"]["laps_total"]), ("laps", 1, 5))
        # Run until the leader has crossed the line but not the whole field.
        for _ in range(3000):
            self.t += 0.1
            app.tick()
            done = sum(1 for n in source.mock_laps if n >= 1)
            if 0 < done < source.num_cars:
                break
        shown = app.build_snapshot()["overlays"]["standings"]
        self.assertTrue(0 < len(shown) < source.num_cars)
        self.assertTrue(all(e["laps_completed"] >= 1 for e in shown))
        self.assertEqual([e["pos"] for e in shown], list(range(1, len(shown) + 1)))
        self.assertEqual(app.build_snapshot()["overlays"]["progress"]["lap"], 2)

    def test_race_start_shows_only_the_header_until_lap_2(self):
        app, source = self.app(race_laps=5)  # reveal is on by default
        real = source.read
        state = {"green": False}

        def read():
            f = real()
            if not state["green"]:
                f.session_state = 3  # pace laps: lap counters may already move
                f.laps_completed = [max(n, 1) for n in f.laps_completed]
            return f

        source.read = read
        self.run_for(app, 30)
        ov = app.build_snapshot()["overlays"]
        self.assertEqual(ov["standings"], [])  # before the green: header only
        self.assertEqual(ov["progress"]["mode"], "laps")
        state["green"] = True
        self.run_for(app, 30)
        self.assertEqual(app.build_snapshot()["overlays"]["standings"], [])  # green, but still on lap 1
        for _ in range(3000):
            self.t += 0.1
            app.tick()
            if any((r or 0) >= 2 for r in app._frame.lap):
                break
        shown = app.build_snapshot()["overlays"]["standings"]
        self.assertTrue(shown)
        lap = {r["car_idx"]: r["lap"] for r in app.build_snapshot()["drivers"]}
        self.assertTrue(all(lap[e["car_idx"]] >= 2 for e in shown))

    def test_without_reveal_the_race_shows_everyone(self):
        app, source = self.app(race_laps=5)
        app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": False}})
        self.run_for(app, 5)
        self.assertEqual(len(app.build_snapshot()["overlays"]["standings"]), source.num_cars)

    def test_qualifying_header_counts_time_down(self):
        app, _ = self.app(session="qualify")
        self.run_for(app, 10)
        pr = app.build_snapshot()["overlays"]["progress"]
        self.assertEqual(pr["mode"], "time")
        self.assertAlmostEqual(pr["time_remain"], 1190, delta=2)

    def test_reveal_in_qualifying_lists_drivers_without_a_time_last(self):
        app, source = self.app(session="qualify")
        app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": True}})
        self.run_for(app, 200)
        source.offtrack_until = [self.t + 1000] * source.num_cars  # every lap from now on is invalid
        shown = app.build_snapshot()["overlays"]["standings"]
        timed = [e for e in shown if e["best"]]
        self.assertEqual(shown[:len(timed)], timed)
        self.assertTrue(all(e["gap"] is None for e in shown[len(timed):]))

    def test_header_choice(self):
        app, _ = self.app(race_laps=5)
        app.command("overlay_settings", {"overlay": "standings", "values": {"header_info": "time"}})
        self.run_for(app, 2)
        self.assertEqual(app.build_snapshot()["overlays"]["progress"]["mode"], "time")


class ClassTagTests(unittest.TestCase):
    def test_strip_class_prefix(self):
        from apex.league import strip_class_prefix
        self.assertEqual(strip_class_prefix("(P) Dave Price"), "Dave Price")
        self.assertEqual(strip_class_prefix("  (PA)Mat Gatter"), "Mat Gatter")
        self.assertEqual(strip_class_prefix("Dave Price"), "Dave Price")
        self.assertEqual(strip_class_prefix("Dave (The Rocket) Price"), "Dave (The Rocket) Price")
        self.assertEqual(strip_class_prefix("(P)"), "(P)")

    def test_saving_fills_nicknames_but_keeps_own_ones(self):
        from apex.league import normalise_profile
        p = normalise_profile({"name": "L", "strip_class_prefix": True, "drivers": [
            {"name": "(P) Dave Price"}, {"name": "(AM) Mat Gatter", "nickname": "Matty"}, {"name": "Ben Gibbons"}]})
        self.assertEqual([d["nickname"] for d in p["drivers"]], ["Dave Price", "Matty", ""])
        self.assertEqual(p["drivers"][0]["name"], "(P) Dave Price")
        off = normalise_profile({"name": "L", "drivers": [{"name": "(P) Dave Price"}]})
        self.assertEqual(off["drivers"][0]["nickname"], "")

    def test_overlays_show_the_clean_name_and_the_panel_keeps_the_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = MockSource(seed=4, clock=lambda: 0.0)
            source.drivers[1]["UserName"] = "(P) Ayrton Vale"
            source.drivers[2]["UserName"] = "(SP) Owen Price"
            app = App(source, dict(DEFAULTS), LeagueStore(tmp))
            app.command("overlay_settings", {"overlay": "standings", "values": {"reveal": False}})  # everyone, from the start
            app.tick()
            from apex.league import profile_from_session
            prof = profile_from_session(app.build_snapshot()["drivers"], "Tagged")
            prof["strip_class_prefix"] = True
            prof = app.leagues.save(prof)
            app.leagues.set_active(prof["id"])
            snap = app.build_snapshot()
            panel = {d["car_idx"]: d["name"] for d in snap["drivers"]}
            stream = {e["car_idx"]: (e["name"], e["nickname"]) for e in snap["overlays"]["standings"]}
            walk = {e["car_idx"]: e["name"] for e in snap["gridwalk"]["entries"]}
            self.assertEqual(panel[1], "(P) Ayrton Vale")
            self.assertEqual(stream[1], ("Ayrton Vale", ""))
            self.assertEqual(walk[2], "Owen Price")
            # Not in the roster at all: still shown without the tag.
            app.leagues.save(dict(prof, drivers=[d for d in prof["drivers"] if d["cust_id"] != 100001]))
            snap = app.build_snapshot()
            self.assertEqual({e["car_idx"]: e["name"] for e in snap["overlays"]["standings"]}[2], "Owen Price")


class ClassFromTagTests(unittest.TestCase):
    CLASSES = [{"id": "pro", "name": "Pro", "match": []}, {"id": "sp", "name": "Semi-Pro", "match": []},
               {"id": "pa", "name": "Pro-Am", "match": []}, {"id": "am", "name": "Am", "match": []},
               {"id": "gold", "name": "Gold", "match": ["GT3"]}]

    def test_tags(self):
        from apex.league import class_for_tag, class_tag
        self.assertEqual(class_tag("(sp) Ben Gibbons"), "SP")
        self.assertIsNone(class_tag("Ben Gibbons"))
        pick = lambda t: (class_for_tag(self.CLASSES, t) or {}).get("id")
        self.assertEqual([pick(t) for t in ("P", "SP", "PA", "AM", "G", "PRO-AM", "X")],
                         ["pro", "sp", "pa", "am", "gold", "pa", None])

    def test_all_seven_tiers(self):
        from apex.league import class_for_tag
        tiers = [{"id": n.lower(), "name": n, "match": []}
                 for n in ("PRO", "SEMI-PRO", "PRO-AM", "AM", "GOLD", "SILVER", "BRONZE")]
        pick = lambda t: (class_for_tag(tiers, t) or {}).get("id")
        self.assertEqual([pick(t) for t in ("P", "SP", "PA", "AM", "G", "S", "B")],
                         ["pro", "semi-pro", "pro-am", "am", "gold", "silver", "bronze"])

    def test_tag_beats_car_class_but_not_an_own_pick(self):
        store = LeagueStore(tempfile.mkdtemp())
        profile = {"classes": self.CLASSES}
        self.assertEqual(store.class_for(None, "GT3", profile, "(SP) Ben Gibbons")["id"], "sp")
        self.assertEqual(store.class_for(None, "GT3", profile, "Ben Gibbons")["id"], "gold")
        self.assertEqual(store.class_for({"class_id": "am"}, "GT3", profile, "(SP) Ben Gibbons")["id"], "am")
        # The session name wins over the roster's: tags change when drivers move class.
        self.assertEqual(store.class_for({"name": "(P) Ben Gibbons"}, "GT3", profile, "(PA) Ben Gibbons")["id"], "pa")
