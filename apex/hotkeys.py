"""System-wide hotkeys (Windows): the Hotkeys window's keys with Ctrl or Alt in
them work whichever program is in front (iRacing, OBS...).

Plain keys (1, C...) stay in the app's own windows, so they never take
ordinary typing away from other programs. A combination is written like
"ctrl+alt+1" or "ctrl+shift+c" (see keyOf in web/app.js) and is registered
with Windows (RegisterHotKey) on a thread of its own, which runs the action
when it's pressed. One another program already holds is reported as taken.
"""

import ctypes
import sys
import threading

IS_WINDOWS = sys.platform == "win32"
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
WM_HOTKEY, WM_APP = 0x0312, 0x8000
MODS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT}


def parse(combo):
    """"ctrl+alt+1" -> (modifiers, virtual key), or None if it can't be system-wide."""
    parts = str(combo or "").lower().split("+")
    base, mods = parts[-1], parts[:-1]
    if not mods or any(m not in MODS for m in mods) or not ({"ctrl", "alt"} & set(mods)):
        return None
    if len(base) == 1 and ("a" <= base <= "z" or "0" <= base <= "9"):
        vk = ord(base.upper())
    elif base.startswith("num") and base[3:].isdigit() and len(base) == 4:
        vk = 0x60 + int(base[3:])                    # number pad 0-9
    elif base.startswith("f") and base[1:].isdigit() and 1 <= int(base[1:]) <= 24:
        vk = 0x70 + int(base[1:]) - 1                # F1-F24
    elif base == " ":
        vk = 0x20
    else:
        return None
    flags = 0
    for m in mods:
        flags |= MODS[m]
    return flags, vk


def system_wide(mapping):
    """The part of {key: action} that can be system-wide (has Ctrl or Alt)."""
    return {k: a for k, a in (mapping or {}).items() if parse(k)}


class GlobalHotkeys:
    def __init__(self, run):
        """``run(action)`` is called (on a thread of its own) when a hotkey is pressed."""
        self.run = run
        self.available = IS_WINDOWS
        self.taken = []          # combinations another program holds
        self._wanted = {}
        self._ids = {}           # hotkey id -> action
        self._tid = None
        self._ready = threading.Event()
        if self.available:
            threading.Thread(target=self._loop, name="hotkeys", daemon=True).start()
            self._ready.wait(2)

    def set(self, mapping):
        """Use these {combination: action} (anything not system-wide is left out)."""
        self._wanted = system_wide(mapping)
        if self.available and self._tid:
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_APP + 1, 0, 0)

    def _loop(self):
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        msg = wintypes.MSG()
        # A message queue for this thread before anyone posts to it.
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self._tid = kernel32.GetCurrentThreadId()
        self._ready.set()
        self._apply(user32)
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                action = self._ids.get(msg.wParam)
                if action:
                    threading.Thread(target=self._fire, args=(action,), daemon=True).start()
            elif msg.message == WM_APP + 1:
                self._apply(user32)

    def _fire(self, action):
        try:
            self.run(action)
        except Exception as e:  # a hotkey that can't do its thing right now (no car on camera...)
            print(f"[apex] hotkey {action}: {e}")

    def _apply(self, user32):
        """Hotkeys can only be registered on the thread that listens for them: here."""
        for hid in list(self._ids):
            user32.UnregisterHotKey(None, hid)
        self._ids, taken = {}, []
        for hid, (combo, action) in enumerate(sorted(self._wanted.items()), start=1):
            mods, vk = parse(combo)
            if user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk):
                self._ids[hid] = action
            else:
                taken.append(combo)
        self.taken = taken
        if taken:
            print(f"[apex] hotkeys taken by another program: {', '.join(taken)}")
