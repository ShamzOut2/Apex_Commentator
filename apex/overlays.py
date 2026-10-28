"""Settings for the stream overlays (standings and the qualifying lap tracker).

They're changed from the app's Overlays tab and kept in
``data/overlays.json`` so OBS pages look the same after a restart.
"""

import json
import threading
from pathlib import Path

NAME_FORMATS = ("full", "initial_last", "last_initial", "last", "first", "abbrev", "nickname")

DEFAULTS = {
    "standings": {
        "visible": True,
        "mode": "overall",        # "overall" or "class"
        "class_key": "",          # "class" mode: one class only ("" = every class, one block each)
        "rows": 20,               # most drivers shown (per class in "class" mode)
        "name_format": "last_initial",
        "show_team": True,
        "show_logo": True,
        "show_number": True,
        "show_gap": True,
    },
    "laps": {
        "visible": True,
        "count": 4,               # small trackers along the bottom
        "name_format": "initial_last",
        "reference": "personal",  # sector colours against "personal" bests or the "session" (class) best
        "green_s": 0.2,
        "hide_s": 5.0,
        "show_team": True,
        "show_logo": True,
        "show_number": True,
        "show_driver_number": False,
        "show_invalid": False,    # small trackers: also show laps already invalid
        "practice": False,        # also run in practice sessions (it always runs in qualifying)
    },
}

LIMITS = {"rows": (1, 64), "count": (0, 12), "green_s": (0.0, 5.0), "hide_s": (0.0, 60.0)}
CHOICES = {"mode": ("overall", "class"), "reference": ("personal", "session"), "name_format": NAME_FORMATS}


def normalise(settings):
    out = {}
    settings = settings if isinstance(settings, dict) else {}
    for section, defaults in DEFAULTS.items():
        given = settings.get(section) if isinstance(settings.get(section), dict) else {}
        out[section] = {key: _value(key, given.get(key, default), default) for key, default in defaults.items()}
    return out


def _value(key, value, default):
    try:
        if isinstance(default, bool):
            return bool(value)
        if isinstance(default, (int, float)):
            value = type(default)(value)
            lo, hi = LIMITS.get(key, (value, value))
            return min(max(value, lo), hi)
        value = str(value)
        return value if key not in CHOICES or value in CHOICES[key] else default
    except (TypeError, ValueError):
        return default


class OverlaySettings:
    def __init__(self, path=None):
        """``path`` None keeps settings in memory only."""
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self.settings = normalise({})
        if self.path:
            try:
                self.settings = normalise(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass

    def get(self):
        return self.settings

    def update(self, section, values):
        if section not in DEFAULTS:
            raise ValueError(f"Unknown overlay '{section}'")
        with self._lock:
            merged = {**self.settings, section: {**self.settings[section], **(values or {})}}
            self.settings = normalise(merged)
            if not self.path:
                return self.settings
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
            except OSError as e:
                print(f"[apex] couldn't save overlay settings: {e}")
        return self.settings
