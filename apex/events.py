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
  pace *and* is well under the usual speed at that point of the track (so
  braking for a hairpin isn't one). Ignored on pit road and under caution.
* **Spins** - a slowdown or off track where the car also rotates sharply
  within ``spin_window_s`` (0.2 s): iRacing sends the heading only for the
  car driven on this PC, so for every car the signs are its steering
  snapping to opposite lock, or it travelling backwards along the track
  (turned round). Without those it stays a slowdown.
* Off tracks and slowdowns share a per-car cooldown, so one moment (a spin
  that leaves the track) is one event rather than two.
* **Incident points** - when session info reports a higher incident count for
  a driver, the points are attached to that car's off track/slowdown from the
  last few seconds, or recorded as a stand-alone incident.
* **Pit stops** (races) - pit in, and pit out with the stop time and the
  places it cost.
* **Places lost after an off** (races) - once the car has been back on track
  for a few seconds, if it dropped places since going off.
* **Penalties** - a car being shown the black flag, disqualification,
  meatball (repairs) or a warning.
* **Fastest laps** - a new fastest lap in the car's class.

Each event stores the session number and session time, which is what the
replay system uses to jump straight to it.
"""

import itertools
import math
from collections import deque

from .sources import (
    CAUTION_FLAGS,
    FLAG_BLACK,
    FLAG_DISQUALIFY,
    FLAG_FURLED,
    FLAG_REPAIR,
    STATE_RACING,
    TRK_NOT_IN_WORLD,
    TRK_OFF_TRACK,
    TRK_ON_TRACK,
)

INCIDENT_MATCH_WINDOW_S = 15.0
PAIR_FORGET_S = 1.0
MIN_BASELINE_SPEED = 15.0  # m/s; below this a car is not "at speed"
RECOVERY_SETTLE_S = 5.0    # back on track this long before counting places lost
TIME_JUMP_S = 2.0          # a bigger jump means a replay skip: start afresh
SPEED_BINS = 250           # the track split into this many pieces for "usual speed here"
SPEED_BIN_MIN_SAMPLES = 8  # samples in a piece before its usual speed counts
SPIN_BACKWARDS_M = 3.0     # this far backwards along the track: the car has turned round
SPIN_MATCH_S = 3.0         # rotation this close to a slowdown / off track makes it a spin
HISTORY_S = 1.5
PENALTY_FLAGS = (
    (FLAG_DISQUALIFY, "Disqualified"),
    (FLAG_BLACK, "Black flag"),
    (FLAG_REPAIR, "Meatball (repairs)"),
    (FLAG_FURLED, "Warning"),
)


def _at(seq, i, default=None):
    return seq[i] if i < len(seq) else default


def _angle(a):
    """An angle difference wrapped to -pi..pi."""
    return (a + math.pi) % (2 * math.pi) - math.pi


class EventDetector:
    def __init__(self, cfg):
        self.hold_s = float(cfg.get("overtake_hold_s", 1.5))
        self.max_gap = float(cfg.get("overtake_max_gap_laps", 0.04))
        self.slow_ratio = float(cfg.get("slowdown_ratio", 0.35))
        self.corner_ratio = float(cfg.get("slowdown_corner_ratio", 0.5))
        self.spin_window_s = float(cfg.get("spin_window_s", 0.2))
        self.spin_yaw = math.radians(float(cfg.get("spin_yaw_deg", 45.0)))
        self.spin_steer = math.radians(float(cfg.get("spin_steer_deg", 180.0)))
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
        self._history = {}        # car -> deque of (time, metres moved, steer, yaw)
        self._rotated = {}        # car -> (time, how) of its last sharp rotation
        self._moment = {}         # car -> its last off track / slowdown event, to upgrade to a spin
        self._prev_surface = {}
        self._last_kind_time = {}
        self._session_num = None
        self._pit = {}            # car -> {"on", "since", "pos"}
        self._recover = {}        # car -> {"pos", "when", "back"} after going off
        self._prev_flags = {}
        self._car_best = {}
        self._class_best = {}
        self._laps_baselined = False
        # Usual speed at each piece of the track: [average m/s, samples]. Kept
        # per track, not per session: the same corners stay the same.
        if getattr(self, "_track_m", None) is None:
            self._usual = [[0.0, 0] for _ in range(SPEED_BINS)]

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
        if dt is not None and (dt <= 0 or dt > TIME_JUMP_S):
            # Time stood still, went backwards or jumped (pause, session change,
            # replay skip): start afresh rather than compare across the gap.
            if dt != 0:
                self.reset()
                self._session_num = frame.session_num
            self._prev_time = now
            return []
        self._prev_time = now
        caution = bool(frame.session_flags & CAUTION_FLAGS)
        created = []
        created += self._detect_surface_and_speed(frame, drivers, track_length_m, dt, caution)
        racing = is_race and frame.session_state == STATE_RACING
        created += self._detect_race_events(frame, drivers, is_race, racing)
        created += self._detect_fastest_laps(frame, drivers)
        if racing and not caution:
            created += self._detect_overtakes(frame, drivers)
        else:
            self._pairs.clear()
        return created

    def _detect_surface_and_speed(self, frame, drivers, track_length_m, dt, caution):
        created = []
        now = frame.session_time
        if track_length_m != getattr(self, "_track_m", None):
            self._track_m = track_length_m
            self._usual = [[0.0, 0] for _ in range(SPEED_BINS)]  # another track
        for idx in drivers:
            surface = _at(frame.surface, idx, TRK_NOT_IN_WORLD)
            pct = _at(frame.pct, idx, -1.0)
            on_pit = bool(_at(frame.on_pit, idx, False))
            prev_surface = self._prev_surface.get(idx)
            self._prev_surface[idx] = surface

            if surface == TRK_OFF_TRACK and prev_surface == TRK_ON_TRACK and not on_pit:
                if self._cooled_down(idx, "moment", now):
                    created.append(self._moment_event("offtrack", idx, frame, drivers))

            prev_pct = self._prev_pct.get(idx)
            self._prev_pct[idx] = pct
            if surface == TRK_NOT_IN_WORLD or pct < 0 or prev_pct is None or prev_pct < 0 or not dt:
                self._forget_speed(idx)
                continue
            delta = pct - prev_pct
            if delta < -0.5:
                delta += 1.0  # crossed the line
            if delta < -0.01 or delta > 0.5:
                # Teleport (tow, reset, replay jump): restart the speed estimate.
                self._forget_speed(idx)
                continue
            if not on_pit:
                self._track_rotation(idx, frame, now, delta * track_length_m)
            speed = max(0.0, delta) * track_length_m / dt
            fast = self._speed_fast.get(idx, speed)
            fast = fast + 0.5 * (speed - fast)
            base = self._speed_base.get(idx, speed)
            self._speed_fast[idx] = fast
            if on_pit or caution:
                self._speed_base[idx] = fast
                continue
            usual = self._usual[min(SPEED_BINS - 1, int(pct * SPEED_BINS))]
            # Slow for this corner, not just slower than a moment ago (braking).
            slow_here = usual[1] < SPEED_BIN_MIN_SAMPLES or fast < usual[0] * self.corner_ratio
            if base > MIN_BASELINE_SPEED and fast < base * self.slow_ratio and slow_here:
                if self._cooled_down(idx, "moment", now):
                    created.append(self._moment_event(
                        "slowdown", idx, frame, drivers,
                        speed_kph=round(fast * 3.6), from_kph=round(base * 3.6),
                    ))
                # Let the baseline follow the slow car so it can re-arm later.
                self._speed_base[idx] = base + 0.2 * (fast - base)
            else:
                self._speed_base[idx] = base + 0.03 * (fast - base)
                if surface == TRK_ON_TRACK and fast > MIN_BASELINE_SPEED:
                    # Learn the usual speed here from cars running normally.
                    n = min(usual[1] + 1, 50)
                    usual[0] += (fast - usual[0]) / n
                    usual[1] = n
        return created

    def _forget_speed(self, idx):
        self._speed_fast.pop(idx, None)
        self._speed_base.pop(idx, None)
        self._history.pop(idx, None)

    # -- spins ----------------------------------------------------------------

    def _moment_event(self, kind, idx, frame, drivers, **extra):
        """An off track or slowdown: a spin if the car has just rotated sharply."""
        ev = self._emit(kind, idx, frame, drivers, **extra)
        self._moment[idx] = ev
        rot = self._rotated.get(idx)
        if rot and frame.session_time - rot[0] <= SPIN_MATCH_S:
            self._make_spin(ev, rot[1])
        return ev

    @staticmethod
    def _make_spin(ev, how):
        ev["spin"] = how
        if ev["type"] == "slowdown":
            ev["type"] = "spin"

    def _track_rotation(self, idx, frame, now, moved_m):
        """Look for a sharp rotation of the car within the spin window."""
        steer = _at(frame.steer, idx)
        yaw = frame.yaw if idx == frame.player_car_idx and frame.is_live else None
        hist = self._history.setdefault(idx, deque())
        hist.append((now, moved_m, steer, yaw))
        while hist and now - hist[0][0] > HISTORY_S:
            hist.popleft()
        how = None
        backwards = -sum(m for _, m, _, _ in hist if m < 0)
        if backwards >= SPIN_BACKWARDS_M:
            how = "backwards"
        for t, _, s, y in hist:
            if now - t > self.spin_window_s + 1e-6:
                continue
            if yaw is not None and y is not None and abs(_angle(yaw - y)) >= self.spin_yaw:
                how = "yaw"
                break
            if steer is not None and s is not None and abs(steer - s) >= self.spin_steer:
                how = how or "steer"
        if how is None:
            return
        self._rotated[idx] = (now, how)
        ev = self._moment.get(idx)
        if ev is not None and not ev.get("spin") and now - ev["session_time"] <= SPIN_MATCH_S:
            self._make_spin(ev, how)

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
    def _positions(frame, drivers, racing):
        """car_idx -> position: live order while racing, iRacing's otherwise."""
        if not racing:
            return {idx: _at(frame.position, idx, 0) for idx in drivers if _at(frame.position, idx, 0)}
        progress = []
        for idx in drivers:
            lap, pct = _at(frame.lap, idx, -1), _at(frame.pct, idx, -1.0)
            if lap is not None and lap >= 0 and pct is not None and pct >= 0:
                progress.append((lap + pct, idx))
        progress.sort(reverse=True)
        return {idx: i + 1 for i, (_, idx) in enumerate(progress)}

    def _detect_race_events(self, frame, drivers, is_race, racing):
        created = []
        now = frame.session_time
        pos = self._positions(frame, drivers, racing)
        for idx in drivers:
            # Pit stops.
            on_pit = bool(_at(frame.on_pit, idx, False))
            pit = self._pit.get(idx)
            if pit is None:
                self._pit[idx] = {"on": on_pit, "since": now, "pos": pos.get(idx)}
            elif on_pit != pit["on"]:
                if is_race and on_pit:
                    created.append(self._emit("pit_in", idx, frame, drivers, position=pos.get(idx)))
                elif is_race:
                    created.append(self._emit(
                        "pit_out", idx, frame, drivers, position=pos.get(idx), from_position=pit["pos"],
                        duration=round(now - pit["since"], 1),
                    ))
                self._pit[idx] = {"on": on_pit, "since": now, "pos": pos.get(idx)}

            # Places lost after going off.
            surface = _at(frame.surface, idx, TRK_NOT_IN_WORLD)
            rec = self._recover.get(idx)
            if racing and rec is None and surface == TRK_OFF_TRACK and idx in pos:
                self._recover[idx] = {"pos": pos[idx], "when": now, "back": None}
            elif rec is not None:
                if surface == TRK_ON_TRACK:
                    rec["back"] = rec["back"] or now
                    if now - rec["back"] >= RECOVERY_SETTLE_S:
                        after = pos.get(idx)
                        if racing and after and after > rec["pos"]:
                            created.append(self._emit(
                                "position", idx, frame, drivers, when=rec["when"], position=after,
                                from_position=rec["pos"], reason="off",
                            ))
                        del self._recover[idx]
                else:
                    rec["back"] = None
                    if now - rec["when"] > 120:
                        del self._recover[idx]

            # Penalty flags, as they're shown.
            flags = int(_at(frame.car_flags, idx, 0) or 0)
            prev = self._prev_flags.get(idx)
            self._prev_flags[idx] = flags
            if prev is not None:
                for bit, label in PENALTY_FLAGS:
                    if flags & bit and not prev & bit:
                        created.append(self._emit("penalty", idx, frame, drivers, penalty=label))
        return created

    def _detect_fastest_laps(self, frame, drivers):
        created = []
        for idx, d in drivers.items():
            best = _at(frame.best_lap, idx, -1.0)
            if not best or best <= 0:
                continue
            if idx in self._car_best and best >= self._car_best[idx] - 1e-4:
                continue
            self._car_best[idx] = best
            cls = d.get("car_class") or ""
            if cls in self._class_best and best >= self._class_best[cls] - 1e-4:
                continue
            self._class_best[cls] = best
            # Laps already set when the app started aren't news.
            if self._laps_baselined:
                created.append(self._emit("fastest_lap", idx, frame, drivers, lap_time=round(best, 3), car_class=cls))
        self._laps_baselined = True
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
                if ev["car_idx"] == idx and ev["type"] in ("offtrack", "slowdown", "spin", "incident"):
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
