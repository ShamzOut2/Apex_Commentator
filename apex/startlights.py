"""The starting lights overlay's state: how many red lights are lit, and lights out.

Three ways the lights count down, all ending with the race going green:

- iRacing's own start lights (a standing start): its Ready flag starts the
  count, a light every ``step`` seconds; Set has them all lit; Go is lights out.
- A rolling start: once the pace car pulls into the pits (its last lap), a
  light every ``step`` seconds from then, held lit until the green: wherever
  iRacing waves it (on an oval, a restart point well before the line). With
  no pace car seen, iRacing's "one lap to green": the lights come on one a
  step as the leader gets within that many steps of the line (its speed).
  While the pace car's out leading the field it's never the green, whatever
  iRacing's flags say (it can say "racing" with no caution out then); and if
  they said so then, they can't tell the green either: it's the leader
  crossing the line.
- By hand (a hotkey): a light every step from the press.

Once all are lit they stay lit until the green. The green is iRacing's Go,
or the race running with no caution or pace-lap flag out (the session can
already be "racing" behind the pace car). Lights out shows for ``out_s``
seconds, then the overlay goes. Nothing shows outside a race's start, after
its first green (no lights at restarts), or for a green it didn't count
down to (the app started mid-race).
"""

import math

START_READY = 0x20000000
START_SET = 0x40000000
START_GO = 0x80000000
ONE_LAP_TO_GREEN = 0x0200
CAUTION = 0x0008 | 0x0100 | 0x4000 | 0x8000   # yellow, yellow waving, caution, caution waving
PARADE, RACING = 3, 4                          # iRacing's session states


def is_green(state, flags):
    """The race under way: iRacing's Go, or racing with no caution or pace flag."""
    return bool(flags & START_GO) or (state >= RACING and not flags & (CAUTION | ONE_LAP_TO_GREEN))


class StartLights:
    def __init__(self):
        self._key = None
        self.reset()

    def reset(self):
        self._manual = None   # session time of the hotkey press
        self._ready = None    # session time iRacing's Ready flag came up
        self._go = None       # session time of the green
        self._green = False   # the race has gone green (no more counts by themselves)
        self._peak = 0        # lights lit so far (never fewer until the green)
        self._seen = False    # a count shown (so lights out follows)
        self._last = None     # (t, leader progress) for its speed
        self._rate = None     # the leader's laps a second
        self._pitted = None   # session time the pace car pulled in (the last pace lap)
        self._flags_lie = False  # iRacing's flags said "green" behind the pace car: no use for the green
        self._line = None     # the leader's lap + 1 as the pace car pulled in: the line the green's at then
        self.source = None    # what started the count shown: "hand", "standing", "rolling"

    def count(self, t):
        """The hotkey: start counting now (again, from the first light)."""
        self._manual = t
        self._peak = 0
        self._pitted = None
        self._line = None  # (the green at the next line, if it's by the line)
        self._go = None
        self._green = False

    def update(self, key, t, *, race, state, flags, leader, final_lap=False, pace_leading=False, auto="all", lights=5, step=1.0,
               out_s=3.0):
        """The lights now: None (not on screen) or {"lit", "lights", "out"}.
        ``key`` is the session (a new one starts afresh); ``state`` / ``flags``
        iRacing's session state and flags; ``leader``: the leading car's progress
        (laps + lap fraction) or None; ``final_lap``: the last pace lap of a
        rolling start (the pace car's in the pits); ``pace_leading``: the pace
        car's out on track in front of the field (not the green yet)."""
        if key != self._key:
            first, self._key = self._key is None, key
            if not first:  # a new session (a press before the first look kept)
                self.reset()
        if not race:
            return None
        green = is_green(state, flags)
        if pace_leading and not flags & START_GO:
            self._flags_lie = self._flags_lie or green
            green = False
        if final_lap and leader is not None and self._line is None:
            self._line = math.floor(leader) + 1
        elif not final_lap:
            self._line = None
        if final_lap and self._flags_lie and not flags & START_GO:
            green = leader is not None and self._line is not None and leader >= self._line
        if green:
            if self._go is None:
                self._go = t
            self._green = True
            self._manual = None
            if self._seen and 0 <= t - self._go < out_s:
                return {"lit": 0, "lights": lights, "out": True}
            return None
        self._go = None
        if self._green and self._manual is None:
            return None  # a caution after the start: no lights at the restart
        phase = None  # steps since the count started (lit = floor of it)
        if self._manual is not None and t >= self._manual:
            phase = (t - self._manual) / step
            self.source = self.source or "hand"
        if auto in ("all", "standing") and not self._green:
            if flags & START_SET:
                phase = lights
                self.source = self.source or "standing"
            elif flags & START_READY:
                self._ready = self._ready if self._ready is not None else t
                phase = max(phase or 0, (t - self._ready) / step)
                self.source = self.source or "standing"
        if auto == "all" and not self._green and final_lap:
            # The pace car's pulled in: a light a step from then, held till the green.
            if self._pitted is None:
                self._pitted = t
            phase = max(phase or 0, (t - self._pitted) / step)
            self.source = self.source or "rolling"
        elif not final_lap:
            self._pitted = None
        rolling = auto == "all" and not self._green and state >= PARADE and leader is not None \
            and flags & ONE_LAP_TO_GREEN
        if rolling:
            eta = self._eta(t, leader)
            if eta is not None and eta < (lights + 1) * step:
                phase = max(phase or 0, lights - eta / step + 1)
                self.source = self.source or "rolling"
        else:
            self._last = None
        if phase is None and not self._peak:
            return None
        self._peak = max(self._peak, min(lights, int(phase or 0)))
        self._seen = True
        return {"lit": self._peak, "lights": lights, "out": False}

    def _eta(self, t, progress):
        """Seconds until the leader reaches the line, from its speed (smoothed)."""
        last, self._last = self._last, (t, progress)
        if last and t > last[0]:
            rate = (progress - last[1]) / (t - last[0])
            if 0 < rate < 0.2:
                self._rate = rate if self._rate is None else self._rate * 0.8 + rate * 0.2
        if not self._rate:
            return None
        ahead = -progress % 1.0  # to the next whole lap: the line
        return ahead / self._rate
