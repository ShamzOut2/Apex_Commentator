"""IRacingSource against a stand-in for pyirsdk (the real one needs Windows + the sim)."""

import sys
import tempfile
import types
import unittest

from apex.config import DEFAULTS
from apex.core import App
from apex.league import LeagueStore


class FakeIRSDK:
    def __init__(self):
        self.is_initialized = False
        self.is_connected = False
        self.session_info_update = 1
        self.sent = []
        self.frozen = False
        self.sim_running = True
        self.startups = 0
        self.vars = {
            "SessionTime": 61.5, "SessionNum": 2, "SessionState": 4, "SessionFlags": 0,
            "CamCarIdx": 1, "CamGroupNumber": 9, "ReplayFrameNumEnd": 1,
            "ReplaySessionTime": 61.5, "ReplaySessionNum": 2, "ReplayPlaySpeed": 1,
            "CarIdxLap": [-1, 3, 3], "CarIdxLapDistPct": [-1.0, 0.5, 0.48],
            "CarIdxPosition": [0, 1, 2], "CarIdxClassPosition": [0, 1, 2],
            "CarIdxOnPitRoad": [False, False, False], "CarIdxTrackSurface": [-1, 3, 3],
            "CarIdxF2Time": [0.0, 0.0, 1.2], "CarIdxLastLapTime": [-1.0, 90.1, 90.5],
            "CarIdxBestLapTime": [-1.0, 89.9, 90.2],
        }
        self.info = {
            "WeekendInfo": {"TrackDisplayName": "Spa", "TrackLength": "6.93 km"},
            "SessionInfo": {"Sessions": [{"SessionNum": 2, "SessionType": "Race", "SessionName": "RACE"}]},
            "DriverInfo": {"Drivers": [
                {"CarIdx": 0, "UserName": "Pace Car", "CarIsPaceCar": 1, "CarNumber": "0"},
                {"CarIdx": 1, "UserName": "Amy", "UserID": 11, "CarNumber": "007", "CurDriverIncidentCount": 0},
                {"CarIdx": 2, "UserName": "Ben", "UserID": 22, "CarNumber": "12", "CurDriverIncidentCount": 2},
                {"CarIdx": 3, "UserName": "Spec", "IsSpectator": 1, "CarNumber": ""},
            ]},
            "CameraInfo": {"Groups": [{"GroupNum": 9, "GroupName": "TV1"}]},
        }

    def startup(self):
        self.startups += 1
        if not self.sim_running:
            return False
        self.is_initialized = self.is_connected = True
        return True

    def shutdown(self):
        self.is_initialized = self.is_connected = False

    def __getitem__(self, key):
        assert key in self.vars or key in self.info, key
        return self.vars.get(key, self.info.get(key))

    def freeze_var_buffer_latest(self):
        self.frozen = True

    def unfreeze_var_buffer_latest(self):
        self.frozen = False

    def cam_switch_num(self, car_number="1", group=1, camera=0):
        self.sent.append(("cam_switch_num", car_number, group, camera))

    def cam_switch_pos(self, position=0, group=1, camera=0):
        self.sent.append(("cam_switch_pos", position, group, camera))

    def replay_search(self, search_mode=0):
        self.sent.append(("replay_search", search_mode))

    def replay_search_session_time(self, session_num=0, session_time_ms=0):
        self.sent.append(("replay_search_session_time", session_num, session_time_ms))

    def replay_set_play_speed(self, speed=0, slow_motion=False):
        self.sent.append(("replay_set_play_speed", speed, slow_motion))


class IRacingSourceTests(unittest.TestCase):
    def setUp(self):
        sys.modules["irsdk"] = types.SimpleNamespace(IRSDK=FakeIRSDK)
        from apex.sources import IRacingSource
        self.source = IRacingSource()
        self.source.RETRY_S = 0
        self.ir = self.source.ir
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(self.source, dict(DEFAULTS), LeagueStore(self.tmp.name))

    def tearDown(self):
        sys.modules.pop("irsdk", None)
        self.tmp.cleanup()

    def test_reads_session_and_drivers(self):
        self.assertTrue(self.app.tick())
        self.assertFalse(self.ir.frozen)
        snap = self.app.build_snapshot()
        self.assertEqual(snap["session"]["track"], "Spa")
        self.assertEqual(snap["session"]["type"], "Race")
        self.assertTrue(snap["replay"]["live"])
        self.assertEqual([(d["pos"], d["name"]) for d in snap["drivers"]], [(1, "Amy"), (2, "Ben")])
        self.assertEqual(snap["drivers"][1]["incidents"], 2)
        self.assertEqual(snap["camera"]["groups"], [{"num": 9, "name": "TV1"}])

    def test_watch_keeps_leading_zero_car_numbers(self):
        self.app.tick()
        self.app.command("watch", {"car_idx": 1})
        self.assertEqual(self.ir.sent[-1], ("cam_switch_num", "007", 9, 0))

    def test_incident_points_from_session_info(self):
        self.app.tick()
        self.ir.info["DriverInfo"]["Drivers"][2]["CurDriverIncidentCount"] = 6
        self.ir.session_info_update += 1
        self.ir.vars["SessionTime"] += 5
        self.app.tick()
        incidents = [e for e in self.app.detector.events if e["type"] == "incident"]
        self.assertEqual([(e["driver"], e["incidents"], e["session_num"]) for e in incidents], [("Ben", 4, 2)])

    def test_no_detection_while_watching_a_replay(self):
        self.app.tick()
        self.ir.vars["ReplayFrameNumEnd"] = 5000
        self.ir.vars["CarIdxTrackSurface"] = [-1, 0, 0]
        self.ir.vars["SessionTime"] += 1
        self.app.tick()
        self.assertEqual(self.app.detector.events, [])
        self.assertFalse(self.app.build_snapshot()["replay"]["live"])

    def test_disconnect_and_reconnect(self):
        self.assertTrue(self.app.tick())
        self.ir.is_connected = False
        self.ir.sim_running = False
        self.assertFalse(self.app.tick())
        self.assertFalse(self.app.build_snapshot()["connected"])
        self.ir.sim_running = True
        self.assertTrue(self.app.tick())
        self.assertEqual(len(self.app.build_snapshot()["drivers"]), 2)


if __name__ == "__main__":
    unittest.main()
