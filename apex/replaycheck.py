"""What iRacing sends while a replay is on screen during a race.

iRacing's telemetry in a replay: the session clock (SessionTime) goes on
live, but which of the per-car values (where each car is, places, gaps)
are the live race's and which the replay's isn't the same everywhere. Two
things here find out:

* ``ReplayProbe`` watches for it by itself: while a replay is *paused* the
  replay's cars stand still, so cars on track still moving round the lap
  mean iRacing's car data is the live race's (the app can then time gaps
  and intervals live during replays); cars standing still while the clock
  runs mean it's the replay's (the app times them at the line, lap by lap).
* ``ReplayCheck`` writes the values that tell, once a second, to a CSV file
  (the test: is SessionTime advancing, IsReplayPlaying true, are positions
  and flags still updating, is the replay frame moving on?), for a look
  afterwards.
"""

import csv
import json
import time
from pathlib import Path

ON_TRACK = 3          # iRacing TrackSurface: on track
LIVE_AFTER_S = 2.0    # cars moving this long with the replay paused: live
REPLAY_AFTER_S = 3.0  # cars standing still this long with the replay paused (the clock running): the replay's


def _moved(a, b):
    """How far round the lap between two lap distances (0-1), across the line too."""
    d = abs(a - b)
    return min(d, 1.0 - d)


class ReplayProbe:
    """Whether iRacing's car data is live while a replay is on screen: "live",
    "replay", or None (not seen yet). Fed every frame; only a paused replay
    during a race (the live clock running) tells."""

    def __init__(self):
        self.verdict = None
        self.reset()

    def reset(self):
        self._last = None          # (session time, {car: lap distance}) of the last paused frame
        self._moving_s = 0.0       # time with the replay paused and cars moving
        self._still_s = 0.0        # time with the replay paused and every car still

    def update(self, frame, racing):
        """``racing``: a race under way (green or chequered) in the session on now."""
        if frame.is_live or not racing or frame.replay_speed != 0:
            self._last = None
            return self.verdict
        on_track = {idx: p for idx, (p, s) in enumerate(zip(frame.pct, frame.surface))
                    if s == ON_TRACK and p is not None and p >= 0}
        last, self._last = self._last, (frame.session_time, on_track)
        if not last or not on_track:
            return self.verdict
        dt = frame.session_time - last[0]
        if dt <= 0 or dt > 1.0:
            return self.verdict  # the sim paused, or a gap in the frames: nothing to tell
        both = [idx for idx in on_track if idx in last[1]]
        if not both:
            return self.verdict
        moving = sum(1 for idx in both if _moved(on_track[idx], last[1][idx]) > 1e-5)
        if moving >= max(1, len(both) // 2):
            self._moving_s += dt
            self._still_s = 0.0
        elif moving == 0:
            self._still_s += dt
            self._moving_s = 0.0
        if self._moving_s >= LIVE_AFTER_S:
            self.verdict = "live"
        elif self._still_s >= REPLAY_AFTER_S:
            self.verdict = "replay"
        return self.verdict


# The values the check writes, a column each (per-car ones as JSON lists).
COLUMNS = ("wall_time", "SessionTime", "SessionNum", "SessionState", "SessionFlags", "IsReplayPlaying",
           "ReplayFrameNum", "ReplayFrameNumEnd", "ReplaySessionTime", "ReplaySessionNum", "ReplayPlaySpeed",
           "CamCarIdx", "CarIdxPosition", "CarIdxClassPosition", "CarIdxLap", "CarIdxLapCompleted",
           "CarIdxLapDistPct", "CarIdxF2Time", "CarIdxEstTime", "CarIdxLastLapTime", "CarIdxOnPitRoad",
           "CarIdxTrackSurface")


class ReplayCheck:
    """The replay data check: once a second, iRacing's values that show what's
    live during a replay, written to a CSV file (one row a second)."""

    def __init__(self, folder, clock=time.time):
        self.folder = Path(folder)
        self.clock = clock
        self.path = None
        self.rows = 0
        self._file = None
        self._writer = None
        self._next = 0.0
        self._cars = []  # the cars in it (car_idx), the per-car lists cut to them

    @property
    def on(self):
        return self._file is not None

    def start(self, cars=()):
        self.stop()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / time.strftime("replay-check-%Y%m%d-%H%M%S.csv", time.localtime(self.clock()))
        self._file = open(self.path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(COLUMNS)
        self._file.flush()
        self.rows, self._next = 0, 0.0
        self._cars = sorted(cars)
        return self.path

    def stop(self):
        if self._file is not None:
            self._file.close()
        self._file = self._writer = None

    def write(self, frame, cars=None):
        """A row, if a second has gone by since the last (``cars``: the car_idx in the session)."""
        if self._file is None:
            return False
        now = self.clock()
        if now < self._next:
            return False
        self._next = now + 1.0
        if cars:
            self._cars = sorted(set(self._cars) | set(cars))

        def cut(values, digits=None):
            out = [values[i] if i < len(values) else None for i in self._cars]
            return json.dumps([round(v, digits) if digits is not None and isinstance(v, float) else v for v in out])

        self._writer.writerow([
            time.strftime("%H:%M:%S", time.localtime(now)), round(frame.session_time, 3), frame.session_num,
            frame.session_state, frame.session_flags, int(bool(frame.is_replay_playing)), frame.replay_frame_num,
            frame.replay_frames_from_end, round(frame.replay_session_time, 3), frame.replay_session_num,
            frame.replay_speed, frame.cam_car_idx,
            cut(frame.position), cut(frame.class_position), cut(frame.lap), cut(frame.laps_completed),
            cut(frame.pct, 5), cut(frame.f2_time, 3), cut(frame.est_time, 3), cut(frame.last_lap, 3),
            cut([int(bool(x)) for x in frame.on_pit]), cut(frame.surface),
        ])
        self._file.flush()
        self.rows += 1
        return True
