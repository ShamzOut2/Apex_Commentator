import json
import tempfile
import unittest

from apex import championship as ch
from apex.league import LeagueStore, normalise_profile, profile_from_session
from tests.test_app import make_app


def res(driver, pos, cls="", start=None, laps=20, led=0, fl=None, inc=1, status="finished", adjust=0):
    return {"driver": driver, "name": driver.upper(), "class_id": cls, "position": pos, "start_position": start or pos,
            "laps": laps, "laps_led": led, "fastest_lap": fl, "incidents": inc, "status": status, "adjust": adjust}


def profile(rules=None, rounds=(), penalties=(), classes=(), drivers=()):
    return normalise_profile({
        "name": "L", "classes": list(classes), "drivers": list(drivers),
        "championship": {"rules": rules or {}, "rounds": list(rounds), "penalties": list(penalties)},
    })


def table(p, live=None):
    st = ch.standings(p, live)
    return {r["driver"]: r for g in st["groups"] for r in g["drivers"]}, st


class RulesTests(unittest.TestCase):
    def test_parse_points(self):
        self.assertEqual(ch.parse_points("25, 18 15;12"), [25, 18, 15, 12])
        self.assertEqual(ch.parse_points(["3", "x", -1, 0.5]), [3, 0, 0.5])

    def test_defaults(self):
        rules = ch.normalise({})["rules"]
        self.assertEqual(rules["points"][:3], [25, 18, 15])
        self.assertEqual(set(rules["bonuses"]), set(ch.BONUS_KEYS))


class ScoringTests(unittest.TestCase):
    def test_position_points_and_bonuses(self):
        rules = {"points": [10, 6, 4], "bonuses": {"pole": 1, "fastest_lap": 2, "led_lap": 1, "most_laps_led": 3,
                                                   "clean_race": 1, "most_places_gained": 2}}
        p = profile(rules, [{"id": "r1", "results": [
            res("a", 1, start=2, led=5, fl=90.5, inc=0),
            res("b", 2, start=1, led=15, fl=90.1),
            res("c", 3, start=3, inc=2),
        ]}])
        rows, _ = table(p)
        # a: 10 + led 1 + clean 1 + gained 1 place (most) 2
        self.assertEqual(rows["a"]["points"], 14)
        # b: 6 + pole 1 + fastest lap 2 + led 1 + most led 3
        self.assertEqual(rows["b"]["points"], 13)
        self.assertEqual(rows["c"]["points"], 4)
        self.assertEqual([rows[d]["pos"] for d in "abc"], [1, 2, 3])

    def test_fastest_lap_only_in_top_n(self):
        rules = {"points": [1, 1, 1], "bonuses": {"fastest_lap": 5}, "fastest_lap_top": 2}
        p = profile(rules, [{"id": "r1", "results": [res("a", 1, fl=91), res("b", 2, fl=92), res("c", 3, fl=89)]}])
        rows, _ = table(p)
        self.assertEqual((rows["a"]["points"], rows["c"]["points"]), (6, 1))

    def test_dsq_dnf_and_classification(self):
        rules = {"points": [10, 8, 6, 4], "classified_pct": 75, "dnf_scores": True}
        p = profile(rules, [{"id": "r1", "results": [
            res("a", 1, status="dsq"), res("b", 2), res("c", 3, status="dnf", laps=18), res("d", 4, status="dnf", laps=5),
        ]}])
        rows, _ = table(p)
        # a is disqualified: b wins; c is classified (18/20 laps); d isn't.
        self.assertEqual([rows[d]["points"] for d in "abcd"], [0, 10, 8, 0])

    def test_race_distance_is_per_class(self):
        rules = {"points": [10, 8], "classified_pct": 75}
        p = profile(rules, [{"id": "r1", "results": [
            res("a", 1, "pro", laps=20), res("b", 2, "pro", laps=14),
            res("c", 3, "am", laps=16), res("d", 4, "am", laps=12),
        ]}])
        rows, _ = table(p)
        # b did 14/20 (70%): DNF, no points. d did 12/16 (75%): classified.
        self.assertEqual([rows[d]["points"] for d in "abcd"], [10, 0, 10, 8])
        result = rows["b"]["rounds"][0]["result"]
        self.assertEqual((result["status"], result["short"]), ("dnf", True))
        results = [ch.normalise_result(res("b", 2, "pro", laps=14)), ch.normalise_result(res("a", 1, "pro", laps=20))]
        self.assertEqual([r["status"] for r in ch.apply_distance_rule(results, ch.normalise_rules(rules))],
                         ["dnf", "finished"])

    def test_provisional_round_skips_distance_rule(self):
        p = profile({"points": [10, 8], "classified_pct": 75}, [])
        live = {"id": "r1", "name": "R1", "track": "", "date": "", "multiplier": 1, "no_drop": False, "provisional": True,
                "results": [ch.normalise_result(res("a", 1, laps=2)), ch.normalise_result(res("b", 2, laps=1))]}
        rows = {r["driver"]: r for g in ch.projection(p, live) for r in g["drivers"]}
        self.assertEqual(rows["b"]["points"], 8)

    def test_both_scores_class_and_overall_separately(self):
        classes = [{"id": "pro", "name": "Pro", "color": "#ff0000"}, {"id": "am", "name": "Am", "color": "#0000ff"}]
        rules = {"points": [10, 5], "overall_points": [20, 15, 10, 5], "scoring": "both"}
        p = profile(rules, [{"id": "r1", "results": [
            res("a", 1, "pro"), res("b", 2, "am"), res("c", 3, "pro"), res("d", 4, "am")]}], classes=classes)
        st = ch.standings(p)
        self.assertEqual([g["name"] for g in st["groups"]], ["Overall", "Pro", "Am"])
        pts = {g["name"]: {r["driver"]: r["points"] for r in g["drivers"]} for g in st["groups"]}
        self.assertEqual(pts["Overall"], {"a": 20, "b": 15, "c": 10, "d": 5})
        self.assertEqual(pts["Pro"], {"a": 10, "c": 5})
        self.assertEqual(pts["Am"], {"b": 10, "d": 5})

    def test_live_round_skips_an_imported_race(self):
        champ = ch.normalise({"rounds": [{"id": "r1", "session": "123:2", "results": [res("a", 1)]}, {"id": "r2"}]})
        self.assertIsNone(ch.live_round_for(champ, "123:2"))
        self.assertEqual(ch.live_round_for(champ, "999:2")["id"], "r2")

    def test_old_saves_without_new_rules_still_score(self):
        p = {"name": "Old", "drivers": [], "classes": [], "championship": {
            "rules": {"points": [5]}, "rounds": [{"id": "r1", "results": [res("a", 1)]}], "penalties": []}}
        self.assertEqual(ch.standings(p)["groups"][0]["drivers"][0]["points"], 5)

    def test_dnf_doesnt_score_when_off(self):
        p = profile({"points": [10, 8], "dnf_scores": False},
                    [{"id": "r1", "results": [res("a", 1), res("b", 2, status="dnf")]}])
        self.assertEqual(table(p)[0]["b"]["points"], 0)

    def test_classes_score_separately(self):
        classes = [{"id": "pro", "name": "Pro", "color": "#ff0000"}, {"id": "am", "name": "Am", "color": "#0000ff"}]
        p = profile({"points": [10, 5]}, [{"id": "r1", "results": [
            res("a", 1, "pro"), res("b", 2, "am"), res("c", 3, "pro"), res("d", 4, "am")]}], classes=classes)
        rows, st = table(p)
        self.assertEqual([g["name"] for g in st["groups"]], ["Pro", "Am"])
        self.assertEqual([rows[d]["points"] for d in "abcd"], [10, 10, 5, 5])
        overall = profile({"points": [10, 5], "scoring": "overall"}, p["championship"]["rounds"], classes=classes)
        rows, st = table(overall)
        self.assertEqual(len(st["groups"]), 1)
        self.assertEqual([rows[d]["points"] for d in "abcd"], [10, 5, 0, 0])

    def test_drop_rounds_multiplier_and_no_drop(self):
        rules = {"points": [10, 5], "drop_rounds": 1}
        rounds = [
            {"id": "r1", "results": [res("a", 1), res("b", 2)]},
            {"id": "r2", "results": [res("a", 2), res("b", 1)]},
            {"id": "r3", "multiplier": 2, "no_drop": True, "results": [res("b", 1)]},
        ]
        rows, _ = table(profile(rules, rounds))
        # a: 10, 5, missed r3 (can't drop it) -> drops the 5 -> 10
        self.assertEqual(rows["a"]["points"], 10)
        self.assertEqual(rows["a"]["gross"], 15)
        # b: 5, 10, 20 -> drops the 5 -> 30
        self.assertEqual(rows["b"]["points"], 30)
        dropped = [s["round"] for s in rows["b"]["rounds"] if s["dropped"]]
        self.assertEqual(dropped, ["r1"])

    def test_drops_wait_until_there_are_more_rounds(self):
        rows, _ = table(profile({"points": [10, 5], "drop_rounds": 2}, [{"id": "r1", "results": [res("a", 1)]}]))
        self.assertEqual(rows["a"]["points"], 10)

    def test_penalties_and_adjustments(self):
        p = profile({"points": [10, 8]}, [{"id": "r1", "results": [res("a", 1, adjust=-2), res("b", 2)]}],
                    penalties=[{"driver": "b", "round_id": "r1", "points": 3, "licence": 2, "reason": "Avoidable contact"}])
        rows, _ = table(p)
        self.assertEqual(rows["a"]["points"], 8)
        self.assertEqual(rows["b"]["points"], 5)
        self.assertEqual(rows["b"]["licence_points"], 2)

    def test_tie_broken_on_countback(self):
        p = profile({"points": [10, 10]}, [{"id": "r1", "results": [res("a", 2), res("b", 1)]}])
        st = ch.standings(p)
        self.assertEqual([r["driver"] for r in st["groups"][0]["drivers"]], ["b", "a"])

    def test_team_championship(self):
        drivers = [{"cust_id": 1, "name": "A", "team": "Red"}, {"cust_id": 2, "name": "B", "team": "Red"},
                   {"cust_id": 3, "name": "C", "team": "Blue"}]
        rounds = [{"id": "r1", "results": [res("cust:1", 1), res("cust:3", 2), res("cust:2", 3)]}]
        teams = ch.standings(profile({"points": [10, 6, 4], "team_best": 1}, rounds, drivers=drivers))["teams"]
        self.assertEqual([(t["team"], t["points"]) for t in teams], [("Red", 10), ("Blue", 6)])

    def test_live_projection(self):
        p = profile({"points": [10, 5]}, [{"id": "r1", "results": [res("a", 1), res("b", 2)]}, {"id": "r2"}])
        live = {"id": "r2", "name": "Round 2", "track": "", "date": "", "multiplier": 1, "no_drop": False,
                "results": [ch.normalise_result(res("b", 1)), ch.normalise_result(res("a", 2))]}
        rows = {r["driver"]: r for g in ch.projection(p, live) for r in g["drivers"]}
        self.assertEqual((rows["b"]["points_before"], rows["b"]["points"], rows["b"]["gained"]), (5, 15, 10))
        self.assertEqual((rows["a"]["pos_before"], rows["a"]["pos"]), (1, 1))
        self.assertEqual(ch.live_round_for(p["championship"])["id"], "r2")


class SessionTests(unittest.TestCase):
    def test_live_snapshot_and_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=2)
            drivers = app.build_snapshot()["drivers"]
            league = profile_from_session(drivers, "Season")
            league["championship"] = {"rounds": [{"id": "r1", "name": "Round 1"}]}
            league = app.leagues.save(league)
            app.leagues.set_active(league["id"])
            snap = app.build_snapshot()["championship"]
            self.assertTrue(snap["live"])
            self.assertEqual(snap["round"], "Round 1")
            rows = [r for g in snap["groups"] for r in g["drivers"]]
            self.assertEqual(len(rows), len(drivers))
            self.assertTrue(all(r["gained"] == r["race_points"] for r in rows))
            results, added = app.session_results(app.leagues.get(league["id"]))
            self.assertEqual(added, 0)
            self.assertEqual([r["position"] for r in results], list(range(1, len(drivers) + 1)))
            self.assertTrue(all(r["class_id"] for r in results))

    def test_finished_dnf_and_dns_from_a_watched_race(self):
        from apex.config import DEFAULTS
        from apex.core import App
        from apex.sources import MockSource
        with tempfile.TemporaryDirectory() as tmp:
            t = [0.0]
            src = MockSource(seed=5, clock=lambda: t[0], race_laps=3, no_shows=1)
            app = App(src, dict(DEFAULTS), LeagueStore(tmp))
            for k in range(4000):
                t[0] += 0.1
                if k == 1500:
                    src.out[4] = True  # car 5 retires on lap 2
                app.tick()
                if src.checkered and all(src.done[i] or src.out[i] for i in range(src.num_cars)):
                    break
            league = profile_from_session(app.build_snapshot()["drivers"], "S")
            results, _ = app.session_results(league)
            status = {r["name"]: r["status"] for r in results}
            names = [d["UserName"] for d in src.drivers[1:]]
            self.assertEqual(status[names[4]], "dnf")
            self.assertEqual(status[names[-1]], "dns")
            self.assertEqual(sum(1 for s in status.values() if s == "finished"), src.num_cars - 2)
            winner = results[0]
            self.assertEqual((winner["status"], winner["laps"]), ("finished", 3))
            self.assertGreater(winner["laps_led"], 0)

    def test_saved_with_league(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LeagueStore(tmp)
            p = store.save({"name": "S", "championship": {"rules": {"points": "3,2,1", "drop_rounds": 2},
                                                           "rounds": [{"name": "Opener", "results": [res("x", 1)]}]}})
            again = store.get(p["id"])["championship"]
            self.assertEqual(again["rules"]["points"], [3, 2, 1])
            self.assertEqual(again["rounds"][0]["name"], "Opener")
            json.dumps(ch.standings(store.get(p["id"])))
