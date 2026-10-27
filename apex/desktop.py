"""Desktop integration: the app window, single instance, message boxes, log file.

The control panel is the same web UI as in a browser, shown in a native
window through pywebview (Edge WebView2 on Windows). Without pywebview the
app falls back to the default browser.
"""

import ctypes
import importlib.util
import sys
import threading

from .paths import APP_NAME, FROZEN, USER_DIR

# The installer waits for this mutex to disappear before replacing files.
MUTEX_NAME = "ApexCommentatorRunning"
ERROR_ALREADY_EXISTS = 183
IS_WINDOWS = sys.platform == "win32"

_mutex = None


def log_to_file():
    """Send output to a log file when there is no console (the packaged app)."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    USER_DIR.mkdir(parents=True, exist_ok=True)
    log = open(USER_DIR / "apex.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    return log


def alert(message, error=False):
    """Tell the user something: a message box in the packaged app, else the console."""
    print(message)
    if IS_WINDOWS and FROZEN:
        flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, str(message), APP_NAME, flags)


def claim_single_instance():
    """True if this is the only running copy (always True off Windows)."""
    global _mutex
    if not IS_WINDOWS:
        return True
    kernel32 = ctypes.windll.kernel32
    _mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def window_available():
    try:
        return importlib.util.find_spec("webview") is not None
    except (ImportError, ValueError):
        return False


def run_window(url, title, close_event):
    """Show the control panel in a native window. Blocks until it is closed.

    Setting ``close_event`` (e.g. for an update restart) closes the window.
    Returns False if no window could be opened, so the caller can fall back.
    """
    import webview

    try:
        window = webview.create_window(
            title, url, width=1440, height=900, min_size=(960, 600), background_color="#0f1115",
        )

        def watch():
            close_event.wait()
            window.destroy()

        threading.Thread(target=watch, name="window-close", daemon=True).start()
        # Keep localStorage (small UI preferences) between launches.
        webview.start(private_mode=False, storage_path=str(USER_DIR / "webview"))
    except Exception as e:  # e.g. WebView2 runtime missing
        print(f"[apex] couldn't open the app window: {e!r}")
        return False
    return True
