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

    def test_both_adds_up_per_championship(self):
        classes = [{"id": "pro", "name": "PRO"}, {"id": "am", "name": "AM"}]
        drivers = [{"cust_id": i, "name": n, "team": t} for i, n, t in ((1, "A", "Red"), (2, "B", "Red"), (3, "C", "Blue"), (4, "D", "Blue"))]
        rules = {"scoring": "both", "points": [10, 6, 4], "overall_points": [20, 15, 10, 5], "classified_pct": 0,
                 "bonuses": {"fastest_lap": 1}}
        rounds = [
            {"id": "r1", "results": [res("cust:1", 1, "pro"), res("cust:3", 2, "am", fl=80), res("cust:2", 3, "pro"), res("cust:4", 4, "am")]},
            {"id": "r2", "results": [res("cust:3", 1, "am"), res("cust:2", 2, "pro", fl=80), res("cust:4", 3, "am"), res("cust:1", 4, "pro")]},
        ]
        p = profile(rules, rounds, penalties=[{"driver": "cust:2", "points": 2}], classes=classes, drivers=drivers)
        st = ch.standings(p)
        tables = {g["name"]: {d["driver"]: ([s["points"] for s in d["rounds"]], d["points"]) for d in g["drivers"]}
                  for g in st["groups"]}
        # Overall positions: R1 A 20, C 15+1 (fastest), B 10, D 5; R2 C 20, B 15+1, D 10, A 5.
        self.assertEqual(tables["Overall"], {"cust:3": ([16, 20], 36), "cust:1": ([20, 5], 25),
                                             "cust:2": ([10, 16], 24), "cust:4": ([5, 10], 15)})
        # Class positions: the fastest lap in each class gets the bonus there.
        self.assertEqual(tables["PRO"], {"cust:1": ([10, 6], 16), "cust:2": ([6, 11], 15)})
        self.assertEqual(tables["AM"], {"cust:3": ([11, 10], 21), "cust:4": ([6, 6], 12)})
        self.assertIn("overall positions: 20, 15, 10, 5", st["groups"][0]["basis"])
        self.assertIn("class positions: 10, 6, 4", st["groups"][1]["basis"])
        # Teams take overall points by default (penalty off): Red 25 + 26 - 2, Blue 36 + 15.
        self.assertEqual({t["team"]: t["points"] for t in st["teams"]}, {"Red": 49, "Blue": 51})
        p["championship"]["rules"]["team_points"] = "class"
        self.assertEqual({t["team"]: t["points"] for t in ch.standings(p)["teams"]}, {"Red": 31, "Blue": 33})

    def test_secondary_class_has_its_own_championship(self):
        classes = [{"id": "pro", "name": "Pro"}, {"id": "am", "name": "Am"},
                   {"id": "rookie", "name": "Rookie Cup", "role": "secondary"}]
        drivers = [{"cust_id": i, "name": n, "class2_id": c2} for i, n, c2 in
                   ((1, "A", ""), (2, "B", "rookie"), (3, "C", ""), (4, "D", "rookie"))]
        rounds = [{"id": "r1", "results": [res("cust:1", 1, "pro"), res("cust:2", 2, "am"),
                                           res("cust:3", 3, "pro"), res("cust:4", 4, "pro")]}]
        # Whatever the scoring, the rookies are ranked among themselves (B 1st, D 2nd).
        for scoring, names in (("class", ["Pro", "Am", "Rookie Cup"]), ("overall", ["Overall", "Rookie Cup"])):
            p = profile({"points": [10, 5], "scoring": scoring, "classified_pct": 0}, rounds, classes=classes, drivers=drivers)
            st = ch.standings(p)
            self.assertEqual([g["name"] for g in st["groups"]], names)
            rookie = st["groups"][-1]
            self.assertTrue(rookie["secondary"])
            self.assertEqual([(r["driver"], r["points"]) for r in rookie["drivers"]], [("cust:2", 10), ("cust:4", 5)])
            self.assertIn("among its drivers", rookie["basis"])
        # The main class standings don't change: D still scores in Pro.
        pts = {g["name"]: {r["driver"]: r["points"] for r in g["drivers"]} for g in ch.standings(
            profile({"points": [10, 5, 2]}, rounds, classes=classes, drivers=drivers))["groups"]}
        self.assertEqual(pts["Pro"], {"cust:1": 10, "cust:3": 5, "cust:4": 2})
        # Round results and the calendar know the secondary class's winner.
        p = profile({"points": [10, 5]}, rounds, classes=classes, drivers=drivers)
        rows = ch.round_results(p, p["championship"]["rounds"][0], "rookie")
        self.assertEqual([(r["driver"], r["rank"], r["points"]) for r in rows], [("cust:2", 1, 10), ("cust:4", 2, 5)])
        self.assertIn("rookie", [w["group"] for w in ch.calendar(p)[0]["winners"]])

    def test_secondary_class_scoring_choices(self):
        classes = [{"id": "pro", "name": "Pro"}, {"id": "am", "name": "Am"},
                   {"id": "rookie", "name": "Rookie Cup", "role": "secondary"}]
        drivers = [{"cust_id": i, "name": n, "class2_id": c2} for i, n, c2 in
                   ((1, "A", ""), (2, "B", "rookie"), (3, "C", ""), (4, "D", "rookie"))]
        rounds = [{"id": "r1", "results": [res("cust:1", 1, "pro"), res("cust:2", 2, "am"),
                                           res("cust:3", 3, "pro"), res("cust:4", 4, "pro")]}]

        def rookie(scoring, how):
            rules = {"scoring": scoring, "points": [10, 5, 2], "overall_points": [20, 15, 10, 5], "classified_pct": 0,
                     "secondary_scoring": {"rookie": how}}
            st = ch.standings(profile(rules, rounds, classes=classes, drivers=drivers))
            g = next(g for g in st["groups"] if g["key"] == "rookie")
            return [(r["driver"], r["points"]) for r in g["drivers"]], g["basis"]

        # Ranked among themselves on the class points: B 1st (10), D 2nd (5).
        self.assertEqual(rookie("both", "own")[0], [("cust:2", 10), ("cust:4", 5)])
        # Their main class points: B won Am (10), D was 3rd in Pro (2).
        pts, basis = rookie("both", "class")
        self.assertEqual((pts, basis), ([("cust:2", 10), ("cust:4", 2)], "The points its drivers score in their own class"))
        # Their overall points: B 2nd (15), D 4th (5); even when only classes are scored.
        self.assertEqual(rookie("both", "overall")[0], [("cust:2", 15), ("cust:4", 5)])
        self.assertEqual(rookie("class", "overall")[0], [("cust:2", 15), ("cust:4", 5)])
        self.assertEqual(ch.normalise_rules({"secondary_scoring": {"rookie": "own", "x": "bogus", "y": "class"}})["secondary_scoring"],
                         {"y": "class"})

    def test_sum_adds_class_and_overall_points(self):
        classes = [{"id": "pro", "name": "Pro"}, {"id": "am", "name": "Am"}]
        rules = {"scoring": "sum", "points": [10, 5], "overall_points": [4, 3, 2, 1], "classified_pct": 0,
                 "bonuses": {"fastest_lap": 1}}
        rounds = [{"id": "r1", "multiplier": 2, "results": [
            res("a", 1, "pro"), res("b", 2, "am", fl=80), res("c", 3, "pro"), res("d", 4, "am")]}]
        st = ch.standings(profile(rules, rounds, classes=classes))
        pts = {g["name"]: {r["driver"]: r["points"] for r in g["drivers"]} for g in st["groups"]}
        # (class points + bonus + overall points) x 2: a (10+4), b (10+1+3), c (5+2), d (5+1).
        self.assertEqual(pts["Overall"], {"a": 28, "b": 28, "c": 14, "d": 12})
        self.assertEqual(pts["Pro"], {"a": 28, "c": 14})
        self.assertEqual(pts["Am"], {"b": 28, "d": 12})
        self.assertIn("+ overall points (4, 3, 2, 1)", st["groups"][1]["basis"])

    def test_overall_championship_has_its_own_points(self):
        classes = [{"id": "pro", "name": "Pro"}, {"id": "am", "name": "Am"}]
        rounds = [{"id": "r1", "results": [res("a", 1, "pro"), res("b", 2, "am"), res("c", 3, "pro")]}]
        # Overall only, on its own points.
        rows, st = table(profile({"scoring": "overall", "points": [10, 5], "overall_points": [3, 2, 1]}, rounds, classes=classes))
        self.assertEqual([g["name"] for g in st["groups"]], ["Overall"])
        self.assertEqual([rows[d]["points"] for d in "abc"], [3, 2, 1])
        # With class championships too: each on its own points, side by side.
        st = ch.standings(profile({"scoring": "both", "points": [10, 5], "overall_points": [3, 2, 1]}, rounds, classes=classes))
        pts = {g["name"]: {r["driver"]: r["points"] for r in g["drivers"]} for g in st["groups"]}
        self.assertEqual(pts, {"Overall": {"a": 3, "b": 2, "c": 1}, "Pro": {"a": 10, "c": 5}, "Am": {"b": 10}})

    def test_class_points_table(self):
        classes = [{"id": "pro", "name": "Pro"}, {"id": "am", "name": "Am"}]
        rules = {"points": [10, 5], "class_points": {"am": "3, 2", "pro": ""}}
        rounds = [{"id": "r1", "results": [res("a", 1, "pro"), res("b", 2, "am"), res("c", 3, "pro"), res("d", 4, "am")]}]
        rows, _ = table(profile(rules, rounds, classes=classes))
        self.assertEqual([rows[d]["points"] for d in "abcd"], [10, 3, 5, 2])
        self.assertEqual(ch.normalise_rules(rules)["class_points"], {"am": [3, 2]})

    def test_old_saves_without_new_rules_still_score(self):
        p = {"name": "Old", "drivers": [], "classes": [], "championship": {
            "rules": {"points": [5]}, "rounds": [{"id": "r1", "results": [res("a", 1)]}], "penalties": []}}
        self.assertEqual(ch.standings(p)["groups"][0]["drivers"][0]["points"], 5)

    def test_dnf_doesnt_score_when_off(self):
        p = profile({"points": [10, 8], "dnf_scores": False},
                    [{"id": "r1", "results": [res("a", 1), res("b", 2, status="dnf")]}])
        self.assertEqual(table(p)[0]["b"]["points"], 0)
        self.assertEqual(repr(table(p)[1]["groups"][0]["drivers"][1]["rounds"][0]["points"]), "0")  # not 0.0

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

    def test_custom_points_systems(self):
        schemes = [{"id": "sprint", "name": "Sprint", "points": [10, 8, 6]},
                   {"id": "feature", "name": "Feature", "points": [50, 40, 30], "overall_points": [60, 45, 35]}]
        rules = {"points": [25, 18, 15], "scoring": "both", "custom_schemes": True, "schemes": schemes}
        rounds = [{"id": "r1", "scheme": "sprint", "results": [res("a", 1, "pro"), res("b", 2, "pro")]},
                  {"id": "r2", "scheme": "feature", "results": [res("b", 1, "pro"), res("a", 2, "pro")]},
                  {"id": "r3", "results": [res("a", 1, "pro"), res("b", 2, "pro")]}]
        rows = {(g["key"], r["driver"]): r for g in ch.standings(profile(rules, rounds))["groups"] for r in g["drivers"]}
        self.assertEqual(rows[("pro", "a")]["points"], 10 + 40 + 25)      # sprint, feature, usual
        self.assertEqual(rows[("overall", "b")]["points"], 8 + 60 + 18)   # the feature's own overall points
        # Turned off: every round on the usual points.
        off = dict(rules, custom_schemes=False)
        rows = {(g["key"], r["driver"]): r for g in ch.standings(profile(off, rounds))["groups"] for r in g["drivers"]}
        self.assertEqual(rows[("pro", "a")]["points"], 25 + 18 + 25)
        norm = ch.normalise_rules(rules)
        self.assertEqual([sc["name"] for sc in norm["schemes"]], ["Sprint", "Feature"])

    def test_dropping_a_whole_race_meeting(self):
        rules = {"points": [10, 5], "drop_rounds": 1, "drop_meetings": True}
        rounds = [
            {"id": "h1", "event": "Fuji", "results": [res("a", 2), res("b", 1)]},   # a: 5
            {"id": "h2", "event": "Fuji", "results": [res("a", 2), res("b", 1)]},   # a: 5 (Fuji = 10)
            {"id": "r3", "results": [res("a", 1), res("b", 2)]},                    # a: 10
            {"id": "r4", "results": [res("a", 2), res("b", 1)]},                    # a: 5
        ]
        rows, _ = table(profile(rules, rounds))
        # a's worst: r4 alone (5) beats the meeting (10): the meeting counts as one.
        self.assertEqual([s["round"] for s in rows["a"]["rounds"] if s["dropped"]], ["r4"])
        self.assertEqual(rows["a"]["points"], 20)
        # b: Fuji 20, r3 5, r4 10 -> drops r3.
        self.assertEqual([s["round"] for s in rows["b"]["rounds"] if s["dropped"]], ["r3"])
        # Two drops: the meeting's races go together.
        rows, _ = table(profile(dict(rules, drop_rounds=2), rounds))
        self.assertEqual(sorted(s["round"] for s in rows["a"]["rounds"] if s["dropped"]), ["h1", "h2", "r4"])

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

    def test_results_saved_by_themselves_when_the_race_is_over(self):
        from apex.config import DEFAULTS
        from apex.core import App
        from apex.sources import MockSource
        with tempfile.TemporaryDirectory() as tmp:
            t = [0.0]
            src = MockSource(seed=5, clock=lambda: t[0], race_laps=3, no_shows=1)
            app = App(src, dict(DEFAULTS), LeagueStore(tmp))
            app.RESULTS_EVERY_S = app.RESULTS_GRACE_S = 0
            app.tick()
            league = profile_from_session(app.build_snapshot()["drivers"], "S")
            league["championship"] = {"rules": {"points": [25, 18, 15]}, "rounds": [
                {"id": "r1", "name": "Round 1"}, {"id": "r2", "name": "Round 2"}]}
            league = app.leagues.save(league)
            app.leagues.set_active(league["id"])
            saved_at = None
            for k in range(6000):
                t[0] += 0.1
                if k == 1500:
                    src.out[4] = True  # car 5 retires on lap 2
                app.tick()
                if app.leagues.get(league["id"])["championship"]["rounds"][0]["results"]:
                    saved_at = k
                    break
            self.assertIsNotNone(saved_at, "results weren't saved")
            self.assertTrue(src.checkered)
            champ = app.leagues.get(league["id"])["championship"]
            r1, r2 = champ["rounds"]
            names = [d["UserName"] for d in src.drivers[1:]]
            status = {r["name"]: r["status"] for r in r1["results"]}
            self.assertEqual((status[names[4]], status[names[-1]]), ("dnf", "dns"))
            self.assertEqual(r1["session"], app.session_key())
            self.assertEqual(r2["results"], [])
            notice = app.build_snapshot()["results_auto"]
            self.assertEqual((notice["on"], notice["saved"]["name"], notice["saved"]["round"]), (True, "Round 1", "r1"))
            # The standings have the race in them; it's saved once.
            winner = ch.standings(app.leagues.get(league["id"]))["groups"][0]["drivers"][0]
            self.assertEqual(winner["points"], 25)
            for _ in range(50):
                t[0] += 0.1
                app.tick()
            self.assertEqual(app.leagues.get(league["id"])["championship"]["rounds"][1]["results"], [])

    def test_results_saved_when_the_session_moves_on(self):
        from apex.config import DEFAULTS
        from apex.core import App
        from apex.sources import MockSource
        with tempfile.TemporaryDirectory() as tmp:
            t = [0.0]
            src = MockSource(seed=5, clock=lambda: t[0])
            app = App(src, dict(DEFAULTS), LeagueStore(tmp))
            app.RESULTS_EVERY_S = 0
            for _ in range(600):
                t[0] += 0.1
                app.tick()
            league = app.leagues.save(dict(profile_from_session(app.build_snapshot()["drivers"], "S"),
                                           championship={"rounds": []}))
            app.leagues.set_active(league["id"])
            app.tick()  # racing: the race is being watched
            self.assertIsNotNone(app._results_watch)
            app._session_meta["subsession"] = 999  # a new session
            app.tick()
            champ = app.leagues.get(league["id"])["championship"]
            self.assertEqual(len(champ["rounds"]), 1)  # no rounds yet: one is made
            self.assertEqual(champ["rounds"][0]["name"], "Round 1")
            self.assertEqual(len(champ["rounds"][0]["results"]), len(app._drivers))
            # Turned off: nothing is saved.
            app.command("auto_results", {"enabled": False})
            self.assertFalse(app.build_snapshot()["results_auto"]["on"])

    def test_saved_with_league(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LeagueStore(tmp)
            p = store.save({"name": "S", "championship": {"rules": {"points": "3,2,1", "drop_rounds": 2},
                                                           "rounds": [{"name": "Opener", "results": [res("x", 1)]}]}})
            again = store.get(p["id"])["championship"]
            self.assertEqual(again["rules"]["points"], [3, 2, 1])
            self.assertEqual(again["rounds"][0]["name"], "Opener")
            json.dumps(ch.standings(store.get(p["id"])))
