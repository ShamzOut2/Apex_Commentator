"""League builder: fetch league rosters from the iRacing Data API and keep
editable league profiles on disk.

A league profile is a small JSON file in ``data/leagues/``::

    {
      "id": "12345",
      "league_id": 12345,
      "name": "Sunday Night GT3",
      "source": "iracing",          # iracing | session | manual
      "updated_at": "2026-10-27T19:00:00Z",
      "drivers": [
        {"cust_id": 123456, "name": "Jane Doe", "nickname": "JD",
         "car_number": "7", "team": "Apex Racing", "notes": "Leads the title"}
      ]
    }

Commentator edits (nicknames, teams, notes) live in the profile, so they
survive re-fetching: a refresh only adds new members and updates names and
numbers.

Authentication uses iRacing's OAuth "password limited" grant, which needs a
client ID and secret issued by iRacing in addition to your login. See
README.md for details.
"""

import base64
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TOKEN_URL = "https://oauth.iracing.com/oauth2/token"
DATA_URL = "https://members-ng.iracing.com/data"
EDITABLE_FIELDS = ("nickname", "team", "notes")


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
    return result


def profile_from_session(drivers, name):
    """Build a profile from the drivers currently in the session."""
    return {
        "id": _slug(name),
        "league_id": None,
        "name": name,
        "source": "session",
        "updated_at": _now_iso(),
        "drivers": [{
            "cust_id": d.get("cust_id"),
            "name": d.get("name", ""),
            "nickname": "",
            "car_number": d.get("number", ""),
            "team": d.get("team", ""),
            "notes": "",
        } for d in drivers],
    }


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
        if entry["name"] or entry["cust_id"] is not None:
            drivers.append(entry)
    pid = str(profile.get("id") or (league_id if league_id is not None else _slug(name)))
    return {
        "id": _slug(pid) if league_id is None else str(pid),
        "league_id": league_id,
        "name": name,
        "source": profile.get("source") or "manual",
        "updated_at": _now_iso(),
        "drivers": drivers,
    }


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
        return profile

    def delete(self, profile_id):
        path = self._path(profile_id)
        if path.exists():
            path.unlink()
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
