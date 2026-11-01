import tempfile
import unittest
from datetime import date

from apex import heats
from apex.league import profile_from_session
from tests.test_app import make_app

DAY = date(2026, 11, 5)


def race(num, kind):
    return {"num": num, "kind": kind}


class KindTests(unittest.TestCase):
    def test_kinds(self):
        kind = lambda t, n: heats.race_kind({"SessionType": t, "SessionName": n})  # noqa: E731
        self.assertEqual(kind("Race", "RACE"), "race")
        self.assertEqual(kind("Race", "HEAT 1"), "heat")
        self.assertEqual(kind("Heat Race", "HEAT 2"), "heat")
        self.assertEqual(kind("Race", "CONSOLATION"), "consolation")
        self.assertEqual(kind("Race", "LAST CHANCE HEAT"), "consolation")
        self.assertEqual(kind("Race", "FEATURE"), "feature")
        self.assertEqual(kind("Feature", "FEATURE"), "feature")
        self.assertEqual(kind("Open Qualify", "HEAT QUALIFY"), "")
        self.assertEqual(kind("Practice", "PRACTICE"), "")
        self.assertEqual(kind("Lone Qualify", "QUALIFY"), "")


class MatchTests(unittest.TestCase):
    ROUNDS = [{"name": "Round 1", "date": "2026-10-29"}, {"name": "Heat", "date": "2026-11-05"},
              {"name": "Consolation", "date": "2026-11-05"}, {"name": "Feature", "date": "2026-11-05"},
              {"name": "Heat", "date": "2026-11-12"}]

    def test_the_days_rounds_in_order(self):
        races = [race(3, "heat"), race(4, "consolation"), race(5, "feature")]
        self.assertEqual(heats.match_rounds(races, self.ROUNDS, DAY), {3: 1, 4: 2, 5: 3})
        # Just after midnight: still yesterday's event.
        self.assertEqual(heats.match_rounds(races, self.ROUNDS, date(2026, 11, 6)), {3: 1, 4: 2, 5: 3})
        # No rounds that day: the rounds still to be run, from the first (by kind, then in order).
        self.assertEqual(heats.match_rounds(races, self.ROUNDS, date(2026, 11, 20)), {3: 1, 4: 2, 5: 0})
        # A single race: just the season's next round (not matched here).
        self.assertEqual(heats.match_rounds([race(2, "race")], self.ROUNDS, DAY), {})

    def test_two_races_named_race(self):
        """Two race sessions iRacing calls RACE and RACE: still the meeting's two rounds."""
        rounds = [{"id": "a", "name": "Brands Sprint", "event": "Brands", "results": [1]},
                  {"id": "b", "name": "Brands Feature", "event": "Brands", "results": [1]},
                  {"id": "c", "name": "Spa Sprint", "event": "Spa"}, {"id": "d", "name": "Spa Feature", "event": "Spa"},
                  {"id": "e", "name": "Monza Sprint", "event": "Monza"}]
        races = [race(2, "race"), race(3, "race")]
        # No dates: the first meeting still to be run.
        self.assertEqual(heats.match_rounds(races, rounds, DAY), {2: 2, 3: 3})
        # The round marked Live: its meeting.
        self.assertEqual(heats.match_rounds(races, rounds, DAY, live_id="e"), {2: 4})
        self.assertEqual(heats.match_rounds(races, rounds, DAY, live_id="d"), {2: 2, 3: 3})
        # The first race's results already in its round: it keeps it, the
        # second race goes to the meeting's other round.
        rounds[2] = dict(rounds[2], results=[1], session="777:2")
        self.assertEqual(heats.match_rounds(races, rounds, DAY, event_key=777), {2: 2, 3: 3})
        # Rounds that aren't meetings: the next ones still to be run.
        plain = [{"name": "Round 1", "results": [1]}, {"name": "Round 2"}, {"name": "Round 3"}, {"name": "Round 4"}]
        self.assertEqual(heats.match_rounds(races, plain, DAY), {2: 1, 3: 2})

    def test_by_kind_then_order(self):
        # Rounds listed in another order: each race goes with its kind's round.
        rounds = [{"name": "Feature", "date": "2026-11-05"}, {"name": "Heat 1", "date": "2026-11-05"},
                  {"name": "Heat 2", "date": "2026-11-05"}, {"name": "Consi", "date": "2026-11-05"}]
        races = [race(3, "heat"), race(4, "heat"), race(5, "consolation"), race(6, "feature")]
        self.assertEqual(heats.match_rounds(races, rounds, DAY), {3: 1, 4: 2, 5: 3, 6: 0})
        # Rounds with other names: in order.
        plain = [{"name": "Race A", "date": "2026-11-05"}, {"name": "Race B", "date": "2026-11-05"}]
        self.assertEqual(heats.match_rounds(races, plain, DAY), {3: 0, 4: 1})

    def test_titles(self):
        self.assertEqual(heats.round_title(2, "Spa Heat A"), "Spa Heat A")  # just the round's own name
        self.assertEqual(heats.round_title(2, " "), "Round 2")


class HeatEventTests(unittest.TestCase):
    def test_races_named_and_scored_as_their_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=2)
            app._today = lambda: DAY
            with app._lock:
                sessions = app._session_meta["sessions"]
                sessions[0].update(SessionType="Race", SessionName="HEAT 1")  # the race on screen
                sessions[1] = {"SessionType": "Race", "SessionName": "CONSOLATION"}
                sessions[2] = {"SessionType": "Race", "SessionName": "FEATURE"}
            league = profile_from_session(app.build_snapshot()["drivers"], "Heats")
            league["championship"] = {"rounds": [
                {"id": "r1", "name": "Opener", "date": "2026-10-29"},
                {"id": "r2", "name": "Spa Night - Race 1", "date": "2026-11-05"},
                {"id": "r3", "name": "Spa Night - Race 2", "date": "2026-11-05"},
                {"id": "r4", "name": "Spa Night - Race 3", "date": "2026-11-05"}]}
            league = app.leagues.save(league)
            app.leagues.set_active(league["id"])
            snap = app.build_snapshot()
            self.assertEqual((snap["session"]["kind"], snap["session"]["round_title"]), ("heat", "Spa Night - Race 1"))
            # The live championship counts this race as round 2, not the empty round 1.
            self.assertEqual(snap["championship"]["round"], "Spa Night - Race 1")
            app.command("overlay_settings", {"overlay": "standings", "values": {"round_titles": "off"}})
            self.assertEqual(app.build_snapshot()["session"]["round_title"], "")
            # Another day (no rounds dated that day): the rounds still to be run.
            app._today = lambda: date(2026, 12, 1)
            app.command("overlay_settings", {"overlay": "standings", "values": {"round_titles": "name"}})
            self.assertEqual(app.build_snapshot()["session"]["round_title"], "Opener")
            # Its results go to its round.
            app._today = lambda: DAY
            app._save_results(app.leagues.get(league["id"]), app.session_key(), app.session_results(league)[0], "Spa")
            rounds = app.leagues.get(league["id"])["championship"]["rounds"]
            self.assertEqual([bool(r.get("results")) for r in rounds], [False, True, False, False])


    def test_two_races_called_race_take_their_rounds_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = make_app(tmp, minutes=2)
            app._today = lambda: DAY
            with app._lock:
                sessions = app._session_meta["sessions"]
                sessions[0].update(SessionType="Race", SessionName="RACE")  # the race on screen
                sessions[1] = {"SessionType": "Race", "SessionName": "RACE"}
            league = profile_from_session(app.build_snapshot()["drivers"], "Doubles")
            league["championship"] = {"rounds": [  # no dates: the meeting still to be run
                {"id": "r1", "name": "Sprint (LCQ)", "event": "Brands Hatch"},
                {"id": "r2", "name": "Feature", "event": "Brands Hatch"},
                {"id": "r3", "name": "Sprint", "event": "Spa"}]}
            league = app.leagues.save(league)
            app.leagues.set_active(league["id"])
            snap = app.build_snapshot()
            self.assertEqual(snap["session"]["round_title"], "Sprint (LCQ)")
            self.assertEqual(app._race_title(league, 1, sessions[1]), "Feature")
            app.command("board_show", {"kind": "results", "group": "", "round": "session:0"})
            self.assertEqual(app.build_snapshot()["board"]["title"], "Sprint (LCQ) result")

if __name__ == "__main__":
    unittest.main()
