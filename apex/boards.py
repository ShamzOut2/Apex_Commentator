"""Full-screen boards: championship tables, the season calendar and race results.

The commentator puts one on screen from the Boards tab (``board.html`` is the
OBS page). What each board shows is set in its settings (see ``overlays``).
Boards are built from the active league's saved championship.
"""

from . import championship
from .league import logo_url, strip_class_prefix
from .makes import logo_for as make_logo

KINDS = ("championship", "teams", "makes", "calendar", "results")
TITLES = {
    "championship": "Championship standings", "teams": "Teams' championship", "makes": "Manufacturers' championship",
    "calendar": "Season calendar", "results": "Finishing order",
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
        return {"groups": [], "rounds": []}
    table = championship.standings(league)
    groups = []
    for g in table["groups"]:
        name, color, _ = _group_info(league, g["key"])
        groups.append({"key": g["key"], "name": name, "color": color})
    rounds = [{"id": r["id"], "name": r["name"], "track": r["track"], "scored": r["scored"]} for r in table["rounds"]]
    return {"groups": groups, "rounds": rounds, "teams": bool(table["teams"]),
            "has_teams": any(d.get("team") for d in league.get("drivers", []))}


def _person(league, name, nickname):
    """A driver's name as the stream shows it (see App._stream_name)."""
    if league.get("strip_class_prefix"):
        return nickname or strip_class_prefix(name)
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
    out = {"kind": kind, "group": params.get("group") or "", "round": params.get("round") or "", "league": league["name"], "title": TITLES[kind], "subtitle": "",
           "banner": _banner(league, cfg), "sponsors": _sponsor_strip(league, cfg), "settings": cfg, "accent": None, "group_logo": None,
           "league_logo": logo_url(league["id"], league.get("logo")) if cfg["league_logo"] and league.get("logo") else None}
    group = params.get("group") or championship.OVERALL
    if kind in ("championship", "makes", "results"):
        name, color, logo = _group_info(league, group)
        out["subtitle"], out["accent"], out["group_logo"] = name, color, logo
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
        for d in (g["drivers"] if g else [])[:cfg["rows"]]:
            roster = next((x for x in league.get("drivers", []) if championship._key(x) == d["driver"]), {})
            make = roster.get("car_make", "")
            rows.append({
                "pos": d["pos"], "name": _person(league, d["name"], roster.get("nickname", "")),
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
        for t in table["teams"][:cfg["rows"]]:
            team = info.get(t["team"].lower(), {})
            per = {s["round"]: s["points"] for s in t["rounds"]}
            rows.append(dict(t, team_logo=team_logos.get(t["team"].lower()), color=team.get("color") or None,
                             drivers=[_person(league, d["name"], d["nickname"]) for d in t["drivers"]],
                             rounds=[per.get(r["id"]) for r in last]))
        out["rows"] = rows
    elif kind == "makes":
        out["rows"] = [dict(m, make_logo=make_logo(m["make"])) for m in championship.make_standings(league, group)[:cfg["rows"]]]
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
            out["title"] = "Running order" if source == "live" else f"{live_results['name'].title()} result"
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
                    row.update(points=None, gained=None)
            if rd["id"] != "live":
                n = champ["rounds"].index(rd) + 1
                name = " · ".join(filter(None, [rd["event"], rd["name"]]))
                out["title"] = f"{name} result" if name else f"Round {n} result"
                out["subtitle"] = " · ".join(filter(None, [out["subtitle"], rd["track"]]))
        out["rows"] = rows[:cfg["rows"]]
    return out


def meetings(cal):
    """The calendar with each race meeting (rounds next to each other with the
    same ``event``) as one entry: its first race's details, ``last`` (its last
    round's number), and each race's winners named by race."""
    out = []
    for r in cal:
        prev = out[-1] if out else None
        if r["event"] and prev and prev.get("event") == r["event"]:
            prev["last"] = r["round"]
            prev["races"].append(r["name"])
            prev["done"] = prev["done"] and r["done"]
            prev["winners"] += [dict(w, race=r["name"]) for w in r["winners"]]
            continue
        entry = dict(r, last=None, races=[r["name"]])
        if r["event"]:
            entry["name"] = r["event"]
            entry["winners"] = [dict(w, race=r["name"]) for w in r["winners"]]
        out.append(entry)
    return out
