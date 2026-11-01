"""Championship points: a league's season, scored to its own rules.

A league profile can carry a ``championship``:

* **rules**: points per finishing position (and optionally per qualifying
  position), any of the bonuses in ``BONUSES``, drop rounds, how far a
  fastest-lap bonus reaches, how much of the race a driver must cover to
  score, and whether points are scored per class (one championship per
  class), overall, both (each result scores separately in its class's
  championship and the overall one), or class and overall added together
  (``sum``: one total per driver, from their class position and their
  overall position, ranked in each class's table and the overall one). A
  class can have its own points table (``class_points``).
* **secondary classes** (a league class with ``role: "secondary"``, given to
  drivers by hand as their ``class2_id``): a championship of their own,
  whatever the scoring. How it scores is up to the league
  (``secondary_scoring``, by class id): ``own`` (the default) ranks its
  drivers by where they finished among each other, on the class's own
  points table or the class one; ``class`` counts the points each driver
  scores in their main class; ``overall`` the points they score overall.
* **rounds**: each round's results, imported from iRacing or typed in, with a
  points multiplier (double points finales) and a "can't be dropped" flag.
  Rounds next to each other with the same ``event`` are the races of one
  race meeting (e.g. three heat races at one track on one night): each race
  is a round of its own for the points, and the calendar shows the meeting.
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
SCORING = ("class", "overall", "both", "sum", "overall_class")
SECONDARY_SCORING = ("own", "class", "overall")
OVERALL = "overall"  # the key of the overall championship

DEFAULT_RULES = {
    "points": [25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
    "qualifying_points": [],
    "bonuses": {k: 0 for k in BONUS_KEYS},
    "scoring": "class",         # "class": a championship per class; "overall": one for everyone;
                                # "both": a championship per class and one overall, scored separately
                                # "sum": class points + overall points, one total
                                # "overall_class": overall points (by overall position) count in the
                                #   class tables too: each class ranks its drivers on their overall points
    "overall_points": [],       # "both"/"sum": points for overall positions ([] = same as "points")
    "class_points": {},         # a class's own points table, by class id (else "points")
    "secondary_scoring": {},    # a secondary class's points: "own" (default), "class" or "overall", by class id
    "drop_rounds": 0,           # each driver's worst N rounds don't count (once they've more than N)
    "drop_meetings": False,     # a race meeting's races drop together, as one (its points added up)
    # Custom points systems: named points tables a round can use instead of
    # the usual ones (e.g. "Sprint", "Feature"), on when custom_schemes is ticked.
    "custom_schemes": False,
    "schemes": [],              # [{"id", "name", "points": [...], "overall_points": [...] ([] = the same)}]
    "fastest_lap_top": 0,       # fastest-lap bonus only if finishing in the top N (0 = anyone)
    "classified_pct": 75,       # must complete this % of the class winner's laps to score, else DNF (0 = off)
    "dnf_scores": True,         # a DNF still scores the points for where it was classified
    "team_best": 0,             # team championship: best N drivers per team per round (0 = all)
    "team_points": "overall",   # "both": teams score their drivers' "overall" or "class" points
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
        "class_points": {str(k)[:60]: pts for k, v in (rules.get("class_points") or {}).items()
                         if (pts := parse_points(v))} if isinstance(rules.get("class_points"), dict) else {},
        "secondary_scoring": {str(k)[:60]: v for k, v in (rules.get("secondary_scoring") or {}).items()
                              if v in SECONDARY_SCORING and v != "own"} if isinstance(rules.get("secondary_scoring"), dict) else {},
        "drop_rounds": _num(rules.get("drop_rounds"), 0, lo=0, hi=50, cast=int),
        "drop_meetings": bool(rules.get("drop_meetings")),
        "custom_schemes": bool(rules.get("custom_schemes")),
        "schemes": [{"id": _id(sc.get("id")), "name": str(sc.get("name") or "Points").strip()[:40] or "Points",
                     "points": parse_points(sc.get("points", [])), "overall_points": parse_points(sc.get("overall_points", []))}
                    for sc in (rules.get("schemes") or []) if isinstance(sc, dict)][:50],
        "fastest_lap_top": _num(rules.get("fastest_lap_top"), 0, lo=0, hi=200, cast=int),
        "classified_pct": _num(rules.get("classified_pct", DEFAULT_RULES["classified_pct"]), 0, lo=0, hi=100),
        "dnf_scores": bool(rules.get("dnf_scores", True)),
        "team_best": _num(rules.get("team_best"), 0, lo=0, hi=20, cast=int),
        "team_points": "class" if rules.get("team_points") == "class" else "overall",
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
        "gap": _num(r.get("gap"), None, lo=0),  # seconds behind the winner, for the finishing order board
        "race_time": _num(r.get("race_time"), None, lo=0),  # their whole race, in seconds, where known
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
            "event": str(rd.get("event") or "").strip()[:80],     # the race meeting it's a race of
            "track": str(rd.get("track") or "").strip(),
            "config": str(rd.get("config") or "").strip()[:80],      # the track's layout
            "track_id": rd.get("track_id") if isinstance(rd.get("track_id"), int) else None,
            "date": str(rd.get("date") or "").strip()[:10],
            "time": str(rd.get("time") or "").strip()[:5],           # start time, "19:30"
            "length": str(rd.get("length") or "").strip()[:40],     # "60 min", "30 laps", ...
            "multiplier": _num(rd.get("multiplier"), 1.0, lo=0, hi=10),
            "no_drop": bool(rd.get("no_drop")),
            # A race meeting's race: its grid's first N turned round (the starting grid board).
            "reverse_grid": bool(rd.get("reverse_grid")),
            "reverse_top": int(_num(rd.get("reverse_top"), 0, lo=0, hi=60)),
            "scheme": str(rd.get("scheme") or "")[:40],  # a custom points system's id ("" = the usual points)
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


def secondary_classes(profile):
    """{driver: their secondary class id} for drivers in one."""
    ids = {c["id"] for c in profile.get("classes", []) if c.get("role") == "secondary"}
    return {_key(d): d["class2_id"] for d in profile.get("drivers", []) if d.get("class2_id") in ids}


def _group_keys(result, rules, second=None):
    """The championships a result scores in: its class's, the overall one, or
    both; and its driver's secondary class's (``second``: {driver: class id})."""
    if rules["scoring"] == "overall":
        keys = [OVERALL]
    elif rules["scoring"] in ("both", "sum", "overall_class"):
        keys = [result["class_id"], OVERALL]
    else:
        keys = [result["class_id"]]
    extra = (second or {}).get(result.get("driver"))
    return keys + [extra] if extra and extra not in keys else keys


def _points_table(group, rules):
    if group in rules["class_points"]:
        return rules["class_points"][group]
    if group == OVERALL and rules["overall_points"]:
        return rules["overall_points"]
    return rules["points"]


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


def round_rules(rd, rules):
    """The rules a round is scored with: its custom points system's tables
    (with custom points systems on), else the usual ones."""
    if not rules.get("custom_schemes") or not rd.get("scheme"):
        return rules
    scheme = next((sc for sc in rules.get("schemes") or [] if sc["id"] == rd["scheme"]), None)
    if scheme is None or not scheme["points"]:
        return rules
    return dict(rules, points=scheme["points"], overall_points=scheme["overall_points"], class_points={})


def score_round(rd, rules, second=None):
    """Points for every result in a round: {championship key: {driver: {"total", "position", "bonus", ...}}}.

    ``second``: {driver: secondary class id} (``secondary_classes``).
    A provisional round (the race in progress) skips the race-distance rule:
    mid-race, nobody has covered the distance yet. A round with a custom
    points system is scored with its tables (``round_rules``).
    """
    rules = round_rules(rd, rules)
    groups = {}
    for r in rd["results"]:
        for key in _group_keys(r, rules, second):
            groups.setdefault(key, []).append(r)
    distance = {} if rd.get("provisional") else race_distance(rd["results"])
    added = rules["scoring"] == "sum"
    out = {key: _score_group(key, results, rules, rd["multiplier"], distance, bonuses=not (added and key == OVERALL))
           for key, results in groups.items()}
    if added and OVERALL in out:
        _add_overall(out, rd, rules)
    if rules["scoring"] == "overall_class" and OVERALL in out:
        _overall_as_class(out, rd)
    _secondary_points(out, rd, rules, second, distance)
    return out


def _secondary_points(scores, rd, rules, second, distance):
    """Secondary classes that count their drivers' class or overall points:
    those points, in the order the drivers finished among themselves."""
    for group in {c for c in (second or {}).values() if rules["secondary_scoring"].get(c) in ("class", "overall")}:
        own = scores.get(group)
        if not own:
            continue
        how = rules["secondary_scoring"][group]
        overall = scores.get(OVERALL)
        if how == "overall" and overall is None:
            # Scored per class only: the overall points are worked out for this.
            overall = _score_group(OVERALL, rd["results"], rules, rd["multiplier"], distance)
        for r in rd["results"]:
            entry = own.get(r["driver"])
            source = (overall if how == "overall" else scores.get(r["class_id"], {})).get(r["driver"]) if entry else None
            if source:
                own[r["driver"]] = dict(entry, **{k: source[k] for k in ("position", "qualifying", "bonus", "adjust", "total")
                                                  if k in source}, from_group=OVERALL if how == "overall" else r["class_id"])


def _overall_as_class(scores, rd):
    """Overall points are class points: each driver's class score is what
    they scored overall (their overall position's points, bonuses and all);
    their place in the class (wins, countback) stays their class finish."""
    overall = scores[OVERALL]
    for r in rd["results"]:
        d = r["driver"]
        mine, ov = scores.get(r["class_id"], {}).get(d), overall.get(d)
        if mine and ov:
            scores[r["class_id"]][d] = dict(mine, **{k: ov[k] for k in ("position", "qualifying", "bonus", "adjust", "total") if k in ov},
                                            from_group=OVERALL)


def _add_overall(scores, rd, rules):
    """Class and overall added together: each driver's class score gets their
    overall position's points, and the overall table ranks those totals."""
    overall = scores[OVERALL]
    for r in rd["results"]:
        d = r["driver"]
        mine, ov = scores.get(r["class_id"], {}).get(d), overall.get(d)
        if not mine or not ov:
            continue
        mine["overall_position"] = ov["position"]
        mine["total"] = _round(mine["total"] + ov["position"] * rd["multiplier"])
        overall[d] = dict(mine, group=OVERALL, rank=ov["rank"])


def _score_group(group, results, rules, multiplier, distance, bonuses=True):
    bonus_cfg = rules["bonuses"] if bonuses else {k: 0 for k in BONUS_KEYS}
    points = _points_table(group, rules)
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
                 "qualifying": 0, "bonus": {}, "adjust": r["adjust"], "total": _round(r["adjust"])}
        out[d] = entry
        # Disqualified, or short of the race distance: no points at all.
        if st == "dsq" or d in short:
            continue
        if d in rank and (st == "finished" or rules["dnf_scores"]):
            entry["position"] = points[rank[d] - 1] if rank[d] <= len(points) else 0
        q = rules["qualifying_points"] if bonuses else []
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
    second = secondary_classes(profile)
    per_round = {rd["id"]: score_round(rd, rules, second) for rd in scored}

    # Which championships each driver is in: their latest result's class
    # (a driver who changes class moves with it), and/or overall.
    latest = {}
    names = {}
    for rd in scored:
        for r in rd["results"]:
            latest[r["driver"]] = _group_keys(r, rules, second)
            names[r["driver"]] = r["name"] or names.get(r["driver"], "")
    penalties = {}
    licence = {}
    # A penalty picked from the roster for a driver whose results are under
    # another key (e.g. results saved before their iRacing ID was in the
    # roster): it's theirs, matched by name, so it comes off every
    # championship they score in (their class's as well as overall).
    def plain(name):  # "(P) Dave  PRICE" -> "dave price"
        return " ".join(re.sub(r"^\s*\([^()]*\)\s*", "", str(name or "")).lower().split())

    by_name = {}
    for d in latest:
        for n in {plain((roster.get(d) or {}).get("name")), plain(names.get(d)),
                  plain(d[len("name:"):]) if d.startswith("name:") else ""}:
            if n:
                by_name.setdefault(n, d)
    for p in champ["penalties"]:
        d = p["driver"]
        if d not in latest:
            entry = roster.get(d) or {}
            for n in (plain(entry.get("name")), plain(entry.get("nickname")), plain(d[len("name:"):]) if d.startswith("name:") else ""):
                if n and n in by_name:
                    d = by_name[n]
                    break
        penalties[d] = penalties.get(d, 0) + p["points"]
        licence[d] = licence.get(d, 0) + p["licence"]
    for d in list(penalties) + list(licence):
        if d not in latest:
            latest[d] = _group_keys({"driver": d, "class_id": ((roster.get(d) or {}).get("class_id", "")).replace("-", "")}, rules, second)

    drop = rules["drop_rounds"]
    groups = {}
    for d, keys in latest.items():
        for group in keys:
            groups.setdefault(group, []).append(_driver_row(d, group, scored, per_round, live_round, drop,
                                                            penalties, licence, roster, names, rules["drop_meetings"]))
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
        secondary = bool(cls) and cls.get("role") == "secondary"
        if key == OVERALL:
            name, order = "Overall", -1
        elif cls:
            # Secondary classes after the main ones.
            name, order = cls["name"], list(classes).index(key) + (500 if secondary else 0)
        else:
            name, order = (key.replace("iracing:", "") or "No class"), 999
        out_groups.append({"key": key, "name": name, "color": cls["color"] if cls else None,
                           "drivers": members, "order": order, "secondary": secondary,
                           "basis": _basis(key, secondary, rules)})
    out_groups.sort(key=lambda g: g["order"])
    return {
        "rounds": [{"id": rd["id"], "name": rd["name"], "track": rd["track"], "date": rd["date"],
                    "multiplier": rd["multiplier"], "no_drop": rd["no_drop"], "live": rd is live_round,
                    "scored": bool(rd["results"])} for rd in rounds],
        "groups": out_groups,
        "teams": _team_standings(profile, scored, per_round, rules, penalties),
    }


def _points_text(table):
    return f"{', '.join(str(p) for p in table[:6])}{'…' if len(table) > 6 else ''}"


def _basis(key, secondary, rules):
    """What a table is scored on, so class and overall totals make sense side by side."""
    if secondary:
        how = rules["secondary_scoring"].get(key, "own")
        if how == "class":
            return "The points its drivers score in their own class"
        if how == "overall":
            return "The points its drivers score overall"
        return f"Scored on positions among its drivers: {_points_text(_points_table(key, rules))}"
    if rules["scoring"] == "sum":
        overall = _points_text(_points_table(OVERALL, rules))
        if key == OVERALL:
            return f"Class points + overall points ({overall})"
        return f"Class points ({_points_text(_points_table(key, rules))}) + overall points ({overall})"
    if rules["scoring"] == "overall_class" and key != OVERALL:
        return f"Overall points, by overall position: {_points_text(_points_table(OVERALL, rules))}"
    basis = "overall positions" if key == OVERALL else "class positions"
    return f"Scored on {basis}: {_points_text(_points_table(key, rules))}"


def _driver_row(d, group, scored, per_round, live_round, drop, penalties, licence, roster, names, by_meeting=False):
    scores = []
    for rd in scored:
        res = per_round[rd["id"]].get(group, {}).get(d)
        # Rounds a driver missed score 0 and are the first to drop.
        scores.append({"round": rd["id"], "points": res["total"] if res else 0, "result": res,
                       "droppable": not rd["no_drop"], "dropped": False, "live": rd is live_round})
    # What drops: each round, or with by_meeting a race meeting's races as one
    # (their points added up; it can drop only if none of them is "can't drop").
    units = []
    for rd, s in zip(scored, scores):
        if by_meeting and rd.get("event") and units and units[-1]["event"] == rd["event"]:
            units[-1]["scores"].append(s)
        else:
            units.append({"event": rd.get("event") if by_meeting else None, "scores": [s]})
    droppable = sorted((u for u in units if all(s["droppable"] for s in u["scores"])),
                       key=lambda u: (sum(s["points"] for s in u["scores"]), any(s["result"] is not None for s in u["scores"])))
    # Early in a season there's nothing to drop yet: at least one round
    # (or meeting) always counts.
    for u in droppable[:min(drop, len(units) - 1)]:
        for s in u["scores"]:
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


def _team_group(result, rules):
    """Which of a result's points count for its team."""
    if rules["scoring"] == "sum":
        return result["class_id"]  # the same total as overall
    if rules["scoring"] == "both":
        return OVERALL if rules["team_points"] == "overall" else result["class_id"]
    return _group_keys(result, rules)[0]


def _dropped(scored, points, rules):
    """The rounds whose points don't count, by id: the worst ``drop_rounds``
    (with ``drop_meetings`` a race meeting's races as one, their points added
    up), never a "can't drop" one, and always at least one round (or meeting)
    still counting. ``points``: {round id: points} (a round missing scored 0)."""
    drop = rules["drop_rounds"]
    if not drop:
        return set()
    units = []
    for rd in scored:
        p = points.get(rd["id"]) or 0
        if rules["drop_meetings"] and rd.get("event") and units and units[-1]["event"] == rd["event"]:
            u = units[-1]
            u["ids"].append(rd["id"])
            u["points"] += p
            u["ok"] = u["ok"] and not rd["no_drop"]
        else:
            units.append({"event": rd.get("event") if rules["drop_meetings"] else None, "ids": [rd["id"]],
                          "points": p, "ok": not rd["no_drop"]})
    worst = sorted((u for u in units if u["ok"]), key=lambda u: u["points"])
    return {i for u in worst[:min(drop, len(units) - 1)] for i in u["ids"]}


def _team_standings(profile, scored, per_round, rules, penalties):
    """Teams score their drivers' points (with class and overall championships,
    the overall points unless the rules say class).

    Each team: its total, points per round, wins (its drivers' wins in the
    championship it scores in) and what each driver brought in.
    """
    roster = {_key(d): d for d in profile.get("drivers", []) if d.get("team", "").strip()}
    if not roster:
        return []
    rounds, wins, by_round = {}, {}, {}
    for rd in scored:
        by_team = {}
        for r in rd["results"]:
            d = roster.get(r["driver"])
            res = per_round[rd["id"]].get(_team_group(r, rules), {}).get(r["driver"])
            if d and res:
                by_team.setdefault(d["team"].strip(), []).append((res["total"], r["driver"], res["rank"]))
        for team, entries in by_team.items():
            entries.sort(key=lambda e: -e[0])
            counted = entries[:rules["team_best"]] if rules["team_best"] else entries
            pts = _round(sum(e[0] for e in counted))
            rounds.setdefault(team, {})[rd["id"]] = pts
            wins[team] = wins.get(team, 0) + sum(1 for e in entries if e[2] == 1)
            for total, driver, _ in counted:
                m = by_round.setdefault(team, {}).setdefault(rd["id"], {})
                m[driver] = m.get(driver, 0) + total
    # Drop rounds: a team's worst rounds don't count (nor what its drivers scored in them).
    totals, members, dropped = {}, {}, {}
    for team, per in rounds.items():
        dropped[team] = _dropped(scored, per, rules)
        totals[team] = sum(p for rid, p in per.items() if rid not in dropped[team])
        for rid, scores in by_round.get(team, {}).items():
            if rid in dropped[team]:
                continue
            for driver, total in scores.items():
                members.setdefault(team, {})[driver] = members.setdefault(team, {}).get(driver, 0) + total
    pens = {}
    for d, p in penalties.items():
        team = roster[d]["team"].strip() if d in roster else None
        if team in totals:
            totals[team] -= p
            pens[team] = pens.get(team, 0) + p
            members.setdefault(team, {})[d] = members[team].get(d, 0) - p
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], -wins.get(kv[0], 0), kv[0].lower()))
    lead = ranked[0][1] if ranked else 0
    out = []
    for i, (team, pts) in enumerate(ranked, start=1):
        drivers = sorted(members.get(team, {}).items(), key=lambda kv: -kv[1])
        out.append({
            "pos": i, "team": team, "points": _round(pts), "behind": _round(lead - pts),
            "ahead": _round(ranked[i - 2][1] - pts) if i > 1 else None,
            "wins": wins.get(team, 0), "penalty_points": _round(pens.get(team, 0)),
            "rounds": [{"round": rd["id"], "points": rounds.get(team, {}).get(rd["id"]), "dropped": rd["id"] in dropped.get(team, ())}
                       for rd in scored],
            "drivers": [{"driver": d, "name": roster[d].get("name", ""), "nickname": roster[d].get("nickname", ""),
                         "points": _round(p)} for d, p in drivers],
        })
    return out


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
    per, wins = {}, {}
    scored = [rd for rd in champ["rounds"] if rd["results"]]
    for rd in scored:
        scores = score_round(rd, rules, secondary_classes(profile)).get(group, {})
        for r in rd["results"]:
            res = scores.get(r["driver"])
            make = r.get("make") or (roster.get(r["driver"]) or {}).get("car_make", "")
            if not res or not make:
                continue
            per.setdefault(make, {})[rd["id"]] = per.setdefault(make, {}).get(rd["id"], 0) + res["total"]
            if res["rank"] == 1:
                wins[make] = wins.get(make, 0) + 1
    # Drop rounds: a manufacturer's worst rounds don't count, as for the drivers.
    totals = {}
    for make, rounds in per.items():
        out = _dropped(scored, rounds, rules)
        totals[make] = sum(p for rid, p in rounds.items() if rid not in out)
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], -wins.get(kv[0], 0), kv[0].lower()))
    lead = ranked[0][1] if ranked else 0
    return [{"pos": i, "make": m, "points": _round(p), "behind": _round(lead - p), "wins": wins.get(m, 0)}
            for i, (m, p) in enumerate(ranked, start=1)]


def round_results(profile, rd, group):
    """One round's finishing order in one championship, with the points scored."""
    champ = normalise(profile.get("championship"))
    rules = champ["rules"]
    roster = _roster(profile)
    second = secondary_classes(profile)
    scored = score_round(rd, rules, second)
    if group in scored:
        scores = scored[group]
    else:
        # A finishing order the points system doesn't score (e.g. overall when
        # points go by class): everyone in it (everyone, or the class's drivers)
        # by position, no points.
        mine = [r for r in rd["results"] if group == OVERALL or r["class_id"] == group or second.get(r["driver"]) == group]
        order = sorted((r for r in mine if r["status"] not in ("dns",)), key=lambda r: r["position"] or 10_000)
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
            "status": s["status"], "short": s["short"], "points": s["total"], "gap": r.get("gap"),
            "race_time": r.get("race_time"),
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
            for group, scores in score_round(rd, rules, secondary_classes(profile)).items():
                win = next((d for d, s in scores.items() if s["rank"] == 1), None)
                if win:
                    info = roster.get(win) or {}
                    name = info.get("name") or next((r["name"] for r in rd["results"] if r["driver"] == win), win)
                    winners.append({"group": group, "name": name, "nickname": info.get("nickname", "")})
            # Overall first, then the classes in the league's order.
            order = [OVERALL] + [c["id"] for c in profile.get("classes", [])]
            winners.sort(key=lambda w: order.index(w["group"]) if w["group"] in order else 99)
        out.append({"round": i, "id": rd["id"], "name": rd["name"], "event": rd["event"], "track": rd["track"], "config": rd["config"],
                    "date": rd["date"], "time": rd["time"], "length": rd["length"], "done": bool(rd["results"]),
                    "multiplier": rd["multiplier"], "winners": winners})
    return out
