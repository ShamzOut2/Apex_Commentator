"""Settings for the stream overlays (standings and the qualifying lap tracker).

They're changed from the app's Overlays tab and kept in
``data/overlays.json`` so OBS pages look the same after a restart.
"""

import json
import re
import threading
from pathlib import Path

NAME_FORMATS = ("full", "initial_last", "last_initial", "last", "first", "abbrev", "nickname")

DEFAULTS = {
    "standings": {
        "visible": True,
        "mode": "overall",        # "overall" or "class"
        "class_key": "",          # "class" mode: one class only ("" = every class, one block each)
        "rows": 20,               # most drivers shown (per class in "class" mode)
        "rows_last": 0,           # "overall": when there are more drivers, also the last N (last place included)
        "name_format": "last_initial",
        "show_team": True,
        "show_logo": True,
        "show_number": True,
        "show_gap": True,         # race: gap to the leader; qualifying: gap to pole
        "show_interval": False,   # to the car ahead
        "show_pos_change": True,  # race: places gained / lost since the start
        "show_best_lap": False,
        "show_last_lap": False,
        "show_laps": False,       # laps completed
        "show_pits": False,       # pit stops made
        "show_pit_status": True,  # "PIT" while on pit road
        # Start of a session: only the header (session, laps / time left), and
        # each driver appears once they've completed a lap.
        "reveal": False,
        "header_info": "auto",    # "auto" (laps or time, whichever the session is limited by), "laps", "time", "none"
        # Fastest lap: a purple stopwatch by the holder's name (each class's
        # holder in "class" mode), and a purple pill at the top middle of the
        # screen for fl_flash_s when someone sets a new fastest lap.
        "show_fastest_icon": True,
        "fl_flash": True,
        "fl_flash_s": 6.0,
        "fl_flash_classes": False,  # also a new fastest lap in each class, not just overall
    },
    # Sponsor logos on their own (sponsors.html), over the race.
    "sponsors": {
        "visible": False,
        "place": "bottom-right",  # a corner, an edge ("top", "bottom": centred), or "left" / "right" (centred)
        "layout": "rotate",       # "rotate": one logo at a time; "row": all of them together
        "interval_s": 8.0,        # "rotate": seconds per logo
        "size": 90,               # logo height in px (1920x1080)
        "background": True,       # a dark panel behind the logos
        "title": "",              # a small caption above them, e.g. "Partners"
        "sponsor_ids": "",        # which sponsors, comma separated ("" = all, "none" = none)
    },
    # Full-screen boards (board.html), one section each. Every board has:
    # banner ("none", "top", "bottom", "left", "right"), banner_id (which of
    # the league's banners, "" = the first of the right shape),
    # league_logo (the league's logo in the header), sponsors (where the
    # sponsor logos go, the same places as a banner) and sponsor_ids (which,
    # as for the sponsors overlay).
    "board_championship": {
        "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "",
        "rows": 20, "rounds": 0,  # rounds: points from the last N rounds as columns (0 = none)
        "show_number": True, "show_team": True, "show_logo": True, "show_make": True,
        "show_gap": True, "show_ahead": False,  # gap to the leader; gap to the driver ahead
        "show_wins": False, "show_penalty": False,
    },
    "board_teams": {
        "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "",
        "rows": 12, "rounds": 0,  # rounds: the team's points from the last N rounds as columns
        "show_logo": True, "show_color": True,  # team logo; team colour stripe
        "show_drivers": True,  # the drivers who scored for the team, under its name
        "show_gap": True, "show_ahead": False, "show_wins": False, "show_penalty": False,
    },
    "board_makes": {"banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", "rows": 12, "show_logo": True,
                    "show_gap": True, "show_wins": True},
    "board_calendar": {"banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "",
                       "style": "cards",  # "cards" (built from the rounds) or "image" (the league's own calendar graphic)
                       "show_date": True, "show_time": True, "show_config": True, "show_length": True,
                       "show_winners": True},
    "board_results": {
        "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "",
        "rows": 30, "show_number": True, "show_team": True, "show_logo": True, "show_make": True,
        "show_laps": True, "show_gained": True, "show_fastest": True, "show_points": True, "show_status": True,
    },
    "laps": {
        "visible": True,
        "count": 4,               # small trackers along the bottom
        "name_format": "initial_last",
        "reference": "personal",  # sector colours against "personal" bests or the "session" (class) best
        "sectors": 3,             # sectors shown: the track's split points merged into this many (0 = all of them)
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

LIMITS = {"rows_last": (0, 30), "fl_flash_s": (1.0, 60.0), "size": (30, 300), "interval_s": (1.0, 120.0), "rows": (1, 64), "rounds": (0, 10), "count": (0, 12), "sectors": (0, 12), "green_s": (0.0, 5.0), "hide_s": (0.0, 60.0)}
PLACES = ("top-left", "top", "top-right", "left", "right", "bottom-left", "bottom", "bottom-right")
CHOICES = {"banner": ("none", "top", "bottom", "left", "right"), "sponsors": ("none", "top", "bottom", "left", "right"),
           "place": PLACES, "style": ("cards", "image"), "layout": ("rotate", "row"), "mode": ("overall", "class"), "header_info": ("auto", "laps", "time", "none"), "reference": ("personal", "session"), "name_format": NAME_FORMATS}


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
        value = str(value)[:200]
        if key == "sponsor_ids":
            return ",".join(re.sub(r"[^a-z0-9]", "", v) for v in value.split(",") if re.sub(r"[^a-z0-9]", "", v))
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
