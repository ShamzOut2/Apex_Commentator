import io
import tempfile
import time
import unittest
from pathlib import Path

from apex.config import DEFAULTS
from apex.core import App, CommandError
from apex.cutout import Cutout, CutoutError, dependencies_available, keep_central_object
from apex.league import LeagueStore, profile_from_session
from apex.photobooth import PhotoBooth
from apex.sources import CAM_UI_HIDDEN, MockSource

HAVE_IMAGING = dependencies_available()


class FakeCutout:
    """Stands in for the AI model: returns a tiny PNG."""

    def __init__(self):
        self.download = {"state": "idle", "done": 0, "total": 0, "error": None}
        self.calls = 0

    def model_ready(self):
        return True

    def ensure_model(self):
        return None

    def cut(self, data):
        self.calls += 1
        return b"\x89PNG\r\n\x1a\n" + b"\0" * 16


def wait_until(predicate, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@unittest.skipUnless(HAVE_IMAGING, "Pillow/numpy/onnxruntime not installed")
class PhotoBoothTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source = MockSource(seed=5)
        self.source.screenshots_dir = root / "shots"
        self.app = App(self.source, dict(DEFAULTS), LeagueStore(root / "leagues"))
        for _ in range(5):
            self.app.tick()
        snap = self.app.build_snapshot()
        league = self.app.leagues.save(profile_from_session(snap["drivers"][:3], "Booth League"))
        self.app.leagues.set_active(league["id"])
        self.cutout = FakeCutout()
        self.booth = PhotoBooth(self.app, root / "shots", root / "booth", self.cutout,
                                settle_s=0, sleep=lambda s: time.sleep(0.01))
        self.app.photobooth = self.booth

    def tearDown(self):
        self.tmp.cleanup()

    def run_booth(self, **params):
        self.app.command("photobooth_start", params)
        self.assertTrue(wait_until(lambda: not self.booth.busy))
        return self.booth.status()

    def test_photographs_every_loaded_car_and_saves_to_the_league(self):
        self.app.command("watch", {"car_idx": 3, "group": 2})
        self.app.tick()
        self.source.commands.clear()
        status = self.run_booth(group=9)
        self.assertEqual(status["state"], "done", status["error"])
        self.assertEqual(status["total"], len(self.app._drivers))
        self.assertTrue(all(r["state"] == "saved" for r in status["results"]))
        self.assertEqual(self.cutout.calls, status["total"])
        # Every driver, in or not yet in the roster, now has a car photo.
        league = self.app.leagues.active()
        self.assertEqual(len(league["drivers"]), status["total"])
        self.assertTrue(all(d["car_image"] for d in league["drivers"]))
        grid = self.app.build_snapshot()["gridwalk"]["entries"]
        self.assertTrue(all(e["car_image"].startswith(f"/api/logos/{league['id']}/car-") for e in grid))
        # iRacing's panels were hidden for the shots and the camera put back after.
        cmds = self.source.commands
        self.assertEqual(cmds[0], ("cam_set_state", CAM_UI_HIDDEN))
        self.assertEqual(sum(1 for c in cmds if c[0] == "screenshot"), status["total"])
        shots = [c for c in cmds if c[0] == "cam_switch_num"][:-1]
        self.assertTrue(all(c[2] == 9 for c in shots))  # the chosen camera group
        self.assertEqual(cmds[-2], ("cam_switch_num", self.app._drivers[3]["number"], 2, 0))
        self.assertEqual(cmds[-1], ("cam_set_state", 0))
        # Raw shots moved out of iRacing's folder into the app's own.
        self.assertEqual(list((Path(self.tmp.name) / "shots").glob("*.png")), [])
        self.assertEqual(len(list((Path(self.tmp.name) / "booth" / "raw").rglob("*.png"))), status["total"])

    def test_single_car(self):
        status = self.run_booth(car_idx=2)
        self.assertEqual([r["car_idx"] for r in status["results"]], [2])
        self.assertEqual(status["state"], "done")

    def test_without_cutout_saves_a_resized_jpeg(self):
        status = self.run_booth(car_idx=2, cutout=False)
        self.assertEqual(status["state"], "done", status["error"])
        self.assertEqual(self.cutout.calls, 0)
        self.assertTrue(status["results"][0]["image"].endswith(".jpg"))

    def test_explains_when_iracing_saves_no_screenshots(self):
        self.source.screenshots_dir = None  # iRacing's capture setting is off
        self.booth.shot_timeout_s = 0.3
        status = self.run_booth()
        self.assertEqual(status["state"], "error")
        self.assertIn("Video and Screen Capture", status["error"])
        self.assertEqual(self.source.commands[-1], ("cam_set_state", 0))  # still restored

    def test_needs_an_active_league_and_one_run_at_a_time(self):
        self.app.leagues.set_active(None)
        with self.assertRaises(CommandError):
            self.app.command("photobooth_start", {})
        self.app.leagues.set_active(self.app.leagues.list()[0]["id"])
        self.booth.settle_s = 0.2
        self.app.command("photobooth_start", {})
        with self.assertRaises(CommandError):
            self.app.command("photobooth_start", {})
        self.app.command("photobooth_cancel", {})
        self.assertTrue(wait_until(lambda: not self.booth.busy))
        self.assertEqual(self.booth.state, "cancelled")


class FakeDownload:
    def __init__(self, data):
        self.data = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n=-1):
        return self.data.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class CutoutModelTests(unittest.TestCase):
    def test_download_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = Cutout(tmp, opener=lambda req, timeout=None: FakeDownload(b"not the model"))
            with self.assertRaises(CutoutError):
                c.ensure_model()
            self.assertFalse(c.model_ready())
            self.assertEqual(list(Path(tmp).iterdir()), [])  # partial file cleaned up
            self.assertEqual(c.download["state"], "error")

    def test_existing_model_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "isnet-general-use.onnx").write_bytes(b"x")
            c = Cutout(tmp, opener=lambda *a, **k: self.fail("should not download"))
            self.assertTrue(c.model_ready())
            self.assertEqual(c.ensure_model().name, "isnet-general-use.onnx")


    @unittest.skipUnless(HAVE_IMAGING, "Pillow/numpy not installed")
    def test_keeps_the_object_in_the_middle(self):
        from PIL import Image, ImageDraw
        mask = Image.new("L", (800, 400), 0)
        d = ImageDraw.Draw(mask)
        d.rectangle([0, 150, 160, 330], fill=255)      # neighbouring car at the edge
        d.rectangle([250, 100, 650, 320], fill=255)    # the car on camera
        out = keep_central_object(mask)
        self.assertEqual(out.getpixel((450, 200)), 255)
        self.assertEqual(out.getpixel((80, 240)), 0)
        bbox = out.point(lambda v: 255 if v > 24 else 0).getbbox()
        self.assertTrue(240 <= bbox[0] <= 252 and 648 <= bbox[2] <= 660, bbox)

    @unittest.skipUnless(HAVE_IMAGING, "Pillow/numpy not installed")
    def test_separates_a_car_that_only_touches(self):
        from PIL import Image, ImageDraw
        mask = Image.new("L", (800, 400), 0)
        d = ImageDraw.Draw(mask)
        d.rectangle([0, 150, 236, 330], fill=255)      # neighbour...
        d.rectangle([236, 280, 252, 300], fill=255)    # ...its wheel touching the bumper of...
        d.rectangle([250, 100, 650, 320], fill=255)    # ...the car on camera
        out = keep_central_object(mask)
        self.assertEqual(out.getpixel((450, 200)), 255)
        self.assertEqual(out.getpixel((80, 240)), 0)


if __name__ == "__main__":
    unittest.main()
