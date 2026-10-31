"""An eyedropper: the colour of the screen where the user next clicks (Windows).

The colour boxes' own eyedropper (in the system colour picker) doesn't work
inside the app window, so the app does it itself: ``pick()`` waits for a
left click anywhere on screen (Esc or the time running out cancels) and
returns the colour of that pixel as "#rrggbb". Elsewhere it returns None
(a browser uses its own EyeDropper instead).
"""

import sys
import time

VK_LBUTTON, VK_ESCAPE = 0x01, 0x1B
POLL_S = 0.01


def available():
    return sys.platform == "win32"


def pick(timeout_s=20.0, clock=time.monotonic, sleep=time.sleep):
    """"#rrggbb" of the pixel the user clicks, or None (cancelled, timed out, not Windows)."""
    if not available():
        return None
    import ctypes
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    down = lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)  # noqa: E731
    end = clock() + timeout_s
    # The click on the eyedropper button itself: wait for it to be let go first.
    while down(VK_LBUTTON) and clock() < end:
        sleep(POLL_S)
    while clock() < end:
        if down(VK_ESCAPE):
            return None
        if down(VK_LBUTTON):
            pt = wintypes.POINT()
            if not user32.GetCursorPos(ctypes.byref(pt)):
                return None
            dc = user32.GetDC(None)
            try:
                c = gdi32.GetPixel(dc, pt.x, pt.y)
            finally:
                user32.ReleaseDC(None, dc)
            if c == 0xFFFFFFFF:  # CLR_INVALID
                return None
            return f"#{c & 0xFF:02x}{(c >> 8) & 0xFF:02x}{(c >> 16) & 0xFF:02x}"
        sleep(POLL_S)
    return None
