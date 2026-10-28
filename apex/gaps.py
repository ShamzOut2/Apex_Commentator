"""Race gaps from timing points, like the timing loops of a real circuit.

iRacing's own gap (``CarIdxF2Time``) only refreshes now and then for other
cars, so it sticks and lags behind the live running order. Instead, the
track is split into points about every 10 m. When a car passes one, the time
is noted (interpolated between telemetry samples). A car's gap to another car
is how long ago the other car was at the exact spot this one is at now (its
time there interpolated between points). It counts up while a car is slow or
stopped, and it always follows the order on track.
"""

import math

POINT_SPACING_M = 10.0
MIN_POINTS, MAX_POINTS = 100, 1000
KEEP_LAPS = 3          # passing times kept per car (enough to time lapped cars)
MAX_STEP_LAPS = 0.05   # a bigger jump in one sample is a tow / reset: no times for it
TIME_JUMP_S = 2.0      # a bigger jump in time (back from a replay): no times across it


class GapTimer:
    def __init__(self):
        self.points = MIN_POINTS
        self.reset()

    def reset(self):
        self._passed = {}     # car -> {point number: session time}, point number = lap * points + point
        self._last = {}       # car -> (time, progress in laps)
        self._prev_time = None
        self._session = None

    def set_track(self, track_m):
        points = int(min(MAX_POINTS, max(MIN_POINTS, (track_m or 0) / POINT_SPACING_M)))
        if points != self.points:
            self.points = points
            self.reset()

    def update(self, session, now, progress):
        """``progress``: {car: laps + lap distance} for cars on track (-1 or absent: not in the world)."""
        if session != self._session or (self._prev_time is not None and now < self._prev_time):
            self.reset()
            self._session = session
        elif self._prev_time is not None and now - self._prev_time > TIME_JUMP_S:
            self._last = {}  # times already noted stay right; just don't interpolate across the gap
        self._prev_time = now
        n = self.points
        for car, p in progress.items():
            if p is None or p < 0:
                self._last.pop(car, None)
                continue
            last = self._last.get(car)
            self._last[car] = (now, p)
            if last is None:
                continue
            t0, p0 = last
            if p <= p0 or p - p0 > MAX_STEP_LAPS or now <= t0:
                continue  # stopped, backwards, or teleported
            passed = self._passed.setdefault(car, {})
            first, end = math.floor(p0 * n) + 1, math.floor(p * n)
            for k in range(first, end + 1):
                passed[k] = t0 + (k / n - p0) / (p - p0) * (now - t0)
            if end >= first and len(passed) > (KEEP_LAPS + 1) * n:
                for k in [k for k in passed if k < end - KEEP_LAPS * n]:
                    del passed[k]

    def gap(self, car, ahead, progress, now):
        """Seconds ``car`` is behind ``ahead``: how long ago ``ahead`` was where
        ``car`` is now (``progress``: laps + lap distance, at time ``now``). None if unknown.

        Works for a replay of an earlier moment too: the times are the race's own.
        """
        theirs = self._passed.get(ahead)
        if not theirs or progress is None or progress < 0:
            return None
        x = progress * self.points
        k = math.floor(x)
        # A point can be missing (e.g. a lap counter glitch at the line): look a little either side.
        before = next((p for p in range(k, k - 5, -1) if p in theirs), None)
        after = next((p for p in range(k + 1, k + 6) if p in theirs), None)
        if before is None:
            return None
        t = theirs[before]
        if after is not None:
            t += (theirs[after] - theirs[before]) * (x - before) / (after - before)
        return max(0.0, now - t)
