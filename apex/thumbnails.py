"""Grid walk car thumbnails: a folder of pictures the user has made, one per
driver and car, named ``<iRacing ID>.<car name>.png`` (e.g.
``123456.Porsche 911 GT3 R (992).png``; JPG and WebP too).

Each driver in the session is matched to their picture by iRacing ID (their
customer ID) and car: the car name in the file is compared with iRacing's
names for the car they're in (its full and short names, and its folder name,
e.g. ``porsche992rgt3``), ignoring case, spaces and punctuation. A driver with
only one picture gets that one whatever its car name says.
"""

import re
import time
from pathlib import Path

EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
RESCAN_S = 3.0  # look for new or changed files at most this often


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def parse_name(filename):
    """"123456.Porsche 911 GT3 R.png" -> (123456, "Porsche 911 GT3 R"), or None."""
    path = Path(filename)
    if path.suffix.lower() not in EXTENSIONS:
        return None
    cust, dot, car = path.stem.partition(".")
    if not cust.strip().isdigit():
        return None
    return int(cust.strip()), car.strip() if dot else ""


class Thumbnails:
    def __init__(self, folder=None, clock=time.monotonic):
        self.clock = clock
        self.folder = None
        self.error = ""
        self._files = {}     # cust_id -> [(normalised car name, file name)]
        self._count = 0
        self._stamp = None   # (folder mtime, newest file mtime, file count): rescan when it changes
        self._checked = float("-inf")
        self.set_folder(folder)

    def set_folder(self, folder):
        """Use this folder ("" or None: none). Raises ValueError if it isn't one."""
        folder = str(folder or "").strip().strip('"')
        if not folder:
            self.folder, self.error = None, ""
            self._files, self._count, self._stamp = {}, 0, None
            return
        path = Path(folder).expanduser()
        if not path.is_dir():
            raise ValueError(f"Can't find the folder {folder}")
        self.folder, self.error = path, ""
        self._stamp, self._checked = None, float("-inf")
        self.refresh()

    def refresh(self, force=False):
        """Read the folder again if anything in it has changed (cheap to call often)."""
        if self.folder is None:
            return
        now = self.clock()
        if not force and now - self._checked < RESCAN_S:
            return
        self._checked = now
        try:
            entries = [p for p in self.folder.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS]
            stamp = (self.folder.stat().st_mtime, max((p.stat().st_mtime for p in entries), default=0), len(entries))
        except OSError as e:
            self.error = f"Can't read the folder: {e}"
            self._files, self._count = {}, 0
            return
        self.error = ""
        if stamp == self._stamp and not force:
            return
        self._stamp = stamp
        files = {}
        for p in sorted(entries, key=lambda p: p.name.lower()):
            parsed = parse_name(p.name)
            if parsed:
                files.setdefault(parsed[0], []).append((_norm(parsed[1]), p.name))
        self._files = files
        self._count = sum(len(v) for v in files.values())

    @property
    def count(self):
        return self._count

    def match(self, cust_id, car_names=()):
        """The picture for this driver in this car (a file name in the folder), or None."""
        options = self._files.get(cust_id) if isinstance(cust_id, int) else None
        if not options:
            return None
        names = [n for n in (_norm(c) for c in car_names) if n]
        for n in names:  # the same car
            hit = next((f for car, f in options if car and car == n), None)
            if hit:
                return hit
        for n in names:  # one name inside the other ("Porsche 911 GT3 R" / "Porsche 911 GT3 R (992)")
            hit = next((f for car, f in options if car and (car in n or n in car)), None)
            if hit:
                return hit
        return options[0][1] if len(options) == 1 else None

    def path(self, name):
        """The file to serve for ``name`` (a file in the folder, nothing outside it), or None."""
        if self.folder is None or not name or "/" in name or "\\" in name or name.startswith("."):
            return None
        p = self.folder / name
        return p if p.suffix.lower() in EXTENSIONS and p.is_file() else None

    def version(self, name):
        """A number that changes when the file does (for the picture's URL)."""
        p = self.path(name)
        try:
            return int(p.stat().st_mtime) if p else 0
        except OSError:
            return 0
