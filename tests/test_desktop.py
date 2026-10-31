import sys
import threading
import types
import unittest

from apex import desktop


class FakeEvent:
    def __init__(self):
        self._event = threading.Event()
        self.handlers = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def set(self):
        self._event.set()
        for fn in self.handlers:
            fn()

    def is_set(self):
        return self._event.is_set()

    def wait(self, timeout=None):
        return self._event.wait(timeout)


class FakeWindow:
    def __init__(self, title, url, **kw):
        self.title, self.url, self.kw = title, url, kw
        self.native = object()  # made straight away, as once the app is running
        self.events = types.SimpleNamespace(closed=FakeEvent(), shown=FakeEvent())
        self.destroyed = False

    def destroy(self):
        self.destroyed = True
        self.events.closed.set()


class OnScreenOverlayTests(unittest.TestCase):
    def setUp(self):
        self.made = []
        fake = types.ModuleType("webview")
        fake.screens = [types.SimpleNamespace(width=2560, height=1440, x=0, y=0),
                        types.SimpleNamespace(width=1920, height=1080, x=2560, y=0)]

        def create_window(title, url, **kw):
            w = FakeWindow(title, url, **kw)
            self.made.append(w)
            return w

        fake.create_window = create_window
        self._old = sys.modules.get("webview")
        sys.modules["webview"] = fake
        desktop._main_window = object()
        desktop._overlays.clear()
        desktop._windows.clear()

    def tearDown(self):
        desktop._main_window = None
        desktop._overlays.clear()
        desktop._windows.clear()
        if self._old is None:
            sys.modules.pop("webview", None)
        else:
            sys.modules["webview"] = self._old

    def settle(self):
        """Wait for the overlay jobs queued so far."""
        done = threading.Event()
        desktop._run(done.set)
        self.assertTrue(done.wait(5))

    def test_show_move_and_remove(self):
        self.assertTrue(desktop.show_overlay("standings", "http://x/standings.html?desktop=1", "Standings", 1))
        self.assertEqual(desktop.overlays_on_screen(), {"standings": 1})  # straight away, for the app
        self.settle()
        w = self.made[0]
        self.assertEqual((w.kw["screen"].width, w.kw["on_top"], w.kw["focus"], w.kw["frameless"]), (1920, True, False, True))
        self.assertTrue(w.kw["transparent"])  # the page's browser view must be see-through
        desktop.show_overlay("standings", "http://x/standings.html?desktop=1", "Standings", 0)  # move it
        self.settle()
        self.assertTrue(w.destroyed)
        self.assertEqual((len(self.made), desktop.overlays_on_screen()), (2, {"standings": 0}))
        desktop.hide_overlay("standings")
        self.assertEqual(desktop.overlays_on_screen(), {})
        self.settle()
        self.assertTrue(self.made[1].destroyed)

    def test_remove_all_and_remove_before_it_opened(self):
        desktop.show_overlay("board", "u1", "Boards", 0)
        desktop.show_overlay("laps", "u2", "Laps", 0)
        desktop.hide_overlay("laps")  # gone before its window was made
        self.settle()
        self.assertEqual([w.title for w in self.made], ["Boards"])
        desktop.show_overlay("sponsors", "u3", "Sponsors", 0)
        self.settle()
        desktop.hide_overlay()
        self.settle()
        self.assertTrue(all(w.destroyed for w in self.made))
        self.assertEqual(desktop.overlays_on_screen(), {})

    def test_closed_by_hand(self):
        desktop.show_overlay("board", "u1", "Boards", 0)
        self.settle()
        self.made[0].destroy()  # e.g. Alt+F4
        self.assertEqual(desktop.overlays_on_screen(), {})

    def test_without_the_app_window(self):
        desktop._main_window = None
        self.assertFalse(desktop.show_overlay("board", "u", "Boards", 0))
        self.assertEqual(desktop.screens(), [])

    def test_the_page_says_where_it_draws(self):
        desktop.show_overlay("standings", "u", "Standings", 0)
        self.settle()
        desktop.set_region("standings", [[50, 50, 580, 93]])
        self.assertEqual(desktop._regions["standings"], [[50, 50, 580, 93]])
        desktop.show_overlay("standings", "u", "Standings", 1)  # a new window: its page reports again
        self.settle()
        self.assertNotIn("standings", desktop._regions)


class RegionCommandTests(unittest.TestCase):
    def test_rectangles_reach_the_window(self):
        from apex.core import App
        from apex.config import DEFAULTS
        from apex.league import LeagueStore
        from apex.sources import MockSource
        import tempfile

        got = []
        with tempfile.TemporaryDirectory() as tmp:
            app = App(MockSource(seed=1), dict(DEFAULTS), LeagueStore(tmp))
            app.desktop = types.SimpleNamespace(region=lambda page, rects: got.append((page, rects)))
            app.command("desktop_region", {"page": "standings", "rects": [[1.6, 2, 30, 40, 99], "junk"]})
            app.command("desktop_region", {"page": "standings_screen", "rects": None})
            app.command("desktop_region", {"page": "not-an-overlay", "rects": []})
        self.assertEqual(got, [("standings", [[1, 2, 30, 40]]), ("standings_screen", None)])

