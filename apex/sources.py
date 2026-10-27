"""Telemetry sources.

A source exposes one small interface used by the rest of the app:

* ``connect()``           try to attach to the sim, returns ``True`` when connected
* ``connected``           current connection state
* ``read()``              latest telemetry ``Frame`` (or ``None`` when disconnected)
* ``session_info()``      ``(update_counter, dict)`` of the parsed session YAML
* broadcast commands      ``cam_switch_num``, ``cam_switch_pos``,
                          ``replay_search``, ``replay_search_session_time``,
                          ``replay_set_play_speed``

``IRacingSource`` talks to the real sim through pyirsdk (Windows only).
``MockSource`` simulates a race so the overlay can be developed and demoed
without iRacing running.
"""

import math
import random
import threading
import time
from dataclasses import dataclass, field

# Values mirrored from the iRacing SDK so this module imports on any OS.
TRK_NOT_IN_WORLD = -1
TRK_OFF_TRACK = 0
TRK_IN_PIT_STALL = 1
TRK_APPROACHING_PITS = 2
TRK_ON_TRACK = 3

STATE_RACING = 4
STATE_CHECKERED = 5

FLAG_YELLOW = 0x0008
FLAG_YELLOW_WAVING = 0x0100
FLAG_CAUTION = 0x4000
FLAG_CAUTION_WAVING = 0x8000
CAUTION_FLAGS = FLAG_YELLOW | FLAG_YELLOW_WAVING | FLAG_CAUTION | FLAG_CAUTION_WAVING

RPY_SRCH_TO_END = 1
RPY_SRCH_PREV_INCIDENT = 8
RPY_SRCH_NEXT_INCIDENT = 9

CS_AT_INCIDENT = -3
CS_AT_LEADER = -2
CS_AT_EXCITING = -1


@dataclass
class Frame:
    """One telemetry sample. Per-car lists are indexed by CarIdx."""

    session_time: float = 0.0
    session_num: int = 0
    session_state: int = 0
    session_flags: int = 0
    cam_car_idx: int = -1
    cam_group: int = 0
    replay_frames_from_end: int = 0
    replay_session_time: float = 0.0
    replay_session_num: int = 0
    replay_speed: int = 1
    lap: list = field(default_factory=list)
    pct: list = field(default_factory=list)
    position: list = field(default_factory=list)
    class_position: list = field(default_factory=list)
    on_pit: list = field(default_factory=list)
    surface: list = field(default_factory=list)
    f2_time: list = field(default_factory=list)
    last_lap: list = field(default_factory=list)
    best_lap: list = field(default_factory=list)

    @property
    def is_live(self):
        # ReplayFrameNumEnd counts frames from the end of the replay tape;
        # it sits at 0-1 while watching live.
        return self.replay_frames_from_end <= 10


class IRacingSource:
    """Live iRacing connection via pyirsdk."""

    name = "iracing"

    def __init__(self):
        import irsdk  # imported lazily: Windows-only at runtime

        self._irsdk = irsdk
        self.ir = irsdk.IRSDK()
        self.connected = False
        self._lock = threading.Lock()
        self._info = {}
        self._info_update = -1
        self._last_attempt = float("-inf")

    RETRY_S = 2.0

    def connect(self):
        """Keep the connection healthy; cheap to call every tick."""
        with self._lock:
            if self.connected and not (self.ir.is_initialized and self.ir.is_connected):
                self.ir.shutdown()
                self.connected = False
                self._info_update = -1
            # startup() polls the sim's local status page, so don't hammer it.
            if not self.connected and time.monotonic() - self._last_attempt >= self.RETRY_S:
                self._last_attempt = time.monotonic()
                if self.ir.startup():
                    self.connected = bool(self.ir.is_initialized and self.ir.is_connected)
            return self.connected

    def _var(self, name, default=None):
        try:
            value = self.ir[name]
        except Exception:
            return default
        return default if value is None else value

    def read(self):
        if not self.connected:
            return None
        with self._lock:
            ir = self.ir
            ir.freeze_var_buffer_latest()
            v = self._var
            frame = Frame(
                session_time=v("SessionTime", 0.0),
                session_num=v("SessionNum", 0),
                session_state=v("SessionState", 0),
                session_flags=v("SessionFlags", 0),
                cam_car_idx=v("CamCarIdx", -1),
                cam_group=v("CamGroupNumber", 0),
                replay_frames_from_end=v("ReplayFrameNumEnd", 0),
                replay_session_time=v("ReplaySessionTime", 0.0),
                replay_session_num=v("ReplaySessionNum", 0),
                replay_speed=v("ReplayPlaySpeed", 1),
                lap=v("CarIdxLap", []),
                pct=v("CarIdxLapDistPct", []),
                position=v("CarIdxPosition", []),
                class_position=v("CarIdxClassPosition", []),
                on_pit=v("CarIdxOnPitRoad", []),
                surface=v("CarIdxTrackSurface", []),
                f2_time=v("CarIdxF2Time", []),
                last_lap=v("CarIdxLastLapTime", []),
                best_lap=v("CarIdxBestLapTime", []),
            )
            ir.unfreeze_var_buffer_latest()
            return frame

    def session_info(self):
        if not self.connected:
            return self._info_update, self._info
        with self._lock:
            update = self.ir.session_info_update
            if update != self._info_update:
                info = {}
                for key in ("WeekendInfo", "SessionInfo", "DriverInfo", "CameraInfo"):
                    try:
                        info[key] = self.ir[key] or {}
                    except Exception:
                        info[key] = {}
                self._info, self._info_update = info, update
            return self._info_update, self._info

    # -- broadcast commands -------------------------------------------------

    def cam_switch_num(self, car_number, group=0, camera=0):
        with self._lock:
            self.ir.cam_switch_num(str(car_number), group, camera)

    def cam_switch_pos(self, position, group=0, camera=0):
        with self._lock:
            self.ir.cam_switch_pos(position, group, camera)

    def replay_search(self, mode):
        with self._lock:
            self.ir.replay_search(mode)

    def replay_search_session_time(self, session_num, session_time_ms):
        with self._lock:
            self.ir.replay_search_session_time(session_num, int(session_time_ms))

    def replay_set_play_speed(self, speed=1, slow_motion=False):
        with self._lock:
            self.ir.replay_set_play_speed(speed, slow_motion)


# ---------------------------------------------------------------------------
# Mock source
# ---------------------------------------------------------------------------

MOCK_NAMES = [
    "Ayrton Vale", "Kimi Strand", "Lena Brooks", "Marco Feld", "Sofia Reyes",
    "Jonas Kahl", "Priya Natarajan", "Tom Okafor", "Elise Morin", "Dan Kowalski",
    "Hugo Brandt", "Mei Tanaka", "Owen Price", "Carla Duarte", "Felix Lund",
    "Nadia Sorensen", "Ravi Mehta", "Grace Whitfield", "Luca Bianchi", "Sam Ito",
]


class MockSource:
    """Self-contained race simulation for development and demos.

    Cars circulate with varying pace so they genuinely overtake each other,
    occasionally run off track (with incident points), and sometimes pit.
    Camera and replay commands are honoured so the UI behaves as it would
    against the sim.
    """

    name = "mock"
    TRACK_LENGTH_KM = 4.2

    def __init__(self, num_cars=18, seed=None, time_scale=1.0, clock=time.monotonic):
        self.rng = random.Random(seed)
        self.clock = clock
        self.time_scale = time_scale
        self.connected = False
        self._lock = threading.Lock()
        self.num_cars = min(num_cars, len(MOCK_NAMES))
        self.session_time = 0.0
        self._last_clock = None
        self.info_update = 1
        self.cam_car_idx = 1
        self.cam_group = 1
        # Replay state: None while live, otherwise the session time being shown.
        self.replay_time = None
        self.replay_speed = 1
        self.commands = []  # log of received commands (used by tests)
        n = self.num_cars
        # Every third car is a slower GT4 so the mock race is multiclass.
        self.base_lap = [88.0 + self.rng.uniform(0, 4) + (5.0 if self._is_gt4(i) else 0.0) for i in range(n)]
        # Staggered grid: car i starts slightly behind car i-1.
        self.progress = [-(i * 0.006) for i in range(n)]
        self.slow_until = [0.0] * n
        self.offtrack_until = [0.0] * n
        self.pit_until = [0.0] * n
        self.incidents = [0] * n
        self.pending_incidents = []  # (apply_at, car_idx, points)
        self.last_lap = [-1.0] * n
        self.best_lap = [-1.0] * n
        self.lap_start = [0.0] * n
        self.phase = [self.rng.uniform(0, math.tau) for _ in range(n)]
        self.drivers = self._build_drivers()

    @staticmethod
    def _is_gt4(i):
        return i % 3 == 2

    def _build_drivers(self):
        drivers = [{
            "CarIdx": 0, "UserName": "Pace Car", "AbbrevName": "Pace", "UserID": -1,
            "TeamName": "", "CarNumber": "0", "CarNumberRaw": 0, "CarIsPaceCar": 1,
            "IsSpectator": 0, "CarScreenNameShort": "Safety Car", "CarClassShortName": "",
            "CarClassColor": 0xFFFFFF, "IRating": 0, "LicString": "",
            "CurDriverIncidentCount": 0, "TeamIncidentCount": 0,
        }]
        for i in range(self.num_cars):
            name = MOCK_NAMES[i]
            first, last = name.split(" ", 1)
            num = str((i * 7) % 97 + 2)
            drivers.append({
                "CarIdx": i + 1, "UserName": name, "AbbrevName": f"{last}, {first[0]}",
                "UserID": 100000 + i, "TeamName": "", "CarNumber": num,
                "CarNumberRaw": int(num), "CarIsPaceCar": 0, "IsSpectator": 0,
                "CarScreenNameShort": "GT4" if self._is_gt4(i) else "GT3",
                "CarClassShortName": "GT4" if self._is_gt4(i) else "GT3",
                "CarClassID": 4084 if self._is_gt4(i) else 4083,
                "CarClassColor": 0x53FF77 if self._is_gt4(i) else 0xFFDA59, "IRating": 1500 + (self.num_cars - i) * 120,
                "LicString": "A 3.21", "CurDriverIncidentCount": 0, "TeamIncidentCount": 0,
            })
        return drivers

    def connect(self):
        self.connected = True
        return True

    # -- simulation ---------------------------------------------------------

    def _advance(self):
        now = self.clock()
        if self._last_clock is None:
            self._last_clock = now
            return
        dt = min(now - self._last_clock, 1.0) * self.time_scale
        self._last_clock = now
        self.step(dt)

    def step(self, dt):
        """Advance the simulation by ``dt`` seconds of session time."""
        rng = self.rng
        self.session_time += dt
        t = self.session_time
        for i in range(self.num_cars):
            # Pace oscillates per car so cars trade places.
            pace = 1.0 + 0.02 * math.sin(t / 31.0 + self.phase[i])
            if t < self.slow_until[i]:
                pace *= 0.15
            if t < self.pit_until[i]:
                pace *= 0.35
            prev = self.progress[i]
            self.progress[i] += dt / self.base_lap[i] * pace
            if int(math.floor(self.progress[i])) > int(math.floor(prev)) and self.progress[i] >= 1:
                lap_time = t - self.lap_start[i]
                if self.lap_start[i] > 0:
                    self.last_lap[i] = lap_time
                    if self.best_lap[i] < 0 or lap_time < self.best_lap[i]:
                        self.best_lap[i] = lap_time
                self.lap_start[i] = t
                if rng.random() < 0.04 and t > 120:
                    self.pit_until[i] = t + 22
            # Random off-track moment: ~once every 7 minutes per car.
            if t > 15 and t > self.slow_until[i] + 10 and rng.random() < dt / 420.0:
                self.offtrack_until[i] = t + 2.5
                self.slow_until[i] = t + 3.0
                points = rng.choice([1, 2, 4])
                # Incident points reach session info a few seconds later, like the sim.
                self.pending_incidents.append((t + rng.uniform(2, 5), i, points))
        still_pending = []
        for apply_at, i, points in self.pending_incidents:
            if t >= apply_at:
                self.incidents[i] += points
                self.drivers[i + 1]["CurDriverIncidentCount"] = self.incidents[i]
                self.info_update += 1
            else:
                still_pending.append((apply_at, i, points))
        self.pending_incidents = still_pending
        if self.replay_time is not None:
            self.replay_time += dt * self.replay_speed
            if self.replay_time >= t:
                self.replay_time = None

    def read(self):
        with self._lock:
            self._advance()
            t = self.session_time
            n = self.num_cars + 1
            lap = [-1] * n
            pct = [-1.0] * n
            on_pit = [False] * n
            surface = [TRK_NOT_IN_WORLD] * n
            last_lap = [-1.0] * n
            best_lap = [-1.0] * n
            order = sorted(range(self.num_cars), key=lambda i: -self.progress[i])
            position = [0] * n
            f2 = [0.0] * n
            leader = self.progress[order[0]]
            for rank, i in enumerate(order, start=1):
                position[i + 1] = rank
                f2[i + 1] = max(0.0, (leader - self.progress[i]) * 90.0)
            for i in range(self.num_cars):
                p = self.progress[i]
                idx = i + 1
                lap[idx] = max(0, int(math.floor(p)) + 1) if p >= 0 else 0
                pct[idx] = p % 1.0
                on_pit[idx] = t < self.pit_until[i]
                if on_pit[idx]:
                    surface[idx] = TRK_APPROACHING_PITS
                elif t < self.offtrack_until[i]:
                    surface[idx] = TRK_OFF_TRACK
                else:
                    surface[idx] = TRK_ON_TRACK
                last_lap[idx] = self.last_lap[i]
                best_lap[idx] = self.best_lap[i]
            live = self.replay_time is None
            return Frame(
                session_time=t,
                session_num=0,
                session_state=STATE_RACING,
                session_flags=0,
                cam_car_idx=self.cam_car_idx,
                cam_group=self.cam_group,
                replay_frames_from_end=0 if live else int((t - self.replay_time) * 60),
                replay_session_time=t if live else self.replay_time,
                replay_session_num=0,
                replay_speed=self.replay_speed,
                lap=lap, pct=pct, position=position, class_position=list(position),
                on_pit=on_pit, surface=surface, f2_time=f2,
                last_lap=last_lap, best_lap=best_lap,
            )

    def session_info(self):
        with self._lock:
            info = {
                "WeekendInfo": {
                    "TrackDisplayName": "Mock Raceway", "TrackConfigName": "Grand Prix",
                    "TrackLength": f"{self.TRACK_LENGTH_KM:.2f} km", "EventType": "Race",
                },
                "SessionInfo": {"Sessions": [{
                    "SessionNum": 0, "SessionType": "Race", "SessionName": "RACE",
                    "SessionLaps": "30", "SessionTime": "unlimited",
                }]},
                "DriverInfo": {"DriverCarIdx": 1, "Drivers": [dict(d) for d in self.drivers]},
                "CameraInfo": {"Groups": [
                    {"GroupNum": 1, "GroupName": "Nose"},
                    {"GroupNum": 2, "GroupName": "Gearbox"},
                    {"GroupNum": 3, "GroupName": "Roll Bar"},
                    {"GroupNum": 4, "GroupName": "Chase"},
                    {"GroupNum": 5, "GroupName": "Far Chase"},
                    {"GroupNum": 6, "GroupName": "Cockpit"},
                    {"GroupNum": 9, "GroupName": "TV1"},
                    {"GroupNum": 10, "GroupName": "TV2"},
                    {"GroupNum": 11, "GroupName": "TV3"},
                    {"GroupNum": 14, "GroupName": "Blimp"},
                    {"GroupNum": 15, "GroupName": "Chopper"},
                ]},
            }
            return self.info_update, info

    # -- broadcast commands -------------------------------------------------

    def _car_idx_for_number(self, car_number):
        for d in self.drivers:
            if str(d["CarNumber"]) == str(car_number):
                return d["CarIdx"]
        return None

    def cam_switch_num(self, car_number, group=0, camera=0):
        with self._lock:
            self.commands.append(("cam_switch_num", str(car_number), group, camera))
            idx = self._car_idx_for_number(car_number)
            if idx is not None:
                self.cam_car_idx = idx
            if group:
                self.cam_group = group

    def cam_switch_pos(self, position, group=0, camera=0):
        with self._lock:
            self.commands.append(("cam_switch_pos", position, group, camera))
            if position == CS_AT_LEADER or position == 1:
                order = sorted(range(self.num_cars), key=lambda i: -self.progress[i])
                self.cam_car_idx = order[0] + 1
            elif position > 0:
                order = sorted(range(self.num_cars), key=lambda i: -self.progress[i])
                if position <= len(order):
                    self.cam_car_idx = order[position - 1] + 1
            if group:
                self.cam_group = group

    def replay_search(self, mode):
        with self._lock:
            self.commands.append(("replay_search", mode))
            if mode == RPY_SRCH_TO_END:
                self.replay_time = None
                self.replay_speed = 1

    def replay_search_session_time(self, session_num, session_time_ms):
        with self._lock:
            self.commands.append(("replay_search_session_time", session_num, int(session_time_ms)))
            target = session_time_ms / 1000.0
            self.replay_time = target if target < self.session_time else None

    def replay_set_play_speed(self, speed=1, slow_motion=False):
        with self._lock:
            self.commands.append(("replay_set_play_speed", speed, slow_motion))
            self.replay_speed = speed
