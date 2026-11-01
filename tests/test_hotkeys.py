import tempfile
import unittest

from apex.hotkeys import GlobalHotkeys, parse, system_wide
from apex.league import profile_from_session
from tests.test_app import make_app


class ParseTests(unittest.TestCase):
    def test_only_ctrl_or_alt_combinations_go_system_wide(self):
        self.assertEqual(parse("ctrl+alt+1"), (0x3, ord("1")))
        self.assertEqual(parse("ctrl+shift+c"), (0x6, ord("C")))
        self.assertEqual(parse("alt+f5"), (0x1, 0x74))
        self.assertEqual(parse("ctrl+alt+num3"), (0x3, 0x63))
        for plain in ("1", "c", "shift+1", "ctrl+alt+;", "win+1", ""):
            self.assertIsNone(parse(plain), plain)
        self.assertEqual(system_wide({"1": "cam:Nose", "ctrl+alt+1": "cam:TV1", "shift+2": "ov:laps"}), {"ctrl+alt+1": "cam:TV1"})

    def test_not_windows(self):
        hk = GlobalHotkeys(lambda action: None)
        if not hk.available:
            hk.set({"ctrl+alt+1": "cam:TV1"})  # nothing to do, nothing breaks
            self.assertEqual(hk.taken, [])


class HotkeyActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app, cls.source = make_app(cls.tmp.name, minutes=1)
        league = cls.app.leagues.save(profile_from_session(cls.app.build_snapshot()["drivers"], "S"))
        cls.app.leagues.set_active(league["id"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def press(self, action):
        return self.app.command("hotkey", {"action": action})

    def test_tower_keys(self):
        app = self.app
        mode, bar = app.overlays.get()["standings"]["mode"], app.overlays.get()["standings"]["sponsor_bar"]
        self.press("tower:mode")
        self.assertEqual(app.overlays.get()["standings"]["mode"], "class" if mode == "overall" else "overall")
        self.press("tower:mode")
        self.assertEqual(app.overlays.get()["standings"]["mode"], mode)
        self.press("tower:sponsor")
        self.assertEqual(app.overlays.get()["standings"]["sponsor_bar"], not bar)
        self.press("tower:sponsor")
        self.assertEqual(app.overlays.get()["standings"]["sponsor_bar"], bar)

    def test_overlays_boards_and_grid_walk(self):
        app = self.app
        was = app.overlays.get()["laps"]["visible"]
        self.press("ov:laps")
        self.assertEqual(app.overlays.get()["laps"]["visible"], not was)
        self.press("ov:laps")
        self.assertEqual(app.overlays.get()["laps"]["visible"], was)
        # A board on screen; the same key again takes it off; another swaps.
        self.press("board:calendar:")
        self.assertEqual(app.board["kind"], "calendar")
        self.press("board:results:overall")
        self.assertEqual((app.board["kind"], app.board["params"]["round"]), ("results", "latest"))
        self.press("board:results:overall")
        self.assertIsNone(app.board["kind"])
        self.press("board:calendar:")
        self.press("board:off")
        self.assertIsNone(app.board["kind"])
        self.press("gw:toggle")
        self.assertTrue(app.gridwalk.visible)
        self.press("gw:next")
        self.assertEqual(app.gridwalk.index, 2)
        self.press("gw:prev")
        self.assertEqual(app.gridwalk.index, 0)
        self.press("gw:toggle")
        self.assertFalse(app.gridwalk.visible)

    def test_everything_on_my_screen(self):
        class Desk:
            def __init__(self):
                self.up = {}

            def show(self, page, url, name, screen):
                self.up[page] = screen
                return True

            def hide(self, page=None):
                self.up = {k: v for k, v in self.up.items() if page and k != page}

            def on_screen(self):
                return dict(self.up)

            def screens(self):
                return []

        self.app.desktop = desk = Desk()
        try:
            self.app.command("desktop_screen", {"tab": "overlays", "screen": 1})
            self.app.command("desktop_screen", {"tab": "boards", "screen": 2})
            self.press("desk:overlays")
            self.assertEqual(desk.up, {k: 1 for k in ("standings", "laps", "sponsors", "driver", "battle", "pits")})
            self.press("desk:boards")  # on the screen picked for each tab
            self.assertEqual(desk.up["board"], 2)
            self.press("desk:gridwalk")  # the Overlays tab's screen
            self.assertEqual(desk.up["gridwalk"], 1)
            self.press("desk:off")
            self.assertEqual(desk.up, {})
            self.press("desk:boards_toggle")  # boards on the screen picked for them, then off again
            self.assertEqual(desk.up, {"board": 2})
            self.press("desk:boards_toggle")
            self.assertEqual(desk.up, {})
        finally:
            self.app.desktop = None

    def test_everything_off_and_back(self):
        app = self.app
        ov = lambda k: app.overlays.get()[k]["visible"]  # noqa: E731
        app.cmd_overlay_settings("laps", {"visible": True})
        app.cmd_overlay_settings("driver", {"visible": False})
        self.press("board:calendar:")
        self.press("all:toggle")
        self.assertEqual((ov("laps"), ov("driver"), app.board["kind"]), (False, False, None))
        self.press("all:toggle")  # what was up comes back, nothing else
        self.assertEqual((ov("laps"), ov("driver"), app.board["kind"]), (True, False, "calendar"))
        self.press("board:off")
        for k in app.TOGGLE_ALL:
            app.cmd_overlay_settings(k, {"visible": False})
        self.press("all:toggle")  # nothing up: every overlay comes on
        self.assertTrue(all(ov(k) for k in app.TOGGLE_ALL))
        self.press("all:toggle")

    def test_overlays_and_boards_apart(self):
        app = self.app
        ov = lambda k: app.overlays.get()[k]["visible"]  # noqa: E731
        app.cmd_overlay_settings("laps", {"visible": True})
        app.command("board_show", {"kind": "grid", "group": "", "round": "next"})
        app.command("board_reveal", {"step": "next"})
        params = dict(app.board["params"])
        self.press("all:boards")  # just the board
        self.assertEqual((app.board["kind"], ov("laps")), (None, True))
        self.press("all:overlays")  # just the overlays
        self.assertFalse(ov("laps"))
        self.press("all:boards")  # the same board back, as it was
        self.assertEqual((app.board["kind"], app.board["params"]), ("grid", params))
        self.press("all:overlays")
        self.assertTrue(ov("laps"))
        self.press("board:off")

    def test_championship_battle_key(self):
        app = self.app
        app.cmd_overlay_settings("battle", {"visible": False, "drivers": ""})
        from apex.core import CommandError
        with self.assertRaises(CommandError):
            self.press("battle:toggle")  # nobody picked yet
        app.cmd_overlay_settings("battle", {"drivers": "cust:1,cust:2"})
        self.press("battle:toggle")
        self.assertTrue(app.overlays.get()["battle"]["visible"])
        self.press("battle:toggle")
        self.assertFalse(app.overlays.get()["battle"]["visible"])
        self.assertEqual(app.overlays.get()["battle"]["drivers"], "cust:1,cust:2")  # the picks stay

    def test_tower_header_key(self):
        app = self.app
        app.cmd_overlay_settings("standings", {"header_info": "laps"})
        self.press("tower:header")
        self.assertEqual(app.overlays.get()["standings"]["header_info"], "time")
        self.press("tower:header")
        self.assertEqual(app.overlays.get()["standings"]["header_info"], "laps")
        app.cmd_overlay_settings("standings", {"header_info": "auto"})
        app._header_mode = "time"  # automatic, showing the time: the key goes to laps
        self.press("tower:header")
        self.assertEqual(app.overlays.get()["standings"]["header_info"], "laps")

    def test_cameras(self):
        group = self.app._camera_groups[1]
        self.source.commands.clear()
        self.press(f"cam:{group['name']}")
        self.assertTrue(any(c[0] == "cam_switch_num" and c[2] == group["num"] for c in self.source.commands))
        from apex.core import CommandError
        with self.assertRaises(CommandError):
            self.press("cam:No Such Camera")

    def test_keys_are_kept_for_next_time(self):
        class Fake:
            available, taken = True, []

            def set(self, mapping):
                self.mapping = mapping

        self.app.global_hotkeys = fake = Fake()
        try:
            r = self.app.command("hotkeys", {"keys": {"1": "cam:Nose", "ctrl+alt+c": "board:calendar:"}})
            self.assertEqual(r["system_wide"], 1)
            self.assertEqual(fake.mapping, {"ctrl+alt+c": "board:calendar:"})
            self.assertEqual(self.app.settings.get("global_hotkeys"), {"ctrl+alt+c": "board:calendar:"})
            self.assertTrue(self.app.build_snapshot()["hotkeys"]["system_wide"])
        finally:
            self.app.global_hotkeys = None
