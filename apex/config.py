"""Configuration loading.

Settings come from ``config.json`` in the project root (copy
``config.example.json``). Every key is optional; anything missing falls back
to ``DEFAULTS``. iRacing credentials may also be supplied via environment
variables so they never need to be written to disk.
"""

import json
import os
from pathlib import Path

from .paths import USER_DIR as ROOT  # config.json and data/ live here

DEFAULTS = {
    # Web server. Use "0.0.0.0" to open the overlay from another PC on your LAN.
    "host": "127.0.0.1",
    "port": 8180,
    # How often telemetry is sampled (Hz). Event detection runs at this rate.
    "poll_hz": 10,
    # How often the overlay is pushed a fresh snapshot (Hz).
    "push_hz": 4,
    # Replay behaviour.
    "replay_preroll_s": 6.0,      # start replays this many seconds before the event
    "replay_auto_return_s": 0,    # >0: jump back to live after this many seconds
    "default_camera_group": "",   # camera group name to use for Watch/Replay ("" = keep current)
    # Grid walk defaults (both can be changed live from the Grid walk tab).
    "gridwalk_interval_s": 8,     # seconds each pair of drivers stays on screen
    "gridwalk_style": "track",    # "track" (cars on a grid), "grid" (grid map) or "h2h" (head to head)
    # Event detection tuning.
    "overtake_hold_s": 1.5,       # a pass must hold this long to count
    "overtake_max_gap_laps": 0.04,  # only cars this close on track are compared
    "slowdown_ratio": 0.35,       # speed falling below this fraction of recent speed = incident
    "event_cooldown_s": 8.0,      # min seconds between incidents of the same kind per car
    "max_events": 300,
    # iRacing Data API (league builder). Prefer the env vars below.
    "iracing_username": "",
    "iracing_password": "",
    "iracing_client_id": "",
    "iracing_client_secret": "",
    "leagues_dir": "data/leagues",
    # Photo booth: where iRacing saves screenshots ("" = Documents\\iRacing\\screenshots)
    # and how long to let the camera settle on each car before the shot.
    "screenshots_dir": "",
    "photobooth_settle_s": 1.6,
    # Updates: check GitHub for new releases and offer them in the app.
    "update_check": True,
    "update_repo": "ShamzOut2/Apex_Commentator",
    "github_token": "",           # only needed if the repository is private
}

ENV_KEYS = {
    "iracing_username": "IRACING_USERNAME",
    "iracing_password": "IRACING_PASSWORD",
    "iracing_client_id": "IRACING_CLIENT_ID",
    "iracing_client_secret": "IRACING_CLIENT_SECRET",
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
