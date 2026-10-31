import sys
import unittest

from apex import screenpick


class ScreenPickTests(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "Windows reads the real screen")
    def test_only_on_windows(self):
        self.assertFalse(screenpick.available())
        self.assertIsNone(screenpick.pick(timeout_s=0))


if __name__ == "__main__":
    unittest.main()
