"""Settings for the stream overlays (standings and the qualifying lap tracker).

They're changed from the app's Overlays tab and kept in
``data/overlays.json`` so OBS pages look the same after a restart.
"""

import json
import re
import threading
from pathlib import Path

# Every overlay and board's background: "default" (overlays see-through,
# boards and full screens their own look), a solid "color" or an uploaded
# "image" (see backgrounds.py), at bg_opacity percent; and its size (scale,
# percent: an overlay grows or shrinks from where it sits, a board or full
# screen from the middle).
BACKGROUND = {"bg": "default", "bg_color": "#0b0d12", "bg_image": "", "bg_opacity": 100, "scale": 100}

# Overlays and boards with columns can dim each column on its own:
# col_opacity "gap:60,laps:40" (percent; columns left out are 100), used
# while col_opacity_on is ticked.
COLUMN_OPACITY = {"col_opacity_on": False, "col_opacity": ""}

NAME_FORMATS = ("full", "initial_last", "last_initial", "last", "first", "abbrev", "nickname")

# The standings' columns after the driver, in the order shown: the tower's
# (each switched on and off with its show_ setting) and the full screen's
# (a fixed set: Last and Pits in races only). "" for the full screen keeps
# its usual order, which differs between races and qualifying.
TOWER_COLUMNS = ("pos_change", "laps", "pits", "last_lap", "best_lap", "gap", "interval")
SCREEN_COLUMNS = ("laps", "gap", "interval", "last_lap", "best_lap", "pits")
ORDERS = {"column_order": TOWER_COLUMNS, "screen_column_order": SCREEN_COLUMNS}

DEFAULTS = {
    "standings": {
        "visible": True,
        "mode": "overall",        # "overall" or "class"
        "class_key": "",          # "class" mode: one class only ("" = every class, one block each)
        "rows": 20,               # most drivers shown (per class in "class" mode)
        # "overall", more drivers than rows: rows_last more under the top of the
        # order, after a small gap. "rotate": the rest of the field, that many at
        # a time, a new set every rows_extra_s (then back to the first);
        # "last": always the last ones (last place included).
        "rows_last": 0,
        "rows_extra_mode": "rotate",
        "rows_extra_s": 6.0,
        "rows_extra_opacity": 100,
        "width": 0,               # tower width in px; 0 = automatic (each column fits what's in it)
        "name_format": "last_initial",
        "show_team": True,
        "show_logo": True,
        "show_number": True,
        "show_stripe": True,      # the coloured bar by each driver (class or team colour)
        "show_col_labels": True,  # the column headings (GAP, INT...) under the header
        "leader_cell": "leader",  # race: the leader's gap box shows "leader" (Leader) or "lap" (the lap they're on)
        "color_number": True,     # the car number on a background in the class colour (off: just the number)
        "show_gap": True,         # race: gap to the leader; qualifying: gap to pole
        "show_interval": False,   # to the car ahead
        "close_s": 0.15,          # race: an interval this close (or closer) shows red (0 = off)
        "show_pos_change": True,  # race: places gained / lost since the start
        "show_best_lap": False,
        "show_last_lap": False,
        "show_laps": False,       # laps completed
        "show_pits": False,       # pit stops made
        "show_pit_status": True,  # "PIT" while on pit road
        "column_order": ",".join(TOWER_COLUMNS),
        "screen_column_order": "",
        **COLUMN_OPACITY,
        # Start of a session: only the header (session, laps / time left), and
        # each driver appears once they've completed a lap.
        "reveal": True,
        "header_info": "auto",    # "auto" (laps or time, whichever the session is limited by), "laps", "time", "none"
        # The header (tower and full screen): the series (the active league's
        # name) and the track under the session name, and session names of
        # your own ("" = RACE, QUALIFYING, or iRacing's name for practice).
        "show_series": True, "show_track": True,
        "title_race": "", "title_qualify": "", "title_practice": "",
        "title_wrap": False,      # a long session name: onto two lines (True) or one line, the tower widening for it
        # Fastest lap: a purple stopwatch by the holder's name (each class's
        # holder in "class" mode), and a purple pill at the top middle of the
        # screen for fl_flash_s when someone sets a new fastest lap.
        "show_fastest_icon": True,
        "fl_flash": True,
        "fl_flash_s": 6.0,
        "fl_flash_classes": False,  # also a new fastest lap in each class, not just overall
        **BACKGROUND,
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
        **BACKGROUND,
    },
    # "Who's this": a board at the bottom centre for the driver on camera (driver.html).
    "driver": {
        "visible": True,
        "hide_s": 8.0,            # seconds it stays up after the camera moves to someone (0 = while they're on camera)
        "name_format": "full",
        "show_number": True, "show_team": True, "show_logo": True, "show_make": True,
        "show_class": True,       # the class, in multiclass races
        "show_position": True,    # P3 (and P1 in class, in multiclass races)
        **BACKGROUND,
    },
    # The grid walk's own settings are with the grid walk; this is just its background.
    "gridwalk": dict(BACKGROUND),
    # Full-screen boards (board.html), one section each. Every board has:
    # banner ("none", "top", "bottom", "left", "right"), banner_id (which of
    # the league's banners, "" = the first of the right shape),
    # league_logo (the league's logo in the header), sponsors (where the
    # sponsor logos go, the same places as a banner) and sponsor_ids (which,
    # as for the sponsors overlay).
    "board_championship": {**COLUMN_OPACITY, 
        "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND,
        "rows": 20, "rounds": 0,  # rounds: points from the last N rounds as columns (0 = none)
        "show_number": True, "show_team": True, "show_logo": True, "show_make": True,
        "show_gap": True, "show_ahead": False,  # gap to the leader; gap to the driver ahead
        "show_wins": False, "show_penalty": False,
    },
    "board_teams": {**COLUMN_OPACITY, 
        "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND,
        "rows": 12, "rounds": 0,  # rounds: the team's points from the last N rounds as columns
        "show_logo": True, "show_color": True,  # team logo; team colour stripe
        "show_drivers": True,  # the drivers who scored for the team, under its name
        "show_gap": True, "show_ahead": False, "show_wins": False, "show_penalty": False,
    },
    "board_makes": {**COLUMN_OPACITY, "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND, "rows": 12, "show_logo": True,
                    "show_gap": True, "show_wins": True},
    "board_calendar": {"banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND,
                       "style": "cards",  # "cards" (built from the rounds) or "image" (the league's own calendar graphic)
                       "show_date": True, "show_time": True, "show_config": True, "show_length": True,
                       "show_winners": True,
                       # Each round's title: "both" (Round 3 · its name), "name" (its own name) or "number" (Round 3).
                       "round_title": "both",
                       # weekday_short: Sun 22 Nov; numeric: 22/11/26; day_month: 22nd November;
                       # full: 22nd November 2026; weekday: Sunday 22nd November.
                       "date_format": "weekday_short",
                       "show_multiplier": True},  # "×2 points" on rounds worth more (or less)
    "board_results": {**COLUMN_OPACITY, 
        "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND,
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
        **BACKGROUND,
    },
}

LIMITS = {"rows_extra_s": (1.0, 120.0), "rows_extra_opacity": (10, 100), "width": (0, 1400), "scale": (50, 200), "bg_opacity": (0, 100), "close_s": (0.0, 2.0), "rows_last": (0, 30), "fl_flash_s": (3.0, 60.0), "size": (30, 300), "interval_s": (1.0, 120.0), "rows": (1, 64), "rounds": (0, 10), "count": (0, 12), "sectors": (0, 12), "green_s": (0.0, 5.0), "hide_s": (0.0, 60.0)}
PLACES = ("top-left", "top", "top-right", "left", "right", "bottom-left", "bottom", "bottom-right")
CHOICES = {"banner": ("none", "top", "bottom", "left", "right"), "sponsors": ("none", "top", "bottom", "left", "right"),
           "bg": ("default", "color", "image"), "place": PLACES,
           "round_title": ("both", "name", "number"), "rows_extra_mode": ("rotate", "last"),
           "leader_cell": ("leader", "lap"),
           "date_format": ("weekday_short", "numeric", "day_month", "full", "weekday"), "style": ("cards", "image"), "layout": ("rotate", "row"), "mode": ("overall", "class"), "header_info": ("auto", "laps", "time", "none"), "reference": ("personal", "session"), "name_format": NAME_FORMATS}


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
        if key == "bg_color":
            return value.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else default
        if key == "bg_image":
            return value if re.fullmatch(r"(bg-[0-9a-f]{12}\.(png|jpg|webp|svg))?", value) else default
        if key in ORDERS:
            return column_order(value, ORDERS[key]) if value else ("" if key == "screen_column_order" else default)
        if key == "col_opacity":
            out = []
            for part in value.split(","):
                col, _, pct = part.partition(":")
                col = col.strip()
                if re.fullmatch(r"[a-z_]{1,20}", col) and pct.strip().isdigit() and int(pct) < 100:
                    out.append(f"{col}:{max(0, int(pct))}")
            return ",".join(out)
        if key == "sponsor_ids":
            return ",".join(re.sub(r"[^a-z0-9]", "", v) for v in value.split(",") if re.sub(r"[^a-z0-9]", "", v))
        return value if key not in CHOICES or value in CHOICES[key] else default
    except (TypeError, ValueError):
        return default


def column_order(value, known):
    """A column order: the known columns given, in that order, then any left out."""
    picked = []
    for key in str(value).split(","):
        key = key.strip()
        if key in known and key not in picked:
            picked.append(key)
    return ",".join(picked + [k for k in known if k not in picked])


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
