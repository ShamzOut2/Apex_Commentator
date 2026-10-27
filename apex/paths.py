"""Where things live, for both a source checkout and the packaged Windows app.

* ``APP_DIR``: the program's own read-only files (``web/``, built-in logos).
  In the packaged app that is PyInstaller's bundle folder.
* ``USER_DIR``: everything the user creates (``config.json``, ``data/``).
  A source checkout keeps these next to the code, as before. The packaged app
  keeps them in ``%APPDATA%\\Apex Commentator`` so updates and reinstalls
  never touch them.
"""

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
APP_NAME = "Apex Commentator"

if FROZEN:
    APP_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    USER_DIR = Path(os.environ.get("APPDATA") or Path.home() / ".config") / APP_NAME
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    USER_DIR = APP_DIR

WEB_DIR = APP_DIR / "web"
