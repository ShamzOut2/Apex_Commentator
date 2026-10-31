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
# Overlays (not boards) can be moved from where they sit: px on the 1920x1080 screen.
OFFSET = {"offset_x": 0, "offset_y": 0}
# How big team logos are drawn, in % of their usual size (every overlay and
# board that shows them).
LOGO = {"logo_scale": 100}
BACKGROUND = {"bg": "default", "bg_color": "#0b0d12", "bg_image": "", "bg_opacity": 100, "scale": 100}

# Overlays and boards with columns can dim each column on its own:
# col_opacity "gap:60,laps:40" (percent; columns left out are 100), used
# while col_opacity_on is ticked.
# Every board: "Page 2 / 3" in its header when it runs to more than one page;
# its accent colour (the line under the header...: "default" = the class
# colour, or "color" = accent_color); gold, silver and bronze for places 1-3
# (podium); the league's name in the header (show_league); and keep_leader:
# the leader / winner at the top of every page.
PAGING = {"page_number": True, "accent": "default", "accent_color": "#ff7a1a", "podium": True, "show_league": True,
          "keep_leader": True}
COLUMN_OPACITY = {"col_opacity_on": False, "col_opacity": "", "col_bg_color": "#0e1015"}

NAME_FORMATS = ("full", "initial_last", "last_initial", "last", "first", "abbrev", "nickname")

# The standings' columns after the driver, in the order shown: the tower's
# (each switched on and off with its show_ setting) and the full screen's
# (a fixed set: Last and Pits in races only). "" for the full screen keeps
# its usual order, which differs between races and qualifying.
TOWER_COLUMNS = ("pos_change", "laps", "pits", "last_lap", "best_lap", "gap", "interval")
SCREEN_COLUMNS = ("laps", "gap", "interval", "last_lap", "best_lap", "pits")
ORDERS = {"column_order": TOWER_COLUMNS, "screen_column_order": SCREEN_COLUMNS}

DEFAULTS = {
    "standings": {**LOGO, 
        "visible": True,
        "mode": "overall",        # "overall" or "class"
        "class_key": "",          # "class" mode: one class only ("" = every class, one block each)
        "rows": 20,               # most drivers shown (per class in "class" mode)
        # More drivers than rows: rows_last more under the top of the order
        # (by class: of each class), after a small gap. "rotate": the rest of the field, that many at
        # a time, a new set every rows_extra_s (then back to the first);
        # "last": always the last ones (last place included).
        "rows_last": 0,
        # By class: its own most drivers and extra drivers, for each class.
        "rows_class": 20, "rows_last_class": 0,
        "rows_extra_mode": "rotate",
        "rows_extra_s": 6.0,
        "rows_extra_opacity": 100,
        "width": 0,               # tower width in px; 0 = automatic (each column fits what's in it)
        "name_format": "last_initial",
        "show_team": True,
        "show_logo": True,
        "team_logo_side": "first",  # the team logo column before the driver / team name ("first") or after it ("last")
        "team_name_place": "under",  # tower: the team name under the driver's name ("under") or a column of its own ("column")
        # The car number's background and the bar by each driver: the colour of
        # the driver's "main" or "secondary" class (none, a plain number and no
        # bar, for a driver without one; with no league, iRacing's class colours).
        "class_colors": "main",
        "stripe_colors": "same",  # the bar's class colour: "same" as the car number's, or its own "main" / "secondary"
        "show_number": True,
        "show_stripe": True,      # the coloured bar by each driver (class or team colour)
        "show_col_labels": True,  # the column headings (GAP, INT...) under the header
        "leader_cell": "leader",  # race: the leader's gap box shows "leader" (Leader) or "lap" (the lap they're on)
        "interval_leader": "blank",  # race: the leader's interval box: "blank", "leader" (Leader) or "lap" (the lap they're on)
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
        # Heat racing: names of your own for the heats, consolation and feature
        # ("" = iRacing's, e.g. HEAT 1), and on the day of a heat event each race
        # named as its league round is named ("name") or not ("off"; see heats.py).
        "title_heat": "", "title_consolation": "", "title_feature": "",
        "round_titles": "name",
        "title_wrap": False,      # a long session name: onto two lines (True) or one line, the tower widening for it
        "time_left_word": True,   # "12:34 LEFT" (off: just 12:34)
        # Accent colour: the time / lap in the header, the bar down the tower
        # header's left and the line under the full screen's header.
        # "default" (orange), "color" (accent_color) or "session" (by session:
        # accent_practice, accent_qualify, accent_race).
        "accent": "default", "accent_color": "#ff7a1a",
        "accent_practice": "#ffffff", "accent_qualify": "#b14cff", "accent_race": "#ff4d4d",
        # A small bar under the tower's header with a sponsor logo (several take
        # turns every sponsor_bar_s seconds): which (sponsor_bar_ids, "" = all) and how tall.
        "sponsor_bar": False, "sponsor_bar_ids": "", "sponsor_bar_s": 8.0, "sponsor_bar_size": 44,
        # Fastest lap: a purple stopwatch by the holder's name (each class's
        # holder in "class" mode), and a purple pill at the top middle of the
        # screen for fl_flash_s when someone sets a new fastest lap.
        "show_fastest_icon": True,
        "name_width": 0,          # the driver name column's width in px (0 = automatic)
        "finish_flag": True,      # race: a waving chequered flag by each driver once they've taken the flag
        "fl_flash": True,
        "fl_flash_s": 6.0,
        "fl_flash_classes": False,  # also a new fastest lap in each class, not just overall
        **BACKGROUND, **OFFSET,
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
        **BACKGROUND, **OFFSET,
    },
    # "Who's this": a board at the bottom centre for the driver on camera (driver.html).
    "driver": {**LOGO, 
        "visible": True,
        "hide_s": 8.0,            # seconds it stays up after the camera moves to someone (0 = while they're on camera)
        "stay": False,            # stay up for as long as the camera's on them (hide_s not used)
        "name_format": "full",
        "show_number": True, "show_team": True, "show_logo": True, "show_make": True,
        "show_class": True,       # the class, in multiclass races
        "show_position": True,    # P3 (their place overall)
        "position_shown": "overall",  # "overall" (P3), "class" (P1, the class under it) or "both" (P3, and P1 GT3 under it)
        "pos_class_name": True,       # the class's name with the class position ("P1 GT3", or just "P1")
        "class_colors": "main",   # colours from the driver's main or secondary class (see standings)
        "team_place": "under",    # "under": the team logo by the team name, the car badge at the end; "end": those two swapped
        "team_logo_side": "first",  # the team logo before ("first") or after ("last") the team name
        **BACKGROUND, **OFFSET,
    },
    # Pit stops (pits.html): a card for a car in the pit lane, with its pit
    # lane time (entry line to exit line) and its time in the pit box. who:
    # "all" (every car in the pit lane, at most count) or "camera" (the car
    # on camera only); hold_s: how long a finished stop stays up.
    "pits": {**LOGO, 
        "visible": True,
        "who": "all", "count": 3, "hold_s": 8.0, "race_only": True,
        "show_s": 0.0,  # a card goes after this long in the pit lane, even before the exit (0 = until the exit)
        "place": "right",
        "name_format": "last_initial",
        "show_number": True, "show_team": True, "show_logo": True, "show_position": True,
        "class_colors": "main",
        **BACKGROUND, **OFFSET,
    },
    # Championship battle (battle.html): a few drivers' championship places
    # and points, live during a race (as if it finished now), and the points
    # between them. group: which championship ("overall" or a class id);
    # drivers: who, comma separated driver keys (cust:123), up to six.
    "battle": {**LOGO, 
        "visible": False,
        "group": "overall",
        "drivers": "",
        "place": "top-right",
        "title": "",              # its heading ("" = the championship's name)
        "name_format": "last_initial",
        "show_number": True, "show_team": False, "show_logo": True,
        "show_race_points": True,  # during a race: the points this race gives them (+18)
        "show_change": True,      # during a race: places gained / lost in the championship
        "gap_to": "first",        # the points gap to the first of them ("first") or to the driver above ("ahead")
        **BACKGROUND, **OFFSET,
    },
    # The grid walk's own settings are with the grid walk; this is just its background.
    "gridwalk": {**LOGO, **BACKGROUND, **OFFSET,
                 "name_format": "full", "show_nickname": True,
                 "neighbours": "show",  # the cars either side on the grid: "show", or "hide" (just the pair)
                 "car_scale": 100,      # the car pictures' size, % of a car's length in its box
                 # The drivers' cards, as the driver-on-camera card's settings:
                 "show_position": True, "position_shown": "overall", "pos_class_name": True,
                 "show_number": True, "show_team": True, "show_logo": True, "show_make": True, "show_class": True,
                 "class_colors": "main",
                 "qual_shown": "gap",   # qualifying: "gap" (to the class pole), "interval" (to the car ahead in class), "time", "none"
                 "track_qual": True,    # the same, painted on the track under each box's number
                 "flip_cars": False},  # car pictures facing the other way (the cars should point right, up the road)
    # Full-screen boards (board.html), one section each. Every board has:
    # banner ("none", "top", "bottom", "left", "right"), banner_id (which of
    # the league's banners, "" = the first of the right shape),
    # league_logo (the league's logo in the header), sponsors (where the
    # sponsor logos go, the same places as a banner) and sponsor_ids (which,
    # as for the sponsors overlay).
    "board_championship": {**LOGO, **COLUMN_OPACITY, **PAGING, 
        "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND,
        "name_format": "full",  # drivers' names: full, A. Driver, ... (as the overlays)
        "rows": 20, "rounds": 0,  # rounds: points from the last N rounds as columns (0 = none)
        "show_number": True, "show_team": True, "show_logo": True, "show_make": True,
        "team_logo_side": "first",  # the team logo column before ("first") or after ("last") the team name
        "show_gap": True, "show_ahead": False,  # gap to the leader; gap to the driver ahead
        "show_wins": False, "show_penalty": False,
    },
    "board_teams": {**LOGO, **COLUMN_OPACITY, **PAGING, 
        "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND,
        "name_format": "full",  # drivers' names: full, A. Driver, ... (as the overlays)
        "rows": 12, "rounds": 0,  # rounds: the team's points from the last N rounds as columns
        "show_logo": True, "show_color": True,  # team logo; team colour stripe
        "team_logo_side": "first",
        "show_drivers": True,  # the drivers who scored for the team, under its name
        "show_gap": True, "show_ahead": False, "show_wins": False, "show_penalty": False,
    },
    "board_makes": {**COLUMN_OPACITY, **PAGING, "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND, "rows": 12, "show_logo": True,
                    "show_gap": True, "show_wins": True},
    "board_calendar": {**PAGING, "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND,
                       "rows": 24,  # race meetings a page
                       "style": "cards",  # "cards" (built from the rounds) or "image" (the league's own calendar graphic)
                       "show_date": True, "show_time": True, "show_config": True, "show_length": True,
                       "show_winners": True,
                       "winner_groups": "",  # whose winners: championship keys, comma separated ("" all, "none" none)
                       # Each race's box: its name (show_race_name), and the
                       # winners' class names (show_winner_class) and names as.
                       "show_race_name": True, "show_winner_class": True, "winner_name_format": "initial_last",
                       # Each round's title: "both" (Round 3 · its name), "name" (its own name) or "number" (Round 3).
                       "round_title": "both",
                       # weekday_short: Sun 22 Nov; numeric: 22/11/26; day_month: 22nd November;
                       # full: 22nd November 2026; weekday: Sunday 22nd November.
                       "date_format": "weekday_short",
                       "show_multiplier": True},  # "×2 points" on rounds worth more (or less)
    "board_results": {**LOGO, **COLUMN_OPACITY, **PAGING, 
        "banner": "none", "banner_id": "", "league_logo": True, "sponsors": "none", "sponsor_ids": "", **BACKGROUND,
        "name_format": "full",  # drivers' names: full, A. Driver, ... (as the overlays)
        "rows": 30, "show_number": True, "show_team": True, "show_logo": True, "show_make": True, "team_logo_side": "first",
        "show_laps": True, "show_gained": True, "show_fastest": True, "show_points": True,
        # Gap to the winner and to the car ahead (a DNF / DNS / DSQ shows there instead).
        "show_gap": True, "show_interval": True,
        "winner_gap": "laps",  # the winner's Gap cell: "laps" (13 laps), "time" (their race time, else laps) or "none"
    },
    "laps": {**LOGO, 
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
        **BACKGROUND, **OFFSET,
    },
}

LIMITS = {"logo_scale": (40, 250), "car_scale": (40, 250), "name_width": (0, 600), "rows_extra_s": (1.0, 120.0), "rows_extra_opacity": (10, 100), "width": (0, 1400), "scale": (50, 200), "bg_opacity": (0, 100), "close_s": (0.0, 2.0), "rows_last": (0, 30), "rows_class": (1, 64), "rows_last_class": (0, 30), "fl_flash_s": (3.0, 60.0), "size": (30, 300), "interval_s": (1.0, 120.0), "rows": (1, 64), "rounds": (0, 10), "count": (0, 12), "sectors": (0, 12), "green_s": (0.0, 5.0), "hide_s": (0.0, 120.0), "hold_s": (0.0, 60.0), "show_s": (0.0, 300.0), "sponsor_bar_s": (2.0, 120.0), "sponsor_bar_size": (20, 120), "offset_x": (-1920, 1920), "offset_y": (-1080, 1080)}
PLACES = ("top-left", "top", "top-right", "left", "right", "bottom-left", "bottom", "bottom-right")
CHOICES = {"banner": ("none", "top", "bottom", "left", "right"), "sponsors": ("none", "top", "bottom", "left", "right"),
           "bg": ("default", "color", "image"), "place": PLACES,
           "round_title": ("both", "name", "number"), "rows_extra_mode": ("rotate", "last"),
           "leader_cell": ("leader", "lap"), "interval_leader": ("blank", "leader", "lap"), "round_titles": ("name", "off"), "team_place": ("under", "end"), "accent": ("default", "color", "session"), "gap_to": ("first", "ahead"), "team_logo_side": ("first", "last"), "team_name_place": ("under", "column"), "class_colors": ("main", "secondary"), "stripe_colors": ("same", "main", "secondary"), "who": ("all", "camera"), "position_shown": ("overall", "class", "both"), "winner_gap": ("laps", "time", "none"), "neighbours": ("show", "hide"), "qual_shown": ("gap", "interval", "time", "none"),
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
        value = str(value)[:600 if key == "drivers" else 200]
        if key.endswith("bg_color") or key.startswith("accent_"):
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
        if key == "drivers":
            keys = [k.strip() for k in value.split(",") if re.fullmatch(r"(cust:\d{1,12}|name:[^,]{1,60})", k.strip())]
            return ",".join(dict.fromkeys(keys[:6]))
        if key == "group":
            return value if re.fullmatch(r"[A-Za-z0-9:_ .\-]{1,80}", value) else default
        if key in ("sponsor_ids", "sponsor_bar_ids"):
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
