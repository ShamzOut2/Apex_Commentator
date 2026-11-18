"""Apex Labs licence key: optional during early access.

People get a free key at https://apex-labs-3kf.pages.dev/key/ (Discord
sign-in) and paste it in Home → Licence. The app sends the key to the Apex
Labs key service, which answers with a licence signed with Ed25519. The
licence is kept in ``data/licence.json`` and checked here against the public
key below, so it works offline until it expires (30 days after the last
check) and can't be forged by editing the file.

Nothing in the app is locked: without a key, or offline, everything works as
before. The service is checked when the app starts and then once a day.

The PC id is a random id shared with Apex Overlays (``%APPDATA%\\Apex Labs\\pc-id``)
so one PC running both apps counts once against the key's limit of 5 PCs.
"""

import base64
import calendar
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVICE = "https://apex-keys.shamzout.workers.dev"
PUBLIC_KEY = "0oLW-0hzSRd5aBYMf78Bgdb1yJ_xq91Qnrf-6n2P9Lk"
GET_KEY_URL = "https://apex-labs-3kf.pages.dev/key/"
APP = "commentator"
CHECK_EVERY_S = 24 * 3600
OFFLINE = "Couldn't reach the Apex Labs key service. Your licence keeps working offline; it will check again later."


class LicenceError(Exception):
    """A message ready to show the user."""


def normalise_key(text):
    """``APEX-XXXX-XXXX-XXXX-XXXX`` from whatever was pasted, or None."""
    raw = re.sub(r"[\s-]", "", str(text or "").upper()).replace("O", "0").replace("I", "1").replace("L", "1")
    if not re.fullmatch(r"APEX[0-9A-HJKMNP-TV-Z]{16}", raw):
        return None
    return "APEX-" + "-".join(raw[i:i + 4] for i in range(4, 20, 4))


def default_pc_id_file():
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "Apex Labs" / "pc-id"


# ---------- Ed25519 signature check (RFC 8032), standard library only ----------

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _I % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


def _add(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, point):
    q = (0, 1, 1, 0)
    while s:
        if s & 1:
            q = _add(q, point)
        point = _add(point, point)
        s >>= 1
    return q


def _equal(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _decompress(data):
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def ed25519_verify(public, message, signature):
    """True if ``signature`` is ``public``'s Ed25519 signature of ``message``."""
    if len(public) != 32 or len(signature) != 64:
        return False
    a, r = _decompress(public), _decompress(signature[:32])
    if a is None or r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    return _equal(_mul(s, _G), _add(r, _mul(h, a)))


def _b64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def read_token(token, public_key=PUBLIC_KEY):
    """The licence inside a signed token, or None if the signature is wrong."""
    try:
        body, sig = str(token).split(".")
        if not ed25519_verify(_b64(public_key), body.encode("ascii"), _b64(sig)):
            return None
        data = json.loads(_b64(body))
        return data if isinstance(data, dict) else None
    except (ValueError, UnicodeError):
        return None


def _parse_time(text):
    try:
        return calendar.timegm(time.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return 0


# ---------- the licence ----------

class Licence:
    def __init__(self, version, state_file=None, pc_id_file=None, enabled=True, opener=None,
                 service=SERVICE, public_key=PUBLIC_KEY, clock=time.time):
        self.version = version
        self.state_file = Path(state_file) if state_file else None
        self.pc_id_file = Path(pc_id_file) if pc_id_file else default_pc_id_file()
        self.enabled = enabled
        self.service = service.rstrip("/")
        self.public_key = public_key
        self.clock = clock
        self._open = opener or urllib.request.urlopen
        self._lock = threading.Lock()
        self.state = {}
        if self.state_file:
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                self.state = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                pass
        self._pc_id = None

    # --- storage ---

    @property
    def pc_id(self):
        if self._pc_id:
            return self._pc_id
        try:
            value = self.pc_id_file.read_text(encoding="utf-8").strip()
            if re.fullmatch(r"[A-Za-z0-9_-]{16,64}", value):
                self._pc_id = value
                return value
        except OSError:
            pass
        value = self.state.get("pc_id") or secrets.token_urlsafe(18)
        try:
            self.pc_id_file.parent.mkdir(parents=True, exist_ok=True)
            self.pc_id_file.write_text(value, encoding="utf-8")
        except OSError:
            self.state["pc_id"] = value  # can't share it: keep our own
            self._save()
        self._pc_id = value
        return value

    def _save(self):
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    # --- what the app asks ---

    def current(self):
        """The verified licence for this key and PC, or None (no key, expired, tampered)."""
        token, key = self.state.get("token"), self.state.get("key")
        if not token or not key:
            return None
        lic = read_token(token, self.public_key)
        if not lic or lic.get("key") != key or lic.get("pc_id") != self.pc_id or lic.get("app") != APP:
            return None
        if _parse_time(lic.get("expires_at")) <= self.clock():
            return None
        return lic

    def has_feature(self, name):
        lic = self.current()
        return bool(lic) and ("all" in lic.get("features", []) or name in lic.get("features", []))

    def status(self):
        lic = self.current()
        key = self.state.get("key") or ""
        return {
            "enabled": self.enabled,
            "has_key": bool(key),
            "key": key,
            "valid": bool(lic),
            "user": (lic or {}).get("user", ""),
            "tier": (lic or {}).get("tier", ""),
            "tier_name": (lic or {}).get("tier_name", ""),
            "features": (lic or {}).get("features", []),
            "expires_at": (lic or {}).get("expires_at", ""),
            "checked_at": self.state.get("checked_at", ""),
            "error": self.state.get("error", ""),
            "manage_url": self.state.get("manage_url") or self.service + "/",
            "get_key_url": GET_KEY_URL,
        }

    # --- talking to the key service ---

    def _post(self, path, payload):
        req = urllib.request.Request(
            self.service + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": f"Apex-Commentator/{self.version}"},
            method="POST",
        )
        try:
            with self._open(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                data = json.loads(e.read().decode("utf-8"))
            except (ValueError, OSError):
                data = {}
            raise LicenceError(data.get("message") or f"The key service answered {e.code}.") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ConnectionError(OFFLINE) from e

    def _activate(self, key):
        data = self._post("/v1/activate", {"key": key, "pc_id": self.pc_id, "app": APP, "version": self.version})
        token = data.get("token", "")
        lic = read_token(token, self.public_key)
        if not lic or lic.get("key") != key or lic.get("pc_id") != self.pc_id:
            raise LicenceError("The key service sent a licence this app couldn't verify. Please update the app.")
        return data

    def set_key(self, text):
        """Add a key (checks it with the service first). Returns the status."""
        key = normalise_key(text)
        if not key:
            raise LicenceError("That doesn't look like an Apex Labs key. It looks like APEX-XXXX-XXXX-XXXX-XXXX.")
        try:
            data = self._activate(key)
        except ConnectionError as e:
            raise LicenceError("Couldn't reach the Apex Labs key service. Check your internet connection and try again.") from e
        with self._lock:
            self.state.update(key=key, token=data["token"], checked_at=_now_iso(self.clock()), error="",
                              manage_url=data.get("manage_url", ""))
            self._save()
        return self.status()

    def remove(self):
        """Forget the key on this PC and free its slot (if the service can be reached)."""
        key = self.state.get("key")
        if key:
            try:
                self._post("/v1/deactivate", {"key": key, "pc_id": self.pc_id})
            except (LicenceError, ConnectionError):
                pass
        with self._lock:
            for name in ("key", "token", "checked_at", "error", "manage_url"):
                self.state.pop(name, None)
            self._save()
        return self.status()

    def refresh(self):
        """Check the key again. Offline keeps the saved licence; a turned-off key loses it."""
        key = self.state.get("key")
        if not key or not self.enabled:
            return self.status()
        try:
            data = self._activate(key)
        except ConnectionError as e:
            with self._lock:
                self.state["error"] = str(e)
                self._save()
            return self.status()
        except LicenceError as e:
            with self._lock:
                self.state["error"] = str(e)
                self.state.pop("token", None)
                self._save()
            return self.status()
        with self._lock:
            self.state.update(token=data["token"], checked_at=_now_iso(self.clock()), error="",
                              manage_url=data.get("manage_url", ""))
            self._save()
        return self.status()

    def start(self):
        """Check in the background now and then once a day."""
        if not self.enabled:
            return

        def loop():
            time.sleep(5)
            while True:
                try:
                    self.refresh()
                except Exception as e:  # never take the app down over a licence check
                    print(f"[apex] licence check: {e!r}")
                time.sleep(CHECK_EVERY_S)

        threading.Thread(target=loop, name="licence", daemon=True).start()


def _now_iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
