import tempfile
import unittest
from pathlib import Path

from apex.thumbnails import Thumbnails, parse_name
from tests.test_app import make_app

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16


def picture(folder, name, data=PNG):
    (Path(folder) / name).write_bytes(data)


class NameTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(parse_name("123456.Porsche 911 GT3 R (992).png"), (123456, "Porsche 911 GT3 R (992)"))
        self.assertEqual(parse_name("123456.bmwm4gt3.JPG"), (123456, "bmwm4gt3"))
        self.assertEqual(parse_name("123456.png"), (123456, ""))
        self.assertIsNone(parse_name("Joe Bloggs.Porsche.png"))   # not an iRacing ID
        self.assertIsNone(parse_name("123456.Porsche.gif"))       # not a picture we use
        self.assertIsNone(parse_name("notes.txt"))


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        for name in ("111.Porsche 911 GT3 R (992).png", "111.BMW M4 GT3.png", "222.mclaren720sgt3.webp",
                     "333.Ferrari 296 GT3.jpg", "readme.txt"):
            picture(d, name)
        self.clock = [0.0]
        self.th = Thumbnails(d, clock=lambda: self.clock[0])

    def tearDown(self):
        self.tmp.cleanup()

    def test_by_id_and_car(self):
        th = self.th
        self.assertEqual(th.count, 4)
        # The same driver in two cars: the one they're in.
        self.assertEqual(th.match(111, ["BMW M4 GT3", "BMW M4 GT3", "bmwm4gt3"]), "111.BMW M4 GT3.png")
        self.assertEqual(th.match(111, ["Porsche 911 GT3 R (992)"]), "111.Porsche 911 GT3 R (992).png")
        # Named after iRacing's car folder; or a shorter name for the car.
        self.assertEqual(th.match(222, ["McLaren 720S GT3", "McLaren 720S GT3", "mclaren720sgt3"]), "222.mclaren720sgt3.webp")
        self.assertEqual(th.match(111, ["Porsche 911 GT3 R"]), "111.Porsche 911 GT3 R (992).png")
        # Only one picture: that one, whatever the car. Several and none fit: none.
        self.assertEqual(th.match(333, ["Audi R8 LMS EVO II GT3"]), "333.Ferrari 296 GT3.jpg")
        self.assertIsNone(th.match(111, ["Audi R8 LMS EVO II GT3"]))
        self.assertIsNone(th.match(999, ["BMW M4 GT3"]))
        self.assertIsNone(th.match(None, ["BMW M4 GT3"]))

    def test_new_pictures_and_safe_paths(self):
        picture(self.tmp.name, "999.Audi R8 LMS EVO II GT3.png")
        self.th.refresh()
        self.assertIsNone(self.th.match(999, ["Audi R8 LMS EVO II GT3"]))  # not looked at again yet
        self.clock[0] += 5
        self.th.refresh()
        self.assertEqual(self.th.match(999, ["Audi R8 LMS EVO II GT3"]), "999.Audi R8 LMS EVO II GT3.png")
        self.assertIsNone(self.th.path("../secret.png"))
        self.assertIsNone(self.th.path("readme.txt"))
        self.assertTrue(self.th.path("333.Ferrari 296 GT3.jpg"))
        with self.assertRaises(ValueError):
            self.th.set_folder(str(Path(self.tmp.name) / "nope"))


class GridWalkPictureTests(unittest.TestCase):
    def test_grid_walk_uses_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as pics:
            app, _ = make_app(tmp, minutes=1)
            entries = app.build_snapshot()["gridwalk"]["entries"]
            first, second = entries[0], entries[1]
            picture(pics, f"{first['cust_id']}.{first['car_name']}.png")
            picture(pics, f"{second['cust_id']}.Some Other Car.png")
            picture(pics, f"{second['cust_id']}.Another Car.png")
            self.assertEqual(app.command("gridwalk_folder", {"folder": pics}), {"folder": pics, "count": 3})
            self.assertEqual(app.settings.get("gridwalk_thumbs_dir"), pics)
            g = app.build_snapshot()["gridwalk"]
            a, b = g["entries"][0], g["entries"][1]
            self.assertTrue(a["has_thumb"])
            self.assertTrue(a["car_image"].startswith(f"/api/thumbs/{first['cust_id']}."))
            self.assertFalse(b["has_thumb"])  # two pictures, neither of this car
            self.assertEqual((g["thumbs"]["count"], g["thumbs"]["matched"]), (3, 1))
            app.command("gridwalk_folder", {"folder": ""})
            self.assertIsNone(app.settings.get("gridwalk_thumbs_dir"))


if __name__ == "__main__":
    unittest.main()
