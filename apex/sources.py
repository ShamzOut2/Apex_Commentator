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
# Per-car flags (CarIdxSessionFlags)
FLAG_CHECKERED = 0x0001
FLAG_WHITE = 0x0002
FLAG_GREEN = 0x0004
FLAG_BLUE = 0x0020
FLAG_BLACK = 0x010000
FLAG_DISQUALIFY = 0x020000
FLAG_FURLED = 0x080000   # rolled black flag: a warning
FLAG_REPAIR = 0x100000   # meatball: must pit for repairs
CAUTION_FLAGS = FLAG_YELLOW | FLAG_YELLOW_WAVING | FLAG_CAUTION | FLAG_CAUTION_WAVING

RPY_SRCH_TO_END = 1
RPY_SRCH_PREV_INCIDENT = 8
RPY_SRCH_NEXT_INCIDENT = 9

CAM_UI_HIDDEN = 0x0008
VIDEO_SCREENSHOT = 0

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
    cam_state: int = 0
    replay_frames_from_end: int = 0
    replay_session_time: float = 0.0
    replay_session_num: int = 0
    replay_speed: int = 1
    session_time_remain: float = -1.0   # huge or -1 when the session isn't timed
    session_laps_remain: int = -1       # 32767 or -1 when it isn't lap-limited
    lap: list = field(default_factory=list)
    laps_completed: list = field(default_factory=list)
    pct: list = field(default_factory=list)
    position: list = field(default_factory=list)
    class_position: list = field(default_factory=list)
    on_pit: list = field(default_factory=list)
    surface: list = field(default_factory=list)
    f2_time: list = field(default_factory=list)
    last_lap: list = field(default_factory=list)
    best_lap: list = field(default_factory=list)
    car_flags: list = field(default_factory=list)

    def timeline(self):
        """(session number, session time) of what's on screen: live, or the replay being watched."""
        if self.is_live or self.replay_session_time <= 0:
            return self.session_num, self.session_time
        return self.replay_session_num, self.replay_session_time

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
                cam_state=v("CamCameraState", 0),
                replay_frames_from_end=v("ReplayFrameNumEnd", 0),
                replay_session_time=v("ReplaySessionTime", 0.0),
                replay_session_num=v("ReplaySessionNum", 0),
                replay_speed=v("ReplayPlaySpeed", 1),
                session_time_remain=v("SessionTimeRemain", -1.0),
                session_laps_remain=v("SessionLapsRemainEx", -1),
                lap=v("CarIdxLap", []),
                laps_completed=v("CarIdxLapCompleted", []),
                pct=v("CarIdxLapDistPct", []),
                position=v("CarIdxPosition", []),
                class_position=v("CarIdxClassPosition", []),
                on_pit=v("CarIdxOnPitRoad", []),
                surface=v("CarIdxTrackSurface", []),
                f2_time=v("CarIdxF2Time", []),
                last_lap=v("CarIdxLastLapTime", []),
                best_lap=v("CarIdxBestLapTime", []),
                car_flags=v("CarIdxSessionFlags", []),
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
                for key in ("WeekendInfo", "SessionInfo", "DriverInfo", "CameraInfo", "QualifyResultsInfo",
                            "SplitTimeInfo"):
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

    def cam_set_state(self, state):
        with self._lock:
            self.ir.cam_set_state(state)

    def screenshot(self):
        """Ask iRacing to save a screenshot (needs Video and Screen Capture enabled)."""
        with self._lock:
            self.ir.video_capture(VIDEO_SCREENSHOT)


# ---------------------------------------------------------------------------
# Mock source
# ---------------------------------------------------------------------------

MOCK_TEAMS = ["Apex Racing", "Redline Motorsport", "Northbound GT", "Kestrel Works", "Vanta Racing", "Halcyon Motorsport"]
MOCK_COLORS = ["d7263d", "1b76d1", "f2c94c", "111111", "ffffff", "2a9d58", "f2994a", "7b2cbf", "56ccf2", "9aa5b1"]

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

    SECTOR_STARTS = (0.0, 0.32, 0.68)

    def __init__(self, num_cars=18, seed=None, time_scale=1.0, clock=time.monotonic, session="race",
                 race_laps=0, retirements=False, no_shows=0, sectors=3):
        # "race", or "qualify": cars leave the pits and do timed laps, no grid.
        self.session_kind = session
        if sectors != 3:
            # Like many real tracks: lots of uneven split points.
            self.SECTOR_STARTS = tuple(round(k / sectors + (0.02 if k % 2 else -0.015) * (k > 0), 3)
                                       for k in range(sectors))
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
        self.cam_state = 0
        self.screenshots_dir = None  # where screenshot() writes, like iRacing's folder
        n = self.num_cars
        # Every third car is a slower GT4 so the mock race is multiclass.
        self.base_lap = [88.0 + self.rng.uniform(0, 4) + (5.0 if self._is_gt4(i) else 0.0) for i in range(n)]
        # Qualifying: base pace plus a little luck; the grid follows the lap times.
        self.qual_time = [round(self.base_lap[i] - 1.2 + self.rng.uniform(0, 1.5), 3) for i in range(n)]
        self.qual_order = sorted(range(n), key=lambda i: self.qual_time[i])
        # Staggered grid in qualifying order (a race), or spread out on an
        # out lap from the pits (qualifying).
        self.progress = [0.0] * n
        for rank, i in enumerate(self.qual_order):
            self.progress[i] = -(rank * 0.006) if session == "race" else -0.95 + i * (0.9 / n)
        self.slow_until = [0.0] * n
        self.offtrack_until = [0.0] * n
        self.pit_until = [0.0] * n
        self.incidents = [0] * n
        self.lap_noise = [[1.0] * len(self.SECTOR_STARTS) for _ in range(n)]
        self.black_flag = [False] * n
        self.served = [False] * n
        self.pending_incidents = []  # (apply_at, car_idx, points)
        self.last_lap = [-1.0] * n
        self.best_lap = [-1.0] * n
        self.subsession_id = self.rng.randint(10_000_000, 99_999_999)
        # Races can end: the flag comes out when the leader completes
        # ``race_laps`` (0 = never). With ``retirements``, now and then a car
        # retires (leaves the world). ``out`` cars are not in the world.
        self.race_laps = race_laps
        self.retirements = retirements
        self.checkered = False
        self.out = [i >= n - no_shows for i in range(n)]  # the last ``no_shows`` never join
        self.done = [False] * n
        self.laps_led = [0] * n
        self.mock_laps = [0] * n
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
                "UserID": 100000 + i, "TeamName": MOCK_TEAMS[i % len(MOCK_TEAMS)], "CarNumber": num,
                "CarNumberRaw": int(num), "CarIsPaceCar": 0, "IsSpectator": 0,
                "CarScreenNameShort": "GT4" if self._is_gt4(i) else "GT3",
                "CarClassShortName": "GT4" if self._is_gt4(i) else "GT3",
                "CarClassID": 4084 if self._is_gt4(i) else 4083,
                "CarClassColor": 0x53FF77 if self._is_gt4(i) else 0xFFDA59, "IRating": 1500 + (self.num_cars - i) * 120,
                "LicString": "A 3.21", "CurDriverIncidentCount": 0, "TeamIncidentCount": 0,
                "CarDesignStr": self._design(),
                "HelmetDesignStr": self._design(),
                "CarNumberDesignStr": "0,0,ffffff,111111,000000",
            })
        return drivers

    def _results(self):
        """Race results the way iRacing publishes them (updated as laps complete)."""
        order = sorted(range(self.num_cars), key=lambda i: (-self.mock_laps[i], -self.progress[i]))
        return [{
            "Position": pos, "ClassPosition": pos - 1, "CarIdx": i + 1, "LapsComplete": self.mock_laps[i],
            "LapsLed": self.laps_led[i], "FastestTime": round(self.best_lap[i], 4) if self.best_lap[i] > 0 else -1,
            "Incidents": self.incidents[i],
            # iRacing keeps "Running" for a car that's parked but connected.
            "ReasonOutStr": "Disconnected" if self.out[i] and self.mock_laps[i] else "Running",
        } for pos, i in enumerate(order, start=1) if self.mock_laps[i] or not self.out[i]]

    def _design(self):
        """A random iRacing-style design string: pattern,colour1,colour2,colour3."""
        colors = self.rng.sample(MOCK_COLORS, 3)
        return f"{self.rng.randint(0, 20)},{colors[0]},{colors[1]},{colors[2]}"

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
            if self.out[i]:
                continue
            if self.retirements and self.session_kind == "race" and not self.checkered and t > 60 \
                    and rng.random() < dt / 2400.0:
                self.out[i] = True  # retired: towed, parked and left
                continue
            # Pace oscillates per car so cars trade places.
            pace = 1.0 + 0.02 * math.sin(t / 31.0 + self.phase[i])
            # Each lap and sector is a little different, so there are PBs to beat.
            sector = sum(1 for b in self.SECTOR_STARTS[1:] if self.progress[i] % 1.0 >= b)
            pace *= self.lap_noise[i][sector]
            if t < self.slow_until[i]:
                pace *= 0.15
            if t < self.pit_until[i]:
                pace *= 0.35
            prev = self.progress[i]
            self.progress[i] += dt / self.base_lap[i] * pace
            if self.session_kind == "qualify" and prev < 0 <= self.progress[i]:
                self.lap_start[i] = t  # out lap done: the first flying lap starts
            crossed = int(math.floor(self.progress[i])) > int(math.floor(prev))
            if self.race_laps and crossed and self.progress[i] >= self.race_laps:
                self.checkered = True  # the leader has done the distance
            just_done = self.checkered and crossed and not self.done[i]
            if just_done:
                self.done[i] = True  # took the flag
            if self.done[i]:
                pace *= 0.5  # cool-down lap
            if int(math.floor(self.progress[i])) > int(math.floor(prev)) and self.progress[i] >= 1:
                if not self.done[i] or just_done:  # laps stop counting after the flag
                    self.mock_laps[i] = int(math.floor(self.progress[i]))
                    if self.progress[i] >= max(self.progress) - 1e-9 and self.session_kind == "race":
                        self.laps_led[i] += 1
                self.info_update += 1  # results changed
                lap_time = t - self.lap_start[i]
                if self.lap_start[i] > 0:
                    self.last_lap[i] = lap_time
                    if self.best_lap[i] < 0 or lap_time < self.best_lap[i]:
                        self.best_lap[i] = lap_time
                self.lap_start[i] = t
                self.lap_noise[i] = [rng.uniform(0.985, 1.015) for _ in self.SECTOR_STARTS]
                if self.black_flag[i] and not self.served[i]:
                    # Serve the drive-through.
                    self.pit_until[i] = t + 18
                    self.served[i] = True
                elif rng.random() < 0.04 and t > 120:
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
                if self.incidents[i] >= 8 and not self.black_flag[i]:
                    self.black_flag[i] = True  # incident limit: drive-through
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
            laps_completed = [-1] * n
            pct = [-1.0] * n
            on_pit = [False] * n
            surface = [TRK_NOT_IN_WORLD] * n
            last_lap = [-1.0] * n
            best_lap = [-1.0] * n
            car_flags = [0] * n
            position = [0] * n
            f2 = [0.0] * n
            if self.session_kind == "race":
                order = sorted(range(self.num_cars), key=lambda i: -self.progress[i])
                leader = self.progress[order[0]]
                for rank, i in enumerate(order, start=1):
                    position[i + 1] = rank
                    f2[i + 1] = max(0.0, (leader - self.progress[i]) * 90.0)
            else:
                # Qualifying: ranked by best lap; no time, no position.
                timed = sorted((i for i in range(self.num_cars) if self.best_lap[i] > 0), key=lambda i: self.best_lap[i])
                for rank, i in enumerate(timed, start=1):
                    position[i + 1] = rank
            for i in range(self.num_cars):
                p = self.progress[i]
                idx = i + 1
                if self.out[i]:
                    continue  # not in the world: lap -1, pct -1
                lap[idx] = max(0, int(math.floor(p)) + 1) if p >= 0 else 0
                laps_completed[idx] = self.mock_laps[i]
                pct[idx] = p % 1.0
                # Qualifying starts with an out lap from the pit lane.
                on_pit[idx] = t < self.pit_until[i] or (self.session_kind == "qualify" and p < -0.9)
                if on_pit[idx]:
                    surface[idx] = TRK_APPROACHING_PITS
                elif t < self.offtrack_until[i]:
                    surface[idx] = TRK_OFF_TRACK
                else:
                    surface[idx] = TRK_ON_TRACK
                last_lap[idx] = self.last_lap[i]
                best_lap[idx] = self.best_lap[i]
                flags = FLAG_GREEN
                if self.black_flag[i] and not self.served[i]:
                    flags |= FLAG_BLACK
                elif self.incidents[i] >= 6 and not self.black_flag[i]:
                    flags |= FLAG_FURLED
                car_flags[idx] = flags
            live = self.replay_time is None
            return Frame(
                session_time=t,
                session_num=0,
                session_state=STATE_CHECKERED if self.checkered else STATE_RACING,
                session_flags=0,
                cam_car_idx=self.cam_car_idx,
                cam_group=self.cam_group,
                cam_state=self.cam_state,
                replay_frames_from_end=0 if live else int((t - self.replay_time) * 60),
                replay_session_time=t if live else self.replay_time,
                replay_session_num=0,
                replay_speed=self.replay_speed,
                session_time_remain=max(0.0, 1200.0 - t) if self.session_kind == "qualify" else 604800.0,
                session_laps_remain=max(0, self.race_laps - max(self.mock_laps)) if self.race_laps else 32767,
                lap=lap, laps_completed=laps_completed, pct=pct, position=position, class_position=list(position),
                on_pit=on_pit, surface=surface, f2_time=f2,
                last_lap=last_lap, best_lap=best_lap, car_flags=car_flags,
            )

    def session_info(self):
        with self._lock:
            info = {
                "WeekendInfo": {
                    "TrackDisplayName": "Mock Raceway", "TrackConfigName": "Grand Prix",
                    "TrackLength": f"{self.TRACK_LENGTH_KM:.2f} km", "EventType": "Race",
                    "SubSessionID": self.subsession_id,
                },
                "SessionInfo": {"Sessions": [{
                    "SessionNum": 0, "SessionType": "Race", "SessionName": "RACE",
                    "SessionLaps": str(self.race_laps or 30), "SessionTime": "unlimited",
                    "ResultsPositions": self._results(),
                } if self.session_kind == "race" else {
                    "SessionNum": 0, "SessionType": "Open Qualify", "SessionName": "QUALIFY",
                    "SessionLaps": "unlimited", "SessionTime": "1200.0000 sec",
                }]},
                "SplitTimeInfo": {"Sectors": [
                    {"SectorNum": n, "SectorStartPct": pct} for n, pct in enumerate(self.SECTOR_STARTS)
                ]},
                "DriverInfo": {"DriverCarIdx": 1, "Drivers": [dict(d) for d in self.drivers]},
                "QualifyResultsInfo": {"Results": [
                    {"Position": pos, "ClassPosition": pos, "CarIdx": i + 1, "FastestTime": self.qual_time[i]}
                    for pos, i in enumerate(self.qual_order)
                ] if self.session_kind == "race" else []},
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

    def cam_set_state(self, state):
        with self._lock:
            self.commands.append(("cam_set_state", state))
            self.cam_state = state

    def screenshot(self):
        """Write a picture of the car on camera, as iRacing's screenshot key would."""
        with self._lock:
            self.commands.append(("screenshot",))
            if self.screenshots_dir is None:
                return
            driver = self.drivers[self.cam_car_idx] if 0 <= self.cam_car_idx < len(self.drivers) else None
        from pathlib import Path
        folder = Path(self.screenshots_dir)
        folder.mkdir(parents=True, exist_ok=True)
        name = f"mock_{time.strftime('%Y%m%d_%H%M%S')}_{len(self.commands)}.png"
        (folder / name).write_bytes(mock_screenshot(driver))


def mock_screenshot(driver):
    """A stand-in for an iRacing screenshot: the camera car side-on, on track."""
    import io
    from PIL import Image, ImageDraw

    colors = ["#c0392b", "#f4f6f7", "#111111"]
    number = "?"
    if driver:
        parts = str(driver.get("CarDesignStr", "")).split(",")[1:4]
        colors = [f"#{c}" for c in parts if len(c) == 6] or colors
        number = str(driver.get("CarNumber", "?"))
    colors += ["#f4f6f7", "#111111"]
    img = Image.new("RGB", (1600, 900), "#9ec3e6")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 200, 1600, 300], fill="#6d8f4e")
    d.rectangle([0, 300, 1600, 900], fill="#4a4d52")
    for x in range(0, 1600, 100):
        d.rectangle([x, 300, x + 50, 318], fill="#d7263d")
    # A neighbouring car at the left edge, then the camera car in the middle.
    for x0, scale, body in ((-360, 0.75, "#1b76d1"), (380, 1.0, colors[0])):
        def P(x, y):
            return (x0 + x * scale, 330 + y * scale)
        d.polygon([P(0, 260), P(30, 150), P(250, 120), P(380, 40), P(640, 40), P(760, 130), P(860, 170), P(880, 260)],
                  fill=body, outline="#0b0b0b", width=6)
        d.polygon([P(400, 60), P(620, 60), P(700, 125), P(330, 125)], fill="#1d2633")
        d.rectangle([P(0, 200), P(880, 225)], fill=colors[1])
        for wx in (170, 700):
            cx, cy = P(wx, 265)
            d.ellipse([cx - 62 * scale, cy - 62 * scale, cx + 62 * scale, cy + 62 * scale], fill="#121212")
            d.ellipse([cx - 32 * scale, cy - 32 * scale, cx + 32 * scale, cy + 32 * scale], fill="#7d838c")
    d.ellipse([780, 470, 880, 570], fill="#ffffff", outline="#111111", width=4)
    d.text((812, 505), number, fill="#111111")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
