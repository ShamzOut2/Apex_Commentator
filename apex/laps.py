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
* ``overall``: the fastest of anyone this session, whatever their class.

Faster than (or equal to) the reference is purple, within ``green_s`` is green,
anything slower is yellow. With no reference yet, it's purple.

A purple sector against the class or overall best turns green once someone
else (in the class / anyone) goes faster through it: it's no longer the
fastest. A sector only counts towards the bests while its lap is clean: a lap
that's invalidated (off track) takes its sectors out of the bests again.
"""

from .sources import TRK_NOT_IN_WORLD, TRK_OFF_TRACK

MAX_STEP_PCT = 0.25    # more than this between samples: the data skipped
# iRacing's position for other cars (smoothed over the network) can step back
# a little now and then; a step back up to this much is that, not a skip.
JITTER_PCT = 0.02
LOG_DROPS = 10  # dropped laps written to the log, a session
# A car's own gap between samples longer than this: the timing can't be
# trusted (the app missed that much). Short hiccups (the app busy for a
# second or two) are fine: crossings in between are interpolated.
TIME_JUMP_S = 10.0
# The whole timeline jumping back this much (a replay rewound) or forward
# (skipped ahead): laps being timed are dropped and timing starts again.
REWIND_S = 0.5
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


def group_sectors(starts, count):
    """Merge a track's split points into ``count`` sectors (0 = keep them all).

    iRacing often splits a lap into many short sections; broadcasts show
    three. The boundaries kept are the split points nearest to equal thirds
    (or halves, quarters...) of the lap.
    """
    starts = tuple(starts)
    if count <= 0 or len(starts) <= count:
        return starts
    inner = list(starts[1:])
    chosen = []
    for k in range(1, count):
        target = k / count
        pick = min((p for p in inner if p not in chosen and (not chosen or p > chosen[-1])),
                   key=lambda p: abs(p - target), default=None)
        if pick is not None:
            chosen.append(pick)
    return (0.0, *chosen)


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
        self.best_sectors = []   # personal best per sector, from its clean laps done (the lap on now counts separately)
        self.laps = 0            # completed timed laps
        self.iracing_last = None
        self.lap_no = None       # iRacing's lap number for the car (CarIdxLap), last seen
        self.cls = None          # its class key


class LapTracker:
    def __init__(self, green_s=0.2):
        self.green_s = green_s
        self.starts = DEFAULT_SECTORS
        self.session = None
        self.cars = {}
        self.class_best = {}     # class key -> {"lap": t} (sector bests: sector_best())
        self.overall_best = {"lap": None}  # anyone's, whatever the class
        self._logged = 0         # dropped laps logged this session
        self._t = None           # the timeline's time last fed

    def reset(self, session=None):
        self.session = session
        self._logged = 0
        self._t = None
        self.cars = {}
        self.class_best = {}
        self.overall_best = {"lap": None}

    def set_sectors(self, starts):
        starts = tuple(starts)
        if starts != self.starts:
            self.starts = starts
            for c in self.cars.values():
                c.lap = None
                c.best_sectors = []
                c.last = None

    # -- updates ------------------------------------------------------------

    def update(self, frame, class_of):
        """Feed one frame (on the session timeline). ``class_of(car_idx)`` -> class key."""
        if frame.session_num != self.session:
            self.reset(frame.session_num)
        t = frame.session_time
        if self._t is not None and (t < self._t - REWIND_S or t > self._t + TIME_JUMP_S):
            # A replay rewound or skipped: what was being timed no longer
            # follows on. Bests are kept; laps start again from the next line.
            for c in self.cars.values():
                c.pct = c.t = c.lap = c.lap_no = None
                c.last = None
        self._t = t
        for idx in range(len(frame.pct)):
            pct = frame.pct[idx]
            surface = frame.surface[idx] if idx < len(frame.surface) else TRK_NOT_IN_WORLD
            car = self.cars.get(idx)
            if pct is None or pct < 0 or surface == TRK_NOT_IN_WORLD:
                if car:
                    car.pct = car.t = None
                    self._close(car)
                continue
            if car is None:
                car = self.cars[idx] = _Car()
            self._step(idx, car, t, pct, frame, class_of)

    def _step(self, idx, car, t, pct, frame, class_of):
        car.cls = class_of(idx)
        on_pit = bool(frame.on_pit[idx]) if idx < len(frame.on_pit) else False
        surface = frame.surface[idx]
        prev_pct, prev_t = car.pct, car.t
        if prev_pct is not None and 0.0 < (prev_pct - pct) % 1.0 < JITTER_PCT:
            # A hair backwards: the car hasn't really moved back. Keep its
            # furthest position (and the time it got there) and carry on.
            car.iracing_last = _value(frame.last_lap, idx)
            self._adopt_iracing_time(idx, car, t, class_of)
            return
        car.pct, car.t = pct, t
        iracing_before, car.iracing_last = car.iracing_last, _value(frame.last_lap, idx)
        had_lap = car.lap
        self._time_lap(idx, car, t, pct, prev_pct, prev_t, on_pit, surface, iracing_before, class_of)
        # iRacing's own lap counter ticking over is a crossing of the line
        # too: a car whose lap isn't being timed (the crossing was missed:
        # the app joined, a hiccup, a skip) starts one there, out on track.
        lap_seq = getattr(frame, "lap", None) or []
        lap_no = lap_seq[idx] if idx < len(lap_seq) else None
        if lap_no is not None and lap_no >= 0:
            if (car.lap is None and had_lap is None and car.lap_no is not None and lap_no > car.lap_no
                    and not on_pit and surface != TRK_OFF_TRACK):
                car.lap = {"start": t, "splits": [], "valid": True, "colours": [],
                           "ref_lap": car.best_lap, "ref_sectors": list(car.best_sectors)}
            car.lap_no = lap_no
        self._adopt_iracing_time(idx, car, t, class_of)

    def _time_lap(self, idx, car, t, pct, prev_pct, prev_t, on_pit, surface, iracing_before, class_of):
        if prev_pct is None:
            return
        dt = t - prev_t
        forward = (pct - prev_pct) % 1.0
        if dt <= 0:
            return
        if dt > TIME_JUMP_S or forward > MAX_STEP_PCT:
            if car.lap is not None and self._logged < LOG_DROPS:
                # Shown in apex.log (a few a session): why a car's timed lap stopped.
                self._logged += 1
                print(f"[apex] lap timing: car {idx}'s lap dropped (lap position {prev_pct:.4f} -> {pct:.4f} "
                      f"in {dt:.2f} s)")
            self._close(car)  # skipped: the timing can't be trusted from here
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
        ref_p = lap["ref_sectors"][n] if n < len(lap["ref_sectors"]) else None
        # Against the bests as they stand (this sector isn't in them yet).
        ref_s = self.sector_best(n, car.cls)
        ref_o = self.sector_best(n)
        lap["splits"].append(sector)
        lap["colours"].append({
            "personal": colour(sector, ref_p, self.green_s),
            "session": colour(sector, ref_s, self.green_s),
            "overall": colour(sector, ref_o, self.green_s),
        })

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
        self._close(car)

    def _close(self, car):
        """The lap being timed is over (finished, or dropped): if it's clean,
        its sectors go into the car's bests for good; if not, they're gone."""
        lap, car.lap = car.lap, None
        if lap is not None and lap["valid"]:
            for n, s in enumerate(lap["splits"]):
                _keep_best(car.best_sectors, n, s)

    def sector_best(self, n, cls=None):
        """The fastest sector ``n`` this session, of class ``cls`` (None: anyone):
        from clean laps done, and the laps on now while they're clean."""
        best = None
        for c in self.cars.values():
            if cls is not None and c.cls != cls:
                continue
            mine = c.best_sectors[n] if n < len(c.best_sectors) else None
            lap = c.lap
            if lap is not None and lap["valid"] and n < len(lap["splits"]):
                mine = lap["splits"][n] if mine is None else min(mine, lap["splits"][n])
            if mine is not None and (best is None or mine < best):
                best = mine
        return best

    def _now_colour(self, car, n, time, colours, reference, valid):
        """A finished sector's colour now, against the class or overall best as
        it stands: a purple someone has since beaten is green; on a clean lap,
        a sector that's become the fastest (the faster one was on a lap that
        got invalidated) is purple."""
        col = colours.get(reference, colours["personal"])
        if reference in ("session", "overall"):
            best = self.sector_best(n, car.cls if reference == "session" else None)
            if best is not None and best < time - 1e-4:
                return "green" if col == "purple" else col
            if valid and best is not None and time <= best + 1e-4:
                return "purple"
        return col

    def _record_best(self, idx, car, lap_time, class_of):
        if car.best_lap is None or lap_time < car.best_lap:
            car.best_lap = lap_time
        best = self.class_best.setdefault(class_of(idx), {"lap": None, "sectors": []})
        if best["lap"] is None or lap_time < best["lap"]:
            best["lap"] = lap_time
        if self.overall_best["lap"] is None or lap_time < self.overall_best["lap"]:
            self.overall_best["lap"] = lap_time

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
        n = len(last["sectors"]) - 1
        old_sector = last["sectors"][-1]
        last["sectors"][-1] = round(old_sector + diff, 3)
        if last["valid"] and n < len(car.best_sectors) and car.best_sectors[n] is not None \
                and abs(car.best_sectors[n] - old_sector) < 1e-6:
            car.best_sectors[n] = last["sectors"][-1]  # the best was the estimate: now exact
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
                "sectors": [{"time": s, "colour": self._now_colour(car, n, s, c, reference, last["valid"]), "done": 1.0}
                            for n, (s, c) in enumerate(zip(last["sectors"], last["colours"]))],
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
        sectors = [{"time": s, "colour": self._now_colour(car, n, s, c, reference, lap["valid"]), "done": 1.0}
                   for n, (s, c) in enumerate(zip(lap["splits"], lap["colours"]))]
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
