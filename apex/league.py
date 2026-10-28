"""League builder: fetch league rosters from the iRacing Data API and keep
editable league profiles on disk.

A league profile is a small JSON file in ``data/leagues/``::

    {
      "id": "12345",
      "league_id": 12345,
      "name": "Sunday Night GT3",
      "source": "iracing",          # iracing | session | manual
      "updated_at": "2026-10-27T19:00:00Z",
      "classes": [
        {"id": "pro", "name": "Pro", "color": "#e8463c", "match": ["GT3"],
         "logo": "pro-1a2b3c4d.png", "logo_bg": "auto", "logo_tolerance": 18,
         "logo_fill": "edges"}
      ],
      "drivers": [
        {"cust_id": 123456, "name": "Jane Doe", "nickname": "JD",
         "car_number": "7", "team": "Apex Racing", "notes": "Leads the title",
         "class_id": "pro"}
      ]
    }

A driver's class is their ``class_id`` when set, otherwise the first class
whose ``match`` list contains their iRacing car class name. A class logo is
either uploaded (stored in ``data/leagues/logos/<league>/``) or picked from
the built-in library in ``web/logos/`` (``"logo": "lib:pro.svg"``).

The overlay matches each logo's background to the class colour. Layered SVGs
(see ``tools/logo_to_svg.py``) have their badge layer set to the colour
exactly; other images have their background detected and recoloured
(``logo_bg``: ``auto`` detects it, a ``#rrggbb`` value names it, ``keep``
leaves the logo untouched).

Commentator edits (nicknames, teams, notes, classes) live in the profile, so
they survive re-fetching: a refresh only adds new members and updates names
and numbers.

Authentication uses iRacing's OAuth "password limited" grant, which needs a
client ID and secret issued by iRacing in addition to your login. See
README.md for details.
"""

import base64
import hashlib
import json
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .paths import WEB_DIR

LOGO_LIBRARY_DIR = WEB_DIR / "logos"
UPLOADED_LOGO = re.compile(r"[a-z0-9-]+\.(png|jpg|webp|svg)")
LIBRARY_LOGO = re.compile(r"lib:([a-z0-9-]+\.svg)")
TOKEN_URL = "https://oauth.iracing.com/oauth2/token"
DATA_URL = "https://members-ng.iracing.com/data"
EDITABLE_FIELDS = ("nickname", "team", "notes", "class_id", "car_image", "helmet_image")
DRIVER_IMAGES = ("car_image", "helmet_image")
# Distinct defaults handed to new classes, in order.
CLASS_PALETTE = ["#e8463c", "#2f80ed", "#27ae60", "#f2c94c", "#9b51e0", "#f2994a", "#56ccf2", "#eb5ea8"]
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # livery screenshots can be big
LOGO_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "svg": "image/svg+xml"}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class LeagueError(Exception):
    """A user-facing error from the league builder."""


def mask_secret(secret, identifier):
    """iRacing credential masking: base64(sha256(secret + lower(trim(id))))."""
    combined = f"{secret}{identifier.strip().lower()}".encode("utf-8")
    return base64.b64encode(hashlib.sha256(combined).digest()).decode("ascii")


class IRacingDataClient:
    def __init__(self, username, password, client_id, client_secret, timeout=20):
        self.username = username
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._token = None
        self._token_expires = 0.0
        self._refresh_token = None
        self._lock = threading.Lock()

    @property
    def configured(self):
        return all((self.username, self.password, self.client_id, self.client_secret))

    def _post_token(self, params):
        data = urllib.parse.urlencode(params).encode("ascii")
        req = urllib.request.Request(
            TOKEN_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise LeagueError(f"iRacing login failed ({e.code}): {detail}") from e
        except urllib.error.URLError as e:
            raise LeagueError(f"Could not reach iRacing login server: {e.reason}") from e
        self._token = body["access_token"]
        self._token_expires = time.time() + float(body.get("expires_in", 600)) - 30
        self._refresh_token = body.get("refresh_token")

    def _access_token(self):
        with self._lock:
            if self._token and time.time() < self._token_expires:
                return self._token
            if not self.configured:
                raise LeagueError(
                    "iRacing API credentials are not set. Add your username, password, "
                    "client ID and client secret to config.json (or the IRACING_* "
                    "environment variables), or build the league from the current session."
                )
            masked_secret = mask_secret(self.client_secret, self.client_id)
            if self._refresh_token:
                try:
                    self._post_token({
                        "grant_type": "refresh_token",
                        "client_id": self.client_id,
                        "client_secret": masked_secret,
                        "refresh_token": self._refresh_token,
                    })
                    return self._token
                except LeagueError:
                    self._refresh_token = None
            self._post_token({
                "grant_type": "password_limited",
                "client_id": self.client_id,
                "client_secret": masked_secret,
                "username": self.username,
                "password": mask_secret(self.password, self.username),
                "scope": "iracing.auth",
            })
            return self._token

    def get(self, endpoint, **params):
        """GET a Data API endpoint, following the signed ``link`` it returns."""
        url = f"{DATA_URL}/{endpoint}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._access_token()}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.load(resp)
            if isinstance(body, dict) and "link" in body:
                with urllib.request.urlopen(body["link"], timeout=self.timeout) as resp:
                    body = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._token = None
            if e.code == 404:
                raise LeagueError("League not found (check the League ID).") from e
            detail = e.read().decode("utf-8", "replace")[:300]
            raise LeagueError(f"iRacing API error ({e.code}): {detail}") from e
        except urllib.error.URLError as e:
            raise LeagueError(f"Could not reach the iRacing API: {e.reason}") from e
        return body

    def league(self, league_id):
        return self.get("league/get", league_id=int(league_id), include_licenses="false")


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "league"


def profile_from_api(data):
    """Turn a ``league/get`` response into a league profile."""
    league_id = data.get("league_id")
    drivers = []
    for member in data.get("roster") or []:
        drivers.append({
            "cust_id": member.get("cust_id"),
            "name": member.get("display_name", ""),
            "nickname": member.get("nick_name") or "",
            "car_number": str(member.get("car_number") or ""),
            "team": "",
            "notes": "",
        })
    drivers.sort(key=lambda d: d["name"].lower())
    return {
        "id": str(league_id),
        "league_id": league_id,
        "name": data.get("league_name", f"League {league_id}"),
        "source": "iracing",
        "updated_at": _now_iso(),
        "drivers": drivers,
    }


def merge_profiles(existing, fresh):
    """Refresh ``existing`` with ``fresh`` API data, keeping commentator edits."""
    if not existing:
        return fresh
    old = {d.get("cust_id"): d for d in existing.get("drivers", []) if d.get("cust_id") is not None}
    merged = []
    seen = set()
    for d in fresh["drivers"]:
        prev = old.get(d["cust_id"])
        if prev:
            for key in EDITABLE_FIELDS:
                if prev.get(key):
                    d[key] = prev[key]
        merged.append(d)
        seen.add(d["cust_id"])
    # Keep hand-added drivers (no cust_id, or no longer in the roster but annotated).
    for d in existing.get("drivers", []):
        cid = d.get("cust_id")
        if cid is None or (cid not in seen and any(d.get(k) for k in EDITABLE_FIELDS)):
            merged.append(d)
    result = dict(fresh)
    result["drivers"] = merged
    result["classes"] = existing.get("classes", [])
    result["teams"] = existing.get("teams", [])
    return result


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
        })
    return out


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
    class_ids = {c["id"] for c in classes}
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
        teams.append({"name": team_name, "logo": logo if logo and _valid_logo_ref(str(logo)) else None})
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

    def __init__(self, directory, client=None):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.client = client
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
        for f in folder.iterdir():
            if f.name not in used:
                f.unlink(missing_ok=True)

    def save_logo(self, profile_id, class_id, data):
        """Store an uploaded logo for a class and point the class at it."""
        return self.save_image(profile_id, f"class:{class_id}", data)

    def save_image(self, profile_id, target, data):
        """Store an uploaded image and point the profile at it.

        ``target`` is ``class:<class id>``, ``team:<team name>``,
        ``car:<driver key>`` or ``helmet:<driver key>`` (see ``driver_key``).
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

    def logo_file(self, profile_id, filename):
        """Path of a stored logo, or None. Guards against path tricks."""
        if not UPLOADED_LOGO.fullmatch(filename or ""):
            return None
        path = self._logo_dir(profile_id) / filename
        return path if path.is_file() else None

    def delete(self, profile_id):
        path = self._path(profile_id)
        if path.exists():
            path.unlink()
        shutil.rmtree(self._logo_dir(profile_id), ignore_errors=True)
        if profile_id == self.active_id:
            self.set_active(None)

    def fetch(self, league_id):
        try:
            league_id = int(str(league_id).strip())
        except ValueError as e:
            raise LeagueError("League ID must be a number.") from e
        if self.client is None:
            raise LeagueError("iRacing API client is not configured.")
        fresh = profile_from_api(self.client.league(league_id))
        return self.save(merge_profiles(self.get(fresh["id"]), fresh))

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

    def lookup(self, cust_id, car_number):
        """Find the active league's entry for a session driver."""
        profile = self._active
        if not profile:
            return None
        by_number = None
        for d in profile.get("drivers", []):
            if cust_id is not None and d.get("cust_id") == cust_id:
                return d
            if by_number is None and d.get("cust_id") is None and car_number and d.get("car_number") == car_number:
                by_number = d
        return by_number

    def class_for(self, entry, car_class, profile=None):
        """A league's class for a driver: their own pick, else by car class.

        Uses the active league unless ``profile`` is given.
        """
        profile = profile or self._active
        if not profile:
            return None
        classes = profile.get("classes", [])
        if entry and entry.get("class_id"):
            for c in classes:
                if c["id"] == entry["class_id"]:
                    return c
        wanted = (car_class or "").lower()
        if wanted:
            for c in classes:
                if wanted in (m.lower() for m in c.get("match", [])):
                    return c
        return None

    def team_logo(self, team_name, profile=None):
        """Logo reference for a team in a league (the active one by default)."""
        profile = profile or self._active
        if not profile or not team_name:
            return None
        for t in profile.get("teams", []):
            if t["name"].lower() == team_name.strip().lower():
                return t.get("logo")
        return None

    def ensure_driver(self, profile_id, cust_id, name, car_number):
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
        entry = {"cust_id": cust_id, "name": name, "car_number": car_number}
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
                                "car_number": sd.get("number", ""), "team": sd.get("team", "")})
                added += 1
                continue
            if existing.get("cust_id") is None and sd.get("cust_id") is not None:
                existing["cust_id"] = sd["cust_id"]
            for field, value in (("car_number", sd.get("number", "")), ("team", sd.get("team", ""))):
                if value and not existing.get(field):
                    existing[field] = value
        return self.save(profile), added
