"""Race gaps from timing points, like the timing loops of a real circuit.

iRacing's own gap (``CarIdxF2Time``) only refreshes now and then for other
cars, so it sticks and lags behind the live running order. Instead, the
track is split into points about every 10 m. When a car passes one, the time
is noted (interpolated between telemetry samples). A car's gap to another car
is how long ago the other car was at the exact spot this one is at now (its
time there interpolated between points). It counts up while a car is slow or
stopped, and it always follows the order on track.

The passing times are kept for the whole session (a compact array per car),
and they're the race's own, so a replay of any part of the race, watched now
or after the flag, gets the same gaps as it had live. Watching a part not seen
live (the app started late) fills them in as it plays.
"""

import math
from array import array

POINT_SPACING_M = 10.0
MIN_POINTS, MAX_POINTS = 100, 1000
MAX_STEP_LAPS = 0.05   # a bigger jump in one sample is a tow / reset: no times for it
TIME_JUMP_S = 2.0      # a bigger jump in time (a replay skip): no times across it
# iRacing sends other cars' positions a few times a second, not every frame:
# in between, the same distance again. Up to this long, that's a car whose
# next position hasn't come in yet (not one that's stopped): it's put on at
# its pace, and its next move is spread over the whole time since it last moved.
STALE_S = 0.5
# A step back this small is iRacing correcting where it had put a car (not a
# car going backwards): it's let be, the car taken as where it had got to.
JITTER_LAPS = 0.02
NONE = float("nan")


class GapTimer:
    def __init__(self):
        self.points = MIN_POINTS
        self.reset()

    def reset(self):
        self._passed = {}     # car -> array of session times by point number (lap * points + point); NaN: not passed
        self._last = {}       # car -> (time, progress in laps): when it last moved on, and where to
        self._pace = {}       # car -> laps a second, lately
        self._prev_time = None
        self._session = None

    def set_track(self, track_m):
        points = int(min(MAX_POINTS, max(MIN_POINTS, (track_m or 0) / POINT_SPACING_M)))
        if points != self.points:
            self.points = points
            self.reset()

    def update(self, session, now, progress):
        """``progress``: {car: laps + lap distance} for cars on track (-1 or absent: not in the world).

        ``now`` is the time of what's on screen: live, or a replay (going back
        in time keeps what's been timed; it's the race's own)."""
        if session != self._session:
            self.reset()
            self._session = session
        elif self._prev_time is not None and (now < self._prev_time or now - self._prev_time > TIME_JUMP_S):
            self._last, self._pace = {}, {}  # a jump (a replay skip): just don't interpolate across it
        self._prev_time = now
        n = self.points
        for car, p in progress.items():
            if p is None or p < 0:
                self._last.pop(car, None)
                self._pace.pop(car, None)
                continue
            last = self._last.get(car)
            if last is None:
                self._last[car] = (now, p)
                continue
            t0, p0 = last
            if now <= t0:
                continue
            if p == p0 and now - t0 < STALE_S:
                continue  # its next position not in yet: still timed from when it last moved
            if p < p0 and p0 - p < JITTER_LAPS:
                continue  # iRacing correcting where it had it: as far as it had got
            self._last[car] = (now, p)
            if p <= p0 or p - p0 > MAX_STEP_LAPS:
                self._pace.pop(car, None)
                continue  # stopped, backwards, or teleported
            pace = (p - p0) / (now - t0)
            was = self._pace.get(car)
            self._pace[car] = pace if was is None else was + (pace - was) * 0.3
            first, end = math.floor(p0 * n) + 1, math.floor(p * n)
            if end < first:
                continue
            passed = self._passed.get(car)
            if passed is None:
                passed = self._passed[car] = array("d")
            if len(passed) <= end:
                passed.extend([NONE] * (end + 1 - len(passed) + n))  # room for the rest of this lap and the next
            for k in range(first, end + 1):
                if passed[k] != passed[k]:  # the first time it got there (not again after being put back)
                    passed[k] = t0 + (k / n - p0) / (p - p0) * (now - t0)

    def position(self, car, progress, now):
        """Where ``car`` is now, for its gap: ``progress`` as iRacing has it,
        but not behind where it had got to (iRacing correcting a little), and,
        while its next position hasn't come in yet, put on at its pace."""
        last = self._last.get(car)
        if last is None or progress is None or progress < 0:
            return progress
        t0, p0 = last
        if progress < p0 and p0 - progress < JITTER_LAPS:
            progress = p0
        if progress == p0 and 0 < now - t0 < STALE_S and car in self._pace:
            progress = p0 + self._pace[car] * (now - t0)
        return progress

    def line_time(self, car, lap):
        """When ``car`` crossed the line at ``lap`` (progress in whole laps: the
        point at the start of that lap), or None if it wasn't timed."""
        passed = self._passed.get(car)
        k = int(lap) * self.points
        if passed is None or not 0 <= k < len(passed):
            return None
        t = passed[k]
        return t if t == t else None

    def set_line_time(self, car, lap, t):
        """Note when ``car`` crossed the line at ``lap`` without seeing it go
        round: during a replay, from iRacing's results (its last lap time)."""
        k = int(lap) * self.points
        if k < 0:
            return
        passed = self._passed.get(car)
        if passed is None:
            passed = self._passed[car] = array("d")
        if len(passed) <= k:
            passed.extend([NONE] * (k + 1 - len(passed) + self.points))
        passed[k] = t

    def gap(self, car, ahead, progress, now):
        """Seconds ``car`` is behind ``ahead``: how long ago ``ahead`` was where
        ``car`` is now (``progress``: laps + lap distance, at time ``now``). None if unknown.

        Works for a replay of an earlier moment too: the times are the race's own.
        """
        theirs = self._passed.get(ahead)
        if theirs is None or progress is None or progress < 0:
            return None
        x = progress * self.points
        k = math.floor(x)

        def at(p):
            return theirs[p] if 0 <= p < len(theirs) and theirs[p] == theirs[p] else None  # NaN: not passed

        # A point can be missing (a lap counter glitch at the line; the stretch
        # it went round while a replay was on, with nothing timed): the time
        # there is taken between the nearest points timed either side, up to a
        # lap away, at its pace across them (rather than no gap, which fell
        # back to an estimate and made the gaps jump about after each replay).
        before = next((p for p in range(k, max(-1, k - self.points), -1) if at(p) is not None), None)
        after = next((p for p in range(k + 1, k + 1 + self.points) if at(p) is not None), None)
        if before is None or (k - before >= 5 and after is None):
            return None
        t = at(before)
        if after is not None:
            t += (at(after) - t) * (x - before) / (after - before)
        if t > now + 0.5:
            return None  # they got there later than this moment: timed from further on in the replay
        return max(0.0, now - t)
