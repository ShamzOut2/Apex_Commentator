"""The flag overlay's state: which sectors are under a yellow flag.

Sectors are set yellow by hand (hotkeys: a sector on / off, every sector,
clear), the safety car sent out by hand or (``sc_auto``) shown while iRacing
has a full course caution, and, with ``auto`` on, sectors also go yellow by iRacing: a sector goes yellow while a
car is stopped or crawling in it (on or off the track, not in the pits) and
stays yellow ``hold_s`` seconds after it gets going again; a full course
caution makes every sector yellow. Clearing the last yellow shows the
green "track clear" flag for a moment.
"""

ON_TRACK, OFF_TRACK = 3, 0
SLOW_MS = 4.0       # slower than this (m/s) is stopped / crawling
SLOW_FOR_S = 2.0    # for this long before the sector goes yellow


def sectors_text(sectors, count):
    """"Sector 1", "Sectors 1 & 2", "Sectors 1, 2 & 4" or "All Sectors"."""
    picked = sorted(set(sectors))
    if not picked:
        return ""
    if count > 1 and len(picked) >= count:
        return "All Sectors"
    if len(picked) == 1:
        return f"Sector {picked[0]}"
    names = [str(s) for s in picked]
    return f"Sectors {', '.join(names[:-1])} & {names[-1]}"


def sector_of(pct, starts):
    """The 1-based sector a lap fraction is in, from the sectors' start points."""
    n = 1
    for k, start in enumerate(starts):
        if pct >= start:
            n = k + 1
    return n


class SectorFlags:
    def __init__(self):
        self._key = None
        self.manual = set()   # sectors set yellow by hand (1-based)
        self.sc = False       # the safety car out, by hand
        self.reset()

    def reset(self):
        self._slow = {}       # car -> session time it went slow
        self._last = {}       # car -> (t, pct)
        self._held = {}       # sector -> session time its yellow lasts until (auto)
        self._clear_at = None  # the last yellow cleared at (the green flag shows)
        self._was = False

    # -- by hand ---------------------------------------------------------

    def toggle(self, sector, count):
        if 1 <= sector <= count:
            self.manual ^= {sector}
        return sorted(self.manual)

    def set_all(self, count):
        self.manual = set(range(1, count + 1))
        return sorted(self.manual)

    def toggle_sc(self):
        """The safety car out / in, by hand."""
        self.sc = not self.sc
        return self.sc

    def clear(self):
        """Every yellow off (the automatic ones too, until a car stops again),
        and the safety car in."""
        self.manual = set()
        self.sc = False
        self._held = {}
        self._slow = {}
        return []

    # -- each tick -------------------------------------------------------

    def update(self, key, t, *, starts, cars, track_m, auto, caution, racing, hold_s=10.0, clear_s=3.0, done=(),
               sc_auto=False):
        """The flag now: {"sectors", "count", "text", "clear", "sc"} or None (nothing on).
        ``cars``: {car: (pct, surface, on_pit_road)}; ``starts``: each sector's
        start (lap fraction); ``racing``: a session under way, cars timed;
        ``done``: cars that have finished the race (never a hazard); ``sc_auto``:
        the safety car shown while iRacing has a full course caution."""
        if key != self._key:
            self._key = key
            self.manual = set()
            self.sc = False
            self.reset()
        count = max(1, len(starts))
        self.manual = {s for s in self.manual if s <= count}
        if self.sc or (sc_auto and caution and racing):
            # The safety car: the whole track under it.
            self._was, self._clear_at = True, None
            return {"sectors": list(range(1, count + 1)), "count": count, "text": "Safety Car", "clear": False, "sc": True}
        yellow = set(self.manual)
        if auto and racing:
            if caution:
                yellow |= set(range(1, count + 1))
            else:
                for car, sector in self._stopped(t, {c: v for c, v in cars.items() if c not in done}, track_m, starts):
                    self._held[sector] = t + hold_s
                yellow |= {s for s, until in self._held.items() if until > t and s <= count}
        else:
            self._slow, self._last = {}, {}
        self._held = {s: u for s, u in self._held.items() if u > t}
        if yellow:
            self._was, self._clear_at = True, None
            return {"sectors": sorted(yellow), "count": count, "text": sectors_text(yellow, count), "clear": False, "sc": False}
        if self._was:
            self._was, self._clear_at = False, t
        if self._clear_at is not None and 0 <= t - self._clear_at < clear_s:
            return {"sectors": [], "count": count, "text": "Track Clear", "clear": True, "sc": False}
        self._clear_at = None
        return None

    def _stopped(self, t, cars, track_m, starts):
        """(car, sector) for each car stopped or crawling out on track for a while."""
        out = []
        for car, (pct, surface, pit) in cars.items():
            last = self._last.get(car)
            self._last[car] = (t, pct)
            if pct is None or pct < 0 or pit or surface not in (ON_TRACK, OFF_TRACK):
                self._slow.pop(car, None)
                continue
            if not last or t <= last[0]:
                continue
            moved = (pct - last[1] + 0.5) % 1.0 - 0.5  # across the line too
            speed = abs(moved) * track_m / (t - last[0])
            if speed >= SLOW_MS:
                self._slow.pop(car, None)
                continue
            since = self._slow.setdefault(car, t)
            if t - since >= SLOW_FOR_S:
                out.append((car, sector_of(pct, starts)))
        return out
