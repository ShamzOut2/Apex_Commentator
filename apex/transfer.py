"""Export and import: leagues, teams, championships, round results, the
driver roster and the overlay settings.

Exports are saved in ``Documents\\Apex Commentator\\Exports`` (see
``exports_dir``), named after what's in them and the date, so they're easy to
find, send to someone, or keep as a backup.

* ``.json`` files are for importing back into Apex Commentator (on this PC or
  another). They say what they hold (``"apex": "league"``, ``"teams"``, ...),
  and carry their images (logos, banners, photos, backgrounds) inside them.
* ``.csv`` files are for spreadsheets: championship standings, a round's
  results and the roster. Round results and the roster can be imported from
  CSV too (the columns the export writes; extra columns are ignored).
"""

import base64
import binascii
import csv
import datetime
import io
import json
import re

from . import __version__, championship
from .league import UPLOADED_LOGO, LeagueError, _slug, driver_key, normalise_profile, sniff_logo
from .paths import APP_NAME, documents_dir

FORMAT = 1
JSON_KINDS = ("league", "teams", "championship", "round", "overlays")
MAX_IMPORT_BYTES = 200 * 1024 * 1024


class TransferError(ValueError):
    """An export or import that can't be done; the message says why."""


def exports_dir():
    return documents_dir() / APP_NAME / "Exports"


def _clean(text):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", str(text or "")).strip(" .") or "Export"


def save_export(parts, ext, data, folder=None):
    """Write an export; returns its path. ``parts``: what it is, e.g. ("My League", "Teams")."""
    folder = folder or exports_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stem = " - ".join(_clean(p) for p in parts if p) + f" - {datetime.date.today().isoformat()}"
    path = folder / f"{stem}.{ext}"
    n = 2
    while path.exists():
        path = folder / f"{stem} ({n}).{ext}"
        n += 1
    path.write_bytes(data)
    return path


# -- exports --------------------------------------------------------------------

def _envelope(kind, **data):
    return {"apex": kind, "format": FORMAT, "app_version": __version__,
            "exported_at": datetime.datetime.now().isoformat(timespec="seconds"), **data}


def _json_bytes(obj):
    return json.dumps(obj, indent=1, ensure_ascii=False).encode("utf-8")


def _images(store, profile, names):
    """{file name: base64} of a league's stored images."""
    out = {}
    for name in sorted({n for n in names if n and UPLOADED_LOGO.fullmatch(str(n))}):
        path = store.logo_file(profile["id"], name)
        if path:
            out[name] = base64.b64encode(path.read_bytes()).decode("ascii")
    return out


def _league_image_names(profile):
    names = {c.get("logo") for c in profile.get("classes", [])}
    names |= {t.get("logo") for t in profile.get("teams", [])}
    names |= {d.get(k) for d in profile.get("drivers", []) for k in ("car_image", "helmet_image")}
    names |= {b.get("file") for b in profile.get("banners", []) + profile.get("sponsors", [])}
    names |= {profile.get("logo"), profile.get("calendar_image")}
    return names


def export_league(store, profile):
    """Everything about a league: classes, teams, drivers, championship, images."""
    league = {k: v for k, v in profile.items() if k not in ("updated_at",)}
    return _json_bytes(_envelope("league", league=league, images=_images(store, profile, _league_image_names(profile))))


def export_teams(store, profile):
    """Teams (name, short name, colour, logo) and who drives for each."""
    drivers = [{"key": driver_key(d), "cust_id": d.get("cust_id"), "name": d.get("name", ""), "team": d.get("team", "")}
               for d in profile.get("drivers", []) if d.get("team")]
    teams = list(profile.get("teams", []))
    # Teams that are only a name on drivers (never opened in the team builder) count too.
    known = {t["name"].lower() for t in teams}
    for d in drivers:
        if d["team"].lower() not in known:
            known.add(d["team"].lower())
            teams.append({"name": d["team"], "short": "", "color": "", "logo": None})
    return _json_bytes(_envelope("teams", league=profile["name"], teams=teams, drivers=drivers,
                                 images=_images(store, profile, {t.get("logo") for t in teams})))


def _names(profile):
    return {driver_key(d): d.get("name", "") for d in profile.get("drivers", [])}


def export_championship(profile):
    """The points rules, the calendar with every round's results, and penalties."""
    return _json_bytes(_envelope("championship", league=profile["name"],
                                 championship=championship.normalise(profile.get("championship")),
                                 classes=[{"id": c["id"], "name": c["name"]} for c in profile.get("classes", [])],
                                 drivers=_names(profile)))


def _round(profile, round_id):
    champ = championship.normalise(profile.get("championship"))
    for i, rd in enumerate(champ["rounds"], start=1):
        if rd["id"] == round_id:
            return i, rd
    raise TransferError("That round isn't in this league's calendar.")


def export_round(profile, round_id):
    n, rd = _round(profile, round_id)
    return _json_bytes(_envelope("round", league=profile["name"], number=n, round=rd,
                                 classes=[{"id": c["id"], "name": c["name"]} for c in profile.get("classes", [])]))


def _csv_bytes(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")  # the BOM makes Excel read it as UTF-8


def _class_name(profile, class_id):
    return next((c["name"] for c in profile.get("classes", []) if c["id"] == class_id), class_id)


def standings_csv(profile):
    """Every championship table (overall, each class, teams), one after another."""
    st = championship.standings(profile)
    rounds = [r for r in st["rounds"] if r["scored"]]
    heads = [f"R{i}" for i in range(1, len(rounds) + 1)]
    rows = []
    for g in st["groups"]:
        rows += [[f"{g['name']} championship"], ["Pos", "Driver", "Car #", "Team", *heads, "Penalty", "Points", "Gap"]]
        for d in g["drivers"]:
            per = {s["round"]: s for s in d["rounds"]}
            cells = [("" if r["id"] not in per or per[r["id"]]["result"] is None else
                      f"{per[r['id']]['points']}{' (dropped)' if per[r['id']]['dropped'] else ''}") for r in rounds]
            rows.append([d["pos"], d["name"], d["car_number"], d["team"], *cells,
                         d["penalty_points"] or "", d["points"], d["behind"] or ""])
        rows.append([])
    if st["teams"]:
        rows += [["Teams' championship"], ["Pos", "Team", "Drivers", *heads, "Penalty", "Points", "Gap"]]
        for t in st["teams"]:
            per = {r["round"]: r["points"] for r in t["rounds"]}
            rows.append([t["pos"], t["team"], ", ".join(x["name"] for x in t["drivers"]),
                         *[per.get(r["id"]) if per.get(r["id"]) is not None else "" for r in rounds],
                         t["penalty_points"] or "", t["points"], t["behind"] or ""])
    return _csv_bytes(rows)


ROUND_COLUMNS = ["Pos", "Driver", "Cust ID", "Class", "Start", "Laps", "Laps led", "Fastest lap",
                 "Incidents", "Status", "Car", "Points adjust"]


def round_csv(profile, round_id):
    _, rd = _round(profile, round_id)
    rows = [ROUND_COLUMNS]
    for r in sorted(rd["results"], key=lambda r: r["position"] or 999):
        cust = r["driver"][5:] if r["driver"].startswith("cust:") else ""
        rows.append([r["position"] or "", r["name"], cust, _class_name(profile, r["class_id"]), r["start_position"] or "",
                     r["laps"], r["laps_led"], r["fastest_lap"] or "", r["incidents"], r["status"], r["make"],
                     r["adjust"] or ""])
    return _csv_bytes(rows)


DRIVER_COLUMNS = ["Name", "Cust ID", "Car #", "Driver #", "Nickname", "Team", "Notes", "Class", "Secondary class", "Car"]


def drivers_csv(profile):
    rows = [DRIVER_COLUMNS]
    for d in profile.get("drivers", []):
        rows.append([d.get("name", ""), d.get("cust_id") if d.get("cust_id") is not None else "", d.get("car_number", ""),
                     d.get("driver_number", ""), d.get("nickname", ""), d.get("team", ""), d.get("notes", ""),
                     _class_name(profile, d.get("class_id", "")), _class_name(profile, d.get("class2_id", "")),
                     d.get("car_make", "")])
    return _csv_bytes(rows)


def export_overlays(settings, backgrounds):
    """Every overlay's and board's settings, with the background images they use."""
    used = {s.get("bg_image") for s in settings.values() if isinstance(s, dict)}
    images = {}
    for name in sorted(n for n in used if n):
        path = backgrounds.file(name)
        if path:
            images[name] = base64.b64encode(path.read_bytes()).decode("ascii")
    return _json_bytes(_envelope("overlays", settings=settings, images=images))


# -- imports --------------------------------------------------------------------

class Rows(list):
    """A CSV's rows (dicts, lower-case keys); ``event``: the event details at
    the top of an iRacing event result export, else {}."""
    event = {}


def read(data):
    """("json", kind, object) for an Apex Commentator file, or ("csv", None, [dict rows])."""
    if len(data) > MAX_IMPORT_BYTES:
        raise TransferError("That file is too big to import.")
    text = data.decode("utf-8-sig", errors="replace")
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(text)
        except ValueError as e:
            raise TransferError(f"That file isn't readable ({e}).") from e
        kind = obj.get("apex") if isinstance(obj, dict) else None
        if kind not in JSON_KINDS:
            raise TransferError("That isn't an Apex Commentator export.")
        return "json", kind, obj
    event = {}
    lines = text.splitlines()
    head = next((i for i, line in enumerate(lines) if line.lstrip('"').lower().startswith("fin pos")), None)
    if head is not None:
        # iRacing's own event result export: the event's details (start
        # time, track...) above the results table, which starts at "Fin Pos".
        top = [r for r in csv.reader(io.StringIO("\n".join(lines[:head]))) if any(c.strip() for c in r)]
        if len(top) >= 2:
            event = {k.strip().lower(): v.strip() for k, v in zip(top[0], top[1])}
        text = "\n".join(lines[head:])
    rows = Rows({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text)))
    if not rows:
        raise TransferError("That file is empty, or isn't an Apex Commentator export or a CSV.")
    rows.event = event
    return "csv", None, rows


def expect(data, kind, csv_ok=False):
    """Read a file that should be ``kind``; a clear error if it's something else."""
    fmt, got, obj = read(data)
    if fmt == "csv" and csv_ok:
        return "csv", obj
    if fmt == "csv":
        raise TransferError(f"That's a CSV file; this needs a {kind} export (.json) from Apex Commentator.")
    if got != kind:
        raise TransferError(f"That's a {got} export, not a {kind} export.")
    return "json", obj


def _put_images(store, profile_id, images):
    for name, b64 in (images or {}).items():
        if not UPLOADED_LOGO.fullmatch(str(name)):
            continue
        try:
            data = base64.b64decode(b64, validate=True)
            sniff_logo(data)
        except (binascii.Error, ValueError, LeagueError):
            continue
        store.put_image(profile_id, name, data)


def import_league(store, obj):
    """A league export as a new league. Never overwrites one: a name or id
    already in use gets "(imported)" and an id of its own."""
    league = obj.get("league")
    if not isinstance(league, dict):
        raise TransferError("That league export is empty.")
    league = dict(league)
    existing = {p["id"] for p in store.list()}
    names = {p["name"].lower() for p in store.list()}
    if league.get("id") in existing or str(league.get("name", "")).lower() in names:
        base = f"{league.get('name') or 'League'} (imported)"
        name, n = base, 2
        while name.lower() in names:
            name, n = f"{base} {n}", n + 1
        league["name"], league["id"] = name, _slug(name)
        while league["id"] in existing:
            league["id"] = _slug(f"{name} {n}")
            n += 1
    league["league_id"] = league.get("league_id")
    profile = normalise_profile(league)
    _put_images(store, profile["id"], obj.get("images"))
    return store.save(profile)


def import_teams(store, profile, obj):
    """Teams into a league: teams with the same name are replaced, new ones
    added; drivers in the file (matched by customer ID, else name) join their team."""
    teams = [t for t in obj.get("teams") or [] if isinstance(t, dict) and t.get("name")]
    if not teams:
        raise TransferError("That teams export has no teams in it.")
    _put_images(store, profile["id"], obj.get("images"))
    mine = {t["name"].lower(): t for t in profile.get("teams", [])}
    for t in teams:
        mine[str(t["name"]).lower()] = t
    profile["teams"] = list(mine.values())
    by_key = {driver_key(d): d for d in profile.get("drivers", [])}
    by_name = {str(d.get("name", "")).lower(): d for d in profile.get("drivers", [])}
    joined = 0
    for d in obj.get("drivers") or []:
        if not isinstance(d, dict):
            continue
        mine_d = by_key.get(d.get("key")) or by_name.get(str(d.get("name", "")).lower())
        if mine_d is not None:
            mine_d["team"] = d.get("team", "")
            joined += 1
    return store.save(profile), {"teams": len(teams), "drivers": joined}


def _class_ids(profile, file_classes):
    """The file's class ids -> this league's, matched by name."""
    mine = {c["name"].lower(): c["id"] for c in profile.get("classes", [])}
    return {c.get("id"): mine.get(str(c.get("name", "")).lower(), c.get("id"))
            for c in file_classes or [] if isinstance(c, dict)}


def import_championship(store, profile, obj):
    """A championship export replaces the league's championship (rules, calendar, results, penalties)."""
    champ = championship.normalise(obj.get("championship"))
    ids = _class_ids(profile, obj.get("classes"))
    for rd in champ["rounds"]:
        for r in rd["results"]:
            r["class_id"] = ids.get(r["class_id"], r["class_id"])
    rules = champ["rules"]
    rules["class_points"] = {ids.get(k, k): v for k, v in rules["class_points"].items()}
    profile["championship"] = champ
    return store.save(profile), {"rounds": len(champ["rounds"])}


def _num(text, cast=int):
    try:
        return cast(text) if str(text).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _laptime(text):
    """"1:34.597" / "34.597" -> seconds; "-01.345" -> 1.345; None if it isn't one."""
    text = str(text or "").strip().lstrip("-+")
    m = re.fullmatch(r"(?:(\d+):)?(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    value = int(m.group(1) or 0) * 60 + float(m.group(2))
    return round(value, 3) if value > 0 else None


def _result_from_csv(profile, row, store=None):
    """One result from a CSV row: this app's round export, or iRacing's event
    result export ("Fin Pos", "Cust ID", "Laps Comp", "Out", "Interval"...)."""
    from .makes import make_for

    name = row.get("driver") or row.get("name") or ""
    cust = _num(row.get("cust id"))
    roster = next((d for d in profile.get("drivers", []) if cust is not None and d.get("cust_id") == cust), None) or \
        next((d for d in profile.get("drivers", []) if str(d.get("name", "")).lower() == name.lower()), None)
    key = driver_key(roster) if roster else (f"cust:{cust}" if cust is not None else f"name:{name.strip().lower()}")
    iracing = "fin pos" in row
    laps = _num(row.get("laps") or row.get("laps comp")) or 0
    if iracing:
        # iRacing's class: the league's class for the driver (their own pick,
        # name tag or car class), else iRacing's, as for results from the sim.
        car_class = row.get("car class", "")
        cls = store.class_for(roster, car_class, profile, name) if store else None
        class_id = cls["id"] if cls else f"iracing:{car_class or 'Field'}"
        out = row.get("out", "").strip().lower()
        status = "finished" if out in ("running", "") else "dsq" if "disq" in out else "dns" if laps == 0 else "dnf"
        interval = row.get("interval", "")
        gap = None if "l" in interval.lower() else (_laptime(interval) or (0.0 if _num(row.get("fin pos")) == 1 else None))
        return {
            "driver": key, "name": name or (roster or {}).get("name", ""), "class_id": class_id,
            "position": _num(row.get("fin pos")), "start_position": _num(row.get("start pos")),
            "laps": laps, "laps_led": _num(row.get("laps led")) or 0,
            "fastest_lap": _laptime(row.get("fastest lap time")), "incidents": _num(row.get("inc")) or 0,
            "status": status, "make": (roster or {}).get("car_make") or make_for(row.get("car", ""), ""),
            "gap": gap, "has_main": cls is not None,
            # iRacing's average lap is their race time over their laps.
            "race_time": round(_laptime(row.get("average lap time")) * laps, 3) if laps and _laptime(row.get("average lap time")) else None,
        }
    cls = row.get("class", "")
    class_id = next((c["id"] for c in profile.get("classes", []) if c["name"].lower() == cls.lower() or c["id"] == cls), cls)
    status = (row.get("status") or "finished").lower()
    return {
        "driver": key, "name": name or (roster or {}).get("name", ""), "class_id": class_id,
        "position": _num(row.get("pos") or row.get("position")), "start_position": _num(row.get("start")),
        "laps": laps, "laps_led": _num(row.get("laps led")) or 0,
        "fastest_lap": _num(row.get("fastest lap"), float) or _laptime(row.get("fastest lap")),
        "incidents": _num(row.get("incidents")) or 0,
        "status": status, "make": row.get("car", ""), "adjust": _num(row.get("points adjust"), float) or 0,
    }


def _unclassed(profile, result):
    """No main class and no secondary class in a league with classes (a safety
    car, say): left out, as for results from the sim (App._unclassed)."""
    classes = profile.get("classes") or []
    if not classes or not profile.get("hide_unclassed", True) or result.get("has_main", True):
        return False
    roster = next((d for d in profile.get("drivers", []) if driver_key(d) == result["driver"]), None)
    if roster is None:
        return False  # not in the roster: never left out
    return not any(c["id"] == roster.get("class2_id") and c.get("role") == "secondary" for c in classes)


def import_round(store, profile, round_id, fmt, obj):
    """Results into a round of the league's calendar (replacing what's there):
    from a round export (.json) or a CSV with the export's columns."""
    champ = championship.normalise(profile.get("championship"))
    rd = next((r for r in champ["rounds"] if r["id"] == round_id), None)
    if rd is None:
        raise TransferError("Pick a round in this league's calendar to import into.")
    if fmt == "csv":
        results = [_result_from_csv(profile, row, store) for row in obj if row.get("driver") or row.get("name")]
        results = [r for r in results if not _unclassed(profile, r)]
        event = getattr(obj, "event", None) or {}
        if event:
            # iRacing's export: the track and date for a round without them.
            track, _, config = (event.get("track") or "").partition(" - ")
            if track.strip() and not rd.get("track"):
                rd["track"], rd["config"] = track.strip(), config.strip()
            if event.get("start time") and not rd.get("date"):
                rd["date"] = event["start time"][:10]
    else:
        src = obj.get("round") if isinstance(obj.get("round"), dict) else {}
        ids = _class_ids(profile, obj.get("classes"))
        results = [dict(r, class_id=ids.get(r.get("class_id"), r.get("class_id"))) for r in src.get("results") or []
                   if isinstance(r, dict)]
        for key in ("track", "config", "date", "time", "length"):
            if src.get(key) and not rd.get(key):
                rd[key] = src[key]
    results = [championship.normalise_result(r) for r in results]
    results = [r for r in results if r["driver"]]
    if not results:
        raise TransferError("No results found in that file.")
    rd["results"] = results
    rd["session"] = ""
    profile["championship"] = champ
    return store.save(profile), {"results": len(results)}


def import_drivers_csv(store, profile, rows):
    """Roster rows into a league: drivers matched by customer ID (else name) are
    updated with the file's non-empty values; the rest are added."""
    classes = {c["name"].lower(): c["id"] for c in profile.get("classes", [])}
    drivers = profile.setdefault("drivers", [])
    added = updated = 0
    for row in rows:
        name = row.get("name", "")
        cust = _num(row.get("cust id"))
        if not name and cust is None:
            continue
        d = next((x for x in drivers if cust is not None and x.get("cust_id") == cust), None) or \
            next((x for x in drivers if name and str(x.get("name", "")).lower() == name.lower()), None)
        if d is None:
            d = {"name": name, "cust_id": cust}
            drivers.append(d)
            added += 1
        else:
            updated += 1
        for col, key in (("name", "name"), ("car #", "car_number"), ("driver #", "driver_number"), ("nickname", "nickname"),
                         ("team", "team"), ("notes", "notes"), ("car", "car_make")):
            if row.get(col):
                d[key] = row[col]
        if cust is not None:
            d["cust_id"] = cust
        if row.get("class"):
            d["class_id"] = classes.get(row["class"].lower(), d.get("class_id", ""))
        if row.get("secondary class"):
            d["class2_id"] = classes.get(row["secondary class"].lower(), d.get("class2_id", ""))
    return store.save(profile), {"added": added, "updated": updated}


def import_overlays(overlays, backgrounds, obj):
    """Overlay and board settings (and their background images) replace this PC's."""
    settings = obj.get("settings")
    if not isinstance(settings, dict):
        raise TransferError("That overlay settings export is empty.")
    for name, b64 in (obj.get("images") or {}).items():
        try:
            data = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            continue
        try:
            saved = backgrounds.save(data)
        except (LeagueError, OSError):
            continue
        if saved != name:  # same picture, same name: keep the settings pointing at it
            for s in settings.values():
                if isinstance(s, dict) and s.get("bg_image") == name:
                    s["bg_image"] = saved
    count = 0
    for section, values in settings.items():
        if isinstance(values, dict):
            try:
                overlays.update(section, values)
                count += 1
            except ValueError:
                pass  # a section this version doesn't have
    return {"sections": count}
