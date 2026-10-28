"""Championship points: a league's season, scored to its own rules.

A league profile can carry a ``championship``:

* **rules**: points per finishing position (and optionally per qualifying
  position), any of the bonuses in ``BONUSES``, drop rounds, how far a
  fastest-lap bonus reaches, when a driver counts as classified, and whether
  points are scored per class (one championship per class) or overall.
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

DEFAULT_RULES = {
    "points": [25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
    "qualifying_points": [],
    "bonuses": {k: 0 for k in BONUS_KEYS},
    "scoring": "class",         # "class": a championship per class; "overall": one for everyone
    "drop_rounds": 0,           # each driver's worst N rounds don't count (once they've more than N)
    "fastest_lap_top": 0,       # fastest-lap bonus only if finishing in the top N (0 = anyone)
    "classified_pct": 0,        # must complete this % of the winner's laps to score (0 = off)
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
        "scoring": "overall" if rules.get("scoring") == "overall" else "class",
        "drop_rounds": _num(rules.get("drop_rounds"), 0, lo=0, hi=50, cast=int),
        "fastest_lap_top": _num(rules.get("fastest_lap_top"), 0, lo=0, hi=200, cast=int),
        "classified_pct": _num(rules.get("classified_pct"), 0, lo=0, hi=100),
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
            "date": str(rd.get("date") or "").strip()[:10],
            "multiplier": _num(rd.get("multiplier"), 1.0, lo=0, hi=10),
            "no_drop": bool(rd.get("no_drop")),
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


def _group_key(result, rules):
    return result["class_id"] if rules["scoring"] == "class" else ""


def score_round(rd, rules):
    """Points for every result in a round: {driver: {"total", "position", "bonus", "group", ...}}."""
    groups = {}
    for r in rd["results"]:
        groups.setdefault(_group_key(r, rules), []).append(r)
    out = {}
    for group, results in groups.items():
        out.update(_score_group(group, results, rules, rd["multiplier"]))
    return out


def _score_group(group, results, rules, multiplier):
    bonus_cfg = rules["bonuses"]
    # Finishing order within the group: by position; unplaced (DNS) last.
    order = sorted(results, key=lambda r: (r["status"] == "dns", r["position"] or 10_000))
    max_laps = max((r["laps"] for r in results), default=0)
    min_laps = max_laps * rules["classified_pct"] / 100.0 if rules["classified_pct"] else 0
    rank = {}
    place = 0
    for r in order:
        if r["status"] in ("dsq", "dns"):
            continue
        place += 1
        rank[r["driver"]] = place
    starters = [r for r in results if r["start_position"] and r["status"] != "dns"]
    start_rank = {r["driver"]: i for i, r in enumerate(sorted(starters, key=lambda r: r["start_position"]), start=1)}

    def classified(r):
        return r["driver"] in rank and r["laps"] >= min_laps and (r["status"] == "finished" or rules["dnf_scores"])

    eligible_fl = [r for r in results if r["fastest_lap"] and r["status"] not in ("dsq", "dns")
                   and (not rules["fastest_lap_top"] or rank.get(r["driver"], 10_000) <= rules["fastest_lap_top"])]
    best_lap = min((r["fastest_lap"] for r in eligible_fl), default=None)
    most_led = max((r["laps_led"] for r in results if r["status"] != "dsq"), default=0)
    gains = {r["driver"]: start_rank[r["driver"]] - rank[r["driver"]]
             for r in results if r["status"] == "finished" and r["driver"] in rank and r["driver"] in start_rank}
    most_gained = max(gains.values(), default=0)

    out = {}
    for r in results:
        d = r["driver"]
        entry = {"group": group, "rank": rank.get(d), "status": r["status"], "position": 0, "qualifying": 0,
                 "bonus": {}, "adjust": r["adjust"], "total": 0}
        out[d] = entry
        if r["status"] == "dsq":
            entry["total"] = r["adjust"]
            continue
        if classified(r):
            pts = rules["points"]
            entry["position"] = pts[rank[d] - 1] if rank[d] <= len(pts) else 0
        q = rules["qualifying_points"]
        if start_rank.get(d) and start_rank[d] <= len(q):
            entry["qualifying"] = q[start_rank[d] - 1]
        bonus = entry["bonus"]

        def give(key, times=1):
            if bonus_cfg[key] and times:
                bonus[key] = bonus_cfg[key] * times

        if r["status"] != "dns":
            give("started")
            give("pole", start_rank.get(d) == 1)
        if best_lap is not None and r in eligible_fl and r["fastest_lap"] == best_lap:
            give("fastest_lap")
        if r["laps_led"]:
            give("led_lap")
            give("per_lap_led", r["laps_led"])
            give("most_laps_led", r["laps_led"] == most_led)
        if r["status"] == "finished":
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
    """Driver (per class or overall) and team standings for a league's season.

    ``live_round``: a provisional round (same shape as a stored round) that
    replaces the stored round with the same id, or is added if new.
    """
    champ = profile.get("championship") or normalise({})
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

    # Which group each driver is in: the class of their latest result.
    group_of = {}
    names = {}
    for rd in scored:
        for r in rd["results"]:
            group_of[r["driver"]] = _group_key(r, rules)
            names[r["driver"]] = r["name"] or names.get(r["driver"], "")
    penalties = {}
    licence = {}
    for p in champ["penalties"]:
        penalties[p["driver"]] = penalties.get(p["driver"], 0) + p["points"]
        licence[p["driver"]] = licence.get(p["driver"], 0) + p["licence"]
    for d in list(penalties) + list(licence):
        group_of.setdefault(d, _roster_group(roster.get(d), rules))

    drop = rules["drop_rounds"]
    rows = {}
    for d, group in group_of.items():
        scores = []
        for rd in scored:
            res = per_round[rd["id"]].get(d)
            # Rounds a driver missed score 0 and are the first to drop.
            scores.append({"round": rd["id"], "points": res["total"] if res else 0, "result": res,
                           "droppable": not rd["no_drop"], "dropped": False, "live": rd is live_round})
        droppable = sorted((s for s in scores if s["droppable"]), key=lambda s: (s["points"], s["result"] is not None))
        # Early in a season there's nothing to drop yet: at least one round
        # always counts.
        for s in droppable[:min(drop, len(scores) - 1)]:
            s["dropped"] = True
        kept = sum(s["points"] for s in scores if not s["dropped"])
        total = _round(kept - penalties.get(d, 0))
        finishes = sorted(s["result"]["rank"] for s in scores if s["result"] and s["result"]["rank"])
        rd_info = roster.get(d) or {}
        rows[d] = {
            "driver": d, "name": rd_info.get("name") or names.get(d) or d, "team": rd_info.get("team", ""),
            "car_number": rd_info.get("car_number", ""), "group": group, "points": total,
            "gross": _round(sum(s["points"] for s in scores)), "penalty_points": _round(penalties.get(d, 0)),
            "licence_points": _round(licence.get(d, 0)), "rounds": scores, "wins": finishes.count(1),
            "_countback": finishes,
        }

    groups = {}
    for row in rows.values():
        groups.setdefault(row["group"], []).append(row)
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
        out_groups.append({"key": key, "name": cls["name"] if cls else ("Overall" if not key else key),
                           "color": cls["color"] if cls else None, "drivers": members,
                           "order": list(classes).index(key) if cls else 999})
    out_groups.sort(key=lambda g: g["order"])
    return {
        "rounds": [{"id": rd["id"], "name": rd["name"], "track": rd["track"], "date": rd["date"],
                    "multiplier": rd["multiplier"], "no_drop": rd["no_drop"], "live": rd is live_round,
                    "scored": bool(rd["results"])} for rd in rounds],
        "groups": out_groups,
        "teams": _team_standings(profile, scored, per_round, rules, penalties),
    }


def _countback(finishes):
    counts = [finishes.count(p) for p in range(1, 21)]
    return tuple(-c for c in counts)


def _key(d):
    if d.get("cust_id") is not None:
        return f"cust:{d['cust_id']}"
    return f"name:{str(d.get('name', '')).strip().lower()}"


def _roster_group(entry, rules):
    return (entry or {}).get("class_id", "") if rules["scoring"] == "class" else ""


def _team_standings(profile, scored, per_round, rules, penalties):
    team_of = {_key(d): d.get("team", "").strip() for d in profile.get("drivers", []) if d.get("team", "").strip()}
    if not team_of:
        return []
    totals = {}
    for rd in scored:
        by_team = {}
        for d, res in per_round[rd["id"]].items():
            team = team_of.get(d)
            if team:
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
    prior = {r["driver"]: r for g in before["groups"] for r in g["drivers"]}
    groups = []
    for g in after["groups"]:
        rows = []
        for r in g["drivers"]:
            p = prior.get(r["driver"])
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


def live_round_for(champ):
    """The stored round the race in progress counts as."""
    rounds = champ["rounds"]
    if champ["live_round"]:
        return next(rd for rd in rounds if rd["id"] == champ["live_round"])
    return next((rd for rd in rounds if not rd["results"]), None)
