"""Settings changed from inside the app (rather than in ``config.json``).

Kept in ``data/settings.json``. A value set here wins over ``config.json``.
"""

import json
import threading
from pathlib import Path


class UserSettings:
    def __init__(self, path=None):
        """``path`` None keeps settings in memory only."""
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self.values = {}
        if self.path:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.values = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                pass

    def get(self, key, default=None):
        value = self.values.get(key)
        return default if value in (None, "") else value

    def set(self, key, value):
        with self._lock:
            if value in (None, ""):
                self.values.pop(key, None)
            else:
                self.values[key] = value
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.values, indent=2), encoding="utf-8")
