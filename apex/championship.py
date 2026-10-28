"""Championship points: a league's season, scored to its own rules.

A league profile can carry a ``championship``:

* **rules**: points per finishing position (and optionally per qualifying
  position), any of the bonuses in ``BONUSES``, drop rounds, how far a
  fastest-lap bonus reaches, how much of the race a driver must cover to
  score, and whether points are scored per class (one championship per
  class), overall, or both (each result scores separately in its class's
  championship and the overall one).
* **rounds**: each round's results, imported from iRacing or typed in, with a
  points multiplier (double points finales) and a "can't be dropped" flag.
* **penalties**: points taken off after a race, and licence penalty points,
  each with a reason. Penalties can't be dropped.

Everything is worked out from those on demand (``standings``), so editing a
result or a rule re-scores the whole season. ``standings`` can also take a
provisional round built from the race in progress, which is how the live
"if it finished now" projection works.
"""

import re
import uuid

BONUSES = (
    ("pole", "Pole position"),
    ("fastest_lap", "Fastest lap"),
    ("led_lap", "Led at least one lap"),
    ("per_lap_led", "Each lap led"),
    ("most_laps_led", "Most laps led"),
    ("most_places_gained", "Most places gained"),
    ("clean_race", "Clean race (no incidents)"),
    ("finished", "Finished the race"),
    ("started", "Started the race"),
    ("win", "Race win (on top of position points)"),
)
BONUS_KEYS = tuple(k for k, _ in BONUSES)
STATUSES = ("finished", "dnf", "dsq", "dns")
SCORING = ("class", "overall", "both")
OVERALL = "overall"  # the key of the overall championship

DEFAULT_RULES = {
    "points": [25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
    "qualifying_points": [],
    "bonuses": {k: 0 for k in BONUS_KEYS},
    "scoring": "class",         # "class": a championship per class; "overall": one for everyone;
                                # "both": a championship per class and one overall, scored separately
    "overall_points": [],       # "both": points for overall positions ([] = same as "points")
    "drop_rounds": 0,           # each driver's worst N rounds don't count (once they've more than N)
    "fastest_lap_top": 0,       # fastest-lap bonus only if finishing in the top N (0 = anyone)
    "classified_pct": 75,       # must complete this % of the class winner's laps to score, else DNF (0 = off)
    "dnf_scores": True,         # a DNF still scores the points for where it was classified
    "team_best": 0,             # team championship: best N drivers per team per round (0 = all)
}


def _num(value, default=0, lo=None, hi=None, cast=float):
    try:
        v = cast(value)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def parse_points(value):
    """'25, 18, 15' or a list -> list of numbers."""
    if isinstance(value, str):
        value = [p for p in re.split(r"[\s,;]+", value) if p]
    out = []
    for p in value or []:
        v = _num(p, None, lo=0)
        if v is None:
            continue
        out.append(int(v) if v == int(v) else v)
    return out[:100]


def _id(value):
    value = str(value or "").strip()
    return value if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", value) else uuid.uuid4().hex[:10]


def normalise_rules(rules):
    rules = rules if isinstance(rules, dict) else {}
    bonuses = rules.get("bonuses") if isinstance(rules.get("bonuses"), dict) else {}
    return {
        "points": parse_points(rules.get("points", DEFAULT_RULES["points"])),
        "qualifying_points": parse_points(rules.get("qualifying_points", [])),
        "bonuses": {k: _num(bonuses.get(k, 0), 0, lo=-100, hi=1000) for k in BONUS_KEYS},
        "scoring": rules.get("scoring") if rules.get("scoring") in SCORING else "class",
        "overall_points": parse_points(rules.get("overall_points", [])),
        "drop_rounds": _num(rules.get("drop_rounds"), 0, lo=0, hi=50, cast=int),
        "fastest_lap_top": _num(rules.get("fastest_lap_top"), 0, lo=0, hi=200, cast=int),
        "classified_pct": _num(rules.get("classified_pct", DEFAULT_RULES["classified_pct"]), 0, lo=0, hi=100),
        "dnf_scores": bool(rules.get("dnf_scores", True)),
        "team_best": _num(rules.get("team_best"), 0, lo=0, hi=20, cast=int),
    }


def normalise_result(r):
    status = r.get("status") if r.get("status") in STATUSES else "finished"
    fastest = _num(r.get("fastest_lap"), None, lo=0)
    return {
        "driver": str(r.get("driver") or "").strip(),
        "name": str(r.get("name") or "").strip(),
        "class_id": str(r.get("class_id") or "").strip(),
        "position": _int_or_none(r.get("position")),
        "start_position": _int_or_none(r.get("start_position")),
        "laps": _num(r.get("laps"), 0, lo=0, cast=int),
        "laps_led": _num(r.get("laps_led"), 0, lo=0, cast=int),
        "fastest_lap": round(fastest, 3) if fastest else None,
        "incidents": _num(r.get("incidents"), 0, lo=0, cast=int),
        "status": status,
        "adjust": _num(r.get("adjust"), 0, lo=-1000, hi=1000),  # hand-given points (+ or -)
        "make": str(r.get("make") or "").strip()[:40],  # the car driven that round (manufacturers' standings)
    }


def normalise(champ):
    champ = champ if isinstance(champ, dict) else {}
    rounds = []
    for rd in champ.get("rounds") or []:
        if not isinstance(rd, dict):
            continue
        results = [normalise_result(r) for r in rd.get("results") or [] if isinstance(r, dict)]
        rounds.append({
            "id": _id(rd.get("id")),
            "name": str(rd.get("name") or f"Round {len(rounds) + 1}").strip(),
            "track": str(rd.get("track") or "").strip(),
            "config": str(rd.get("config") or "").strip()[:80],      # the track's layout
            "track_id": rd.get("track_id") if isinstance(rd.get("track_id"), int) else None,
            "date": str(rd.get("date") or "").strip()[:10],
            "time": str(rd.get("time") or "").strip()[:5],           # start time, "19:30"
            "length": str(rd.get("length") or "").strip()[:40],     # "60 min", "30 laps", ...
            "multiplier": _num(rd.get("multiplier"), 1.0, lo=0, hi=10),
            "no_drop": bool(rd.get("no_drop")),
            # The iRacing session the results were imported from.
            "session": str(rd.get("session") or "")[:40],
            "results": [r for r in results if r["driver"]],
        })
    round_ids = {rd["id"] for rd in rounds}
    penalties = []
    for p in champ.get("penalties") or []:
        if not isinstance(p, dict) or not str(p.get("driver") or "").strip():
            continue
        penalties.append({
            "id": _id(p.get("id")),
            "driver": str(p["driver"]).strip(),
            "round_id": p.get("round_id") if p.get("round_id") in round_ids else "",
            "points": _num(p.get("points"), 0, lo=0, hi=1000),     # taken off the championship
            "licence": _num(p.get("licence"), 0, lo=0, hi=100),    # licence / penalty points
            "reason": str(p.get("reason") or "").strip()[:200],
        })
    live = champ.get("live_round")
    return {
        "rules": normalise_rules(champ.get("rules")),
        "rounds": rounds,
        "penalties": penalties,
        # The round the race in progress counts as, for the live projection
        # ("" = the first round without results).
        "live_round": live if live in round_ids else "",
    }


# -- scoring ------------------------------------------------------------------


def _group_keys(result, rules):
    """The championships a result scores in: its class's, the overall one, or both."""
    if rules["scoring"] == "overall":
        return [OVERALL]
    if rules["scoring"] == "both":
        return [result["class_id"], OVERALL]
    return [result["class_id"]]


def race_distance(results):
    """Laps the winner of each class completed: what "the race distance" means for a car."""
    out = {}
    for r in results:
        if r["status"] not in ("dsq", "dns"):
            out[r["class_id"]] = max(out.get(r["class_id"], 0), r["laps"])
    return out


def short_of_distance(r, distance, rules):
    """Too few laps to be classified: a DNF that scores nothing."""
    pct = rules["classified_pct"]
    return bool(pct) and r["laps"] < distance.get(r["class_id"], 0) * pct / 100.0 - 1e-9


def apply_distance_rule(results, rules):
    """Mark cars that didn't cover enough of the race as DNF (in place)."""
    distance = race_distance(results)
    for r in results:
        if r["status"] == "finished" and short_of_distance(r, distance, rules):
            r["status"] = "dnf"
    return results


def score_round(rd, rules):
    """Points for every result in a round: {championship key: {driver: {"total", "position", "bonus", ...}}}.

    A provisional round (the race in progress) skips the race-distance rule:
    mid-race, nobody has covered the distance yet.
    """
    groups = {}
    for r in rd["results"]:
        for key in _group_keys(r, rules):
            groups.setdefault(key, []).append(r)
    distance = {} if rd.get("provisional") else race_distance(rd["results"])
    return {key: _score_group(key, results, rules, rd["multiplier"], distance) for key, results in groups.items()}


def _score_group(group, results, rules, multiplier, distance):
    bonus_cfg = rules["bonuses"]
    points = rules["overall_points"] if group == OVERALL and rules["overall_points"] else rules["points"]
    short = {r["driver"] for r in results if short_of_distance(r, distance, rules)}

    def status(r):
        return "dnf" if r["status"] == "finished" and r["driver"] in short else r["status"]

    # Finishing order within the group: by position; unplaced (DNS) last.
    order = sorted(results, key=lambda r: (r["status"] == "dns", r["position"] or 10_000))
    rank = {}
    place = 0
    for r in order:
        if r["status"] in ("dsq", "dns"):
            continue
        place += 1
        rank[r["driver"]] = place
    starters = [r for r in results if r["start_position"] and r["status"] != "dns"]
    start_rank = {r["driver"]: i for i, r in enumerate(sorted(starters, key=lambda r: r["start_position"]), start=1)}

    eligible_fl = [r for r in results if r["fastest_lap"] and r["status"] not in ("dsq", "dns")
                   and (not rules["fastest_lap_top"] or rank.get(r["driver"], 10_000) <= rules["fastest_lap_top"])]
    best_lap = min((r["fastest_lap"] for r in eligible_fl), default=None)
    most_led = max((r["laps_led"] for r in results if r["status"] != "dsq"), default=0)
    gains = {r["driver"]: start_rank[r["driver"]] - rank[r["driver"]]
             for r in results if status(r) == "finished" and r["driver"] in rank and r["driver"] in start_rank}
    most_gained = max(gains.values(), default=0)

    out = {}
    for r in results:
        d = r["driver"]
        st = status(r)
        entry = {"group": group, "rank": rank.get(d), "status": st, "short": d in short, "position": 0,
                 "qualifying": 0, "bonus": {}, "adjust": r["adjust"], "total": r["adjust"]}
        out[d] = entry
        # Disqualified, or short of the race distance: no points at all.
        if st == "dsq" or d in short:
            continue
        if d in rank and (st == "finished" or rules["dnf_scores"]):
            entry["position"] = points[rank[d] - 1] if rank[d] <= len(points) else 0
        q = rules["qualifying_points"]
        if start_rank.get(d) and start_rank[d] <= len(q):
            entry["qualifying"] = q[start_rank[d] - 1]
        bonus = entry["bonus"]

        def give(key, times=1):
            if bonus_cfg[key] and times:
                bonus[key] = bonus_cfg[key] * times

        if st != "dns":
            give("started")
            give("pole", start_rank.get(d) == 1)
        if best_lap is not None and r in eligible_fl and r["fastest_lap"] == best_lap:
            give("fastest_lap")
        if r["laps_led"]:
            give("led_lap")
            give("per_lap_led", r["laps_led"])
            give("most_laps_led", r["laps_led"] == most_led)
        if st == "finished":
            give("finished")
            give("clean_race", r["incidents"] == 0)
            give("win", rank.get(d) == 1)
            give("most_places_gained", most_gained > 0 and gains.get(d) == most_gained)
        raw = entry["position"] + entry["qualifying"] + sum(bonus.values())
        entry["total"] = _round(raw * multiplier + r["adjust"])
    return out


def _round(v):
    v = round(v, 2)
    return int(v) if v == int(v) else v


def standings(profile, live_round=None):
    """Driver standings (one table per championship: each class, overall, or both) and team standings.

    ``live_round``: a provisional round (same shape as a stored round) that
    replaces the stored round with the same id, or is added if new.
    """
    champ = normalise(profile.get("championship"))  # older saves may miss newer rules
    rules = champ["rules"]
    rounds = list(champ["rounds"])
    if live_round is not None:
        rounds = [live_round if rd["id"] == live_round["id"] else rd for rd in rounds]
        if all(rd["id"] != live_round["id"] for rd in rounds):
            rounds.append(live_round)
    scored = [rd for rd in rounds if rd["results"]]
    roster = {_key(d): d for d in profile.get("drivers", [])}
    classes = {c["id"]: c for c in profile.get("classes", [])}
    per_round = {rd["id"]: score_round(rd, rules) for rd in scored}

    # Which championships each driver is in: their latest result's class
    # (a driver who changes class moves with it), and/or overall.
    latest = {}
    names = {}
    for rd in scored:
        for r in rd["results"]:
            latest[r["driver"]] = _group_keys(r, rules)
            names[r["driver"]] = r["name"] or names.get(r["driver"], "")
    penalties = {}
    licence = {}
    for p in champ["penalties"]:
        penalties[p["driver"]] = penalties.get(p["driver"], 0) + p["points"]
        licence[p["driver"]] = licence.get(p["driver"], 0) + p["licence"]
    for d in list(penalties) + list(licence):
        if d not in latest:
            latest[d] = _group_keys({"class_id": (roster.get(d) or {}).get("class_id", "")}, rules)

    drop = rules["drop_rounds"]
    groups = {}
    for d, keys in latest.items():
        for group in keys:
            groups.setdefault(group, []).append(_driver_row(d, group, scored, per_round, live_round, drop,
                                                            penalties, licence, roster, names))
    out_groups = []
    for key, members in groups.items():
        # Ties: most wins, then most seconds, and so on (countback).
        members.sort(key=lambda r: (-r["points"], _countback(r["_countback"]), r["name"].lower()))
        leader = members[0]["points"] if members else 0
        for i, row in enumerate(members, start=1):
            row["pos"] = i
            row["behind"] = _round(leader - row["points"])
            del row["_countback"]
        cls = classes.get(key)
        if key == OVERALL:
            name, order = "Overall", -1
        elif cls:
            name, order = cls["name"], list(classes).index(key)
        else:
            name, order = (key.replace("iracing:", "") or "No class"), 999
        out_groups.append({"key": key, "name": name, "color": cls["color"] if cls else None,
                           "drivers": members, "order": order})
    out_groups.sort(key=lambda g: g["order"])
    return {
        "rounds": [{"id": rd["id"], "name": rd["name"], "track": rd["track"], "date": rd["date"],
                    "multiplier": rd["multiplier"], "no_drop": rd["no_drop"], "live": rd is live_round,
                    "scored": bool(rd["results"])} for rd in rounds],
        "groups": out_groups,
        "teams": _team_standings(profile, scored, per_round, rules, penalties),
    }


def _driver_row(d, group, scored, per_round, live_round, drop, penalties, licence, roster, names):
    scores = []
    for rd in scored:
        res = per_round[rd["id"]].get(group, {}).get(d)
        # Rounds a driver missed score 0 and are the first to drop.
        scores.append({"round": rd["id"], "points": res["total"] if res else 0, "result": res,
                       "droppable": not rd["no_drop"], "dropped": False, "live": rd is live_round})
    droppable = sorted((s for s in scores if s["droppable"]), key=lambda s: (s["points"], s["result"] is not None))
    # Early in a season there's nothing to drop yet: at least one round
    # always counts.
    for s in droppable[:min(drop, len(scores) - 1)]:
        s["dropped"] = True
    kept = sum(s["points"] for s in scores if not s["dropped"])
    finishes = sorted(s["result"]["rank"] for s in scores if s["result"] and s["result"]["rank"])
    info = roster.get(d) or {}
    return {
        "driver": d, "name": info.get("name") or names.get(d) or d, "team": info.get("team", ""),
        "car_number": info.get("car_number", ""), "group": group,
        # Penalties come off every championship the driver is in.
        "points": _round(kept - penalties.get(d, 0)),
        "gross": _round(sum(s["points"] for s in scores)), "penalty_points": _round(penalties.get(d, 0)),
        "licence_points": _round(licence.get(d, 0)), "rounds": scores, "wins": finishes.count(1),
        "_countback": finishes,
    }


def _countback(finishes):
    counts = [finishes.count(p) for p in range(1, 21)]
    return tuple(-c for c in counts)


def _key(d):
    if d.get("cust_id") is not None:
        return f"cust:{d['cust_id']}"
    return f"name:{str(d.get('name', '')).strip().lower()}"


def _team_standings(profile, scored, per_round, rules, penalties):
    """Teams score their drivers' points: overall points when that's the only
    championship, class points otherwise."""
    team_of = {_key(d): d.get("team", "").strip() for d in profile.get("drivers", []) if d.get("team", "").strip()}
    if not team_of:
        return []
    totals = {}
    for rd in scored:
        by_team = {}
        for r in rd["results"]:
            team = team_of.get(r["driver"])
            res = per_round[rd["id"]].get(_group_keys(r, rules)[0], {}).get(r["driver"])
            if team and res:
                by_team.setdefault(team, []).append(res["total"])
        for team, pts in by_team.items():
            pts.sort(reverse=True)
            if rules["team_best"]:
                pts = pts[:rules["team_best"]]
            totals[team] = totals.get(team, 0) + sum(pts)
    for d, p in penalties.items():
        if team_of.get(d) in totals:
            totals[team_of[d]] -= p
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    lead = ranked[0][1] if ranked else 0
    return [{"pos": i, "team": t, "points": _round(p), "behind": _round(lead - p)} for i, (t, p) in enumerate(ranked, start=1)]


def projection(profile, live_round):
    """Live "if it finished now": each driver's points and place before and after the race in progress."""
    before = standings(profile)
    after = standings(profile, live_round)
    prior = {(g["key"], r["driver"]): r for g in before["groups"] for r in g["drivers"]}
    groups = []
    for g in after["groups"]:
        rows = []
        for r in g["drivers"]:
            p = prior.get((g["key"], r["driver"]))
            live = next((s for s in r["rounds"] if s["live"]), None)
            rows.append({
                "driver": r["driver"], "name": r["name"], "team": r["team"], "car_number": r["car_number"],
                "points": r["points"], "pos": r["pos"], "behind": r["behind"],
                "points_before": p["points"] if p else 0, "pos_before": p["pos"] if p else None,
                "gained": _round(r["points"] - (p["points"] if p else 0)),
                "race_points": live["points"] if live else 0,
                "race_rank": live["result"]["rank"] if live and live["result"] else None,
            })
        groups.append({"key": g["key"], "name": g["name"], "color": g["color"], "drivers": rows})
    return groups


def live_round_for(champ, session_key=None):
    """The stored round the race in progress counts as, or None.

    None also when that race has already been imported into a round: the
    saved (and perhaps corrected) results then stand.
    """
    rounds = champ["rounds"]
    if session_key and any(rd["session"] == session_key for rd in rounds):
        return None
    if champ["live_round"]:
        rd = next(rd for rd in rounds if rd["id"] == champ["live_round"])
        return None if rd["results"] and rd["session"] else rd
    return next((rd for rd in rounds if not rd["results"]), None)


# -- for the full-screen boards -------------------------------------------------


def _roster(profile):
    return {_key(d): d for d in profile.get("drivers", [])}


def make_standings(profile, group):
    """Manufacturers' points in one championship (a class, or overall): the sum
    of what their drivers scored each round, in the car they drove that round."""
    champ = normalise(profile.get("championship"))
    rules = champ["rules"]
    roster = _roster(profile)
    totals, wins = {}, {}
    for rd in champ["rounds"]:
        if not rd["results"]:
            continue
        scores = score_round(rd, rules).get(group, {})
        for r in rd["results"]:
            res = scores.get(r["driver"])
            make = r.get("make") or (roster.get(r["driver"]) or {}).get("car_make", "")
            if not res or not make:
                continue
            totals[make] = totals.get(make, 0) + res["total"]
            if res["rank"] == 1:
                wins[make] = wins.get(make, 0) + 1
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], -wins.get(kv[0], 0), kv[0].lower()))
    lead = ranked[0][1] if ranked else 0
    return [{"pos": i, "make": m, "points": _round(p), "behind": _round(lead - p), "wins": wins.get(m, 0)}
            for i, (m, p) in enumerate(ranked, start=1)]


def round_results(profile, rd, group):
    """One round's finishing order in one championship, with the points scored."""
    champ = normalise(profile.get("championship"))
    rules = champ["rules"]
    roster = _roster(profile)
    scored = score_round(rd, rules)
    if group in scored:
        scores = scored[group]
    else:
        # A finishing order the points system doesn't score (e.g. overall when
        # points go by class): everyone by position, no points.
        order = sorted((r for r in rd["results"] if r["status"] not in ("dns",)), key=lambda r: r["position"] or 10_000)
        scores = {r["driver"]: {"rank": None if r["status"] == "dsq" else i, "status": r["status"], "short": False,
                                "total": None} for i, r in enumerate(order, start=1)}
    rows = [r for r in rd["results"] if r["driver"] in scores]
    # Grid positions within this championship (a class's own grid order).
    starters = sorted((r for r in rows if r["start_position"]), key=lambda r: r["start_position"])
    grid = {r["driver"]: i for i, r in enumerate(starters, start=1)}
    best = min((r["fastest_lap"] for r in rows if r["fastest_lap"] and r["status"] not in ("dsq", "dns")), default=None)
    out = []
    for r in sorted(rows, key=lambda r: (scores[r["driver"]]["rank"] is None, scores[r["driver"]]["rank"] or 0)):
        s = scores[r["driver"]]
        info = roster.get(r["driver"]) or {}
        out.append({
            "rank": s["rank"], "driver": r["driver"], "name": info.get("name") or r["name"],
            "nickname": info.get("nickname", ""), "car_number": info.get("car_number", ""),
            "team": info.get("team", ""), "class_id": r["class_id"],
            "make": r.get("make") or info.get("car_make", ""),
            "start": grid.get(r["driver"]), "laps": r["laps"], "laps_led": r["laps_led"],
            "fastest_lap": r["fastest_lap"], "has_fastest": best is not None and r["fastest_lap"] == best,
            "status": s["status"], "short": s["short"], "points": s["total"],
        })
    return out


def calendar(profile):
    """The season's rounds, with each championship's winner for rounds already run."""
    champ = normalise(profile.get("championship"))
    rules = champ["rules"]
    roster = _roster(profile)
    out = []
    for i, rd in enumerate(champ["rounds"], start=1):
        winners = []
        if rd["results"]:
            for group, scores in score_round(rd, rules).items():
                win = next((d for d, s in scores.items() if s["rank"] == 1), None)
                if win:
                    info = roster.get(win) or {}
                    name = info.get("name") or next((r["name"] for r in rd["results"] if r["driver"] == win), win)
                    winners.append({"group": group, "name": name, "nickname": info.get("nickname", "")})
            # Overall first, then the classes in the league's order.
            order = [OVERALL] + [c["id"] for c in profile.get("classes", [])]
            winners.sort(key=lambda w: order.index(w["group"]) if w["group"] in order else 99)
        out.append({"round": i, "id": rd["id"], "name": rd["name"], "track": rd["track"], "config": rd["config"],
                    "date": rd["date"], "time": rd["time"], "length": rd["length"], "done": bool(rd["results"]),
                    "multiplier": rd["multiplier"], "winners": winners})
    return out
