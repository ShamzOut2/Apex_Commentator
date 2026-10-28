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


def documents_dir():
    """The user's Documents folder (follows OneDrive/redirected folders on Windows)."""
    if sys.platform == "win32":
        try:
            import ctypes
            import uuid

            # FOLDERID_Documents
            guid = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")
            buf = ctypes.c_wchar_p()
            fid = (ctypes.c_byte * 16).from_buffer_copy(guid.bytes_le)
            if ctypes.windll.shell32.SHGetKnownFolderPath(fid, 0, None, ctypes.byref(buf)) == 0:
                path = Path(buf.value)
                ctypes.windll.ole32.CoTaskMemFree(buf)
                return path
        except (OSError, AttributeError, ValueError):
            pass
    return Path.home() / "Documents"


def iracing_screenshots_dir():
    """Where iRacing saves screenshots: Documents\\iRacing\\screenshots."""
    return documents_dir() / "iRacing" / "screenshots"
