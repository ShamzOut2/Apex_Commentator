"""Photo booth: photograph each driver's car in iRacing for the grid walk.

iRacing is the renderer: for each car the camera is pointed at it, iRacing's
on-screen panels are hidden, and iRacing's own screenshot is triggered (the
same as the screenshot key, so *Video and Screen Capture* must be enabled in
iRacing's settings). That gives the real car with the driver's real livery,
whatever paint they run.

It works in two phases so the camera is only taken over briefly:

1. **Capture**: go down the list taking one screenshot per car, then put the
   camera and panels back as they were. Screenshots are moved out of
   iRacing's folder into ``photobooth/`` in the user data folder.
2. **Process**: cut each car out of its background (see ``cutout``), or just
   resize the shot, and save it as that driver's car photo in the active
   league, which is where the grid walk takes car images from.
"""

import shutil
import threading
import time
from pathlib import Path

from .cutout import CutoutError, crop_only, dependencies_available
from .league import LeagueError, driver_key
from .sources import CAM_UI_HIDDEN

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tga"}
NO_SCREENSHOT_HELP = (
    "No screenshot appeared in {folder}. In iRacing, turn on Settings → Interface → "
    "Camera & Screen Capture → \"Video and Screen Capture\" (then restart iRacing), "
    "or set \"screenshots_dir\" in config.json if iRacing saves them elsewhere."
)


class PhotoBoothError(Exception):
    """A user-facing photo booth problem."""


class PhotoBooth:
    def __init__(self, app, screenshots_dir, store_dir, cutout, settle_s=1.6, shot_timeout_s=8.0, sleep=time.sleep):
        self.app = app
        self.screenshots_dir = Path(screenshots_dir)
        self.store_dir = Path(store_dir)
        self.cutout = cutout
        self.settle_s = settle_s
        self.shot_timeout_s = shot_timeout_s
        self._sleep = sleep
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self._reset()

    def _reset(self):
        self.state = "idle"   # idle | downloading | capturing | processing | done | error | cancelled
        self.error = None
        self.current = None
        self.use_cutout = True
        self.results = []     # one per car, in order

    # -- status ----------------------------------------------------------------

    def status(self):
        return {
            "state": self.state,
            "error": self.error,
            "current": self.current,
            "use_cutout": self.use_cutout,
            "total": len(self.results),
            "captured": sum(1 for r in self.results if r["shot"]),
            "processed": sum(1 for r in self.results if r["state"] in ("saved", "failed")),
            "results": [{k: r[k] for k in ("car_idx", "name", "number", "state", "error", "image")} for r in self.results],
            "cutout_available": dependencies_available(),
            "model_ready": self.cutout.model_ready() if self.cutout else False,
            "model_download": dict(self.cutout.download) if self.cutout else None,
            "screenshots_dir": str(self.screenshots_dir),
        }

    @property
    def busy(self):
        return self.state in ("downloading", "capturing", "processing")

    # -- control ---------------------------------------------------------------

    def start(self, car_idxs, group, use_cutout=True):
        with self._lock:
            if self.busy:
                raise PhotoBoothError("The photo booth is already running.")
            league = self.app.leagues.active()
            if not league:
                raise PhotoBoothError("Activate a league first (League builder): photos are saved to it.")
            drivers = self.app._drivers
            cars = [drivers[i] for i in car_idxs if i in drivers]
            if not cars:
                raise PhotoBoothError("No drivers to photograph.")
            if use_cutout and not dependencies_available():
                raise PhotoBoothError("Background cut-out isn't available in this install.")
            self._reset()
            self.use_cutout = use_cutout
            self.results = [{"car_idx": d["car_idx"], "name": d["name"], "number": d["number"], "cust_id": d["cust_id"],
                             "state": "waiting", "error": None, "image": None, "shot": None} for d in cars]
            self._cancel.clear()
            self.state = "downloading" if use_cutout and not self.cutout.model_ready() else "capturing"
            self._thread = threading.Thread(target=self._run, args=(league["id"], group), name="photobooth", daemon=True)
            self._thread.start()

    def cancel(self):
        self._cancel.set()

    # -- work --------------------------------------------------------------------

    def _run(self, league_id, group):
        try:
            if self.state == "downloading":
                self.cutout.ensure_model()
                self.state = "capturing"
            self._capture_all(group)
            if self._cancel.is_set():
                self.state = "cancelled"
            self._process_all(league_id)
            if self.state != "cancelled":
                failed = [r for r in self.results if r["state"] != "saved"]
                self.state = "error" if failed and len(failed) == len(self.results) else "done"
                if self.state == "error" and not self.error:
                    self.error = failed[0]["error"]
        except (PhotoBoothError, CutoutError, LeagueError, OSError) as e:
            self.state, self.error = "error", str(e)
        finally:
            self.current = None
            self.app.publish()

    def _image_files(self):
        if not self.screenshots_dir.is_dir():
            return {}
        return {p: p.stat().st_mtime for p in self.screenshots_dir.iterdir()
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS}

    def _wait_for_new_shot(self, before):
        """The file iRacing writes after the screenshot trigger, once fully written."""
        waited = 0.0
        last_size = None
        while waited < self.shot_timeout_s:
            self._sleep(0.25)
            waited += 0.25
            new = [p for p, m in self._image_files().items() if p not in before or m > before[p]]
            if not new:
                continue
            path = max(new, key=lambda p: p.stat().st_mtime)
            size = path.stat().st_size
            if size and size == last_size:
                return path
            last_size = size
        return None

    def _capture_all(self, group):
        source = self.app.source
        frame = self.app._frame
        prev_car, prev_group, prev_state = (frame.cam_car_idx, frame.cam_group, frame.cam_state) if frame else (-1, 0, 0)
        raw_dir = self.store_dir / "raw" / time.strftime("%Y%m%d-%H%M%S")
        raw_dir.mkdir(parents=True, exist_ok=True)
        group = int(group or prev_group or 0)
        try:
            source.cam_set_state(prev_state | CAM_UI_HIDDEN)
            for r in self.results:
                if self._cancel.is_set():
                    break
                self.current = r["name"]
                r["state"] = "capturing"
                self.app.publish()
                source.cam_switch_num(r["number"], group, 0)
                self._sleep(self.settle_s)
                before = self._image_files()
                source.screenshot()
                shot = self._wait_for_new_shot(before)
                if shot is None:
                    r["state"], r["error"] = "failed", "No screenshot"
                    if not any(x["shot"] for x in self.results):
                        # Nothing has worked at all: almost certainly a setting.
                        raise PhotoBoothError(NO_SCREENSHOT_HELP.format(folder=self.screenshots_dir))
                    continue
                safe = "".join(c if c.isalnum() else "-" for c in f"{r['number']}-{r['name']}").strip("-")
                dest = raw_dir / f"{safe}{shot.suffix.lower()}"
                shutil.move(str(shot), dest)
                r["shot"], r["state"] = dest, "captured"
        finally:
            # Put the broadcast back the way it was.
            prev = self.app._drivers.get(prev_car)
            if prev:
                source.cam_switch_num(prev["number"], prev_group, 0)
            source.cam_set_state(prev_state)

    def _process_all(self, league_id):
        if self.state != "cancelled":
            self.state = "processing"
        leagues = self.app.leagues
        for r in self.results:
            if not r["shot"] or r["state"] == "failed":
                continue
            self.current = r["name"]
            r["state"] = "processing"
            self.app.publish()
            try:
                data = r["shot"].read_bytes()
                image = self.cutout.cut(data) if self.use_cutout else crop_only(data)
                key = leagues.ensure_driver(league_id, r["cust_id"], r["name"], r["number"])
                profile = leagues.save_image(league_id, f"car:{key}", image)
                saved = next(d for d in profile["drivers"] if driver_key(d) == key)
                r["image"] = f"/api/logos/{profile['id']}/{saved['car_image']}"
                r["state"] = "saved"
            except (CutoutError, LeagueError, OSError, StopIteration) as e:
                r["state"], r["error"] = "failed", str(e) or "Couldn't save the photo"
