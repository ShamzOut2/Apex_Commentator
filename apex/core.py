"""The app core: polls the source, tracks drivers and events, builds the
snapshot the overlay renders, and runs spectate / replay commands.
"""

import re
import threading
from dataclasses import replace
import time

from . import __version__
from .events import EventDetector
from .gridwalk import GridWalk, grid_order, parse_design, qualifying_times
from .league import driver_key, logo_url
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


def _lap_time(value):
    return round(value, 3) if value and value > 0 else None


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
        self._logged_until = {}    # session num -> race time logged so far
        self.detection = "waiting" # live | replay | paused | waiting
        self._grid_keys = []       # entry keys in automatic order, from the last snapshot
        self.photobooth = None     # set by __main__ (needs the user data folder)

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
        self._logged_until[num] = t
        self.detection = "live" if frame.is_live else "replay"

    # -- session info -------------------------------------------------------

    def _load_session_info(self, info, frame):
        weekend = info.get("WeekendInfo") or {}
        self._track_m = parse_track_length(weekend.get("TrackLength"))
        sessions = (info.get("SessionInfo") or {}).get("Sessions") or []
        self._session_meta = {
            "track": weekend.get("TrackDisplayName", ""),
            "track_config": weekend.get("TrackConfigName", ""),
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
                row["league"] = {k: league.get(k, "") for k in ("nickname", "team", "notes")} if league else None
                row["class_key"] = self._class_key(classes, active_league, league, d)
                row.update({
                    "lap": lap if lap is not None and lap >= 0 else None,
                    "pct": round(pct, 4) if pct is not None and pct >= 0 else None,
                    "official_pos": _at(frame.position, idx, 0) or None,
                    "class_pos": _at(frame.class_position, idx, 0) or None,
                    "on_pit": bool(_at(frame.on_pit, idx, False)),
                    "surface": SURFACES.get(surface, "unknown"),
                    "in_world": surface != TRK_NOT_IN_WORLD,
                    "gap": round(_at(frame.f2_time, idx, 0.0), 3) if is_race else None,
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
            in_class = {}
            for r in rows:
                del r["progress"]
                if r["pos"] is not None:
                    in_class[r["class_key"]] = in_class.get(r["class_key"], 0) + 1
                    r["class_pos"] = in_class[r["class_key"]]
            self._add_start_positions(rows, is_race)
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
                "league": self._league_summary(),
            }
            return snap

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
        cls = self.leagues.class_for(league_entry, driver["car_class"], active_league)
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
        return {
            "car_idx": car_idx,
            "name": d["name"],
            "nickname": league.get("nickname", ""),
            "number": d.get("number", ""),
            "team": team,
            "team_logo": logo_url(pid, self.leagues.team_logo(team, active_league)) if pid else None,
            "car": d.get("car", ""),
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
        return {"id": active["id"], "name": active["name"]} if active else None

    def publish(self):
        snap = self.build_snapshot()
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
        if not self.source.connected and not action.startswith("gridwalk_"):
            raise CommandError("Not connected to iRacing")
        with self._lock:
            result = handler(**params)
        self.publish()
        return result or {}

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

    def cmd_photobooth_cancel(self):
        if self.photobooth is not None:
            self.photobooth.cancel()
