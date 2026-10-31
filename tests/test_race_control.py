import tempfile
import unittest

from apex.core import CommandError
from tests.test_app import make_app


class RaceControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app, self.source = make_app(self.tmp.name, minutes=1)
        self.car = sorted(self.app._drivers)[2]
        self.number = self.app._drivers[self.car]["number"]

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, action, **params):
        return self.app.command(action, params)["sent"]

    def test_penalties(self):
        n = self.number
        self.assertEqual(self.send("rc_penalty", car_idx=self.car, kind="drive_through"), f"!black #{n} D")
        self.assertEqual(self.send("rc_penalty", car_idx=self.car, kind="stop_go"), f"!black #{n}")
        self.assertEqual(self.send("rc_penalty", car_idx=self.car, kind="stop_hold", amount="30", unit="seconds"), f"!black #{n} 30")
        self.assertEqual(self.send("rc_penalty", car_idx=self.car, kind="stop_hold", amount=2, unit="minutes"), f"!black #{n} 120")
        self.assertEqual(self.send("rc_penalty", car_idx=self.car, kind="stop_hold", amount=3, unit="laps"), f"!black #{n} L3")
        self.assertEqual(self.send("rc_penalty", car_idx=self.car, kind="clear"), f"!clear #{n}")
        self.assertEqual(self.source.chat[-1], f"!clear #{n}")
        log = self.app.build_snapshot()["race_control"]["log"]
        self.assertEqual(len(log), 6)
        self.assertTrue(log[3]["label"].startswith("Stop & hold, 2 minutes: "))
        for bad in ({"kind": "stop_hold", "amount": "", "unit": "seconds"}, {"kind": "stop_hold", "amount": 5, "unit": "hours"},
                    {"kind": "stop_hold", "amount": 120, "unit": "laps"}, {"kind": "slap"}):
            with self.assertRaises(CommandError):
                self.app.command("rc_penalty", dict(car_idx=self.car, **bad))
        with self.assertRaises(CommandError):
            self.app.command("rc_penalty", {"car_idx": 999, "kind": "clear"})
        self.assertEqual(len(self.source.chat), 6)  # nothing sent for those

    def test_race_commands(self):
        self.assertEqual(self.send("rc_clear_all"), "!clearall")
        self.assertEqual(self.send("rc_grid", minutes="5"), "!gridset 5")
        self.assertEqual(self.send("rc_start"), "!gridstart")
        self.assertEqual(self.send("rc_message", text="  Green flag \n next lap "), "Green flag next lap")
        with self.assertRaises(CommandError):
            self.app.command("rc_grid", {"minutes": 0})
        with self.assertRaises(CommandError):
            self.app.command("rc_message", {"text": "   "})

    def test_not_connected(self):
        self.source.connected = False
        with self.assertRaises(CommandError):
            self.app.command("rc_start", {})


if __name__ == "__main__":
    unittest.main()
