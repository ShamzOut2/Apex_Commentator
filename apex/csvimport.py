"""Drivers and teams from a spreadsheet (CSV), e.g. a league's sign-up sheet.

``read(text)`` splits it into a header row and rows (comma, semicolon or tab
separated, quotes allowed). ``guess(headers, rows)`` works out which column
is which: iRacing (customer) ID, full name (or first and last name), car
number, team, team colour, class, nickname. The class column is found by its
heading ("Class", "Category"...) or, without one, by its values: a column
with a handful of different words in most rows (GOLD / SILVER / BRONZE, say).
``apply(profile, rows, mapping, class_role)`` puts them into a league:

- a driver already in the league (same iRacing ID, else the same name) gets
  the details from the sheet; anyone else is added;
- each team is added to the league's teams if it isn't there;
- each class is the league's class of that name, made if there isn't one,
  as a main or a secondary class (``class_role``).
"""

import csv
import io
import re

FIELDS = ("cust_id", "name", "first", "last", "number", "team", "team_color", "class", "nickname")
HEADINGS = {
    "cust_id": ("customerid", "custid", "iracingid", "iracingcustomerid", "memberid", "iracingmemberid", "iracing", "id"),
    "name": ("fullname", "name", "drivername", "driver"),
    "first": ("firstname", "first", "forename", "givenname"),
    "last": ("lastname", "last", "surname", "familyname"),
    "number": ("carnumber", "carno", "carnum", "number", "no", "racenumber", "num", "car"),
    "team": ("teamname", "team"),
    "team_color": ("teamcolor", "teamcolour"),
    "class": ("class", "classname", "category", "division", "carclass", "tier", "grade", "licence", "license"),
    "nickname": ("nickname", "nick", "displayname"),
}
# Classes known by name get their usual colour.
CLASS_COLORS = {"gold": "#d4af37", "silver": "#b8bec6", "bronze": "#cd7f32", "platinum": "#e5e4e2", "pro": "#e8463c",
                "proam": "#f2994a", "am": "#27ae60", "rookie": "#2f80ed"}
HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


class CsvError(ValueError):
    pass


def _key(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def read(text):
    """CSV text -> (headers, rows as lists)."""
    text = str(text or "").lstrip("﻿")
    if not text.strip():
        raise CsvError("The file is empty.")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise CsvError("No rows under the heading row.")
    headers = [h.strip() for h in rows[0]]
    width = len(headers)
    return headers, [(r + [""] * width)[:width] for r in rows[1:]]


def guess(headers, rows):
    """{field: column index} for the columns it can tell (see FIELDS)."""
    keys = [_key(h) for h in headers]
    out = {}
    for field in FIELDS:  # an exact heading first, in the order of preference
        for want in HEADINGS[field]:
            i = next((i for i, k in enumerate(keys) if k == want and i not in out.values()), None)
            if i is not None:
                out[field] = i
                break
    for field in FIELDS:  # then a heading that contains one ("Driver full name")
        if field in out:
            continue
        for want in HEADINGS[field]:
            if len(want) < 4:
                continue
            i = next((i for i, k in enumerate(keys) if want in k and i not in out.values()), None)
            if i is not None:
                out[field] = i
                break
    if "class" not in out:
        out.update(_class_by_values(headers, rows, set(out.values())))
    return out


def _class_by_values(headers, rows, taken):
    """A column that looks like classes: a few different words, in most rows."""
    best = None
    for i in range(len(headers)):
        if i in taken:
            continue
        values = [r[i].strip() for r in rows if r[i].strip()]
        if len(values) < max(2, len(rows) // 2):
            continue
        distinct = {v.lower() for v in values}
        # A few words, repeated (names and abbreviations are all different).
        if not 2 <= len(distinct) <= 10 or len(distinct) >= len(values) or any(v.replace(".", "").isdigit() for v in distinct):
            continue
        if sum(len(v) for v in values) / len(values) > 20:
            continue
        score = (len(distinct) / len(values), -len(values))  # the most repeated, then the most filled
        if best is None or score < best[1]:
            best = (i, score)
    return {"class": best[0]} if best else {}


def _cell(row, mapping, field):
    i = mapping.get(field)
    return row[i].strip() if i is not None and 0 <= i < len(row) else ""


def apply(profile, rows, mapping, class_role="main"):
    """Put the sheet's drivers, teams and classes into ``profile`` (changed in
    place). Returns a summary: {"added", "updated", "teams", "classes", "skipped"}."""
    role = "secondary" if class_role == "secondary" else "main"
    drivers = profile.setdefault("drivers", [])
    teams = profile.setdefault("teams", [])
    classes = profile.setdefault("classes", [])
    summary = {"added": 0, "updated": 0, "teams": 0, "classes": 0, "skipped": 0}

    def class_id(name):
        c = next((c for c in classes if _key(c.get("name")) == _key(name) and (c.get("role") or "main") == role), None)
        if c is None:
            c = next((c for c in classes if _key(c.get("name")) == _key(name)), None)
        if c is None:
            base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "class"
            cid, n = base, 2
            while any(x.get("id") == cid for x in classes):
                cid, n = f"{base}-{n}", n + 1
            label = name.title() if name.isupper() and len(name) > 3 else name
            c = {"id": cid, "name": label, "color": CLASS_COLORS.get(_key(name), ""), "match": [], "role": role}
            classes.append(c)
            summary["classes"] += 1
        return c["id"], (c.get("role") or "main")

    for row in rows:
        cid_text = _cell(row, mapping, "cust_id")
        cust_id = int(cid_text) if cid_text.isdigit() else None
        name = _cell(row, mapping, "name") or " ".join(
            p for p in (_cell(row, mapping, "first"), _cell(row, mapping, "last")) if p)
        if not name and cust_id is None:
            summary["skipped"] += 1
            continue
        d = next((x for x in drivers if cust_id is not None and x.get("cust_id") == cust_id), None) \
            or next((x for x in drivers if name and str(x.get("name") or "").strip().lower() == name.lower()), None)
        if d is None:
            d = {"name": name, "cust_id": cust_id, "car_number": "", "nickname": "", "team": "", "notes": ""}
            drivers.append(d)
            summary["added"] += 1
        else:
            summary["updated"] += 1
        if name:
            d["name"] = name
        if cust_id is not None:
            d["cust_id"] = cust_id
        number = _cell(row, mapping, "number").lstrip("#")
        if number:
            d["car_number"] = number
        nick = _cell(row, mapping, "nickname")
        if nick:
            d["nickname"] = nick
        team = _cell(row, mapping, "team")
        if team:
            t = next((t for t in teams if str(t.get("name") or "").strip().lower() == team.lower()), None)
            if t is None:
                t = {"name": team, "short": "", "color": "", "logo": None, "shared": []}
                teams.append(t)
                summary["teams"] += 1
            color = _cell(row, mapping, "team_color")
            if color and HEX.match(color) and not t.get("color"):
                t["color"] = "#" + color.lstrip("#").lower()
            d["team"] = t["name"]
        klass = _cell(row, mapping, "class")
        if klass:
            kid, krole = class_id(klass)
            d["class2_id" if krole == "secondary" else "class_id"] = kid
    return summary
