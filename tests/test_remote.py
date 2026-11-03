import tempfile
import time
import unittest

from apex import remote
from apex.config import DEFAULTS
from apex.core import App, CommandError
from apex.league import LeagueStore
from apex.sources import MockSource
from tests.test_app import FakeClock, wait_for


def make(tmp, **cfg):
    clock = FakeClock()
    source = MockSource(seed=11, clock=clock)
    app = App(source, dict(DEFAULTS, **cfg), LeagueStore(tmp))
    for _ in range(300):
        clock.t += 0.1
        app.tick()
    return app, source, clock


class DualCommentaryTests(unittest.TestCase):
    """A co-commentator's app following the host's camera."""

    def setUp(self):
        self.tmp = [tempfile.TemporaryDirectory() for _ in range(2)]
        self.host, self.host_src, self.host_clock = make(self.tmp[0].name, share_port=0)
        self.guest, self.guest_src, _ = make(self.tmp[1].name)

    def tearDown(self):
        self.guest.command("follow_camera", {"on": False})
        self.host.command("share_camera", {"on": False})
        for t in self.tmp:
            t.cleanup()

    def host_moves(self):
        self.host_clock.t += 0.1
        self.host.tick()
        self.host.share.update(self.host._camera_state())

    def test_the_guest_follows_the_hosts_camera(self):
        code = self.host.command("share_camera", {"on": True})["code"]
        port = self.host.share.port
        snap = self.host.build_snapshot()["remote"]["share"]
        self.assertEqual((snap["on"], snap["code"]), (True, code))
        self.guest.command("follow_camera", {"on": True, "address": f"127.0.0.1:{port}", "code": code})
        self.assertTrue(wait_for(lambda: self.guest.follow.status == "following", 5))
        # The host puts the camera on a driver, with another camera group.
        car = list(self.host._drivers)[4]
        number = self.host._drivers[car]["number"]
        self.host.command("watch", {"car_idx": car, "group": 2})
        self.host_moves()
        switched = lambda: any(c[:3] == ("cam_switch_num", number, 2) for c in self.guest_src.commands)  # noqa: E731
        self.assertTrue(wait_for(switched, 5), self.guest_src.commands)
        self.assertEqual(self.host.share.followers, 1)
        host = self.guest.build_snapshot()["remote"]["follow"]["host"]
        self.assertEqual(host["car"], number)
        # The host replays a moment: the guest goes to the same moment.
        self.host_src.replay_search_session_time(0, 12_000)
        self.host_moves()
        seek = lambda: any(c[0] == "replay_search_session_time" and abs(c[2] - 12_000) <= 1000 for c in self.guest_src.commands)  # noqa: E731
        self.assertTrue(wait_for(seek, 5), self.guest_src.commands)
        # Back to live: the guest too.
        n = len(self.guest_src.commands)
        self.host.command("live", {})
        self.host_moves()
        self.assertTrue(wait_for(lambda: ("replay_search", remote_end()) in self.guest_src.commands[n:], 5))

    def test_free_mode_then_sync(self):
        code = self.host.command("share_camera", {"on": True})["code"]
        self.guest.command("follow_camera", {"on": True, "address": f"127.0.0.1:{self.host.share.port}", "code": code})
        self.assertTrue(wait_for(lambda: self.guest.follow.status == "following" and self.guest.follow.last, 5))
        # Free mode: the host moves on, the co-commentator's camera stays theirs.
        self.assertEqual(self.guest.command("hotkey", {"action": "follow:free"}), {"free": True})
        self.assertTrue(self.guest.build_snapshot()["remote"]["follow"]["free"])
        cars = list(self.host._drivers)
        n = len(self.guest_src.commands)
        self.host.command("watch", {"car_idx": cars[7], "group": 2})
        self.host_moves()
        number = self.host._drivers[cars[7]]["number"]
        self.assertTrue(wait_for(lambda: (self.guest.follow.last or {}).get("car") == number, 5))
        self.assertFalse(any(c[0] == "cam_switch_num" for c in self.guest_src.commands[n:]))
        # Sync: straight to what the host is showing now, and following again.
        self.assertEqual(self.guest.command("follow_free", {"on": False}), {"free": False})
        self.assertIn(("cam_switch_num", number, 2, 0), self.guest_src.commands[n:])
        n = len(self.guest_src.commands)
        self.host.command("watch", {"car_idx": cars[2], "group": 1})
        self.host_moves()
        number = self.host._drivers[cars[2]]["number"]
        self.assertTrue(wait_for(lambda: ("cam_switch_num", number, 1, 0) in self.guest_src.commands[n:], 5))

    def test_a_wrong_code_is_turned_away(self):
        self.host.command("share_camera", {"on": True})
        self.guest.command("follow_camera", {"on": True, "address": f"127.0.0.1:{self.host.share.port}", "code": "000000x"})
        self.assertTrue(wait_for(lambda: self.guest.follow.error == "Wrong code", 5))
        self.assertEqual(self.host.share.followers, 0)

    def test_addresses_typed_in(self):
        url = remote.CameraFollow.url_for
        self.assertEqual(url("192.168.1.20", "123456"), "http://192.168.1.20:8190/follow?code=123456")
        self.assertEqual(url("http://pc.local:9000/", " 1 2"), "http://pc.local:9000/follow?code=1%202")
        with self.assertRaises(CommandError):
            self.guest.command("follow_camera", {"on": True, "address": "", "code": "1"})
        self.assertFalse(self.guest.settings.get("follow_on"))
        # A new code: the old one no longer lets anyone in.
        old = self.host.command("share_camera", {"on": True})["code"]
        new = self.host.command("share_new_code", {})["code"]
        self.assertNotEqual(old, new)
        self.assertEqual(self.host.build_snapshot()["remote"]["share"]["code"], new)


def remote_end():
    from apex.sources import RPY_SRCH_TO_END
    return RPY_SRCH_TO_END


if __name__ == "__main__":
    unittest.main()
