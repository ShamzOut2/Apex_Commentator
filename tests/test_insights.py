"""Talking points, the gap trend, season cards, head-to-heads and the recap (insights.py)."""

import unittest

from apex import insights


def log_of(laps):
    """A LapLog from {car: [lap 1 time, lap 2 time, ...]} (places: in order of crossing each lap)."""
    log = insights.LapLog()
    events = sorted((t, car, i + 1) for car, times in laps.items() for i, t in enumerate(times))
    n = max(laps) + 1
    done = [0] * n
    log.update("race", 0.0, done, list(range(1, n + 1)), list(range(1, n + 1)))
    for t, car, lap in events:
        done[car] = lap
        order = sorted(range(n), key=lambda c: (-done[c], laps.get(c, [0] * lap)[min(lap, len(laps.get(c, []))) - 1] if done[c] else 0))
        pos = [order.index(c) + 1 for c in range(n)]
        log.update("race", t, done, pos, pos)
    return log


class GapTrendTests(unittest.TestCase):
    def test_closing_pulling_steady(self):
        # Car 0 laps in 90 s; car 1 starts 5 s back and is 0.5 s a lap quicker.
        log = log_of({0: [90 * i for i in range(1, 7)], 1: [95 + 89.5 * (i - 1) for i in range(1, 7)]})
        tr = insights.gap_trend(log, 0, 1)
        self.assertEqual([g["lap"] for g in tr["gaps"]], [2, 3, 4, 5, 6])
        self.assertEqual(tr["rate"], -0.5)
        self.assertEqual(tr["trend"], "closing")
        self.assertEqual(tr["catch_laps"], round(tr["gap"] / 0.5, 1))
        self.assertEqual(insights.gap_trend(log, 0, 1, now=1.0)["catch_laps"], 2.0)  # from the gap this moment
        steady = log_of({0: [90 * i for i in range(1, 5)], 1: [92 + 90 * (i - 1) for i in range(1, 5)]})
        self.assertEqual(insights.gap_trend(steady, 0, 1)["trend"], "steady")
        self.assertIsNone(insights.gap_trend(steady, 0, 1)["catch_laps"])
        self.assertEqual(insights.gap_trend(log, 1, 0)["trend"], "pulling")

    def test_not_enough_laps(self):
        log = log_of({0: [90], 1: [92]})
        tr = insights.gap_trend(log, 0, 1)
        self.assertIsNone(tr["rate"])
        self.assertIsNone(tr["trend"])
        self.assertEqual(tr["gap"], 2.0)

    def test_a_tow_lap_and_laps_before_the_app_saw_them_are_left_out(self):
        log = insights.LapLog()
        log.update("r", 10.0, [3, 3], [1, 2], [1, 2])   # first seen mid-race: nothing logged
        log.update("r", 20.0, [4, 3], [1, 2], [1, 2])
        log.update("r", 25.0, [4, 4], [1, 2], [1, 2], towed={1})  # car 1's lap: a tow
        self.assertEqual(log.times, {0: {4: 20.0}})
        log.update("other", 1.0, [0, 0], [2, 1], [2, 1])  # another race: afresh
        self.assertEqual((log.times, log.start), ({}, {0: {"pos": 2, "class_pos": 2}, 1: {"pos": 1, "class_pos": 1}}))


def standing(*results):
    """A championship standings row from finishing places (None: missed, "dnf")."""
    rounds = []
    for r in results:
        if r is None:
            rounds.append({"result": None})
        elif r == "dnf":
            rounds.append({"result": {"rank": 12, "status": "dnf", "short": False}})
        else:
            rounds.append({"result": {"rank": r, "status": "finished", "short": False}})
    return {"pos": 2, "points": 80, "behind": 12, "rounds": rounds}


class SeasonTests(unittest.TestCase):
    def test_season_stats(self):
        st = insights.season_stats(standing(4, 1, None, "dnf", 3, 2, 6))
        self.assertEqual((st["wins"], st["podiums"], st["best"], st["starts"]), (1, 3, 1, 6))
        self.assertEqual(st["form"], ["P1", "DNF", "P3", "P2", "P6"])
        self.assertEqual((st["pos"], st["points"], st["behind"]), (2, 80, 12))
        empty = insights.season_stats({"pos": None, "points": 0, "rounds": []})
        self.assertEqual((empty["wins"], empty["best"], empty["form"]), (0, None, []))

    def test_head_to_head(self):
        a, b = standing(1, 5, "dnf", 2), standing(3, 2, 4, None)
        b["points"] = 50
        h = insights.head_to_head(a, b)
        self.assertEqual(h["ahead"], [1, 1])  # round 1 a ahead, round 2 b ahead; 3 and 4 not both finished
        self.assertEqual(h["points_gap"], 30)


def row(idx, pos, start, **kw):
    return dict({"car_idx": idx, "name": f"Driver {idx}", "number": str(idx + 10), "pos": pos, "start_pos": start,
                 "class_pos": pos, "class_key": "A", "gap": pos * 2.0, "pit_stops": 1, "laps_down": 0, "in_world": True}, **kw)


class TalkingPointTests(unittest.TestCase):
    def test_points(self):
        rows = [row(0, 1, 2), row(1, 2, 8), row(2, 3, 3), row(3, 4, 4, pit_stops=0), row(4, 5, 5), row(5, 6, 1)]
        projection = {"groups": [{"key": "A", "name": "GT3", "drivers": [{"driver": "cust:1", "name": "Driver 1", "pos": 1, "pos_before": 2}]}]}
        season = {0: {"starts": 3, "wins": 0, "podiums": 1}, 2: {"starts": 3, "wins": 1, "podiums": 0}}
        pts = insights.talking_points(rows, projection, season)
        texts = [p["text"] for p in pts]
        self.assertEqual(texts[0], "If it finishes like this, Driver 1 leads the championship")
        self.assertIn("#10 Driver 0 is on course for a first win of the season", texts)
        self.assertIn("#12 Driver 2 is on course for a first podium of the season (P3)", texts)
        self.assertIn("#11 Driver 1 has gained 6 places since the start (P8 → P2)", texts)
        self.assertIn("#15 Driver 5 has dropped 5 places since the start (P1 → P6)", texts)
        self.assertIn("#13 Driver 3 hasn't pitted, the cars around them once or more", texts)
        self.assertEqual(pts[0]["action"], {"board": "championship", "group": "A"})
        self.assertEqual(len({p["key"] for p in pts}), len(pts))  # each its own key
        self.assertEqual(insights.talking_points(rows, projection, season, is_race=False), [])

    def test_closing_in(self):
        log = log_of({0: [90 * i for i in range(1, 7)], 1: [93 + 89.4 * (i - 1) for i in range(1, 7)]})
        rows = [row(0, 1, 1, gap=0.0), row(1, 2, 2, gap=0.9)]
        pts = insights.talking_points(rows, log=log)
        self.assertEqual(pts[0]["kind"], "battle")
        self.assertEqual(pts[0]["action"], {"catching": [0, 1]})
        self.assertIn("closing on #10 Driver 0: 0.6 s a lap, 0.9 s back, on them in about 2 laps", pts[0]["text"])


class RecapTests(unittest.TestCase):
    def test_recap(self):
        log = log_of({0: [90, 180, 270], 1: [91, 179, 268], 2: [95, 200, 300]})
        rows = [row(1, 1, 3, incidents=4), row(0, 2, 1, incidents=0), row(2, 3, 2, incidents=0)]
        rc = insights.recap(rows, log, overtakes={1: 2, 2: 1})
        self.assertEqual(rc["gainer"], {"car_idx": 1, "places": 2, "from": 3, "to": 1})
        self.assertEqual(rc["overtakes"], {"car_idx": 1, "count": 2})
        self.assertEqual(rc["cleanest"], {"car_idx": 0, "incidents": 0})  # 0 incidents and ahead of car 2
        self.assertEqual(rc["chart"]["laps"], 3)
        self.assertEqual(rc["chart"]["cars"][0]["car_idx"], 1)
        self.assertEqual(len(rc["chart"]["cars"][0]["places"]), 4)  # the start, then each lap
        nothing = insights.recap([row(0, 1, 1, incidents=2)], insights.LapLog())
        self.assertIsNone(nothing["gainer"])
        self.assertIsNone(nothing["overtakes"])


if __name__ == "__main__":
    unittest.main()
