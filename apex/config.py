"""Configuration loading.

Settings come from ``config.json`` in the project root (copy
``config.example.json``). Every key is optional; anything missing falls back
to ``DEFAULTS``. The GitHub token may also be supplied via an environment
variable so it never needs to be written to disk.
"""

import json
import os
from pathlib import Path

from .paths import USER_DIR as ROOT  # config.json and data/ live here

DEFAULTS = {
    # Web server. Use "0.0.0.0" to open the overlay from another PC on your LAN.
    "host": "127.0.0.1",
    "port": 8180,
    # How often telemetry is sampled (Hz). Event detection runs at this rate;
    # spin detection looks at 0.2 s windows, so keep it at 20 or more.
    "poll_hz": 30,
    # How often the overlay is pushed a fresh snapshot (Hz).
    "push_hz": 4,
    # Replay behaviour.
    "replay_preroll_s": 6.0,      # start replays this many seconds before the event
    "replay_auto_return_s": 0,    # >0: jump back to live after this many seconds
    "default_camera_group": "",   # camera group name to use for Watch/Replay ("" = keep current)
    # Grid walk defaults (both can be changed live from the Grid walk tab).
    "gridwalk_interval_s": 8,     # seconds each pair of drivers stays on screen
    # Event detection tuning.
    "overtake_hold_s": 1.5,       # a pass must hold this long to count
    "overtake_max_gap_laps": 0.04,  # only cars this close on track are compared
    "slowdown_ratio": 0.35,       # speed falling below this fraction of recent speed = incident
    "slowdown_corner_ratio": 0.5, # ...and below this fraction of the usual speed at that point of the track
    # A slowdown is a spin when the car also rotates within spin_window_s:
    # its heading turns spin_yaw_deg (the car driven on this PC: iRacing only
    # sends heading for that one), its steering snaps spin_steer_deg (opposite
    # lock), or it travels backwards along the track.
    "spin_window_s": 0.2,
    "spin_yaw_deg": 45.0,
    "spin_steer_deg": 180.0,
    # Contact: a car closing on the one just ahead at this speed or more that,
    # within 0.12 s, suddenly stops closing (the jolt of a hit).
    "contact_jolt_kph": 20.0,
    "event_cooldown_s": 8.0,      # min seconds between incidents of the same kind per car
    "max_events": 300,
    "leagues_dir": "data/leagues",
    # Updates: check GitHub for new releases and offer them in the app.
    "update_check": True,
    "update_repo": "ShamzOut2/Apex_Commentator",
    "github_token": "",           # only needed if the repository is private
}

ENV_KEYS = {
    "github_token": "APEX_GITHUB_TOKEN",
}


def load_config(path=None):
    cfg = dict(DEFAULTS)
    path = Path(path) if path else ROOT / "config.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    for key, env in ENV_KEYS.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    leagues_dir = Path(cfg["leagues_dir"])
    cfg["leagues_dir"] = str(leagues_dir if leagues_dir.is_absolute() else ROOT / leagues_dir)
    return cfg
