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


def real_path(path):
    """``path`` with any junctions or symlinks along it replaced by their targets.

    Newer Windows 11 builds refuse to open a path *through* a junction it
    doesn't trust ("WinError 448: untrusted mount point"). iRacing players
    often move ``Documents\\iRacing`` to another drive with a junction, which
    makes iRacing's screenshot folder unreadable that way. Reading where each
    junction points (which doesn't go through it) gives the real folder.
    """
    path = Path(path)
    if os.name != "nt" or not path.is_absolute():
        return path
    current = Path(path.anchor)
    for part in path.parts[1:]:
        step = current / part
        for _ in range(16):  # links to links, within reason
            try:
                if not (os.path.isjunction(step) or step.is_symlink()):
                    break
                target = os.readlink(step)
            except (OSError, ValueError):
                break
            for prefix in ("\\\\?\\UNC\\", "\\\\?\\", "\\??\\"):
                if target.startswith(prefix):
                    target = ("\\\\" if "UNC" in prefix else "") + target[len(prefix):]
                    break
            target = Path(target)
            step = target if target.is_absolute() else step.parent / target
        current = step
    return current


def is_untrusted_mount_error(error):
    """Windows' "untrusted mount point" refusal (see ``real_path``)."""
    return getattr(error, "winerror", None) == 448
