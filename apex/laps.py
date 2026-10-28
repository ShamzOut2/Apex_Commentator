"""Lap and sector timing, for the qualifying tracker and standings.

iRacing only reports whole lap times, so sector splits are timed here from
each car's lap distance (``CarIdxLapDistPct``) crossing the sector starts
in the session's ``SplitTimeInfo``, interpolated between samples.

A lap is timed only from a start/finish crossing out on track: out laps from
the pits aren't timed, and a lap is marked invalid if the car goes off track,
returns to the pits or the data jumps (a tow or a replay skip). Bests (per car
and per class) only take valid laps and sectors.

Sector colours are worked out when each sector completes, against both
references, so the commentator can switch between them live:

* ``personal``: the driver's own best before this lap.
* ``session``: the fastest in the driver's class this session.

Faster than (or equal to) the reference is purple, within ``green_s`` is green,
anything slower is yellow. With no reference yet, it's purple.
"""

from .sources import TRK_NOT_IN_WORLD, TRK_OFF_TRACK

MAX_STEP_PCT = 0.25    # more than this between samples: the data skipped
TIME_JUMP_S = 2.0
LAST_LAP_ADOPT_S = 3.0  # how long to wait for iRacing's own lap time
DEFAULT_SECTORS = (0.0, 1 / 3, 2 / 3)


def sector_starts(info):
    """Sector start points (0..1, first is 0) from session info."""
    sectors = ((info or {}).get("SplitTimeInfo") or {}).get("Sectors") or []
    starts = sorted({float(s.get("SectorStartPct", 0) or 0) for s in sectors if isinstance(s, dict)})
    starts = [p for p in starts if 0.0 <= p < 1.0]
    if not starts or starts[0] != 0.0:
        starts = [0.0] + starts
    return tuple(starts) if len(starts) > 1 else DEFAULT_SECTORS


def colour(time, reference, green_s):
    if reference is None or time <= reference + 1e-4:
        return "purple"
    return "green" if time <= reference + green_s + 1e-4 else "yellow"


def _between(a, b, x):
    """True if x lies in (a, b] going forwards round the lap from a to b."""
    if a <= b:
        return a < x <= b
    return x > a or x <= b


class _Car:
    def __init__(self):
        self.pct = None
        self.t = None
        self.lap = None          # the lap being timed, or None
        self.last = None         # the last completed lap
        self.best_lap = None
        self.best_sectors = []   # personal best per sector (valid only)
        self.laps = 0            # completed timed laps
        self.iracing_last = None


class LapTracker:
    def __init__(self, green_s=0.2):
        self.green_s = green_s
        self.starts = DEFAULT_SECTORS
        self.session = None
        self.cars = {}
        self.class_best = {}     # class key -> {"lap": t, "sectors": [..]}

    def reset(self, session=None):
        self.session = session
        self.cars = {}
        self.class_best = {}

    def set_sectors(self, starts):
        starts = tuple(starts)
        if starts != self.starts:
            self.starts = starts
            for c in self.cars.values():
                c.lap = None
                c.best_sectors = []
                c.last = None
            for b in self.class_best.values():
                b["sectors"] = []

    # -- updates ------------------------------------------------------------

    def update(self, frame, class_of):
        """Feed one frame (on the session timeline). ``class_of(car_idx)`` -> class key."""
        if frame.session_num != self.session:
            self.reset(frame.session_num)
        t = frame.session_time
        for idx in range(len(frame.pct)):
            pct = frame.pct[idx]
            surface = frame.surface[idx] if idx < len(frame.surface) else TRK_NOT_IN_WORLD
            car = self.cars.get(idx)
            if pct is None or pct < 0 or surface == TRK_NOT_IN_WORLD:
                if car:
                    car.pct = car.t = None
                    car.lap = None
                continue
            if car is None:
                car = self.cars[idx] = _Car()
            self._step(idx, car, t, pct, frame, class_of)

    def _step(self, idx, car, t, pct, frame, class_of):
        on_pit = bool(frame.on_pit[idx]) if idx < len(frame.on_pit) else False
        surface = frame.surface[idx]
        prev_pct, prev_t = car.pct, car.t
        car.pct, car.t = pct, t
        iracing_before, car.iracing_last = car.iracing_last, _value(frame.last_lap, idx)
        self._time_lap(idx, car, t, pct, prev_pct, prev_t, on_pit, surface, iracing_before, class_of)
        self._adopt_iracing_time(idx, car, t, class_of)

    def _time_lap(self, idx, car, t, pct, prev_pct, prev_t, on_pit, surface, iracing_before, class_of):
        if prev_pct is None:
            return
        dt = t - prev_t
        forward = (pct - prev_pct) % 1.0
        if dt <= 0:
            return
        if dt > TIME_JUMP_S or forward > MAX_STEP_PCT:
            car.lap = None  # skipped: the timing can't be trusted
            return
        lap = car.lap
        if lap is not None and (on_pit or surface == TRK_OFF_TRACK):
            lap["valid"] = False
            if on_pit:
                car.lap = lap = None  # in lap: stop timing
        # Crossings in order round the lap from prev_pct to pct.
        crossings = []
        for n, start in enumerate(self.starts):
            if _between(prev_pct, pct, start):
                dist = (start - prev_pct) % 1.0
                crossings.append((dist, n, prev_t + dt * (dist / forward if forward else 1.0)))
        for _, n, when in sorted(crossings):
            if n == 0:
                if car.lap is not None:
                    self._finish_lap(idx, car, when, iracing_before, class_of)
                car.lap = None if on_pit else {
                    "start": when, "splits": [], "valid": True, "colours": [],
                    "ref_lap": car.best_lap, "ref_sectors": list(car.best_sectors),
                }
            elif car.lap is not None and len(car.lap["splits"]) == n - 1:
                self._finish_sector(idx, car, when, class_of)

    def _finish_sector(self, idx, car, when, class_of):
        lap = car.lap
        n = len(lap["splits"])
        start = lap["start"] + sum(lap["splits"])
        sector = round(when - start, 3)
        lap["splits"].append(sector)
        best = self.class_best.setdefault(class_of(idx), {"lap": None, "sectors": []})
        ref_p = lap["ref_sectors"][n] if n < len(lap["ref_sectors"]) else None
        ref_s = best["sectors"][n] if n < len(best["sectors"]) else None
        lap["colours"].append({
            "personal": colour(sector, ref_p, self.green_s),
            "session": colour(sector, ref_s, self.green_s),
        })
        if lap["valid"]:
            _keep_best(car.best_sectors, n, sector)
            _keep_best(best["sectors"], n, sector)

    def _finish_lap(self, idx, car, when, iracing_before, class_of):
        lap = car.lap
        if len(lap["splits"]) != len(self.starts) - 1:
            return  # missed a sector (joined mid-lap)
        self._finish_sector(idx, car, when, class_of)
        lap_time = round(when - lap["start"], 3)
        car.laps += 1
        car.last = {
            "lap_time": lap_time, "sectors": list(lap["splits"]), "colours": lap["colours"],
            "valid": lap["valid"], "ref_lap": lap["ref_lap"], "finished": when, "number": car.laps,
            "iracing_before": iracing_before,
        }
        if lap["valid"]:
            self._record_best(idx, car, lap_time, class_of)

    def _record_best(self, idx, car, lap_time, class_of):
        if car.best_lap is None or lap_time < car.best_lap:
            car.best_lap = lap_time
        best = self.class_best.setdefault(class_of(idx), {"lap": None, "sectors": []})
        if best["lap"] is None or lap_time < best["lap"]:
            best["lap"] = lap_time

    def _adopt_iracing_time(self, idx, car, t, class_of):
        """iRacing's own lap time is exact: use it when it arrives soon after the line."""
        last = car.last
        if not last or "iracing_before" not in last or t - last["finished"] > LAST_LAP_ADOPT_S:
            if last:
                last.pop("iracing_before", None)
            return
        value = car.iracing_last
        if value is None or value == last["iracing_before"] or abs(value - last["lap_time"]) > 0.5:
            return
        del last["iracing_before"]
        value = round(value, 3)
        diff = value - last["lap_time"]
        last["lap_time"] = value
        last["sectors"][-1] = round(last["sectors"][-1] + diff, 3)
        if last["valid"]:
            estimate = value - diff
            if car.best_lap is not None and abs(car.best_lap - estimate) < 1e-6:
                car.best_lap = last["ref_lap"]  # it was the best: re-record with the exact time
            best = self.class_best.get(class_of(idx))
            if best and best["lap"] is not None and abs(best["lap"] - estimate) < 1e-6:
                best["lap"] = value
            self._record_best(idx, car, value, class_of)
            # The next lap started on the line with the estimate as its target.
            if car.lap is not None and car.lap["ref_lap"] is not None and abs(car.lap["ref_lap"] - estimate) < 1e-6:
                car.lap["ref_lap"] = car.best_lap

    # -- output -------------------------------------------------------------

    def best(self, idx):
        car = self.cars.get(idx)
        return car.best_lap if car else None

    def state(self, idx, now, reference="personal", hide_s=5.0):
        """What the tracker shows for a car, or None (not on a timed lap)."""
        car = self.cars.get(idx)
        if car is None:
            return None
        last = car.last
        nsec = len(self.starts)
        if last and now - last["finished"] <= hide_s:
            prev = last["ref_lap"]
            return {
                "state": "finished",
                "sectors": [{"time": s, "colour": c[reference], "done": 1.0}
                            for s, c in zip(last["sectors"], last["colours"])],
                "lap_time": last["lap_time"],
                "elapsed": last["lap_time"],
                "valid": last["valid"],
                "previous": prev,
                "delta": round(last["lap_time"] - prev, 3) if prev is not None else None,
                "best": car.best_lap,
                "shown_for": round(now - last["finished"], 2),
            }
        lap = car.lap
        if lap is None:
            return None
        sectors = [{"time": s, "colour": c[reference], "done": 1.0} for s, c in zip(lap["splits"], lap["colours"])]
        n = len(sectors)
        if n < nsec:
            lo = self.starts[n]
            hi = self.starts[n + 1] if n + 1 < len(self.starts) else 1.0
            progress = ((car.pct - lo) % 1.0) / (hi - lo) if hi > lo else 0.0
            sectors.append({"time": None, "colour": None, "done": round(min(max(progress, 0.0), 0.99), 3)})
        sectors += [{"time": None, "colour": None, "done": 0.0} for _ in range(nsec - len(sectors))]
        return {
            "state": "running",
            "sectors": sectors,
            "lap_time": None,
            "elapsed": round(now - lap["start"], 3),
            "valid": lap["valid"],
            "previous": car.best_lap,
            "delta": None,
            "best": car.best_lap,
            "progress": round(car.pct % 1.0, 4),
        }


def _keep_best(seq, n, value):
    while len(seq) <= n:
        seq.append(None)
    if seq[n] is None or value < seq[n]:
        seq[n] = value


def _value(seq, idx):
    v = seq[idx] if idx < len(seq) else None
    return v if v and v > 0 else None
