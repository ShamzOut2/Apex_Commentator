"""Grid walk: step through the starting grid two drivers at a time.

The starting order comes from, in order of preference:

1. ``QualifyResultsInfo`` in the session info (the grid iRacing will use),
2. the results of the most recent qualifying session,
3. iRacing's current positions,
4. car number.

Drivers in the session but missing from that source (no qualifying time,
not loaded onto the track…) go to the back, by car number, so the walk always
covers the whole field. The commentator can reorder entries by hand; a manual
order survives until it is reset.

``GridWalk`` holds the shared walk state (shown/running, current pair,
interval). It advances on the server so every page showing the walk,
such as the control panel preview and the OBS broadcast page, stays in step.
"""

import re
import time

MIN_INTERVAL_S = 2.0
MAX_INTERVAL_S = 120.0
HEX = re.compile(r"^[0-9a-fA-F]{6}$")


def parse_design(text):
    """iRacing design string "pattern,colour1,colour2,colour3" -> dict, or None."""
    parts = [p.strip() for p in str(text or "").split(",")]
    if len(parts) < 2:
        return None
    try:
        pattern = int(parts[0])
    except ValueError:
        pattern = 0
    colors = [f"#{p.lower()}" for p in parts[1:] if HEX.match(p)]
    if not colors:
        return None
    return {"pattern": pattern, "colors": colors[:3]}


def _sorted_results(results, drivers):
    ordered = []
    for r in sorted(results or [], key=lambda r: r.get("Position", 1e9)):
        idx = r.get("CarIdx")
        if idx in drivers and idx not in ordered:
            ordered.append(idx)
    return ordered


def qualifying_times(info):
    """Best qualifying lap per car_idx, from the same sources as the grid."""
    results = (info.get("QualifyResultsInfo") or {}).get("Results")
    if not results:
        sessions = (info.get("SessionInfo") or {}).get("Sessions") or []
        results = next((s["ResultsPositions"] for s in reversed(sessions)
                        if "qual" in str(s.get("SessionType", "")).lower() and s.get("ResultsPositions")), [])
    times = {}
    for r in results or []:
        t = r.get("FastestTime")
        if isinstance(t, (int, float)) and t > 0:
            times[r.get("CarIdx")] = float(t)
    return times


def grid_order(drivers, info, official_positions=None):
    """Starting order as a list of car_idx covering every driver in ``drivers``.

    Returns ``(order, source)`` where source names where the order came from.
    """
    order, source = [], "car number"
    qual = (info.get("QualifyResultsInfo") or {}).get("Results")
    if qual:
        order, source = _sorted_results(qual, drivers), "qualifying"
    if not order:
        sessions = (info.get("SessionInfo") or {}).get("Sessions") or []
        for s in reversed(sessions):
            if "qual" in str(s.get("SessionType", "")).lower() and s.get("ResultsPositions"):
                order, source = _sorted_results(s["ResultsPositions"], drivers), "qualifying session"
                break
    if not order and official_positions:
        ranked = [(p, idx) for idx, p in official_positions.items() if idx in drivers and p]
        order, source = [idx for _, idx in sorted(ranked)], "current positions"

    def by_number(idx):
        num = drivers[idx].get("number", "")
        return (0, int(num), num) if num.isdigit() else (1, 0, num)

    rest = sorted((idx for idx in drivers if idx not in order), key=by_number)
    return order + rest, source


class GridWalk:
    def __init__(self, interval=8.0, clock=time.monotonic):
        self.clock = clock
        self.interval = float(interval)
        self.loop = False
        self.autoplay = True       # move on to the next pair by itself (off: only Next / Prev)
        self.include_absent = False
        self.visible = False
        self.running = False
        self.index = 0             # first grid slot of the pair on screen
        self.step_started = None   # clock time the current pair appeared
        self.paused_elapsed = 0.0  # time already spent on the pair when paused
        self.manual_order = None   # list of entry keys, or None for automatic

    # -- ordering -----------------------------------------------------------

    def apply_order(self, keys):
        """Put ``keys`` (automatic order) into the manual order, if there is one."""
        if not self.manual_order:
            return list(keys)
        present = set(keys)
        ordered = [k for k in self.manual_order if k in present]
        ordered += [k for k in keys if k not in set(ordered)]
        return ordered

    def move(self, keys, key, direction):
        """Move ``key`` one place up (-1) or down (+1) in the current order."""
        order = self.apply_order(keys)
        if key not in order:
            raise ValueError("That driver is not on the grid")
        i = order.index(key)
        j = min(len(order) - 1, max(0, i + (1 if direction > 0 else -1)))
        order[i], order[j] = order[j], order[i]
        self.manual_order = order

    def reset_order(self):
        self.manual_order = None

    # -- playback -----------------------------------------------------------

    def _pair_start(self, index):
        return max(0, int(index)) // 2 * 2

    def start(self, index=0):
        self.visible = True
        self.running = True
        self.index = self._pair_start(index)
        self.step_started = self.clock()
        self.paused_elapsed = 0.0

    def pause(self):
        if self.running:
            self.paused_elapsed = self.clock() - self.step_started
            self.running = False

    def resume(self):
        if not self.visible:
            return self.start(self.index)
        if not self.running:
            self.running = True
            self.step_started = self.clock() - self.paused_elapsed

    def goto(self, index, count):
        self.visible = True
        self.index = min(self._pair_start(index), self._pair_start(max(0, count - 1)))
        self.step_started = self.clock()
        self.paused_elapsed = 0.0

    def step(self, direction, count):
        self.goto(self.index + (2 if direction > 0 else -2), count)

    def hide(self):
        self.visible = False
        self.running = False

    def configure(self, interval=None, loop=None, include_absent=None, autoplay=None):
        if interval is not None:
            self.interval = min(MAX_INTERVAL_S, max(MIN_INTERVAL_S, float(interval)))
        if loop is not None:
            self.loop = bool(loop)
        if include_absent is not None:
            self.include_absent = bool(include_absent)
        if autoplay is not None:
            self.autoplay = bool(autoplay)
            if self.autoplay and self.visible and self.running:
                self.step_started = self.clock()  # the pair on screen gets its full time

    def tick(self, count):
        """Advance to the next pair when its time is up. Returns True if it moved."""
        if not (self.visible and self.running and self.autoplay) or self.step_started is None:
            return False
        if self.clock() - self.step_started < self.interval:
            return False
        if self.index + 2 < count:
            self.index += 2
        elif self.loop and count:
            self.index = 0
        else:
            # The last pair has had its time: the walk is over.
            self.hide()
            return True
        self.step_started = self.clock()
        return True

    def state(self):
        if not self.autoplay:
            elapsed = 0.0
        elif self.running and self.step_started is not None:
            elapsed = self.clock() - self.step_started
        else:
            elapsed = self.paused_elapsed
        return {
            "visible": self.visible,
            "running": self.running,
            "index": self.index,
            "interval": self.interval,
            "elapsed": round(min(elapsed, self.interval), 2),
            "loop": self.loop,
            "autoplay": self.autoplay,
            "include_absent": self.include_absent,
            "manual_order": self.manual_order is not None,
        }
