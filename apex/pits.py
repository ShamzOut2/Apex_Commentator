"""Pit stops, for the pit stop overlay (pits.html).

A stop starts when a car crosses the pit lane entry line (iRacing's
CarIdxOnPitRoad turns on) and ends when it crosses the exit line (it turns
off). Its **pit lane** time runs from the one to the other; its **in box**
time is the time the car spends in its pit box (iRacing's track surface says
"in pit stall"), added up if it moves in and out of it. Times are session
times (the sim's clock), so they're right in replays and with the sim
paused. A finished stop stays for ``hold_s`` so its times can be read.
"""

KEEP_S = 120.0  # finished stops are forgotten after this long


class PitTracker:
    def __init__(self):
        self.stops = {}      # car_idx -> {"entry", "exit", "box", "box_from", "boxed"}
        self._session = None
        self._last_t = None

    def reset(self):
        self.stops = {}
        self._last_t = None

    def update(self, session, t, cars):
        """``cars``: (car_idx, on pit road, in its pit box, in the world) for
        every car, at session time ``t`` of session ``session``."""
        if session != self._session or (self._last_t is not None and t < self._last_t - 1.0):
            self.reset()  # another session, or back in a replay: start again
            self._session = session
        self._last_t = t
        for idx, on_pit, in_box, in_world in cars:
            s = self.stops.get(idx)
            if on_pit and in_world:
                if s is None or s["exit"] is not None:  # through the entry line: a new stop
                    s = self.stops[idx] = {"entry": t, "exit": None, "box": 0.0, "box_from": None, "boxed": False}
                if in_box and s["box_from"] is None:
                    s["box_from"], s["boxed"] = t, True
                elif not in_box and s["box_from"] is not None:
                    s["box"] += t - s["box_from"]
                    s["box_from"] = None
            elif s is not None and s["exit"] is None:  # through the exit line (or gone)
                if s["box_from"] is not None:
                    s["box"] += t - s["box_from"]
                    s["box_from"] = None
                s["exit"] = t
        for idx in [i for i, s in self.stops.items() if s["exit"] is not None and t - s["exit"] > KEEP_S]:
            del self.stops[idx]

    def state(self, t, hold_s=8.0):
        """The stops to show: in the pit lane now, or out of it less than
        ``hold_s`` ago. [{"car_idx", "lane_s", "box_s" (None: not in a box
        yet, or a drive-through), "in_box", "out", "entry"}], first in first."""
        out = []
        for idx, s in self.stops.items():
            if s["exit"] is not None and t - s["exit"] > hold_s:
                continue
            box = s["box"] + (t - s["box_from"] if s["box_from"] is not None else 0.0)
            out.append({"car_idx": idx, "lane_s": round(max(0.0, (s["exit"] if s["exit"] is not None else t) - s["entry"]), 2),
                        "box_s": round(box, 2) if s["boxed"] else None, "in_box": s["box_from"] is not None,
                        "out": s["exit"] is not None, "entry": s["entry"]})
        return sorted(out, key=lambda x: x["entry"])
