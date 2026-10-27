"""The app core: polls the source, tracks drivers and events, builds the
snapshot the overlay renders, and runs spectate / replay commands.
"""

import re
import threading
import time

from .events import EventDetector
from .sources import (
    CS_AT_EXCITING,
    CS_AT_INCIDENT,
    CS_AT_LEADER,
    RPY_SRCH_NEXT_INCIDENT,
    RPY_SRCH_PREV_INCIDENT,
    RPY_SRCH_TO_END,
    STATE_RACING,
    TRK_NOT_IN_WORLD,
)

SESSION_STATES = {
    0: "Invalid", 1: "Get in car", 2: "Warmup", 3: "Parade laps",
    4: "Racing", 5: "Checkered", 6: "Cool down",
}
SURFACES = {-1: "not_in_world", 0: "off_track", 1: "pit_stall", 2: "approaching_pits", 3: "on_track"}
DEFAULT_TRACK_M = 4000.0


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
            # Detect on live data only: replay playback would create duplicates.
            if frame.is_live:
                self.detector.update(frame, self._drivers, self._track_m, self._is_race(frame))
        return True

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
            }
        self._drivers = drivers

    def _session(self, frame):
        return self._session_meta.get("sessions", {}).get(frame.session_num, {})

    def _is_race(self, frame):
        return str(self._session(frame).get("SessionType", "")).lower() == "race"

    # -- snapshot -----------------------------------------------------------

    def build_snapshot(self):
        with self._lock:
            frame = self._frame
            if frame is None:
                return {"connected": False, "source": self.source.name, "league": self._league_summary()}
            is_race = self._is_race(frame)
            racing = is_race and frame.session_state == STATE_RACING
            events = self.detector.events
            counts = {}
            last_event = {}
            for ev in events:
                counts[ev["car_idx"]] = counts.get(ev["car_idx"], 0) + 1
                last_event[ev["car_idx"]] = ev["id"]
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
            session = self._session(frame)
            snap = {
                "connected": True,
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
                "classes": self._ordered_classes(classes),
                "events": events[-100:],
                "league": self._league_summary(),
            }
            return snap

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
                logo = f"/api/logos/{active_league['id']}/{cls['logo']}" if cls.get("logo") else None
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
        if not self.source.connected:
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
