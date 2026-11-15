"""The starting lights overlay's state: how many red lights are lit, and lights out.

Three ways the lights count down, all ending with the race going green:

- iRacing's own start lights (a standing start): its Ready flag starts the
  count, a light every ``step`` seconds; Set has them all lit; Go is lights out.
- A rolling start: on the lap to the green, the lights come on one a step
  as the leader gets within that many steps of the line (from its speed).
- By hand (a hotkey): a light every step from the press.

Once all are lit they stay lit until the green. Lights out shows for
``out_s`` seconds, then the overlay goes. Nothing shows outside a race's
start, and lights out only follows a count that was seen (not when the
app starts mid-race).
"""

START_READY = 0x20000000
START_SET = 0x40000000
START_GO = 0x80000000
ONE_LAP_TO_GREEN = 0x0200


class StartLights:
    def __init__(self):
        self._key = None
        self.reset()

    def reset(self):
        self._manual = None   # session time of the hotkey press
        self._ready = None    # session time iRacing's Ready flag came up
        self._go = None       # session time of the green
        self._peak = 0        # lights lit so far (never fewer until the green)
        self._seen = False    # a count shown (so lights out follows)
        self._last = None     # (t, leader progress) for its speed
        self._rate = None     # the leader's laps a second

    def count(self, t):
        """The hotkey: start counting now (again, from the first light)."""
        self._manual = t
        self._peak = 0
        self._go = None

    def update(self, key, t, *, race, started, flags, leader, auto="all", lights=5, step=1.0, out_s=3.0):
        """The lights now: None (not on screen) or {"lit", "lights", "out"}.
        ``key`` is the session (a new one starts afresh); ``started``: the race
        is under way (iRacing's Racing state); ``leader``: the leading car's
        progress (laps + lap fraction) or None."""
        if key != self._key:
            first, self._key = self._key is None, key
            if not first:  # a new session (a press before the first look kept)
                self.reset()
        if not race:
            return None
        go = started or bool(flags & START_GO)
        if go:
            if self._go is None:
                self._go = t
            self._manual = None
            if self._seen and 0 <= t - self._go < out_s:
                return {"lit": 0, "lights": lights, "out": True}
            return None
        self._go = None
        phase = None  # steps since the count started (lit = floor of it)
        if self._manual is not None and t >= self._manual:
            phase = (t - self._manual) / step
        if auto in ("all", "standing"):
            if flags & START_SET:
                phase = lights
            elif flags & START_READY:
                self._ready = self._ready if self._ready is not None else t
                phase = max(phase or 0, (t - self._ready) / step)
        if auto == "all" and flags & ONE_LAP_TO_GREEN and leader is not None:
            eta = self._eta(t, leader)
            if eta is not None and eta < (lights + 1) * step:
                phase = max(phase or 0, lights - eta / step + 1)
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
