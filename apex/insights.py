"""What a commentator can say about the race and the season, worked out from
what the app already follows:

* ``LapLog``: each car's race at the line: when it completed each lap and
  where it was then (the catching overlay's gap trend, the recap board's
  position chart).
* ``gap_trend``: two cars' gap lap by lap, how fast it's closing (or growing)
  and how many laps until it's gone.
* ``season_stats`` / ``head_to_head``: a driver's season from the
  championship standings, and two drivers' seasons side by side with how
  often each finished ahead of the other.
* ``talking_points``: things worth saying right now (places gained, a
  championship lead changing, a first win or podium on the cards, a car
  closing in, a different pit strategy).
* ``recap``: the race told afterwards: who gained most, who passed most,
  who was cleanest, and every car's place lap by lap.
"""

CATCH_MIN_RATE = 0.05   # s a lap: closing slower than this isn't "catching"
CATCH_MAX_LAPS = 99     # further off than this: no "catches in N laps"


class LapLog:
    """When each car completed each lap of a race, and its place (overall and
    in class) as it did. Only race time seen as it happens is logged (a car
    first seen mid-race has nothing before that); a lap iRacing counts for a
    car towed to its pit box isn't one it drove, so it's left out."""

    def __init__(self):
        self.reset()

    def reset(self, key=None):
        self.key = key
        self.times = {}        # car -> {lap completed: session time}
        self.places = {}       # car -> {lap completed: overall place}
        self.class_places = {}  # car -> {lap completed: place in class}
        self.start = {}        # car -> {"pos", "class_pos"} at the green
        self._done = {}

    def update(self, key, t, laps_completed, positions, class_positions, towed=(), racing=True):
        if key != self.key:
            self.reset(key)
        if not racing:
            return
        for idx, done in enumerate(laps_completed):
            if done is None or done < 0:
                continue
            prev = self._done.get(idx)
            self._done[idx] = done if prev is None else max(prev, done)
            pos = positions[idx] if idx < len(positions) else 0
            cpos = class_positions[idx] if idx < len(class_positions) else 0
            if done == 0 and idx not in self.start and pos:
                self.start[idx] = {"pos": pos, "class_pos": cpos or None}
            if prev is None or done <= prev or idx in towed:
                continue
            self.times.setdefault(idx, {})[done] = round(t, 3)
            if pos:
                self.places.setdefault(idx, {})[done] = pos
            if cpos:
                self.class_places.setdefault(idx, {})[done] = cpos


def _slope(points):
    """Least-squares slope of [(x, y)], or None with fewer than two."""
    if len(points) < 2:
        return None
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    den = sum((x - mx) ** 2 for x, _ in points)
    return None if den == 0 else sum((x - mx) * (y - my) for x, y in points) / den


def gap_trend(log, ahead, behind, laps=5, now=None):
    """The gap from ``ahead`` back to ``behind`` at the line, lap by lap (the
    last ``laps`` laps both completed), its change per lap (minus: closing)
    and, closing, the laps until it's gone (from ``now``, the gap this
    moment, else the last at the line)."""
    ta, tb = log.times.get(ahead, {}), log.times.get(behind, {})
    common = sorted(set(ta) & set(tb))[-max(2, laps):]
    gaps = [{"lap": lap, "gap": round(tb[lap] - ta[lap], 3)} for lap in common]
    rate = _slope([(g["lap"], g["gap"]) for g in gaps])
    gap = now if now is not None else (gaps[-1]["gap"] if gaps else None)
    catch = None
    if rate is not None and rate < -CATCH_MIN_RATE and gap is not None and gap > 0:
        laps_left = gap / -rate
        catch = round(laps_left, 1) if laps_left <= CATCH_MAX_LAPS else None
    return {"gaps": gaps, "rate": round(rate, 3) if rate is not None else None, "gap": gap,
            "trend": None if rate is None else "closing" if rate < -CATCH_MIN_RATE else "pulling" if rate > CATCH_MIN_RATE else "steady",
            "catch_laps": catch}


# -- the season ---------------------------------------------------------------


def _finishes(row):
    """A standings row's race finishes, round by round: rank or None (DNF / DNS / DSQ / not there)."""
    out = []
    for s in row.get("rounds") or []:
        res = s.get("result")
        if res is None:
            out.append(None)
            continue
        out.append(res.get("rank") if res.get("status") == "finished" and not res.get("short") else None)
    return out


def season_stats(row, form=5):
    """A driver's season from their championship standings row: place, points,
    wins, podiums, best finish, the points to the leader and their last
    ``form`` results ("P3", "DNF", or "–" for a round they missed)."""
    finishes = [r for r in _finishes(row) if r]
    raced = [s for s in row.get("rounds") or [] if s.get("result") is not None]
    recent = []
    for s in raced[-form:]:
        res = s["result"]
        st = res.get("status")
        recent.append("DSQ" if st == "dsq" else "DNS" if st == "dns" else "DNF" if st == "dnf" or res.get("short")
                      else f"P{res['rank']}" if res.get("rank") else "–")
    return {"pos": row.get("pos"), "points": row.get("points"), "behind": row.get("behind"),
            "wins": sum(1 for r in finishes if r == 1), "podiums": sum(1 for r in finishes if r <= 3),
            "best": min(finishes) if finishes else None, "starts": len(raced), "form": recent}


def head_to_head(row_a, row_b):
    """Two drivers' seasons side by side (season_stats each) and, over the
    rounds both finished, how many times each finished ahead."""
    fa, fb = _finishes(row_a), _finishes(row_b)
    ahead_a = sum(1 for a, b in zip(fa, fb) if a and b and a < b)
    ahead_b = sum(1 for a, b in zip(fa, fb) if a and b and b < a)
    return {"a": season_stats(row_a), "b": season_stats(row_b), "ahead": [ahead_a, ahead_b],
            "points_gap": round((row_a.get("points") or 0) - (row_b.get("points") or 0), 2)}


# -- talking points ------------------------------------------------------------


def talking_points(rows, projection=None, season=None, log=None, is_race=True, racing=True,
                   gained=5, closing=0.3, close_gap=3.0):
    """Things worth saying now, most worth it first: [{"key", "kind", "text",
    "cars", "action"}]. ``rows``: the standings rows (car_idx, name, number,
    pos, start_pos, class_pos, class_key, gap, pit_stops, best_lap, laps_down,
    in_world); ``projection``: the championship as if the race ended now
    (groups of drivers with pos / pos_before); ``season``: {car_idx: the
    driver's season_stats before this race}; ``log``: the LapLog."""
    out = []
    if not is_race or not racing:
        return out
    placed = sorted((r for r in rows if r.get("pos")), key=lambda r: r["pos"])
    who = lambda r: f"#{r['number']} {r['name']}" if r.get("number") else r["name"]  # noqa: E731
    # The championship lead changing hands if it finished like this.
    for g in (projection or {}).get("groups") or []:
        top = next((d for d in g.get("drivers") or [] if d.get("pos") == 1), None)
        if top and top.get("pos_before") and top["pos_before"] != 1:
            label = f" ({g['name']})" if len((projection or {}).get("groups") or []) > 1 else ""
            out.append({"key": f"lead:{g['key']}:{top['driver']}", "kind": "championship", "rank": 0,
                        "text": f"If it finishes like this, {top['name']} leads the championship{label}",
                        "cars": [], "action": {"board": "championship", "group": g["key"]}})
    # A first win or podium on the cards (in their class when there are classes).
    classes = {r.get("class_key") for r in placed}
    for r in placed:
        st = (season or {}).get(r["car_idx"])
        place = r.get("class_pos") if len(classes) > 1 else r["pos"]
        if not st or not st.get("starts") or not place or r.get("laps_down"):
            continue
        if place == 1 and st["wins"] == 0:
            out.append({"key": f"firstwin:{r['car_idx']}", "kind": "milestone", "rank": 1,
                        "text": f"{who(r)} is on course for a first win of the season", "cars": [r["car_idx"]],
                        "action": {"season": r["car_idx"]}})
        elif place <= 3 and st["podiums"] == 0:
            out.append({"key": f"firstpodium:{r['car_idx']}", "kind": "milestone", "rank": 2,
                        "text": f"{who(r)} is on course for a first podium of the season (P{place})", "cars": [r["car_idx"]],
                        "action": {"season": r["car_idx"]}})
    # A car closing in on the one ahead (the three closest).
    catching = []
    if log is not None:
        for ahead, r in zip(placed, placed[1:]):
            if r.get("laps_down") or ahead.get("laps_down") or r.get("gap") is None or ahead.get("gap") is None:
                continue
            gap = r["gap"] - ahead["gap"]
            if not 0 < gap <= close_gap:
                continue
            tr = gap_trend(log, ahead["car_idx"], r["car_idx"], now=gap)
            if tr["rate"] is not None and tr["rate"] <= -closing:
                if gap < 0.5:
                    where = "right with them now"
                else:
                    n = max(1, round(tr["catch_laps"])) if tr["catch_laps"] else None
                    where = f"{gap:.1f} s back" + (f", on them in about {n} lap{'s' if n != 1 else ''}" if n else "")
                catching.append((gap, {"key": f"catch:{r['car_idx']}:{ahead['car_idx']}", "kind": "battle", "rank": 3,
                                       "text": f"{who(r)} is closing on {who(ahead)}: {abs(tr['rate']):.1f} s a lap, {where}",
                                       "cars": [r["car_idx"], ahead["car_idx"]], "action": {"catching": [ahead["car_idx"], r["car_idx"]]}}))
    out += [p for _, p in sorted(catching, key=lambda x: x[0])[:3]]
    # Places gained (or lost) since the start.
    for r in placed:
        start, pos = r.get("start_pos"), r["pos"]
        if not start or r.get("in_world") is False:
            continue
        if start - pos >= gained:
            out.append({"key": f"gained:{r['car_idx']}", "kind": "places", "rank": 4,
                        "text": f"{who(r)} has gained {start - pos} places since the start (P{start} → P{pos})", "cars": [r["car_idx"]],
                        "action": {"season": r["car_idx"]}})
        elif pos - start >= gained:
            out.append({"key": f"lost:{r['car_idx']}", "kind": "places", "rank": 5,
                        "text": f"{who(r)} has dropped {pos - start} places since the start (P{start} → P{pos})", "cars": [r["car_idx"]],
                        "action": {"season": r["car_idx"]}})
    # A different pit strategy: fewer stops than every car around them.
    for i, r in enumerate(placed):
        near = [x for x in placed[max(0, i - 2):i + 3] if x is not r and x.get("pit_stops") is not None]
        stops = r.get("pit_stops")
        if stops is None or len(near) < 2:
            continue
        least = min(x["pit_stops"] for x in near)
        if stops < least:
            times = lambda n: "once" if n == 1 else "twice" if n == 2 else f"{n} times"  # noqa: E731
            done = "hasn't pitted" if stops == 0 else f"has pitted {times(stops)}"
            out.append({"key": f"pits:{r['car_idx']}:{stops}", "kind": "strategy", "rank": 6,
                        "text": f"{who(r)} {done}, the cars around them {times(least)} or more", "cars": [r["car_idx"]],
                        "action": {"ov": "strategy"}})
    out.sort(key=lambda p: p["rank"])
    return out


# -- the recap -------------------------------------------------------------------


def recap(rows, log, overtakes=None, group=None, class_key=None):
    """The race told afterwards, for the cars in ``class_key``'s class (None:
    everyone): the biggest gainer (start to now), the most passes on track
    (``overtakes``: {car: count}), the cleanest driver (fewest incident points,
    of those still running at the end, the higher placed first on a tie) and
    each car's place at the end of every lap (the chart: lap 0 = the start)."""
    by_class = class_key is not None
    mine = [r for r in rows if r.get("pos") and (not by_class or r.get("class_key") == class_key)]
    pos_k = "class_pos" if by_class else "pos"
    start_k = "class_start_pos" if by_class else "start_pos"
    out = {"gainer": None, "overtakes": None, "cleanest": None, "chart": {"laps": 0, "cars": []}}
    gains = [(r[start_k] - r[pos_k], r) for r in mine if r.get(start_k) and r.get(pos_k)]
    if gains:
        n, r = max(gains, key=lambda x: (x[0], -x[1][pos_k]))
        if n > 0:
            out["gainer"] = {"car_idx": r["car_idx"], "places": n, "from": r[start_k], "to": r[pos_k]}
    counts = [((overtakes or {}).get(r["car_idx"], 0), r) for r in mine]
    if counts:
        n, r = max(counts, key=lambda x: (x[0], -x[1][pos_k]))
        if n > 0:
            out["overtakes"] = {"car_idx": r["car_idx"], "count": n}
    running = [r for r in mine if r.get("incidents") is not None and r.get("in_world") is not False]
    if running:
        r = min(running, key=lambda x: (x["incidents"], x[pos_k]))
        out["cleanest"] = {"car_idx": r["car_idx"], "incidents": r["incidents"]}
    places = log.class_places if by_class else log.places
    laps = max((max(v) for idx, v in places.items() if v and idx in {r["car_idx"] for r in mine}), default=0)
    cars = []
    for r in sorted(mine, key=lambda x: x[pos_k]):
        seen = places.get(r["car_idx"]) or {}
        start = (log.start.get(r["car_idx"]) or {}).get("class_pos" if by_class else "pos") or r.get(start_k)
        line = [start] + [seen.get(lap) for lap in range(1, laps + 1)]
        if any(p for p in line):
            cars.append({"car_idx": r["car_idx"], "pos": r[pos_k], "places": line})
    out["chart"] = {"laps": laps, "cars": cars}
    return out
