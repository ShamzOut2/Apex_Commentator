"""Incident and overtake detection.

Everything here works from telemetry that iRacing exposes for *every* car, so
it works for spectators and commentators, not just the driver in the car:

* **Overtakes** - in a race under green, each pair of cars that are close on
  track is compared by race progress (lap + lap distance). When the order of
  a pair flips and stays flipped for ``overtake_hold_s`` with both cars on
  track (not pit road, not off track), an overtake is recorded at the moment
  the flip *started*. Swaps caused by pit stops or a car going off are ignored.
* **Off tracks** - a car's track surface changing to "off track".
* **Slowdowns** - a car on track whose speed collapses relative to its recent
  pace (spins, contact, stopping). Ignored on pit road and under caution.
* Off tracks and slowdowns share a per-car cooldown, so one moment (a spin
  that leaves the track) is one event rather than two.
* **Incident points** - when session info reports a higher incident count for
  a driver, the points are attached to that car's off track/slowdown from the
  last few seconds, or recorded as a stand-alone incident.

Each event stores the session number and session time, which is what the
replay system uses to jump straight to it.
"""

import itertools

from .sources import (
    CAUTION_FLAGS,
    STATE_RACING,
    TRK_NOT_IN_WORLD,
    TRK_OFF_TRACK,
    TRK_ON_TRACK,
)

INCIDENT_MATCH_WINDOW_S = 15.0
PAIR_FORGET_S = 1.0
MIN_BASELINE_SPEED = 15.0  # m/s; below this a car is not "at speed"


def _at(seq, i, default=None):
    return seq[i] if i < len(seq) else default


class EventDetector:
    def __init__(self, cfg):
        self.hold_s = float(cfg.get("overtake_hold_s", 1.5))
        self.max_gap = float(cfg.get("overtake_max_gap_laps", 0.04))
        self.slow_ratio = float(cfg.get("slowdown_ratio", 0.35))
        self.cooldown_s = float(cfg.get("event_cooldown_s", 8.0))
        self.max_events = int(cfg.get("max_events", 300))
        self._ids = itertools.count(1)
        self.events = []
        # Incident counts are only re-baselined by clear(): they must survive
        # session/reconnect resets or the next increase would go unnoticed.
        self._incidents = {}
        self.reset()

    def reset(self):
        """Forget per-car state (new session or reconnect). Events are kept."""
        self._pairs = {}
        self._prev_pct = {}
        self._prev_time = None
        self._speed_fast = {}
        self._speed_base = {}
        self._prev_surface = {}
        self._last_kind_time = {}
        self._session_num = None

    def clear(self):
        self.events = []
        self._incidents = {}
        self.reset()

    # -- helpers ------------------------------------------------------------

    def _emit(self, kind, car_idx, frame, drivers, when=None, other=None, **extra):
        driver = drivers.get(car_idx, {})
        event = {
            "id": next(self._ids),
            "type": kind,
            "car_idx": car_idx,
            "car_number": driver.get("number", ""),
            "driver": driver.get("name", f"Car {car_idx}"),
            "session_num": frame.session_num,
            "session_time": round(frame.session_time if when is None else when, 2),
            "lap": max(0, _at(frame.lap, car_idx, 0) or 0),
            "incidents": 0,
        }
        if other is not None:
            od = drivers.get(other, {})
            event["other_car_idx"] = other
            event["other_car_number"] = od.get("number", "")
            event["other_driver"] = od.get("name", f"Car {other}")
        event.update(extra)
        self.events.append(event)
        if len(self.events) > self.max_events:
            del self.events[: len(self.events) - self.max_events]
        return event

    def _cooled_down(self, car_idx, kind, now):
        key = (car_idx, kind)
        last = self._last_kind_time.get(key)
        if last is not None and now - last < self.cooldown_s:
            return False
        self._last_kind_time[key] = now
        return True

    # -- main entry point ---------------------------------------------------

    def update(self, frame, drivers, track_length_m, is_race):
        """Process one frame. ``drivers`` maps car_idx -> driver dict.

        Returns the list of events created by this frame.
        """
        if frame.session_num != self._session_num:
            self.reset()
            self._session_num = frame.session_num
        now = frame.session_time
        dt = None if self._prev_time is None else now - self._prev_time
        if dt is not None and dt <= 0:
            # Time stood still or went backwards (paused / session change).
            if dt < 0:
                self.reset()
                self._session_num = frame.session_num
            self._prev_time = now
            return []
        self._prev_time = now
        caution = bool(frame.session_flags & CAUTION_FLAGS)
        created = []
        created += self._detect_surface_and_speed(frame, drivers, track_length_m, dt, caution)
        if is_race and frame.session_state == STATE_RACING and not caution:
            created += self._detect_overtakes(frame, drivers)
        else:
            self._pairs.clear()
        return created

    def _detect_surface_and_speed(self, frame, drivers, track_length_m, dt, caution):
        created = []
        now = frame.session_time
        for idx in drivers:
            surface = _at(frame.surface, idx, TRK_NOT_IN_WORLD)
            pct = _at(frame.pct, idx, -1.0)
            on_pit = bool(_at(frame.on_pit, idx, False))
            prev_surface = self._prev_surface.get(idx)
            self._prev_surface[idx] = surface

            if surface == TRK_OFF_TRACK and prev_surface == TRK_ON_TRACK and not on_pit:
                if self._cooled_down(idx, "moment", now):
                    created.append(self._emit("offtrack", idx, frame, drivers))

            prev_pct = self._prev_pct.get(idx)
            self._prev_pct[idx] = pct
            if surface == TRK_NOT_IN_WORLD or pct < 0 or prev_pct is None or prev_pct < 0 or not dt:
                self._speed_fast.pop(idx, None)
                self._speed_base.pop(idx, None)
                continue
            delta = pct - prev_pct
            if delta < -0.5:
                delta += 1.0  # crossed the line
            if delta < -0.01 or delta > 0.5:
                # Teleport (tow, reset, replay jump): restart the speed estimate.
                self._speed_fast.pop(idx, None)
                self._speed_base.pop(idx, None)
                continue
            speed = max(0.0, delta) * track_length_m / dt
            fast = self._speed_fast.get(idx, speed)
            fast = fast + 0.5 * (speed - fast)
            base = self._speed_base.get(idx, speed)
            self._speed_fast[idx] = fast
            if on_pit or caution:
                self._speed_base[idx] = fast
                continue
            if base > MIN_BASELINE_SPEED and fast < base * self.slow_ratio:
                if self._cooled_down(idx, "moment", now):
                    created.append(self._emit(
                        "slowdown", idx, frame, drivers,
                        speed_kph=round(fast * 3.6), from_kph=round(base * 3.6),
                    ))
                # Let the baseline follow the slow car so it can re-arm later.
                self._speed_base[idx] = base + 0.2 * (fast - base)
            else:
                self._speed_base[idx] = base + 0.03 * (fast - base)
        return created

    def _detect_overtakes(self, frame, drivers):
        now = frame.session_time
        cars = []
        for idx in drivers:
            lap = _at(frame.lap, idx, -1)
            pct = _at(frame.pct, idx, -1.0)
            if lap is None or lap < 1 or pct is None or pct < 0:
                continue
            if _at(frame.surface, idx) != TRK_ON_TRACK or _at(frame.on_pit, idx, False):
                continue
            cars.append((lap + pct, idx))
        cars.sort(reverse=True)

        created = []
        for i, (prog_a, a) in enumerate(cars):
            for prog_b, b in cars[i + 1:]:
                if prog_a - prog_b > self.max_gap:
                    break
                key = (a, b) if a < b else (b, a)
                # +1 when the lower car_idx of the pair is ahead.
                sign = 1 if key[0] == a else -1
                state = self._pairs.get(key)
                if state is None:
                    self._pairs[key] = {"confirmed": sign, "since": None, "seen": now}
                    continue
                state["seen"] = now
                if sign == state["confirmed"]:
                    state["since"] = None
                    continue
                if state["since"] is None:
                    state["since"] = now
                if now - state["since"] >= self.hold_s:
                    passer = key[0] if sign == 1 else key[1]
                    passed = key[1] if sign == 1 else key[0]
                    created.append(self._emit(
                        "overtake", passer, frame, drivers, when=state["since"], other=passed,
                        position=self._live_position(frame, passer, drivers),
                    ))
                    state["confirmed"] = sign
                    state["since"] = None
        stale = [k for k, s in self._pairs.items() if now - s["seen"] > PAIR_FORGET_S]
        for k in stale:
            del self._pairs[k]
        return created

    @staticmethod
    def _live_position(frame, car_idx, drivers):
        mine = (_at(frame.lap, car_idx, 0) or 0) + (_at(frame.pct, car_idx, 0) or 0)
        ahead = 0
        for idx in drivers:
            if idx == car_idx:
                continue
            lap = _at(frame.lap, idx, -1)
            pct = _at(frame.pct, idx, -1.0)
            if lap is None or lap < 0 or pct is None or pct < 0:
                continue
            if lap + pct > mine:
                ahead += 1
        return ahead + 1

    # -- incident points from session info --------------------------------

    def update_incidents(self, frame, drivers):
        """Compare incident counts from session info; call when it changes."""
        created = []
        now = frame.session_time
        for idx, d in drivers.items():
            count = d.get("incidents")
            if count is None:
                continue
            prev = self._incidents.get(idx)
            self._incidents[idx] = count
            if prev is None or count <= prev:
                continue
            points = count - prev
            recent = None
            for ev in reversed(self.events):
                if now - ev["session_time"] > INCIDENT_MATCH_WINDOW_S:
                    break
                if ev["car_idx"] == idx and ev["type"] in ("offtrack", "slowdown", "incident"):
                    recent = ev
                    break
            if recent is not None:
                recent["incidents"] += points
            else:
                # Session info lags the moment itself by a few seconds.
                ev = self._emit("incident", idx, frame, drivers, when=max(0.0, now - 3.0))
                ev["incidents"] = points
                created.append(ev)
        return created
