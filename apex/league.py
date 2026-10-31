"""League builder: editable league profiles on disk.

A league profile is a small JSON file in ``data/leagues/``::

    {
      "id": "sunday-night-gt3",
      "league_id": null,            # iRacing's League ID (leagues fetched from iRacing in older versions)
      "name": "Sunday Night GT3",
      "source": "session",          # session | manual (iracing: fetched in an older version)
      "updated_at": "2026-10-27T19:00:00Z",
      "classes": [
        {"id": "pro", "name": "Pro", "color": "#e8463c", "match": ["GT3"],
         "logo": "pro-1a2b3c4d.png", "logo_bg": "auto", "logo_tolerance": 18,
         "logo_fill": "edges", "role": "main"},
        {"id": "rookie", "name": "Rookie Cup", "color": "#2f80ed", "match": [],
         "logo": null, "logo_bg": "auto", "logo_tolerance": 18,
         "logo_fill": "edges", "role": "secondary"}
      ],
      "drivers": [
        {"cust_id": 123456, "name": "Jane Doe", "nickname": "JD",
         "car_number": "7", "team": "Apex Racing", "notes": "Leads the title",
         "class_id": "pro", "class2_id": "rookie"}
      ]
    }

A driver's class is their ``class_id`` when set, otherwise the first class
whose ``match`` list contains their iRacing car class name. That's their
main class: the one the overlays show. A driver can also be in one
secondary class (``class2_id``, picked by hand): it works in the background,
with a championship of its own (see championship.py), and never shows on the
overlays. A class logo is
either uploaded (stored in ``data/leagues/logos/<league>/``) or picked from
the built-in library in ``web/logos/`` (``"logo": "lib:pro.svg"``).

The overlay matches each logo's background to the class colour. Layered SVGs
(see ``tools/logo_to_svg.py``) have their badge layer set to the colour
exactly; other images have their background detected and recoloured
(``logo_bg``: ``auto`` detects it, a ``#rrggbb`` value names it, ``keep``
leaves the logo untouched).

Leagues are set up by hand: from the drivers in the current session, from
a blank league, or from a league exported by the app.
"""

import hashlib
import json
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import championship
from .paths import WEB_DIR

LOGO_LIBRARY_DIR = WEB_DIR / "logos"
UPLOADED_LOGO = re.compile(r"[a-z0-9-]+\.(png|jpg|webp|svg)")
LIBRARY_LOGO = re.compile(r"lib:([a-z0-9-]+\.svg)")
EDITABLE_FIELDS = ("nickname", "team", "notes", "class_id", "class2_id", "car_image", "helmet_image", "driver_number", "car_make")
DRIVER_IMAGES = ("car_image", "helmet_image")
# Distinct defaults handed to new classes, in order.
CLASS_PALETTE = ["#e8463c", "#2f80ed", "#27ae60", "#f2c94c", "#9b51e0", "#f2994a", "#56ccf2", "#eb5ea8"]
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # livery screenshots can be big
LOGO_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "svg": "image/svg+xml"}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
# "(P) Dave Price", "(PA)Dave Price": a class tag some leagues put before names.
CLASS_PREFIX = re.compile(r"^\s*\([^()]*\)\s*")


BANNER_SHAPES = ("horizontal", "vertical")


def _uploaded(name):
    """An uploaded image's file name, or None."""
    return name if isinstance(name, str) and UPLOADED_LOGO.fullmatch(name) else None


def normalise_banners(banners):
    """League logos and banners for the full-screen boards: [{id, file, orientation, name}]."""
    out = []
    for b in banners or []:
        if not isinstance(b, dict) or not UPLOADED_LOGO.fullmatch(str(b.get("file") or "")):
            continue
        out.append({
            "id": re.sub(r"[^a-z0-9]", "", str(b.get("id") or ""))[:12] or uuid.uuid4().hex[:8],
            "file": b["file"],
            "orientation": b.get("orientation") if b.get("orientation") in BANNER_SHAPES else "horizontal",
            "name": str(b.get("name") or "").strip()[:60],
        })
    return out


def normalise_sponsors(sponsors):
    """Sponsor logos, for the boards and the sponsors overlay: [{id, file, name}]."""
    out = []
    for s in sponsors or []:
        if not isinstance(s, dict) or not UPLOADED_LOGO.fullmatch(str(s.get("file") or "")):
            continue
        out.append({
            "id": re.sub(r"[^a-z0-9]", "", str(s.get("id") or ""))[:12] or uuid.uuid4().hex[:8],
            "file": s["file"],
            "name": str(s.get("name") or "").strip()[:60],
        })
    return out


def strip_class_prefix(name):
    """'(P) Dave Price' -> 'Dave Price'; other names unchanged."""
    name = str(name or "")
    stripped = CLASS_PREFIX.sub("", name, count=1).strip()
    return stripped or name.strip()


def class_tag(name):
    """'(SP) Ben Gibbons' -> 'SP'; None without a tag."""
    m = CLASS_PREFIX.match(str(name or ""))
    tag = m.group(0).strip()[1:-1].strip() if m else ""
    return tag.upper() or None


def _squash(text):
    return re.sub(r"[^0-9A-Z]", "", str(text or "").upper())


def class_for_tag(classes, tag):
    """The league class a name tag stands for, or None.

    Exact first: the tag is the class's name or one of its "iRacing classes"
    entries ("P" in the Pro class's list). Then initials: "SP" is Semi-Pro,
    "PA" Pro-Am, "P" Pro.
    """
    tag = _squash(tag)
    if not tag:
        return None
    for c in classes:
        if tag in {_squash(c.get("name")), *(_squash(m) for m in c.get("match", []))}:
            return c
    for c in classes:
        words = [w for w in re.split(r"[\s\-_/]+", str(c.get("name") or "")) if w]
        if words and tag == "".join(w[0] for w in words).upper():
            return c
    return None


def fill_clean_nicknames(drivers):
    """Give drivers whose name carries a class tag their clean name as nickname
    (an existing nickname is kept). Returns how many were filled."""
    filled = 0
    for d in drivers:
        name = str(d.get("name") or "")
        if not d.get("nickname") and CLASS_PREFIX.match(name):
            d["nickname"] = strip_class_prefix(name)
            filled += 1
    return filled


class LeagueError(Exception):
    """A user-facing error from the league builder."""


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "league"


def _classes_from_session(drivers):
    """One league class per iRacing car class in the session, using iRacing's colours."""
    classes = []
    seen = set()
    for d in drivers:
        name = d.get("car_class") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        color = d.get("class_color")
        if not (isinstance(color, str) and HEX_COLOR.match(color)) or color.lower() in ("#000000", "#ffffff"):
            color = CLASS_PALETTE[len(classes) % len(CLASS_PALETTE)]
        library = {_slug(l["title"]).replace("-", ""): l["id"] for l in logo_library()}
        classes.append({"id": _slug(name), "name": name, "color": color, "match": [name],
                        "logo": library.get(_slug(name).replace("-", ""))})
    return classes


def profile_from_session(drivers, name):
    """Build a profile from the drivers currently in the session."""
    return {
        "id": _slug(name),
        "league_id": None,
        "name": name,
        "source": "session",
        "updated_at": _now_iso(),
        "classes": _classes_from_session(drivers),
        "drivers": [{
            "cust_id": d.get("cust_id"),
            "name": d.get("name", ""),
            "nickname": "",
            "car_number": d.get("number", ""),
            "team": d.get("team", ""),
            "notes": "",
            "car_make": d.get("make", ""),
        } for d in drivers],
    }


def logo_library():
    """The built-in class logos: ``[{"id": "lib:pro.svg", "title": "PRO", "url": ...}]``."""
    out = []
    for path in sorted(LOGO_LIBRARY_DIR.glob("*.svg")):
        head = path.read_text(encoding="utf-8", errors="replace")[:600]
        m = re.search(r"<title>([^<]*)</title>", head)
        out.append({
            "id": f"lib:{path.name}",
            "title": m.group(1).strip() if m else path.stem.upper(),
            "url": f"/logos/{path.name}",
        })
    return out


def _valid_logo_ref(logo):
    lib = LIBRARY_LOGO.fullmatch(logo)
    if lib:
        return (LOGO_LIBRARY_DIR / lib.group(1)).is_file()
    return bool(UPLOADED_LOGO.fullmatch(logo))


def logo_url(profile_id, logo):
    """Where the overlay loads a class logo from."""
    if not logo:
        return None
    lib = LIBRARY_LOGO.fullmatch(logo)
    if lib:
        return f"/logos/{lib.group(1)}"
    return f"/api/logos/{_slug(profile_id)}/{logo}"


def normalise_classes(classes):
    out = []
    ids = set()
    for i, c in enumerate(classes or []):
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            raise LeagueError("Every class needs a name.")
        cid = _slug(c.get("id") or name)
        base, n = cid, 2
        while cid in ids:
            cid, n = f"{base}-{n}", n + 1
        ids.add(cid)
        color = str(c.get("color") or "").strip()
        if not HEX_COLOR.match(color):
            color = CLASS_PALETTE[i % len(CLASS_PALETTE)]
        match = c.get("match") or []
        if isinstance(match, str):
            match = match.split(",")
        logo = c.get("logo") or None
        if logo is not None and not _valid_logo_ref(str(logo)):
            logo = None
        logo_bg = str(c.get("logo_bg") or "auto").strip().lower()
        if logo_bg not in ("auto", "keep") and not HEX_COLOR.match(logo_bg):
            logo_bg = "auto"
        try:
            tolerance = min(60, max(0, int(c.get("logo_tolerance", 18))))
        except (TypeError, ValueError):
            tolerance = 18
        out.append({
            "id": cid,
            "name": name,
            "color": color.lower(),
            "match": [m.strip() for m in match if str(m).strip()],
            "logo": logo,
            "logo_bg": logo_bg,
            "logo_tolerance": tolerance,
            # "edges": recolour background connected to the logo's border;
            # "all": also enclosed areas of the same colour (e.g. inside an "O").
            "logo_fill": "all" if c.get("logo_fill") == "all" else "edges",
            # "main": shown on the overlays, joined by car class or name tag;
            # "secondary": picked by hand, only for its own championship.
            "role": "secondary" if c.get("role") == "secondary" else "main",
        })
    return out


def main_classes(classes):
    """The classes the overlays show (not the secondary ones)."""
    return [c for c in classes or [] if c.get("role") != "secondary"]


def normalise_profile(profile):
    """Validate a profile coming from the UI and fill in defaults."""
    if not isinstance(profile, dict):
        raise LeagueError("League profile must be a JSON object.")
    name = str(profile.get("name") or "").strip()
    if not name:
        raise LeagueError("League needs a name.")
    league_id = profile.get("league_id")
    if league_id in ("", None):
        league_id = None
    else:
        try:
            league_id = int(league_id)
        except (TypeError, ValueError) as e:
            raise LeagueError("League ID must be a number.") from e
    classes = normalise_classes(profile.get("classes"))
    class_ids = {c["id"] for c in main_classes(classes)}
    secondary_ids = {c["id"] for c in classes} - class_ids
    drivers = []
    for d in profile.get("drivers") or []:
        if not isinstance(d, dict):
            continue
        cust_id = d.get("cust_id")
        try:
            cust_id = int(cust_id) if cust_id not in ("", None) else None
        except (TypeError, ValueError):
            cust_id = None
        entry = {
            "cust_id": cust_id,
            "name": str(d.get("name") or "").strip(),
            "car_number": str(d.get("car_number") or "").strip(),
        }
        for key in EDITABLE_FIELDS:
            entry[key] = str(d.get(key) or "").strip()
        if entry["class_id"] not in class_ids:
            entry["class_id"] = ""
        if entry["class2_id"] not in secondary_ids:
            entry["class2_id"] = ""
        for key in DRIVER_IMAGES:
            if not UPLOADED_LOGO.fullmatch(entry[key]):
                entry[key] = ""
        if entry["name"] or entry["cust_id"] is not None:
            drivers.append(entry)
    teams = []
    seen_teams = set()
    for t in profile.get("teams") or []:
        if not isinstance(t, dict):
            continue
        team_name = str(t.get("name") or "").strip()
        if not team_name or team_name.lower() in seen_teams:
            continue
        seen_teams.add(team_name.lower())
        logo = t.get("logo") or None
        color = str(t.get("color") or "").strip()
        teams.append({
            "name": team_name,
            "short": str(t.get("short") or "").strip()[:8],
            "color": color if HEX_COLOR.fullmatch(color) else "",
            "logo": logo if logo and _valid_logo_ref(str(logo)) else None,
            # The other leagues this team is also in (LeagueStore._sync_teams).
            "shared": sorted({_slug(x) for x in t.get("shared") or [] if isinstance(x, str) and x.strip()}),
        })
    # Overlays show names without a "(P)" class tag: the clean name goes in
    # the nickname (drivers added later, e.g. from a session, included).
    strip = bool(profile.get("strip_class_prefix"))
    if strip:
        fill_clean_nicknames(drivers)
    pid = str(profile.get("id") or (league_id if league_id is not None else _slug(name)))
    return {
        "id": _slug(pid) if league_id is None else str(pid),
        "league_id": league_id,
        "name": name,
        "source": profile.get("source") or "manual",
        "updated_at": _now_iso(),
        "classes": classes,
        "teams": teams,
        "drivers": drivers,
        "championship": championship.normalise(profile.get("championship")),
        "strip_class_prefix": strip,
        # Drivers with neither a main nor a secondary class (a safety car, say)
        # are left off the overlays and out of the results (App._unclassed).
        "hide_unclassed": bool(profile.get("hide_unclassed", True)),
        "banners": normalise_banners(profile.get("banners")),
        "sponsors": normalise_sponsors(profile.get("sponsors")),
        # The league's own logo (board headers) and its own calendar graphic.
        "logo": _uploaded(profile.get("logo")),
        "calendar_image": _uploaded(profile.get("calendar_image")),
    }


def driver_key(driver):
    """Stable reference to a roster driver: their customer ID, else their name."""
    if driver.get("cust_id") is not None:
        return f"cust:{driver['cust_id']}"
    return f"name:{driver.get('name', '').strip().lower()}"


def sniff_logo(data):
    """Return the file extension for a supported image, or raise."""
    if len(data) > MAX_IMAGE_BYTES:
        raise LeagueError("Image is too large (max 8 MB).")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:1024].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "svg"
    raise LeagueError("Image must be a PNG, JPG, WebP or SVG file.")


class LeagueStore:
    """League profiles on disk plus the currently active one."""

    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.active_id = None
        self._active = None
        self._active_file = self.dir / "_active.txt"
        if self._active_file.exists():
            self.set_active(self._active_file.read_text(encoding="utf-8").strip() or None)

    def _path(self, profile_id):
        safe = _slug(profile_id)
        return self.dir / f"{safe}.json"

    def list(self):
        out = []
        for path in sorted(self.dir.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    p = json.load(f)
            except (OSError, ValueError):
                continue
            out.append({
                "id": p.get("id", path.stem),
                "league_id": p.get("league_id"),
                "name": p.get("name", path.stem),
                "drivers": len(p.get("drivers", [])),
                "classes": len(p.get("classes", [])),
                "source": p.get("source"),
                "updated_at": p.get("updated_at"),
                "active": p.get("id", path.stem) == self.active_id,
            })
        return out

    def get(self, profile_id):
        path = self._path(profile_id)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def save(self, profile):
        """Save a league, and keep the teams it shares with other leagues in step."""
        profile = normalise_profile(profile)
        others = self._linked(profile)
        for team in profile.get("teams", []):  # not itself, nor a league since deleted
            team["shared"] = [x for x in team["shared"] if x in others]
        self._pull_members(profile, others)
        profile = self._write(profile)
        self._sync_teams(profile, others)
        return profile

    def _write(self, profile):
        profile = normalise_profile(profile)
        with self._lock:
            tmp = self._path(profile["id"]).with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2)
            tmp.replace(self._path(profile["id"]))
            if profile["id"] == self.active_id:
                self._active = profile
            self._prune_logos(profile)
        return profile

    # -- teams shared between leagues -----------------------------------------
    #
    # A team can be in several leagues (its "shared" list names the others).
    # Saving a league copies each shared team (name, short name, colour, logo)
    # into those leagues and puts its drivers in it there too (the same driver:
    # customer ID, else name). Links are between two leagues only: sharing a
    # team from A to B links A and B, not B to every league A shares it with
    # (that used to spread a team to every league, and brought links back after
    # they were taken off). Drivers without a team are put in the team
    # they're in in a linked league, so newcomers join their team by
    # themselves. Teams are matched by name.

    def _linked(self, profile):
        """Every other saved league, by id (the ones the sync may touch)."""
        out = {}
        for path in self.dir.glob("*.json"):
            if path.stem == profile["id"]:
                continue
            other = self.get(path.stem)
            if other:
                out[other.get("id", path.stem)] = other
        return out

    @staticmethod
    def _same_driver(d, drivers):
        if d.get("cust_id") is not None:
            return next((x for x in drivers if x.get("cust_id") == d["cust_id"]), None)
        name = str(d.get("name") or "").strip().lower()
        return next((x for x in drivers if x.get("cust_id") is None and name
                     and str(x.get("name") or "").strip().lower() == name), None)

    def _pull_members(self, profile, others):
        """Drivers without a team join the shared team they're in elsewhere."""
        for team in profile.get("teams", []):
            for lid in team["shared"]:
                other = others.get(lid)
                if not other:
                    continue
                for od in other.get("drivers", []):
                    if str(od.get("team") or "").strip().lower() != team["name"].lower():
                        continue
                    mine = self._same_driver(od, profile.get("drivers", []))
                    if mine is not None and not str(mine.get("team") or "").strip():
                        mine["team"] = team["name"]

    def _sync_teams(self, profile, others):
        me = profile["id"]
        teams = {t["name"].lower(): t for t in profile.get("teams", [])}
        for lid, other in others.items():
            changed = False
            other_teams = other.setdefault("teams", [])
            # Links this league has dropped: the other league keeps its copy.
            for ot in other_teams:
                mine = teams.get(ot["name"].lower())
                if me in (ot.get("shared") or []) and not (mine and lid in mine["shared"]):
                    ot["shared"] = [x for x in ot["shared"] if x != me]
                    changed = True
            for team in profile.get("teams", []):
                if lid not in team["shared"]:
                    continue
                ot = next((t for t in other_teams if t["name"].lower() == team["name"].lower()), None)
                if ot is None:
                    ot = {"name": team["name"]}
                    other_teams.append(ot)
                logo = self._copy_logo(me, lid, team.get("logo"))
                links = sorted(set(ot.get("shared") or []) | {me})  # its own links, and this league
                new = {"name": team["name"], "short": team["short"], "color": team["color"], "logo": logo, "shared": links}
                if any(ot.get(k) != v for k, v in new.items()):
                    ot.update(new)
                    changed = True
                for d in profile.get("drivers", []):
                    if str(d.get("team") or "").strip().lower() != team["name"].lower():
                        continue
                    theirs = self._same_driver(d, other.get("drivers", []))
                    if theirs is not None and theirs.get("team") != team["name"]:
                        theirs["team"] = team["name"]
                        changed = True
            if changed:
                self._write(other)

    def remove_team_from(self, profile_id, team_name, other_id):
        """Take a team out of another league: the link between the two goes,
        and the other league's copy is deleted (its drivers there are left
        without a team). Returns this league as saved."""
        profile, other = self.get(profile_id), self.get(other_id)
        if profile is None or other is None:
            raise LeagueError("League not found")
        key = str(team_name or "").strip().lower()
        for t in profile.get("teams", []):
            if t["name"].lower() == key:
                t["shared"] = [x for x in t.get("shared") or [] if x != other_id]
        other["teams"] = [t for t in other.get("teams", []) if t["name"].lower() != key]
        for d in other.get("drivers", []):
            if str(d.get("team") or "").strip().lower() == key:
                d["team"] = ""
        self._write(other)
        return self._write(profile)

    def _copy_logo(self, src_id, dst_id, logo):
        """A team logo for another league: library logos as they are, uploads copied over."""
        if not logo or LIBRARY_LOGO.fullmatch(logo):
            return logo
        src = self.logo_file(src_id, logo)
        if src is None:
            return None
        dst = self._logo_dir(dst_id) / logo
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        return logo

    # -- class logos --------------------------------------------------------

    def _logo_dir(self, profile_id):
        return self.dir / "logos" / _slug(profile_id)

    def _prune_logos(self, profile):
        """Delete image files nothing in the profile refers to any more."""
        folder = self._logo_dir(profile["id"])
        if not folder.is_dir():
            return
        used = {c.get("logo") for c in profile.get("classes", [])}
        used |= {t.get("logo") for t in profile.get("teams", [])}
        used |= {d.get(k) for d in profile.get("drivers", []) for k in DRIVER_IMAGES}
        used |= {b.get("file") for b in profile.get("banners", []) + profile.get("sponsors", [])}
        used |= {profile.get("logo"), profile.get("calendar_image")}
        for f in folder.iterdir():
            if f.name not in used:
                f.unlink(missing_ok=True)

    def save_logo(self, profile_id, class_id, data):
        """Store an uploaded logo for a class and point the class at it."""
        return self.save_image(profile_id, f"class:{class_id}", data)

    def save_image(self, profile_id, target, data):
        """Store an uploaded image and point the profile at it.

        ``target`` is ``class:<class id>``, ``team:<team name>``,
        ``car:<driver key>`` or ``helmet:<driver key>`` (see ``driver_key``);
        ``league:logo`` or ``league:calendar_image``; or a new
        ``banner:<horizontal|vertical>`` or ``sponsor:<name>``.
        """
        profile = self.get(profile_id)
        if profile is None:
            raise LeagueError("Save the league before adding images.")
        kind, _, key = str(target).partition(":")
        if kind == "class":
            owner = next((c for c in profile.get("classes", []) if c["id"] == key), None)
            if owner is None:
                raise LeagueError("Save the class before adding its logo.")
            field, prefix = "logo", owner["id"]
        elif kind == "team":
            key = key.strip()
            if not key:
                raise LeagueError("Team needs a name.")
            teams = profile.setdefault("teams", [])
            owner = next((t for t in teams if t["name"].lower() == key.lower()), None)
            if owner is None:
                owner = {"name": key, "logo": None}
                teams.append(owner)
            field, prefix = "logo", f"team-{_slug(key)}"
        elif kind == "league" and key in ("logo", "calendar_image"):
            owner, field, prefix = profile, key, f"league-{key.replace('_', '-')}"
        elif kind == "banner":
            # A new league logo / banner, "horizontal" or "vertical".
            if key not in BANNER_SHAPES:
                raise LeagueError("A banner is horizontal or vertical.")
            owner = {"id": uuid.uuid4().hex[:8], "file": None, "orientation": key, "name": ""}
            profile.setdefault("banners", []).append(owner)
            field, prefix = "file", f"banner-{key}"
        elif kind == "sponsor":
            owner = {"id": uuid.uuid4().hex[:8], "file": None, "name": key.strip()[:60]}
            profile.setdefault("sponsors", []).append(owner)
            field, prefix = "file", "sponsor"
        elif kind in ("car", "helmet"):
            owner = next((d for d in profile.get("drivers", []) if driver_key(d) == key), None)
            if owner is None:
                raise LeagueError("Save the driver before adding images.")
            field, prefix = f"{kind}_image", f"{kind}-{_slug(key)}"
        else:
            raise LeagueError("Unknown image target.")
        ext = sniff_logo(data)
        # The content hash in the name makes browsers pick up a replaced image.
        name = f"{prefix}-{hashlib.sha256(data).hexdigest()[:8]}.{ext}"
        folder = self._logo_dir(profile["id"])
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
        owner[field] = name
        return self.save(profile)

    def put_image(self, profile_id, name, data):
        """Store an image under its own (uploaded-style) name, e.g. from an import.
        The profile still has to refer to it, or the next save tidies it away."""
        if not UPLOADED_LOGO.fullmatch(name or ""):
            raise LeagueError("Not an image name this app uses.")
        sniff_logo(data)
        folder = self._logo_dir(profile_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)

    def logo_file(self, profile_id, filename):
        """Path of a stored logo, or None. Guards against path tricks."""
        if not UPLOADED_LOGO.fullmatch(filename or ""):
            return None
        path = self._logo_dir(profile_id) / filename
        return path if path.is_file() else None

    def duplicate(self, profile_id, name=None):
        """A copy of a league (drivers, classes, teams, championship, images)
        under a new name ("<name> (copy)" unless given) and id."""
        profile = self.get(profile_id)
        if profile is None:
            raise LeagueError("League not found")
        base = str(name or "").strip() or f"{profile.get('name') or profile_id} (copy)"
        new_name, n = base, 2
        taken = {p["id"] for p in self.list()}
        while _slug(new_name) in taken:
            new_name, n = f"{base} {n}", n + 1
        copy = json.loads(json.dumps(profile))
        copy.update(id=_slug(new_name), name=new_name, league_id=None)
        for t in copy.get("teams", []):
            t["shared"] = []  # a copy of its own: its teams aren't linked to other leagues
        src, dst = self._logo_dir(profile_id), self._logo_dir(copy["id"])
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        return self._write(copy)

    def delete(self, profile_id):
        path = self._path(profile_id)
        if path.exists():
            path.unlink()
        shutil.rmtree(self._logo_dir(profile_id), ignore_errors=True)
        if profile_id == self.active_id:
            self.set_active(None)

    def set_active(self, profile_id):
        with self._lock:
            profile = self.get(profile_id) if profile_id else None
            self.active_id = profile["id"] if profile else None
            self._active = profile
            try:
                self._active_file.write_text(self.active_id or "", encoding="utf-8")
            except OSError:
                pass
        return profile

    def active(self):
        return self._active

    def lookup(self, cust_id, car_number, profile=None):
        """Find a league's entry (the active league by default) for a session driver."""
        profile = profile or self._active
        if not profile:
            return None
        by_number = None
        for d in profile.get("drivers", []):
            if cust_id is not None and d.get("cust_id") == cust_id:
                return d
            if by_number is None and d.get("cust_id") is None and car_number and d.get("car_number") == car_number:
                by_number = d
        return by_number

    def class_for(self, entry, car_class, profile=None, name=None):
        """A league's class for a driver: their own pick, else the class tag
        in front of their name ("(P) Dave Price"), else by car class.

        Uses the active league unless ``profile`` is given. ``name`` is the
        driver's name in the session, whose tag can change as they move class.
        """
        profile = profile or self._active
        if not profile:
            return None
        classes = main_classes(profile.get("classes", []))
        if entry and entry.get("class_id"):
            for c in classes:
                if c["id"] == entry["class_id"]:
                    return c
        # The tag in the session name first (it changes as drivers move
        # class), else the one in the roster.
        tag = class_tag(name) or class_tag((entry or {}).get("name"))
        if tag:
            by_tag = class_for_tag(classes, tag)
            if by_tag:
                return by_tag
        wanted = (car_class or "").lower()
        if wanted:
            for c in classes:
                if wanted in (m.lower() for m in c.get("match", [])):
                    return c
        return None

    def team(self, team_name, profile=None):
        """A team in a league (the active one by default), or None."""
        profile = profile or self._active
        if not profile or not team_name:
            return None
        for t in profile.get("teams", []):
            if t["name"].lower() == team_name.strip().lower():
                return t
        return None

    def team_logo(self, team_name, profile=None):
        """Logo reference for a team in a league (the active one by default)."""
        team = self.team(team_name, profile)
        return team.get("logo") if team else None

    def ensure_driver(self, profile_id, cust_id, name, car_number, make=""):
        """Find (or add) a session driver in a league's roster; returns their driver key."""
        with self._lock:
            profile = self.get(profile_id)
        if profile is None:
            raise LeagueError("League not found.")
        drivers = profile.setdefault("drivers", [])
        for d in drivers:
            if cust_id is not None and d.get("cust_id") == cust_id:
                return driver_key(d)
        for d in drivers:
            if d.get("cust_id") is None and d.get("name", "").strip().lower() == name.strip().lower():
                return driver_key(d)
        entry = {"cust_id": cust_id, "name": name, "car_number": car_number, "car_make": make}
        drivers.append(entry)
        self.save(profile)
        return driver_key(entry)

    def import_session(self, profile_id, session_drivers):
        """Merge the session's drivers into a league: add new ones, fill blanks.

        Commentator edits (nicknames, notes, classes, photos) are never touched.
        Returns ``(profile, added)``.
        """
        profile = self.get(profile_id)
        if profile is None:
            raise LeagueError("Save the league first.")
        drivers = profile.setdefault("drivers", [])
        by_id = {d.get("cust_id"): d for d in drivers if d.get("cust_id") is not None}
        by_name = {d.get("name", "").strip().lower(): d for d in drivers if d.get("cust_id") is None}
        added = 0
        for sd in session_drivers:
            existing = by_id.get(sd.get("cust_id")) or by_name.get(sd.get("name", "").strip().lower())
            if existing is None:
                drivers.append({"cust_id": sd.get("cust_id"), "name": sd.get("name", ""),
                                "car_number": sd.get("number", ""), "team": sd.get("team", ""),
                                "car_make": sd.get("make", "")})
                added += 1
                continue
            if existing.get("cust_id") is None and sd.get("cust_id") is not None:
                existing["cust_id"] = sd["cust_id"]
            for field, value in (("car_number", sd.get("number", "")), ("team", sd.get("team", "")),
                                 ("car_make", sd.get("make", ""))):
                if value and not existing.get(field):
                    existing[field] = value
        return self.save(profile), added
