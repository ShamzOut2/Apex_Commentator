"""The app core: polls the source, tracks drivers and events, builds the
snapshot the overlay renders, and runs spectate / replay commands.
"""

import re
import threading
from dataclasses import replace
import time

from . import __version__, championship
from .events import EventDetector
from .gridwalk import GridWalk, grid_order, parse_design, qualifying_times
from .backgrounds import Backgrounds
from .gaps import GapTimer
from .laps import LapTracker, group_sectors, sector_starts
from .overlays import OverlaySettings
from .settings import UserSettings
from .tracks import TrackCatalogue
from . import boards
from .league import driver_key, logo_url, strip_class_prefix
from .makes import logo_for as make_logo
from .makes import make_for
from .sources import (
    CS_AT_EXCITING,
    CS_AT_INCIDENT,
    CS_AT_LEADER,
    RPY_SRCH_NEXT_INCIDENT,
    RPY_SRCH_PREV_INCIDENT,
    RPY_SRCH_TO_END,
    CAUTION_FLAGS,
    FLAG_BLACK,
    FLAG_BLUE,
    FLAG_CHECKERED,
    FLAG_DISQUALIFY,
    FLAG_FURLED,
    FLAG_GREEN,
    FLAG_REPAIR,
    FLAG_WHITE,
    STATE_CHECKERED,
    STATE_RACING,
    TRK_NOT_IN_WORLD,
)

SESSION_STATES = {
    0: "Invalid", 1: "Get in car", 2: "Warmup", 3: "Parade laps",
    4: "Racing", 5: "Checkered", 6: "Cool down",
}
SURFACES = {-1: "not_in_world", 0: "off_track", 1: "pit_stall", 2: "approaching_pits", 3: "on_track"}
DEFAULT_TRACK_M = 4000.0
# Per-car flags, most important first: the first one shown is "the" flag.
CAR_FLAGS = (
    (FLAG_DISQUALIFY, "dq"), (FLAG_BLACK, "black"), (FLAG_REPAIR, "meatball"), (FLAG_FURLED, "warning"),
    (FLAG_BLUE, "blue"), (CAUTION_FLAGS, "yellow"), (FLAG_CHECKERED, "checkered"), (FLAG_WHITE, "white"),
    (FLAG_GREEN, "green"),
)
PENALTY_NAMES = {"dq": "DQ", "black": "Black flag", "meatball": "Meatball", "warning": "Warning"}


class CommandError(Exception):
    pass


def parse_track_length(text):
    """'4.01 km' / '2.49 mi' -> metres."""
    m = re.match(r"\s*([\d.]+)\s*(km|mi)?", str(text or ""))
    if not m:
        return DEFAULT_TRACK_M
    value = float(m.group(1))
    return value * (1609.344 if m.group(2) == "mi" else 1000.0)


def _at(seq, i, default=None):
    return seq[i] if i < len(seq) else default


def car_flags(bits):
    """The flag shown to a car (most important first) and its penalties."""
    bits = int(bits or 0)
    names = [name for bit, name in CAR_FLAGS if bits & bit]
    return {"flag": names[0] if names else None,
            "penalties": [PENALTY_NAMES[n] for n in names if n in PENALTY_NAMES]}


def _rank(standings, is_race):
    """Positions, class positions, gaps and intervals for standings entries in order.

    ``time`` is the gap to the leader in a race, the lap time otherwise.
    """
    first, ahead, in_class = None, {}, {}
    prev = None
    for pos, e in enumerate(standings, start=1):
        k = e["class_key"]
        in_class[k] = in_class.get(k, 0) + 1
        e["pos"], e["class_pos"] = pos, in_class[k]
        t = e.pop("time")
        e["best"] = None if is_race else t
        if first is None:
            first = t
        leader = ahead.setdefault(k, {"first": t, "prev": None})
        if is_race:
            gap, class_gap = t, (t - leader["first"]) if t is not None and leader["first"] is not None else None
        else:
            # Drivers without a lap time (shown once they've done a lap) have no gap.
            gap = t - first if t is not None and first is not None else None
            class_gap = t - leader["first"] if t is not None and leader["first"] is not None else None
        e["gap"] = round(gap, 3) if gap is not None and pos > 1 else None
        e["class_gap"] = round(class_gap, 3) if class_gap is not None and in_class[k] > 1 else None
        # Side by side, the car behind can be a hair ahead on time: never a negative interval.
        e["interval"] = round(max(0.0, t - prev), 3) if t is not None and prev is not None else None
        e["class_interval"] = round(max(0.0, t - leader["prev"]), 3) if t is not None and leader["prev"] is not None else None
        prev = t
        leader["prev"] = t


def _session_limit(text):
    """'30' -> 30 laps; '1200.0000 sec' -> 1200 s; 'unlimited' -> None."""
    m = re.match(r"\s*([\d.]+)", str(text or ""))
    return float(m.group(1)) if m else None


def _laps_down(leader, r):
    """Whole laps a car is behind a leader (0 on the lead lap)."""
    down = leader["progress"] - r["progress"]
    return int(down) if r["progress"] >= 0 and down >= 1 else 0


def _progress(frame, idx):
    """Laps + lap distance of a car, or -1 when it isn't on track."""
    lap, pct = _at(frame.lap, idx, -1), _at(frame.pct, idx, -1.0)
    return lap + pct if lap is not None and lap >= 0 and pct is not None and pct >= 0 else -1


def _lap_time(value):
    return round(value, 3) if value and value > 0 else None


class RaceProgress:
    """Who started a race and who took the chequered flag, from watching it.

    A car started if it was in the world once the race went green. It
    finished if it crossed the line after the chequered flag came out.
    """

    def __init__(self):
        self.session = None
        self.started = set()
        self.finished = set()
        self.checkered = False
        self._laps = {}

    def update(self, frame):
        if frame.session_num != self.session:
            self.__init__()
            self.session = frame.session_num
        if frame.session_state < STATE_RACING:
            return
        in_world = {i for i, s in enumerate(frame.surface) if s != TRK_NOT_IN_WORLD}
        if frame.session_state == STATE_RACING:
            self.started |= in_world
            return
        if frame.session_state >= STATE_CHECKERED and not self.checkered:
            self.checkered = True
            # The winner crossed the line as the flag came out (and anyone
            # crossing with them).
            self.finished |= {i for i in in_world if 0 <= _at(frame.pct, i, -1) < 0.02}
            self._laps = {i: _at(frame.lap, i, -1) for i in in_world}
            return
        for i in in_world:
            lap = _at(frame.lap, i, -1)
            if i in self._laps and lap > self._laps[i]:
                self.finished.add(i)
            self._laps.setdefault(i, lap)

    def status(self, car_idx, session_num, laps, in_world, official_reason):
        """finished / dnf / dns for a car, or None to leave it to iRacing's results."""
        watched = self.session == session_num and self.started
        if watched and car_idx not in self.started:
            return "dns"
        if not watched and laps == 0 and not in_world:
            return "dns"
        if "disq" in official_reason:
            return "dsq"
        if watched and self.checkered:
            return "finished" if car_idx in self.finished else "dnf"
        return None


class App:
    def __init__(self, source, cfg, leagues):
        self.source = source
        self.cfg = cfg
        self.leagues = leagues
        self.detector = EventDetector(cfg)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._snapshot = {"connected": False}
        self._version = 0
        self._changed = threading.Condition()
        self._info_update = None
        self._drivers = {}
        self._camera_groups = []
        self._session_meta = {}
        self._track_m = DEFAULT_TRACK_M
        self._frame = None
        self._return_timer = None
        self._last_push = 0.0
        self.gridwalk = GridWalk(cfg.get("gridwalk_interval_s", 8), cfg.get("gridwalk_style", "track"))
        self._grid_order = []      # car_idx in starting order
        self._grid_source = ""
        self._qual_times = {}      # car_idx -> best qualifying lap
        self._fl_session = None    # fastest laps: the session they're for,
        self._fl_records = {}      # "overall" / class key -> fastest lap so far,
        self._fl_flash = None      # and the newest one, for the flash on stream
        self._logged_until = {}    # session num -> race time logged so far
        self.detection = "waiting" # live | replay | paused | waiting
        self._grid_keys = []       # entry keys in automatic order, from the last snapshot
        self.photobooth = None     # set by __main__ (needs the user data folder)
        self.popout = None         # set by __main__: popout(page) opens a page in its own app window
        self.desktop = None        # set by __main__: on-screen overlays (apex.desktop), with the app window
        self.backgrounds = Backgrounds()  # __main__ gives it a folder: overlay / board background images
        self.laps = LapTracker()
        self.gaps = GapTimer()
        self.overlays = OverlaySettings()  # __main__ gives it a file to keep settings in
        self.settings = UserSettings()     # settings changed in the app (likewise)
        self.tracks = TrackCatalogue()     # likewise: the season calendar's track list
        self.board = {"kind": None, "params": {}}  # the full-screen board on screen, if any
        self._board_cache = (None, None)
        self._class_of = {}        # car_idx -> class key, from the last snapshot
        self._track_sectors = self.laps.starts  # the track's own split points
        self._race = RaceProgress()

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        threading.Thread(target=self._run, name="poller", daemon=True).start()

    def stop(self):
        self._stop.set()

    def _run(self):
        period = 1.0 / max(1.0, float(self.cfg["poll_hz"]))
        push_period = 1.0 / max(0.5, float(self.cfg["push_hz"]))
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.tick()
            except Exception as e:  # keep the overlay alive whatever happens
                print(f"[apex] poll error: {e!r}")
            with self._lock:
                stepped = self.gridwalk.tick(len(self._grid_keys))
            if stepped:
                self.publish()
            if time.monotonic() - self._last_push >= push_period:
                self._last_push = time.monotonic()
                self.publish()
            self._stop.wait(max(0.0, period - (time.monotonic() - started)))

    def tick(self):
        """Read one frame and update state. Returns False while disconnected."""
        frame = self.source.read() if self.source.connect() else None
        if frame is None:
            with self._lock:
                self._frame = None
                self._info_update = None  # reload session info after reconnecting
            return False
        update, info = self.source.session_info()
        with self._lock:
            if update != self._info_update:
                self._load_session_info(info, frame)
                self._info_update = update
                self.detector.update_incidents(frame, self._drivers)
            self._frame = frame
            self._detect(frame)
        return True

    def _detect(self, frame):
        """Log events from whatever iRacing is showing, live or a replay.

        Only race time not logged yet is processed: rewinding during a live
        race doesn't log moments twice, while a saved replay played forward
        logs normally. Events are stamped with that timeline, which is what
        replay seeking uses.
        """
        num, t = frame.timeline()
        logged = self._logged_until.get(num, -1.0)
        if t < logged - 1e-3:
            self.detection = "paused"  # watching something already logged
            return
        if t <= logged + 1e-3:
            return  # no new race time (sim paused): nothing changes
        timeline_frame = replace(frame, session_num=num, session_time=t)
        self.detector.update(timeline_frame, self._drivers, self._track_m, self._is_race(timeline_frame))
        if self._is_race(timeline_frame):
            self._race.update(timeline_frame)
            self.gaps.update(num, t, {idx: _progress(frame, idx) for idx in self._drivers})
        self.laps.green_s = self.overlays.get()["laps"]["green_s"]
        self.laps.update(timeline_frame, self._lap_class)
        self._logged_until[num] = t
        self.detection = "live" if frame.is_live else "replay"

    def _apply_sectors(self):
        """Time the lap in the sectors the overlay shows (a no-op when unchanged)."""
        self.laps.set_sectors(group_sectors(self._track_sectors, self.overlays.get()["laps"]["sectors"]))

    def _lap_class(self, car_idx):
        key = self._class_of.get(car_idx)
        if key is None:
            d = self._drivers.get(car_idx)
            key = f"iracing:{(d and d['car_class']) or 'Field'}"
        return key

    # -- session info -------------------------------------------------------

    def _load_session_info(self, info, frame):
        weekend = info.get("WeekendInfo") or {}
        self._track_m = parse_track_length(weekend.get("TrackLength"))
        self.gaps.set_track(self._track_m)
        self.tracks.remember(weekend.get("TrackID"), weekend.get("TrackDisplayName", ""), weekend.get("TrackConfigName", ""))
        sessions = (info.get("SessionInfo") or {}).get("Sessions") or []
        self._session_meta = {
            "track": weekend.get("TrackDisplayName", ""),
            "track_config": weekend.get("TrackConfigName", ""),
            "subsession": weekend.get("SubSessionID"),
            "sessions": {s.get("SessionNum"): s for s in sessions},
        }
        self._camera_groups = [
            {"num": g.get("GroupNum"), "name": g.get("GroupName", "")}
            for g in (info.get("CameraInfo") or {}).get("Groups") or []
        ]
        drivers = {}
        for d in (info.get("DriverInfo") or {}).get("Drivers") or []:
            if d.get("IsSpectator") or d.get("CarIsPaceCar"):
                continue
            if str(d.get("UserName", "")).lower() == "pace car":
                continue
            idx = d.get("CarIdx")
            team = d.get("TeamName") or ""
            incidents = d.get("TeamIncidentCount") if team and d.get("TeamID") else d.get("CurDriverIncidentCount")
            color = d.get("CarClassColor")
            drivers[idx] = {
                "car_idx": idx,
                "name": d.get("UserName", ""),
                "abbrev": d.get("AbbrevName", ""),
                "cust_id": d.get("UserID"),
                "number": str(d.get("CarNumber", "")),
                "team": team if team != d.get("UserName") else "",
                "car": d.get("CarScreenNameShort", ""),
                "car_name": d.get("CarScreenName") or d.get("CarScreenNameShort", ""),
                # The manufacturer, from iRacing's car name and path.
                "make": make_for(d.get("CarScreenName") or d.get("CarScreenNameShort", ""), d.get("CarPath", "")),
                "car_class": d.get("CarClassShortName") or "",
                "class_color": f"#{int(color):06x}" if isinstance(color, int) else None,
                "irating": d.get("IRating"),
                "license": d.get("LicString", ""),
                "incidents": incidents if isinstance(incidents, int) and incidents >= 0 else None,
                "car_design": parse_design(d.get("CarDesignStr")),
                "helmet_design": parse_design(d.get("HelmetDesignStr")),
            }
        self._drivers = drivers
        official = {i: p for i, p in enumerate(frame.position) if i in drivers} if frame else None
        self._grid_order, self._grid_source = grid_order(drivers, info, official)
        self._qual_times = qualifying_times(info)
        self._track_sectors = sector_starts(info)
        self._apply_sectors()

    def session_key(self):
        """Identifies the session on screen (iRacing's subsession and session number)."""
        sub, frame = self._session_meta.get("subsession"), self._frame
        return f"{sub}:{frame.session_num}" if sub and frame else None

    def _session(self, frame):
        return self._session_meta.get("sessions", {}).get(frame.session_num, {})

    def _is_race(self, frame):
        return str(self._session(frame).get("SessionType", "")).lower() == "race"

    # -- snapshot -----------------------------------------------------------

    def build_snapshot(self):
        with self._lock:
            frame = self._frame
            if frame is None:
                return {
                    "connected": False, "source": self.source.name, "league": self._league_summary(),
                    "version": __version__,
                    "gridwalk": self._gridwalk_snapshot({}, self.leagues.active(), None),
                    "photobooth": self.photobooth.status() if self.photobooth else None,
                    "desktop": self._desktop_snapshot(),
                    **self._boards(self.leagues.active(), lambda: None),
                    "overlays": {"settings": self.overlays.get(), "session_kind": "", "standings": [],
                                 "laps": {"active": False, "camera": None, "trackers": [], "all": [],
                                          "sectors": len(self.laps.starts)}},
                }
            is_race = self._is_race(frame)
            racing = is_race and frame.session_state == STATE_RACING
            events = self.detector.events
            counts = {}
            last_event = {}
            pit_stops = {}
            for ev in events:
                counts[ev["car_idx"]] = counts.get(ev["car_idx"], 0) + 1
                last_event[ev["car_idx"]] = ev["id"]
                if ev["type"] == "pit_out":
                    pit_stops[ev["car_idx"]] = pit_stops.get(ev["car_idx"], 0) + 1
            classes = {}
            active_league = self.leagues.active()
            rows = []
            for idx, d in self._drivers.items():
                lap = _at(frame.lap, idx, -1)
                pct = _at(frame.pct, idx, -1.0)
                surface = _at(frame.surface, idx, TRK_NOT_IN_WORLD)
                row = dict(d)
                league = self.leagues.lookup(d["cust_id"], d["number"])
                row["league"] = {k: league.get(k, "") for k in ("nickname", "team", "notes", "driver_number")} if league else None
                # The car as logged in the league wins over iRacing's car name.
                row["make"] = (league or {}).get("car_make") or d["make"]
                row["make_logo"] = make_logo(row["make"])
                row["class_key"] = self._class_key(classes, active_league, league, d)
                row.update({
                    "lap": lap if lap is not None and lap >= 0 else None,
                    "laps_completed": _at(frame.laps_completed, idx, -1) if _at(frame.laps_completed, idx, -1) >= 0 else None,
                    "pct": round(pct, 4) if pct is not None and pct >= 0 else None,
                    "official_pos": _at(frame.position, idx, 0) or None,
                    "class_pos": _at(frame.class_position, idx, 0) or None,
                    "on_pit": bool(_at(frame.on_pit, idx, False)),
                    "surface": SURFACES.get(surface, "unknown"),
                    "in_world": surface != TRK_NOT_IN_WORLD,
                    "gap": round(_at(frame.f2_time, idx, 0.0), 3) if is_race else None,  # live timing replaces it (_live_gaps)
                    "laps_down": 0,
                    "last_lap": _lap_time(_at(frame.last_lap, idx)),
                    "best_lap": _lap_time(_at(frame.best_lap, idx)),
                    "event_count": counts.get(idx, 0),
                    "pit_stops": pit_stops.get(idx, 0),
                    **car_flags(_at(frame.car_flags, idx, 0) | (frame.session_flags & CAUTION_FLAGS)),
                    "last_event_id": last_event.get(idx),
                    "progress": (lap + pct) if lap is not None and lap >= 0 and pct is not None and pct >= 0 else -1,
                })
                rows.append(row)
            self._assign_positions(rows, racing)
            if racing:
                self._live_gaps(rows, frame)
            in_class = {}
            for r in rows:
                del r["progress"]
                if r["pos"] is not None:
                    in_class[r["class_key"]] = in_class.get(r["class_key"], 0) + 1
                    r["class_pos"] = in_class[r["class_key"]]
            self._add_start_positions(rows, is_race)
            self._class_of = {r["car_idx"]: r["class_key"] for r in rows}
            session = self._session(frame)
            snap = {
                "connected": True,
                "version": __version__,
                "source": self.source.name,
                "session": {
                    "num": frame.session_num,
                    "type": session.get("SessionType", ""),
                    "name": session.get("SessionName", ""),
                    "laps": session.get("SessionLaps", ""),
                    "state": SESSION_STATES.get(frame.session_state, str(frame.session_state)),
                    "time": round(frame.session_time, 1),
                    "flags": frame.session_flags,
                    "track": self._session_meta.get("track", ""),
                    "track_config": self._session_meta.get("track_config", ""),
                },
                "camera": {"car_idx": frame.cam_car_idx, "group": frame.cam_group, "groups": self._camera_groups},
                "replay": {
                    "live": frame.is_live,
                    "session_time": round(frame.replay_session_time, 1),
                    "speed": frame.replay_speed,
                },
                "drivers": rows,
                "detection": self.detection,
                "gridwalk": self._gridwalk_snapshot(classes, active_league, frame),
                "photobooth": self.photobooth.status() if self.photobooth else None,
                "classes": self._ordered_classes(classes),
                "events": events[-200:],
                "desktop": self._desktop_snapshot(),
                "league": self._league_summary(),
                "overlays": self._overlay_snapshot(rows, frame, session, active_league),
                "championship": self._championship_snapshot(rows, frame, is_race, active_league),
                **self._boards(active_league, lambda: self.session_results(active_league, rows)[0] if is_race else None),
            }
            return snap

    # -- championship -------------------------------------------------------

    def session_results(self, profile, rows=None, add_missing=False):
        """The current session as championship results for ``profile``.

        Uses iRacing's official results (laps, laps led, fastest lap, why a car
        is out) where it has them, and the live order otherwise. With
        ``add_missing``, drivers not in the roster are added to ``profile``.
        Returns ``(results, added)``.
        """
        frame = self._frame
        if rows is None:
            rows = self.build_snapshot().get("drivers") or []
        session = self._session(frame) if frame else {}
        official = {r.get("CarIdx"): r for r in session.get("ResultsPositions") or [] if isinstance(r, dict)}
        checkered = bool(frame) and frame.session_state >= STATE_CHECKERED
        results, added = [], 0
        for r in sorted(rows, key=lambda r: r["pos"] or 10_000):
            entry = self.leagues.lookup(r["cust_id"], r["number"], profile)
            if entry is None:
                entry = next((d for d in profile.get("drivers", []) if d.get("cust_id") is None
                              and d.get("name", "").strip().lower() == r["name"].strip().lower()), None)
            if entry is None and add_missing:
                entry = {"cust_id": r["cust_id"], "name": r["name"], "car_number": r["number"], "team": r["team"]}
                profile.setdefault("drivers", []).append(entry)
                added += 1
            key = driver_key(entry) if entry else driver_key({"cust_id": r["cust_id"], "name": r["name"]})
            cls = self.leagues.class_for(entry, r["car_class"], profile, r["name"])
            off = official.get(r["car_idx"], {})
            laps = off.get("LapsComplete")
            if not isinstance(laps, int) or laps < 0:
                laps = max(0, (r["lap"] or 1) - 1)
            fastest = off.get("FastestTime")
            reason = str(off.get("ReasonOutStr") or "Running").strip().lower()
            status = self._race.status(r["car_idx"], frame.session_num if frame else None, laps, r["in_world"], reason)
            if status is None:
                # Not watched to the flag: iRacing's reason the car is out,
                # and mid-race a car that has left the world is out.
                status = "finished" if reason == "running" and (r["in_world"] or checkered) else "dnf"
            incidents = off.get("Incidents") if isinstance(off.get("Incidents"), int) else r["incidents"]
            results.append(championship.normalise_result({
                "driver": key, "name": r["name"],
                "class_id": cls["id"] if cls else f"iracing:{r['car_class'] or 'Field'}",
                "position": r["pos"], "start_position": r["start_pos"], "laps": laps,
                "laps_led": off.get("LapsLed") or 0,
                "fastest_lap": fastest if isinstance(fastest, (int, float)) and fastest > 0 else r["best_lap"],
                "incidents": incidents or 0, "status": status,
                "make": (entry or {}).get("car_make") or r.get("make", ""),
            }))
        return results, added

    def _championship_snapshot(self, rows, frame, is_race, active_league):
        """Season standings for the active league; during a race, as if it finished now."""
        if not active_league:
            return None
        champ = active_league.get("championship") or championship.normalise({})
        racing = is_race and frame.session_state >= STATE_RACING and any(r["pos"] for r in rows)
        champ = championship.normalise(champ)
        if not racing and not any(rd["results"] for rd in champ["rounds"]):
            return None
        rd = championship.live_round_for(champ, self.session_key()) if racing else None
        if racing and rd is None and not champ["rounds"]:
            rd = {"id": "live", "name": "This race", "track": "", "date": "", "multiplier": 1.0, "no_drop": False}
        if rd is not None:
            results, _ = self.session_results(active_league, rows)
            provisional = frame.session_state < STATE_CHECKERED
            groups = championship.projection(active_league, dict(rd, results=results, provisional=provisional))
            return {"live": True, "round": rd["name"], "groups": groups}
        table = championship.standings(active_league)
        groups = [{"key": g["key"], "name": g["name"], "color": g["color"], "drivers": [
            {k: d[k] for k in ("driver", "name", "team", "car_number", "points", "pos", "behind")}
            for d in g["drivers"]]} for g in table["groups"]]
        return {"live": False, "round": None, "groups": groups}

    # -- stream overlays ----------------------------------------------------

    @staticmethod
    def _stream_name(name, nickname, active_league):
        """(name, nickname) to show on stream.

        With the league's "Remove driver class in name" on, the stream name
        is the nickname (the name without its "(P)" tag) and isn't shown again
        as a nickname. The control panel keeps the full name.
        """
        if active_league and active_league.get("strip_class_prefix"):
            return (nickname or strip_class_prefix(name)), ""
        return name, nickname

    def _overlay_entry(self, r, active_league):
        """Who a driver is, for the stream overlays: league details win."""
        lg = r["league"] or {}
        name, nickname = self._stream_name(r["name"], lg.get("nickname", ""), active_league)
        team_name = lg.get("team") or r["team"]
        team = self.leagues.team(team_name, active_league) if active_league else None
        pid = active_league["id"] if active_league else ""
        return {
            "car_idx": r["car_idx"], "name": name, "nickname": nickname,
            "abbrev": r["abbrev"], "number": r["number"], "driver_number": lg.get("driver_number", ""),
            "team": team_name, "team_short": (team or {}).get("short", ""), "team_color": (team or {}).get("color", ""),
            "team_logo": logo_url(pid, team.get("logo")) if team and pid else None,
            "class_key": r["class_key"], "car": r["car"], "on_pit": r["on_pit"], "in_world": r["in_world"],
            # For the full-screen versions.
            "make": r["make"], "make_logo": r["make_logo"],
            "lap": r["lap"], "last_lap": r["last_lap"], "best_lap": r["best_lap"], "pit_stops": r["pit_stops"],
            "laps_completed": r["laps_completed"],
            "laps_down": r.get("laps_down", 0), "class_laps_down": r.get("class_laps_down", 0),
        }

    def _fastest_laps(self, standings, is_race, cfg, frame):
        """Mark who holds the fastest lap (``fastest``: overall, ``class_fastest``:
        in their class) and return the new-fastest-lap flash to show, if any."""
        def lap_of(e):
            t = e.get("best_lap") if is_race else e.get("best")
            return t if t and t > 0 else None

        holders = {}
        for e in standings:
            t = lap_of(e)
            e["fastest"] = e["class_fastest"] = False
            if t is None:
                continue
            for scope in ("overall", e["class_key"]):
                if scope not in holders or t < holders[scope][0] - 1e-4:
                    holders[scope] = (t, e)
        for scope, (_, e) in holders.items():
            e["fastest" if scope == "overall" else "class_fastest"] = True
        # A new fastest lap: flash it. Laps already set when the session (or
        # the app) started aren't news.
        session = (frame.session_num, is_race)
        if session != self._fl_session:
            self._fl_session, self._fl_flash = session, None
            self._fl_records = {scope: t for scope, (t, _) in holders.items()}
        flashed = False
        # Overall first: a lap that's fastest overall and in its class flashes once, as overall.
        for scope, (t, e) in sorted(holders.items(), key=lambda kv: kv[0] != "overall"):
            record = self._fl_records.get(scope)
            if record is not None and t >= record - 1e-4:
                continue
            self._fl_records[scope] = t
            # A race's first laps (standing or rolling start) aren't real fastest laps yet.
            opening = is_race and (e.get("laps_completed") or 0) <= 1
            if not flashed and not opening and (scope == "overall" or cfg["fl_flash_classes"]):
                flashed = True
                self._fl_flash = {"car_idx": e["car_idx"], "name": e["name"], "nickname": e.get("nickname", ""),
                                  "number": e["number"], "class_key": e["class_key"], "lap_time": t,
                                  "scope": "overall" if scope == "overall" else "class", "at": time.monotonic()}
        f = self._fl_flash
        if not (cfg["fl_flash"] and f and time.monotonic() - f["at"] < cfg["fl_flash_s"]):
            return None
        return {k: v for k, v in f.items() if k != "at"} | {"id": f"{f['car_idx']}:{f['lap_time']}"}

    def _session_progress(self, frame, session, rows, mode="auto"):
        """Laps or time left, for the standings header.

        "auto" follows how the session is limited: by laps (lap x of y) or
        by time (time remaining).
        """
        laps_total = _session_limit(session.get("SessionLaps"))
        time_total = _session_limit(session.get("SessionTime"))
        if mode == "auto":
            mode = "laps" if laps_total else "time" if time_total else "none"
        lead = max((r["laps_completed"] or 0 for r in rows if r["laps_completed"] is not None), default=0)
        remain = frame.session_time_remain
        time_remain = remain if remain is not None and 0 <= remain < 604000 else None
        finished = frame.session_state >= STATE_CHECKERED
        lap = min(lead + 1, int(laps_total)) if laps_total else lead + 1
        return {
            "mode": mode,
            "finished": finished,
            "lap": lap if frame.session_state >= STATE_RACING else 0,
            "laps_total": int(laps_total) if laps_total else None,
            "time_remain": round(time_remain, 1) if time_remain is not None else None,
            "time_total": time_total,
        }

    def _official_best(self, session):
        """Fastest lap per car from the session results iRacing publishes."""
        out = {}
        for res in session.get("ResultsPositions") or []:
            t = res.get("FastestTime")
            if isinstance(res.get("CarIdx"), int) and isinstance(t, (int, float)) and t > 0:
                out[res["CarIdx"]] = round(float(t), 3)
        return out

    def _overlay_snapshot(self, rows, frame, session, active_league):
        settings = self.overlays.get()
        kind = str(session.get("SessionType", "")).lower()
        is_race = kind == "race"
        entries = {r["car_idx"]: self._overlay_entry(r, active_league) for r in rows}
        # Standings: race order in a race; otherwise fastest clean lap, and
        # only drivers who have set one (blank at the start of qualifying).
        # With "reveal", a driver only appears once they've completed a lap:
        # the tower fills up as the field crosses the line.
        reveal = settings["standings"]["reveal"]
        standings = []
        if is_race:
            for r in rows:
                if r["pos"] is not None and (not reveal or (r["laps_completed"] or 0) >= 1):
                    standings.append(dict(entries[r["car_idx"]], pos=r["pos"], class_pos=r["class_pos"],
                                          time=r["gap"], pos_change=r["pos_change"]))
        else:
            official = self._official_best(session)
            timed, untimed = [], []
            for r in rows:
                best = official.get(r["car_idx"]) or self.laps.best(r["car_idx"])
                if best:
                    timed.append((best, r))
                elif reveal and (r["laps_completed"] or 0) >= 1:
                    untimed.append((None, r))  # a lap done, but no clean time yet
            timed.sort(key=lambda x: x[0])
            for best, r in timed + untimed:
                standings.append(dict(entries[r["car_idx"]], time=best, pos_change=None))
        _rank(standings, is_race)
        flash = self._fastest_laps(standings, is_race, settings["standings"], frame)
        # The lap tracker: qualifying only (or practice, if asked).
        lap_cfg = settings["laps"]
        active = "qualify" in kind or (lap_cfg["practice"] and "practice" in kind)
        now = frame.timeline()[1]
        place = {e["car_idx"]: e for e in standings}
        trackers = []
        everyone = []
        cam = None
        if active:
            for idx, e in entries.items():
                st = self.laps.state(idx, now, lap_cfg["reference"], lap_cfg["hide_s"])
                stand = place.get(idx, {})
                item = dict(e, lap=st, pos=stand.get("pos"), class_pos=stand.get("class_pos"), best=stand.get("best"),
                            gap=stand.get("gap"), class_gap=stand.get("class_gap"))
                everyone.append(item)
                if idx == frame.cam_car_idx:
                    cam = item
                elif st and (st["valid"] or lap_cfg["show_invalid"] or st["state"] == "finished"):
                    trackers.append(item)
            # First to finish first: the order stays put as laps run.
            # Just finished first, then the laps nearest the line: the order
            # stays put as laps run.
            trackers.sort(key=lambda x: (x["lap"]["state"] != "finished", -x["lap"]["elapsed"]))
        return {
            "settings": settings,
            "session_kind": "race" if is_race else ("qualify" if "qualify" in kind else (kind or "practice")),
            # Racing under green: close intervals mean something (not behind the safety car).
            "green": is_race and frame.session_state == STATE_RACING and not frame.session_flags & CAUTION_FLAGS,
            "progress": self._session_progress(frame, session, rows, settings["standings"]["header_info"]),
            "standings": standings,
            "fastest_flash": flash,
            # "all": every driver, for the full-screen timing page (timed
            # drivers by lap time, then the rest).
            "laps": {"active": active, "camera": cam, "trackers": trackers, "sectors": len(self.laps.starts),
                     "all": sorted(everyone, key=lambda x: (x["pos"] or 10_000, x["name"].lower()))},
        }

    def _add_start_positions(self, rows, is_race):
        """Grid position (overall and in class) and places gained since, in races."""
        by_idx = {r["car_idx"]: r for r in rows}
        in_class = {}
        for start, idx in enumerate(self._grid_order, start=1):
            r = by_idx.get(idx)
            if r is None:
                continue
            in_class[r["class_key"]] = in_class.get(r["class_key"], 0) + 1
            r["start_pos"], r["class_start_pos"] = start, in_class[r["class_key"]]
        for r in rows:
            r.setdefault("start_pos", None)
            r.setdefault("class_start_pos", None)
            gained = is_race and r["pos"] and r["start_pos"]
            r["pos_change"] = r["start_pos"] - r["pos"] if gained else None
            r["class_pos_change"] = r["class_start_pos"] - r["class_pos"] if gained and r["class_pos"] else None

    def _live_gaps(self, rows, frame):
        """Gaps to the leader from the timing points (see gaps.py), in place of
        iRacing's, which lag; iRacing's stays where there's no timing yet."""
        ranked = [r for r in rows if r["pos"] is not None]
        if not ranked:
            return
        leader = ranked[0]
        now = frame.timeline()[1]
        class_leader = {}
        for r in ranked:
            cl = class_leader.setdefault(r["class_key"], r)
            r["laps_down"] = _laps_down(leader, r)
            r["class_laps_down"] = _laps_down(cl, r)
            if r is leader:
                continue
            if r["progress"] < 0:
                r["gap"] = None  # in the garage: no gap
                continue
            gap = self.gaps.gap(r["car_idx"], leader["car_idx"], r["progress"], now)
            if gap is not None:
                r["gap"] = round(gap, 3)

    @staticmethod
    def _assign_positions(rows, racing):
        """Live order while racing, iRacing's official order otherwise."""
        if racing:
            rows.sort(key=lambda r: (-r["progress"], r["official_pos"] or 999))
        else:
            rows.sort(key=lambda r: (r["official_pos"] or 999, r["best_lap"] or 1e9, -r["progress"]))
        for pos, r in enumerate(rows, start=1):
            r["pos"] = pos if (r["official_pos"] or r["progress"] >= 0) else None

    def _class_key(self, classes, active_league, league_entry, driver):
        """Record the driver's class in ``classes`` and return its key.

        League classes win; otherwise the iRacing car class is used as-is.
        """
        cls = self.leagues.class_for(league_entry, driver["car_class"], active_league, driver["name"])
        if cls is not None:
            key = f"league:{cls['id']}"
            if key not in classes:
                logo = logo_url(active_league["id"], cls.get("logo"))
                order = active_league["classes"].index(cls)
                classes[key] = {
                    "key": key, "name": cls["name"], "color": cls["color"], "logo": logo,
                    "logo_bg": cls.get("logo_bg", "auto"), "logo_tolerance": cls.get("logo_tolerance", 18),
                    "logo_fill": cls.get("logo_fill", "edges"),
                    "order": order,
                }
            return key
        name = driver["car_class"] or "Field"
        key = f"iracing:{name}"
        if key not in classes:
            classes[key] = {
                "key": key, "name": name, "color": driver["class_color"] or "#8b93a3", "logo": None,
                "logo_bg": "keep", "logo_tolerance": 0, "logo_fill": "edges", "order": 1000 + len(classes),
            }
        return key

    @staticmethod
    def _ordered_classes(classes):
        out = sorted(classes.values(), key=lambda c: c["order"])
        for c in out:
            del c["order"]
        return out

    # -- grid walk ----------------------------------------------------------

    def _gridwalk_snapshot(self, classes, active_league, frame):
        """Grid entries in walk order plus the walk state.

        Adds any class it meets to ``classes`` so the overlay can colour it.
        """
        entries = {}
        for idx in self._grid_order:
            d = self._drivers.get(idx)
            if d is None:
                continue
            league = self.leagues.lookup(d["cust_id"], d["number"])
            surface = _at(frame.surface, idx, TRK_NOT_IN_WORLD) if frame else TRK_NOT_IN_WORLD
            entries[f"car:{idx}"] = self._grid_entry(
                d, league, active_league, classes, car_idx=idx, in_session=True,
                in_world=surface != TRK_NOT_IN_WORLD,
            )
        if self.gridwalk.include_absent and active_league:
            present_ids = {d["cust_id"] for d in self._drivers.values()}
            present_names = {d["name"].lower() for d in self._drivers.values()}
            for ld in active_league.get("drivers", []):
                if ld.get("cust_id") in present_ids or (ld.get("cust_id") is None and ld["name"].lower() in present_names):
                    continue
                d = {"name": ld["name"], "number": ld.get("car_number", ""), "team": "", "car": "",
                     "car_class": "", "class_color": None, "cust_id": ld.get("cust_id"),
                     "car_design": None, "helmet_design": None}
                entries[f"league:{driver_key(ld)}"] = self._grid_entry(
                    d, ld, active_league, classes, car_idx=None, in_session=False, in_world=False,
                )
        self._grid_keys = list(entries)
        order = self.gridwalk.apply_order(self._grid_keys)
        in_class = {}
        # Gaps are to the class pole time, as in multiclass qualifying.
        class_pole = {}
        for e in entries.values():
            if e["qual_time"]:
                k = e["class_key"]
                class_pole[k] = min(class_pole.get(k, e["qual_time"]), e["qual_time"])
        out = []
        for pos, key in enumerate(order, start=1):
            e = entries[key]
            in_class[e["class_key"]] = in_class.get(e["class_key"], 0) + 1
            pole = class_pole.get(e["class_key"])
            gap = round(e["qual_time"] - pole, 3) if e["qual_time"] and pole else None
            out.append(dict(e, key=key, grid_pos=pos, class_pos=in_class[e["class_key"]], qual_gap=gap))
        return {**self.gridwalk.state(), "source": "manual" if self.gridwalk.manual_order else self._grid_source,
                "entries": out}

    def _grid_entry(self, d, league, active_league, classes, car_idx, in_session, in_world):
        league = league or {}
        pid = active_league["id"] if active_league else ""
        team = league.get("team") or d.get("team") or ""
        name, nickname = self._stream_name(d["name"], league.get("nickname", ""), active_league)
        return {
            "car_idx": car_idx,
            "name": name,
            "nickname": nickname,
            "number": d.get("number", ""),
            "team": team,
            "team_logo": logo_url(pid, self.leagues.team_logo(team, active_league)) if pid else None,
            "car": d.get("car", ""),
            "make": league.get("car_make") or d.get("make", ""),
            "make_logo": make_logo(league.get("car_make") or d.get("make", "")),
            "car_image": logo_url(pid, league.get("car_image")) if pid else None,
            "helmet_image": logo_url(pid, league.get("helmet_image")) if pid else None,
            "car_design": d.get("car_design"),
            "helmet_design": d.get("helmet_design"),
            "class_key": self._class_key(classes, active_league, league or None, d),
            "in_session": in_session,
            "in_world": in_world,
            "qual_time": self._qual_times.get(car_idx),
        }

    def _league_summary(self):
        active = self.leagues.active()
        if not active:
            return None
        return {"id": active["id"], "name": active["name"], "teams": len(active.get("teams", [])),
                "banners": [{k: b[k] for k in ("id", "name", "orientation")} for b in active.get("banners", [])],
                "sponsors": boards.sponsors(active, "")}

    def publish(self):
        snap = self.build_snapshot()
        updater = getattr(self, "updater", None)
        if updater is not None:
            # So the pop-up appears whenever a check finds a new version.
            st = updater.status()
            snap["update"] = {"available": st["available"] and not st["installed"],
                              "version": st["latest"] and st["latest"]["version"], "error": st["error"],
                              "checked_at": st["checked_at"]}
        with self._changed:
            self._snapshot = snap
            self._version += 1
            self._changed.notify_all()

    def wait_snapshot(self, last_version, timeout=15.0):
        """Block until a snapshot newer than ``last_version`` exists."""
        with self._changed:
            self._changed.wait_for(lambda: self._version != last_version, timeout)
            return self._version, self._snapshot

    # -- commands -----------------------------------------------------------

    def _driver(self, car_idx):
        try:
            car_idx = int(car_idx)
        except (TypeError, ValueError) as e:
            raise CommandError("car_idx must be a number") from e
        d = self._drivers.get(car_idx)
        if d is None:
            raise CommandError(f"No driver in car {car_idx}")
        return d

    def _group(self, group):
        """Resolve a camera group number, falling back to config then current."""
        if group not in (None, "", 0, "0"):
            return int(group)
        wanted = str(self.cfg.get("default_camera_group") or "").lower()
        if wanted:
            for g in self._camera_groups:
                if g["name"].lower() == wanted:
                    return g["num"]
        frame = self._frame
        return frame.cam_group if frame else 0

    def command(self, action, params):
        handler = getattr(self, f"cmd_{action}", None)
        if handler is None:
            raise CommandError(f"Unknown action '{action}'")
        # The grid walk can run from the last known grid while disconnected.
        if not self.source.connected and not action.startswith(("gridwalk_", "overlay_", "photobooth_folder", "board_", "popout", "desktop_")):
            raise CommandError("Not connected to iRacing")
        with self._lock:
            result = handler(**params)
        self.publish()
        return result or {}

    # Overlays that can go straight on the user's screen (see desktop.py):
    # page -> (name, path). "desktop" lets the page know (no drop shadows).
    DESKTOP_PAGES = {
        "standings": ("Standings", "/standings.html"),
        "standings_screen": ("Standings (full screen)", "/standings.html?screen=1"),
        "laps": ("Lap tracker", "/laps.html"),
        "laps_screen": ("Lap tracker (full screen)", "/laps.html?screen=1"),
        "sponsors": ("Sponsors", "/sponsors.html"),
        "board": ("Boards", "/board.html"),
        "gridwalk": ("Grid walk", "/gridwalk.html"),
    }

    def _desktop_snapshot(self):
        d = self.desktop
        if d is None:
            return {"available": False, "on_screen": {}, "screens": []}
        return {"available": True, "on_screen": d.on_screen(), "screens": d.screens()}

    def cmd_desktop_show(self, page, screen=0):
        """Put an overlay on the user's own screen (``screen``: which monitor)."""
        if page not in self.DESKTOP_PAGES:
            raise CommandError("That overlay can't go on screen.")
        if self.desktop is None:
            raise CommandError("On-screen overlays need the app window (they don't work from a browser).")
        name, path = self.DESKTOP_PAGES[page]
        if not self.desktop.show(page, f"{path}{'&' if '?' in path else '?'}desktop=1", name, int(screen or 0)):
            raise CommandError("On-screen overlays need the app window (they don't work from a browser).")
        return {"on_screen": self.desktop.on_screen()}

    def cmd_desktop_hide(self, page=None):
        """Take an on-screen overlay down (all of them, with no ``page``)."""
        if self.desktop is not None:
            self.desktop.hide(page)
        return {"on_screen": self.desktop.on_screen() if self.desktop else {}}

    POPOUT_PAGES = {"timing": "Timing", "boards": "Boards"}

    def cmd_popout(self, page):
        """Open a control panel page in its own window. ``opened`` False: the
        page opens a browser window itself (no app window, e.g. in a browser)."""
        if page not in self.POPOUT_PAGES:
            raise CommandError("That page can't be popped out.")
        return {"opened": bool(self.popout and self.popout(page, self.POPOUT_PAGES[page]))}

    def cmd_watch(self, car_idx, group=None, camera=0):
        d = self._driver(car_idx)
        self.source.cam_switch_num(d["number"], self._group(group), int(camera or 0))
        return {"watching": d["name"]}

    def cmd_watch_position(self, position, group=None, camera=0):
        self.source.cam_switch_pos(int(position), self._group(group), int(camera or 0))

    def cmd_watch_special(self, mode, group=None):
        modes = {"leader": CS_AT_LEADER, "incident": CS_AT_INCIDENT, "exciting": CS_AT_EXCITING}
        if mode not in modes:
            raise CommandError(f"Unknown mode '{mode}'")
        self.source.cam_switch_pos(modes[mode], self._group(group), 0)

    def cmd_camera_group(self, group):
        frame = self._frame
        if frame is None or frame.cam_car_idx is None or frame.cam_car_idx < 0:
            raise CommandError("No car is being spectated")
        d = self._drivers.get(frame.cam_car_idx)
        if d is None:
            raise CommandError("Current camera car is not a driver")
        self.source.cam_switch_num(d["number"], int(group), 0)

    def cmd_step_car(self, direction=1, group=None):
        """Watch the car ahead (-1) or behind (+1) the current one."""
        frame = self._frame
        if frame is None:
            raise CommandError("No data")
        order = [r["car_idx"] for r in self.build_snapshot()["drivers"] if r["in_world"]]
        if not order:
            raise CommandError("No cars on track")
        try:
            i = order.index(frame.cam_car_idx)
        except ValueError:
            i = -1 if int(direction) > 0 else 0
        target = order[(i + int(direction)) % len(order)]
        return self.cmd_watch(target, group)

    def cmd_replay_event(self, event_id, preroll=None):
        event = next((e for e in self.detector.events if e["id"] == int(event_id)), None)
        if event is None:
            raise CommandError("That event is no longer stored")
        return self._replay(event["car_idx"], event["session_num"], event["session_time"], preroll)

    def cmd_replay_driver(self, car_idx, preroll=None):
        """Replay the driver's most recent event."""
        idx = int(car_idx)
        event = next((e for e in reversed(self.detector.events) if e["car_idx"] == idx), None)
        if event is None:
            raise CommandError("No incidents or overtakes recorded for this driver yet")
        return self._replay(idx, event["session_num"], event["session_time"], preroll)

    def cmd_replay_seconds(self, seconds=10, car_idx=None):
        """Instant replay: jump back N seconds (optionally on a specific car)."""
        frame = self._frame
        if frame is None:
            raise CommandError("No data")
        base = frame.session_time if frame.is_live else frame.replay_session_time
        idx = int(car_idx) if car_idx not in (None, "") else frame.cam_car_idx
        return self._replay(idx, frame.session_num, base - float(seconds), preroll=0)

    def _replay(self, car_idx, session_num, session_time, preroll=None):
        preroll = float(self.cfg["replay_preroll_s"] if preroll is None else preroll)
        target = max(0.0, float(session_time) - preroll)
        d = self._drivers.get(car_idx)
        group = self._group(None)
        source = self.source

        # Seek first, then point the camera once iRacing has loaded the frame,
        # then play. Done in the background so the HTTP call returns at once.
        def run():
            source.replay_set_play_speed(0, False)
            source.replay_search_session_time(session_num, int(target * 1000))
            time.sleep(0.35)
            if d is not None:
                source.cam_switch_num(d["number"], group, 0)
            time.sleep(0.1)
            source.replay_set_play_speed(1, False)

        threading.Thread(target=run, name="replay", daemon=True).start()
        self._schedule_auto_return()
        return {"replaying": d["name"] if d else None, "session_time": round(target, 1)}

    def _schedule_auto_return(self):
        if self._return_timer:
            self._return_timer.cancel()
            self._return_timer = None
        delay = float(self.cfg.get("replay_auto_return_s") or 0)
        if delay > 0:
            self._return_timer = threading.Timer(delay, self._go_live)
            self._return_timer.daemon = True
            self._return_timer.start()

    def _go_live(self):
        self.source.replay_search(RPY_SRCH_TO_END)
        self.source.replay_set_play_speed(1, False)

    def cmd_live(self):
        if self._return_timer:
            self._return_timer.cancel()
            self._return_timer = None
        self._go_live()

    def cmd_replay_speed(self, speed=1, slow_motion=False):
        self.source.replay_set_play_speed(int(speed), bool(slow_motion))

    def cmd_replay_incident(self, direction=1):
        """Step through iRacing's own incident markers on the replay tape."""
        self.source.replay_search(RPY_SRCH_NEXT_INCIDENT if int(direction) > 0 else RPY_SRCH_PREV_INCIDENT)
        self.source.replay_set_play_speed(1, False)

    def cmd_clear_events(self):
        self.detector.clear()
        self._info_update = None  # re-baseline incident counts

    # -- grid walk commands ---------------------------------------------------

    def _grid_count(self):
        self.build_snapshot()  # refreshes the entry list
        return len(self._grid_keys)

    def cmd_gridwalk_start(self, index=0):
        if not self._grid_count():
            raise CommandError("No drivers on the grid yet")
        self.gridwalk.start(int(index))

    def cmd_gridwalk_pause(self):
        self.gridwalk.pause()

    def cmd_gridwalk_resume(self):
        if not self._grid_count():
            raise CommandError("No drivers on the grid yet")
        self.gridwalk.resume()

    def cmd_gridwalk_next(self):
        self.gridwalk.step(1, self._grid_count())

    def cmd_gridwalk_prev(self):
        self.gridwalk.step(-1, self._grid_count())

    def cmd_gridwalk_goto(self, index):
        self.gridwalk.goto(int(index), self._grid_count())

    def cmd_gridwalk_hide(self):
        self.gridwalk.hide()

    def cmd_gridwalk_settings(self, interval=None, style=None, loop=None, include_absent=None):
        try:
            self.gridwalk.configure(interval, style, loop, include_absent)
        except ValueError as e:
            raise CommandError(str(e)) from e

    def cmd_gridwalk_move(self, key, direction):
        self._grid_count()
        try:
            self.gridwalk.move(self._grid_keys, str(key), int(direction))
        except ValueError as e:
            raise CommandError(str(e)) from e

    def cmd_gridwalk_reset_order(self):
        self.gridwalk.reset_order()

    # -- photo booth -------------------------------------------------------------

    def cmd_photobooth_start(self, car_idx=None, group=None, cutout=True):
        """Photograph one car (car_idx) or every loaded car, in grid order."""
        from .photobooth import PhotoBoothError

        if self.photobooth is None:
            raise CommandError("The photo booth isn't available")
        if car_idx not in (None, ""):
            cars = [int(car_idx)]
        else:
            frame = self._frame
            # Only cars loaded onto the track can be photographed.
            cars = [i for i in self._grid_order
                    if frame and _at(frame.surface, i, TRK_NOT_IN_WORLD) != TRK_NOT_IN_WORLD]
        try:
            self.photobooth.start(cars, self._group(group), use_cutout=bool(cutout))
        except PhotoBoothError as e:
            raise CommandError(str(e)) from e
        return {"cars": len(cars)}

    def cmd_board_show(self, kind, group="", round=""):
        """Put a full-screen board on screen (board.html)."""
        if kind not in boards.KINDS:
            raise CommandError(f"Unknown board '{kind}'")
        if not self.leagues.active():
            raise CommandError("Activate a league first: boards show its championship")
        self.board = {"kind": kind, "params": {"group": str(group or ""), "round": str(round or "")}}
        return {"board": kind}

    def cmd_board_hide(self):
        self.board = {"kind": None, "params": {}}

    def _boards(self, active_league, live_results):
        board, opts = self._board_snapshot(active_league, live_results)
        return {"board": board, "board_options": opts}

    def _board_snapshot(self, active_league, live_results):
        """(board, options): cached until the league, the board or its settings change."""
        settings = self.overlays.get()
        key = (active_league and (active_league["id"], active_league.get("updated_at")), repr(self.board),
               repr({k: v for k, v in settings.items() if k.startswith("board")}))
        live = self.board.get("kind") == "results" and self.board["params"].get("round") == "live"
        if key == self._board_cache[0] and not live:
            return self._board_cache[1]
        value = (boards.build(active_league, self.board, settings, live_results() if live else None),
                 boards.options(active_league))
        self._board_cache = (key, value)
        return value

    def cmd_overlay_settings(self, overlay, values):
        try:
            settings = self.overlays.update(overlay, values)
            self._apply_sectors()
            return {"settings": settings}
        except ValueError as e:
            raise CommandError(str(e)) from e

    def cmd_photobooth_folder(self, folder=""):
        """Where iRacing saves screenshots ("" = its default folder)."""
        from .photobooth import PhotoBoothError
        if self.photobooth is None:
            raise CommandError("The photo booth isn't available")
        try:
            self.photobooth.set_folder(folder)
        except PhotoBoothError as e:
            raise CommandError(str(e)) from e
        self.settings.set("screenshots_dir", str(self.photobooth.custom_dir or ""))
        return {"folder": str(self.photobooth.screenshots_dir)}

    def cmd_photobooth_cancel(self):
        if self.photobooth is not None:
            self.photobooth.cancel()
