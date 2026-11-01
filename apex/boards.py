"""Full-screen boards: championship tables, the season calendar and race results.

The commentator puts one on screen from the Boards tab (``board.html`` is the
OBS page). What each board shows is set in its settings (see ``overlays``).
Boards are built from the active league's saved championship.
"""

from . import championship
from .league import logo_url, strip_class_prefix
from .makes import logo_for as make_logo

KINDS = ("championship", "teams", "makes", "calendar", "results", "qualifying", "grid")
TITLES = {
    "championship": "Championship standings", "teams": "Teams' championship", "makes": "Manufacturers' championship",
    "calendar": "Season calendar", "results": "Finishing order", "qualifying": "Qualifying", "grid": "Starting grid",
}


def _group_info(league, key):
    """(name, colour, logo url) of a championship: a league class, or overall."""
    if key == championship.OVERALL:
        return "Overall", None, None
    for c in league.get("classes", []):
        if c["id"] == key:
            return c["name"], c["color"], logo_url(league["id"], c.get("logo"))
    return (str(key).replace("iracing:", "") or "Drivers"), None, None


def options(league):
    """What the Boards tab can offer: the league's championships and rounds."""
    if not league:
        return {"groups": [], "rounds": [], "classes": []}
    table = championship.standings(league)
    groups = []
    for g in table["groups"]:
        name, color, _ = _group_info(league, g["key"])
        groups.append({"key": g["key"], "name": name, "color": color})
    rounds = [{"id": r["id"], "name": r["name"], "track": r["track"], "scored": r["scored"]} for r in table["rounds"]]
    # Every class of the league (main and secondary), for a finishing order of
    # any of them, whether or not it has points of its own yet.
    classes = [{"key": c["id"], "name": c.get("name") or c["id"], "color": c.get("color") or None,
                "secondary": c.get("role") == "secondary"} for c in league.get("classes", []) if c.get("id")]
    return {"groups": groups, "rounds": rounds, "classes": classes, "teams": bool(table["teams"]),
            "has_teams": any(d.get("team") for d in league.get("drivers", []))}


def _person(league, name, nickname):
    """A driver's full name as the stream shows it (see App._stream_name):
    without its "(P)" class tag when the league says so. The nickname is
    separate (the boards' "Nickname" name style)."""
    if league.get("strip_class_prefix"):
        return strip_class_prefix(name)
    return name


def _banner(league, settings):
    """The league banner this board shows, or None."""
    place = settings["banner"]
    if place == "none":
        return None
    shape = "horizontal" if place in ("top", "bottom") else "vertical"
    banners = league.get("banners", [])
    pick = next((b for b in banners if b["id"] == settings.get("banner_id")), None) or \
        next((b for b in banners if b["orientation"] == shape), None)
    if not pick:
        return None
    return {"url": logo_url(league["id"], pick["file"]), "place": place, "orientation": pick["orientation"]}


def sponsors(league, ids):
    """The league's sponsor logos picked by ``ids`` ("" = all, "none" = none): [{id, name, url}]."""
    wanted = None if not ids else set(ids.split(","))
    return [{"id": s["id"], "name": s["name"], "url": logo_url(league["id"], s["file"])}
            for s in league.get("sponsors", []) if wanted is None or s["id"] in wanted]


def _sponsor_strip(league, settings):
    """Sponsor logos on this board, or None."""
    if settings["sponsors"] == "none":
        return None
    logos = sponsors(league, settings["sponsor_ids"])
    return {"place": settings["sponsors"], "logos": logos} if logos else None


def build(league, board, settings, live_results=None):
    """The board on screen, ready to draw, or None.

    ``live_results``: for a finishing order from a session of the event in
    iRacing ("live", or "session:<number>"): {"name", "race", "results"}."""
    if not league or not board.get("kind"):
        return None
    kind = board["kind"]
    params = board.get("params") or {}
    cfg = settings[f"board_{kind}"]
    out = {"kind": kind, "group": params.get("group") or "", "overall": (params.get("group") or championship.OVERALL) == championship.OVERALL, "round": params.get("round") or "", "league": league["name"], "title": TITLES[kind], "subtitle": "",
           "banner": _banner(league, cfg), "sponsors": _sponsor_strip(league, cfg), "settings": cfg, "accent": None, "group_logo": None,
           "league_logo": logo_url(league["id"], league.get("logo")) if cfg["league_logo"] and league.get("logo") else None}
    group = params.get("group") or championship.OVERALL
    if kind in ("championship", "makes", "results", "qualifying", "grid"):
        name, color, logo = _group_info(league, group)
        out["subtitle"], out["accent"], out["group_logo"] = name, color, logo
    if cfg.get("accent") == "color":
        out["accent"] = cfg.get("accent_color")  # the board's own accent colour, picked in its settings
    team_logos = {t["name"].lower(): logo_url(league["id"], t.get("logo")) for t in league.get("teams", [])}
    numbers = {championship._key(d): d.get("car_number", "") for d in league.get("drivers", [])}

    if kind == "championship":
        table = championship.standings(league)
        # Each driver's class colour (their latest result's class), for the number.
        colours = {c["id"]: c["color"] for c in league.get("classes", [])}
        class_of = {}
        for rd in championship.normalise(league.get("championship"))["rounds"]:
            for r in rd["results"]:
                class_of[r["driver"]] = r["class_id"]
        g = next((x for x in table["groups"] if x["key"] == group), None)
        rounds = [r for r in table["rounds"] if r["scored"]]
        last = rounds[-cfg["rounds"]:] if cfg["rounds"] else []
        rows = []
        for d in (g["drivers"] if g else []):
            roster = next((x for x in league.get("drivers", []) if championship._key(x) == d["driver"]), {})
            make = roster.get("car_make", "")
            rows.append({
                "pos": d["pos"], "name": _person(league, d["name"], roster.get("nickname", "")),
                "nickname": roster.get("nickname", ""),
                "number": numbers.get(d["driver"], ""), "team": d["team"],
                "class_color": colours.get(class_of.get(d["driver"], "")),
                "team_logo": team_logos.get((d["team"] or "").lower()), "make": make, "make_logo": make_logo(make),
                "points": d["points"], "behind": d["behind"], "wins": d["wins"], "penalty": d["penalty_points"],
                "rounds": [next(({"points": s["points"], "dropped": s["dropped"], "played": s["result"] is not None}
                                 for s in d["rounds"] if s["round"] == r["id"]), None) for r in last],
            })
        # Points to the driver one place up.
        for above, row in zip(rows, rows[1:]):
            row["ahead"] = championship._round(above["points"] - row["points"])
        out["round_names"] = [f"R{rounds.index(r) + 1}" for r in last]
        out["rows"] = rows
    elif kind == "teams":
        table = championship.standings(league)
        info = {t["name"].lower(): t for t in league.get("teams", [])}
        rounds = [r for r in table["rounds"] if r["scored"]]
        last = rounds[-cfg["rounds"]:] if cfg["rounds"] else []
        out["round_names"] = [f"R{rounds.index(r) + 1}" for r in last]
        rows = []
        for t in table["teams"]:
            team = info.get(t["team"].lower(), {})
            per = {s["round"]: s["points"] for s in t["rounds"]}
            rows.append(dict(t, team_logo=team_logos.get(t["team"].lower()), color=team.get("color") or None,
                             drivers=[_person(league, d["name"], d["nickname"]) for d in t["drivers"]],
                             people=[{"name": _person(league, d["name"], d["nickname"]), "nickname": d["nickname"]} for d in t["drivers"]],
                             rounds=[per.get(r["id"]) for r in last]))
        out["rows"] = rows
    elif kind == "makes":
        out["rows"] = [dict(m, make_logo=make_logo(m["make"])) for m in championship.make_standings(league, group)]
    elif kind == "calendar":
        # The league's own calendar graphic, when they have one and want it.
        if cfg["style"] == "image" and league.get("calendar_image"):
            out["image"] = logo_url(league["id"], league["calendar_image"])
        cal = championship.calendar(league)
        for r in cal:
            for w in r["winners"]:
                w["name"] = _person(league, w["name"], w["nickname"])
                w["group_name"], w["color"], _ = _group_info(league, w["group"])
        cal = meetings(cal)
        nxt = next((r for r in cal if not r["done"]), None)
        for r in cal:
            r["next"] = r is nxt
        out["rows"] = cal
    elif kind == "results":
        champ = championship.normalise(league.get("championship"))
        source = params.get("round") or "latest"
        live = (source == "live" or source.startswith("session:")) and live_results is not None
        if live:
            rd = {"id": "live", "name": live_results["name"], "track": "", "multiplier": 1.0,
                  "results": live_results["results"], "provisional": True}
            out["title"] = "Running order" if source == "live" else f"{live_results['name']} result"  # named as the tower names it
        else:
            scored = [r for r in champ["rounds"] if r["results"]]
            rd = next((r for r in scored if r["id"] == source), scored[-1] if scored else None)
        rows = []
        if rd:
            for r in championship.round_results(league, rd, group):
                rows.append(dict(r, name=_person(league, r["name"], r["nickname"]),
                                 class_color=next((c["color"] for c in league.get("classes", []) if c["id"] == r["class_id"]), None),
                                 number=r["car_number"], team_logo=team_logos.get((r["team"] or "").lower()),
                                 make_logo=make_logo(r["make"]),
                                 gained=(r["start"] - r["rank"]) if r["start"] and r["rank"] else None))
            if live and not live_results["race"]:
                for row in rows:  # practice or qualifying: an order by best lap, not points
                    row.update(points=None, gained=None, gap=None)
            _gaps(rows, by_lap=live and not live_results["race"])
            if rd["id"] != "live":
                n = champ["rounds"].index(rd) + 1
                name = " · ".join(filter(None, [rd["event"], rd["name"]]))
                out["title"] = f"{name} result" if name else f"Round {n} result"
                out["subtitle"] = " · ".join(filter(None, [out["subtitle"], rd["track"]]))
        out["rows"] = rows
    elif kind == "qualifying":
        rows = []
        if live_results:
            rd = {"id": "live", "name": live_results["name"], "track": "", "multiplier": 1.0,
                  "results": live_results["results"], "provisional": True}
            for r in championship.round_results(league, rd, group):
                if r["status"] == "dns":
                    continue  # no lap set
                rows.append(dict(r, name=_person(league, r["name"], r["nickname"]), class_color=_class_color(league, r["class_id"]),
                                 number=r["car_number"], team_logo=team_logos.get((r["team"] or "").lower()),
                                 make_logo=make_logo(r["make"])))
            _gaps(rows, by_lap=True)
            out["title"] = live_results["name"].title()  # Qualifying, Lone Qualifying, Heat 1 Qualifying...
        out["rows"] = rows
    elif kind == "grid":
        rows = []
        data = live_results or {"rows": [], "name": "Race", "from": "qualifying"}
        mine = [e for e in data["rows"] if group == championship.OVERALL or e["class_id"] == group or e.get("class2_id") == group]
        roster = {championship._key(d): d for d in league.get("drivers", [])}
        best = {}
        for e in mine:
            if e["qual_time"]:
                best[e["class_id"]] = min(best.get(e["class_id"], e["qual_time"]), e["qual_time"])
        in_class = {}
        for i, e in enumerate(mine, start=1):
            in_class[e["class_id"]] = in_class.get(e["class_id"], 0) + 1
            info = roster.get(e["driver"]) or {}
            pole = best.get(e["class_id"])
            rows.append(dict(e, pos=i, class_pos=in_class[e["class_id"]], number=e["car_number"] or info.get("car_number", ""),
                             class_color=_class_color(league, e["class_id"]), team_logo=team_logos.get((e["team"] or "").lower()),
                             make_logo=make_logo(e["make"]),
                             qual_gap=round(e["qual_time"] - pole, 3) if e["qual_time"] and pole and e["qual_time"] > pole else None))
        # Row by row: the rows (two cars each) shown so far; the rest wait, hidden.
        total = -(-len(rows) // 2)
        if cfg.get("grid_reveal") == "rows" and rows:
            try:
                shown = int(params.get("reveal") or 1)
            except (TypeError, ValueError):
                shown = 1
            shown = min(max(shown, 1), total)
            for i, row in enumerate(rows):
                row["hidden"] = i >= shown * 2
            out["reveal"] = shown
        out["reveal_total"] = total
        out["title"] = f"{data['name']} · starting grid" if data["name"] else "Starting grid"
        out["grid_from"] = data["from"]
        out["rows"] = rows
    return _page(out, cfg, params)


def _class_color(league, class_id):
    return next((c["color"] for c in league.get("classes", []) if c["id"] == class_id), None)


def _gaps(rows, by_lap=False):
    """Each finisher's gap to the winner and to the car ahead (``gap`` /
    ``interval`` seconds, or ``gap_laps`` / ``interval_laps`` laps down; a
    DNF, DNS or DSQ has ``out``: what to show there instead). ``by_lap``:
    practice or qualifying, gaps between best laps."""
    ahead = None
    leader = None
    for row in rows:
        row["_gap"] = row.get("gap")  # seconds behind the overall winner, as saved
    # The winner is what the gaps are measured from: 0 behind themselves,
    # also when no gap came with them (no race times yet, an earlier heat, a
    # replay), which used to leave every gap on the board blank.
    first = next((r for r in rows if not by_lap and r.get("rank") is not None and r["status"] == "finished" and not r.get("short")), None)
    if first is not None and first["_gap"] is None:
        first["_gap"] = 0.0
    for row in rows:
        row.update(gap_laps=None, interval=None, interval_laps=None,
                   out="DNF" if row.get("short") else (row["status"].upper() if row["status"] != "finished" else None))
        if by_lap:
            t = row.get("fastest_lap")
            row["gap"] = None
            if t is None or row["out"]:
                continue
            if leader is not None:
                row["gap"] = round(t - leader, 3)
                row["interval"] = round(t - ahead, 3)
            leader = t if leader is None else leader
            ahead = t
            continue
        if row["out"] or row.get("rank") is None:
            row["gap"] = None
            continue
        if leader is None:
            leader, ahead = row, row
            row["gap"], row["winner"] = None, True  # the winner: their laps or race time instead
            continue
        for key, other in (("gap", leader), ("interval", ahead)):
            down = (other.get("laps") or 0) - (row.get("laps") or 0)
            if down > 0:
                row[f"{key}_laps"], row[key] = down, None
            else:
                mine, theirs = row["_gap"], other["_gap"]
                row[key] = round(max(mine - theirs, 0.0), 3) if mine is not None and theirs is not None else None
        ahead = row
    for row in rows:
        row.pop("_gap", None)


def _page(out, cfg, params):
    """Just this page of the board's rows: ``rows`` (the setting) a page, the
    rest on the pages after it. Positions carry on from page to page."""
    rows = out["rows"]
    n = max(1, int(cfg.get("rows") or 1)) if not out.get("image") else max(1, len(rows))
    # keep_leader: the first row (the leader, the winner) heads every page,
    # the rest carrying on from page to page under it.
    keep = bool(cfg.get("keep_leader")) and out["kind"] != "calendar" and n > 1 and len(rows) > n
    pages = max(1, 1 + -(-(len(rows) - n) // (n - 1))) if keep else max(1, -(-len(rows) // n))
    try:
        page = int(params.get("page") or 0)
    except (TypeError, ValueError):
        page = 0
    page = min(max(page, 0), pages - 1)
    if keep and page:
        start = n + (page - 1) * (n - 1)
        shown = [dict(rows[0], kept=True)] + rows[start:start + n - 1]
    else:
        shown = rows[page * n:(page + 1) * n]
    out.update(rows=shown, page=page, pages=pages)
    return out


def meetings(cal):
    """The calendar with each race meeting (rounds next to each other with the
    same ``event``) as one entry: its first race's details, ``last`` (its last
    round's number), each race's winners named by race, and ``sessions``: each
    race's name and length (Race 1 · 20 min) for a meeting's card."""
    out = []
    for r in cal:
        prev = out[-1] if out else None
        if r["event"] and prev and prev.get("event") == r["event"]:
            prev["last"] = r["round"]
            prev["races"].append(r["name"])
            prev["sessions"].append({"name": r["name"], "length": r.get("length", ""), "time": r.get("time", ""),
                                     "winners": list(r["winners"]), "done": r["done"]})
            prev["done"] = prev["done"] and r["done"]
            prev["winners"] += [dict(w, race=r["name"]) for w in r["winners"]]
            continue
        entry = dict(r, last=None, races=[r["name"]],
                     sessions=[{"name": r["name"], "length": r.get("length", ""), "time": r.get("time", ""),
                                "winners": list(r["winners"]), "done": r["done"]}])
        if r["event"]:
            entry["name"] = r["event"]
            entry["winners"] = [dict(w, race=r["name"]) for w in r["winners"]]
        out.append(entry)
    return out
