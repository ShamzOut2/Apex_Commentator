"""Background images for the overlays and boards (their Background setting).

Uploaded once, kept in the user's data folder and offered to every overlay
and board; any of them can use any image.
"""

import hashlib
import re
from pathlib import Path

from .league import sniff_logo

NAME = re.compile(r"bg-[0-9a-f]{12}\.(png|jpg|webp|svg)")


class Backgrounds:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder else None

    def list(self):
        if not self.folder or not self.folder.is_dir():
            return []
        return sorted((f.name for f in self.folder.iterdir() if NAME.fullmatch(f.name)),
                      key=lambda n: (self.folder / n).stat().st_mtime, reverse=True)

    def save(self, data):
        """Store an uploaded image; returns its name. Raises LeagueError if it isn't one."""
        ext = sniff_logo(data)
        name = f"bg-{hashlib.sha256(data).hexdigest()[:12]}.{ext}"
        if self.folder is None:
            raise OSError("no folder to keep backgrounds in")
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / name).write_bytes(data)
        return name

    def file(self, name):
        """Path of a stored background, or None. Guards against path tricks."""
        if not self.folder or not NAME.fullmatch(name or ""):
            return None
        path = self.folder / name
        return path if path.is_file() else None
