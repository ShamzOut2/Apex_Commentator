"""Desktop integration: the app window, single instance, message boxes, log file.

The control panel is the same web UI as in a browser, shown in a native
window through pywebview (Edge WebView2 on Windows). Without pywebview the
app falls back to the default browser.
"""

import ctypes
import importlib.util
import os
import sys
import threading

from .paths import APP_NAME, FROZEN, USER_DIR

# The installer waits for this mutex to disappear before replacing files.
MUTEX_NAME = "ApexCommentatorRunning"
ERROR_ALREADY_EXISTS = 183
IS_WINDOWS = sys.platform == "win32"

_mutex = None
_main_window = None
_popouts = {}  # page -> its pop-out window
_overlays = {}  # overlay page -> (its on-screen window, the screen it's on)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80, 0x80000, 0x8000000
SWP_REFRESH = 0x1 | 0x2 | 0x4 | 0x10 | 0x20  # no size / move / z-order / activate; frame changed
DWM_BB_ENABLE, DWM_BB_BLURREGION, RGN_OR = 0x1, 0x2, 2


LOG_MAX, LOG_KEEP = 5_000_000, 1_000_000  # apex.log: trimmed to its last 1 MB once it's over 5 MB


def trim_log(path, most=None, keep=None):
    """The log is added to on every run: past ``most`` bytes, only its last
    ``keep`` (from a line's start) are kept."""
    most, keep = most or LOG_MAX, keep or LOG_KEEP
    try:
        if path.stat().st_size > most:
            with open(path, "rb") as f:
                f.seek(-keep, os.SEEK_END)
                tail = f.read()
            path.write_bytes(tail[tail.find(b"\n") + 1:])
    except OSError:
        pass


def log_to_file():
    """Send output to a log file when there is no console (the packaged app)."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    USER_DIR.mkdir(parents=True, exist_ok=True)
    path = USER_DIR / "apex.log"
    trim_log(path)
    log = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    return log


def alert(message, error=False):
    """Tell the user something: a message box in the packaged app, else the console."""
    print(message)
    if IS_WINDOWS and FROZEN:
        flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, str(message), APP_NAME, flags)


def reveal(path):
    """Show a file (selected) or folder in the file manager. False if it couldn't."""
    import subprocess

    path = str(path)
    try:
        if IS_WINDOWS:
            subprocess.Popen(["explorer", f"/select,{path}"] if not os.path.isdir(path) else ["explorer", path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
        return True
    except OSError:
        return False


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

    global _main_window
    try:
        window = webview.create_window(
            title, url, width=1440, height=900, min_size=(960, 600), background_color="#0f1115",
        )
        _main_window = window
        # Pop-outs close with the main window.
        window.events.closed += _close_popouts

        def watch():
            close_event.wait()
            window.destroy()

        threading.Thread(target=watch, name="window-close", daemon=True).start()
        # Keep localStorage (small UI preferences) between launches.
        webview.start(private_mode=False, storage_path=str(USER_DIR / "webview"))
    except Exception as e:  # e.g. WebView2 runtime missing
        print(f"[apex] couldn't open the app window: {e!r}")
        return False
    finally:
        _main_window = None
    return True


def open_popout(key, url, title, width=1280, height=820):
    """Open a page of the control panel in a window of its own (or bring its
    pop-out back if it's already open). False when there's no app window, so
    the page opens it as a browser window instead."""
    if _main_window is None:
        return False
    import webview

    window = _popouts.get(key)
    if window is not None:
        try:
            window.restore()
            window.show()
            # No "focus" call in pywebview: briefly on top brings it forward.
            window.on_top = True
            window.on_top = False
            return True
        except Exception:
            _popouts.pop(key, None)
    window = webview.create_window(title, url, width=width, height=height, min_size=(480, 320),
                                   background_color="#0f1115")
    window.events.closed += lambda: _popouts.pop(key, None)
    _popouts[key] = window
    return True


def _close_popouts():
    for window in list(_popouts.values()) + list(_windows.values()):
        try:
            window.destroy()
        except Exception:
            pass
    _popouts.clear()
    _overlays.clear()
    _windows.clear()


# -- on-screen overlays ---------------------------------------------------------
#
# An overlay or board straight on the user's screen, instead of in OBS or a
# browser: a borderless window covering one monitor, always on top, that
# never takes the keyboard and lets the mouse through to whatever is under it
# (iRacing, this app). Needs the app window (pywebview, WebView2 on Windows).
#
# Two things keep it to the overlay itself, as Tauri does for the Apex
# Overlays app's windows:
# - The window is clipped to where the page draws something (the tower, the
#   fastest-lap pill...): the page reports those rectangles (common.js) and
#   the window is cut to them (set_region). Everywhere else the window isn't
#   there at all, so it can't cover the screen or catch the mouse, whatever
#   else happens.
# - Inside that, see-through by its own transparency: the browser view's
#   background is transparent (transparent=True) and Windows' compositor is
#   told to use the window's transparency (blur-behind with an empty region).
# Opening and closing run one at a time on their own thread, so a slow window
# never holds up the app, and each waits for the last to finish.

_jobs = None  # queue of overlay jobs, and the thread working through it
WM_CLOSE, SW_HIDE = 0x10, 0


def _run(job):
    global _jobs
    if _jobs is None:
        import queue

        _jobs = queue.Queue()

        def work():
            while True:
                fn = _jobs.get()
                try:
                    fn()
                except Exception as e:
                    print(f"[apex] on-screen overlay: {e!r}")

        threading.Thread(target=work, name="on-screen-overlays", daemon=True).start()
    _jobs.put(job)


def screens():
    """The monitors: [{index, width, height, x, y}]; [] without the app window."""
    if _main_window is None:
        return []
    try:
        import webview

        return [{"index": i, "width": s.width, "height": s.height, "x": s.x, "y": s.y}
                for i, s in enumerate(webview.screens)]
    except Exception as e:
        print(f"[apex] couldn't list the screens: {e!r}")
        return []


def show_overlay(key, url, title, screen=0):
    """Put a page on screen ``screen`` as an overlay (moving it if it's already
    up). False when there's no app window to do it from."""
    if _main_window is None:
        return False
    _overlays[key] = (None, screen)  # on its way: shown as up straight away
    _run(lambda: _show(key, url, title, screen))
    return True


def hide_overlay(key=None):
    """Take an on-screen overlay down (every one, with no ``key``)."""
    keys = [key] if key else list(_overlays)
    for k in keys:
        _overlays.pop(k, None)
    _run(lambda: [_close(k) for k in keys])


def overlays_on_screen():
    """{overlay page: screen index} of what's up."""
    return {k: screen for k, (_, screen) in _overlays.items()}


_windows = {}  # overlay page -> its window, while it's open (the worker's own record)
_hwnds = {}    # window -> its native handle, to close it by hand if need be


def _show(key, url, title, screen):
    import webview

    _close(key)  # moving screens, or shown again: the old one goes first
    if key not in _overlays:
        return  # taken down again before it got here
    monitors = webview.screens
    _regions.pop(key, None)  # the new page reports its own
    window = webview.create_window(
        title, url, screen=monitors[screen] if 0 <= screen < len(monitors) else None,
        fullscreen=True, frameless=True, on_top=True, focus=False, shadow=False, easy_drag=False,
        resizable=False, transparent=True, background_color="#000000",
    )
    _windows[key] = window
    _overlays[key] = (window, screen)

    def closed():
        # Closed some other way (e.g. Alt+F4): no longer up.
        if _windows.get(key) is window:
            _windows.pop(key, None)
            if _overlays.get(key, (None,))[0] is window:
                _overlays.pop(key, None)

    window.events.closed += closed
    # Windows opened once the app is running are made there and then; if not
    # yet, as soon as it's shown.
    if window.native is not None:
        _see_through(key, window)
    else:
        window.events.shown += lambda: _see_through(key, window)


def _close(key):
    """Close a page's overlay window and wait for it to go (by hand if it won't)."""
    window = _windows.pop(key, None)
    if window is None:
        return
    try:
        window.destroy()
    except Exception as e:
        print(f"[apex] couldn't close the overlay window: {e!r}")
    if not window.events.closed.wait(3) and IS_WINDOWS:
        hwnd = _hwnds.get(window)
        if hwnd:
            print("[apex] overlay window didn't close: closing it by hand")
            ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
            ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    _hwnds.pop(window, None)


_regions = {}  # overlay page -> the rectangles its page last reported (window pixels; None: all of it)


def _win32():
    """user32 / gdi32 / dwmapi with the argument types the calls below need."""
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    gdi32.CreateRectRgn.restype = wintypes.HRGN
    gdi32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
    gdi32.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
    return user32, gdi32, ctypes.windll.dwmapi


class _BlurBehind(ctypes.Structure):
    from ctypes import wintypes as _w
    _fields_ = [("dwFlags", _w.DWORD), ("fEnable", _w.BOOL), ("hRgnBlur", _w.HRGN), ("fTransitionOnMaximized", _w.BOOL)]


def _clip(hwnd, rects):
    """Cut the window to ``rects`` ([x, y, width, height] in window pixels;
    [] = nothing shows, None = the whole window)."""
    user32, gdi32, _ = _win32()
    if rects is None:
        user32.SetWindowRgn(hwnd, None, True)
        return
    region = gdi32.CreateRectRgn(0, 0, 0, 0)
    for x, y, w, h in rects:
        part = gdi32.CreateRectRgn(x, y, x + w, y + h)
        gdi32.CombineRgn(region, region, part, RGN_OR)
        gdi32.DeleteObject(part)
    if not user32.SetWindowRgn(hwnd, region, True):  # on success Windows owns the region
        gdi32.DeleteObject(region)


def set_region(key, rects):
    """The parts of an on-screen overlay's page that show (see _clip)."""
    _regions[key] = rects
    hwnd = _hwnds.get(_windows.get(key))
    if hwnd and IS_WINDOWS:
        try:
            _clip(hwnd, rects)
        except Exception as e:
            print(f"[apex] couldn't fit the overlay window to its overlay: {e!r}")


def _see_through(key, window):
    """Make the overlay window see-through where the page is, and let every
    click through: what Tauri does for a transparent, click-through window
    (blur-behind with an empty region, then a layered, click-through tool
    window), and cut it to the parts of the page that show."""
    if not IS_WINDOWS:
        return
    try:
        from System import Func, Type
        from System.Drawing import Color

        form = window.native
        user32, gdi32, dwmapi = _win32()
        steps = []

        def apply():
            try:
                form.browser.webview.DefaultBackgroundColor = Color.Transparent  # the page's empty parts
            except Exception:
                pass  # pywebview set it already (transparent=True)
            form.BackColor = Color.Black  # what the compositor treats as see-through
            hwnd = int(form.Handle.ToInt64())
            _hwnds[window] = hwnd
            _clip(hwnd, _regions.get(key, []))  # nothing shows until the page says where it draws
            steps.append("clipped")
            empty = gdi32.CreateRectRgn(0, 0, -1, -1)
            blur = _BlurBehind(DWM_BB_ENABLE | DWM_BB_BLURREGION, True, empty, False)
            result = dwmapi.DwmEnableBlurBehindWindow(hwnd, ctypes.byref(blur))
            gdi32.DeleteObject(empty)
            steps.append(f"blur-behind {'on' if result == 0 else f'failed ({result & 0xFFFFFFFF:#x})'}")
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
                                  | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_REFRESH)
            steps.append("click-through")

        form.Invoke(Func[Type](apply))
        print(f"[apex] on-screen overlay '{key}': {', '.join(steps)}")
    except Exception as e:  # the trial in the app takes it down again if it came up solid
        print(f"[apex] couldn't make the overlay '{key}' see-through: {e!r}")
