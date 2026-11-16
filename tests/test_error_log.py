"""apex.log gets every error: the app's own (timed, in full once, then counted),
a failed request's, and the pages' (overlays in OBS, the app's window)."""

import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout, redirect_stderr

from apex.config import DEFAULTS
from apex.core import App
from apex.desktop import StampedLog
from apex.league import LeagueStore
from apex.server import make_server, serve_in_thread
from apex.sources import MockSource
from tests.test_app import FakeClock


class StampTests(unittest.TestCase):
    def test_every_line_starts_with_the_time(self):
        out = io.StringIO()
        log = StampedLog(out, clock=lambda: "12:34:56")
        print("one", file=log)
        log.write("two\nthree")
        log.write(" and more\n")
        self.assertEqual(out.getvalue(), "12:34:56 one\n12:34:56 two\n12:34:56 three and more\n")


class ErrorLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(MockSource(seed=7, clock=FakeClock()), dict(DEFAULTS), LeagueStore(self.tmp.name))
        self.server = make_server(self.app, "127.0.0.1", 0)
        serve_in_thread(self.server)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def logged(self, fn):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            result = fn()
        return result, out.getvalue()

    def test_a_page_error_goes_in_the_log_once_a_minute(self):
        err = {"page": "/standings.html", "message": "TypeError: x is undefined", "source": "/standings.js",
               "line": 42, "stack": "render@/standings.js:42:7"}
        (status, _), out = self.logged(lambda: self.post("/api/client_error", err))
        self.assertEqual(status, 200)
        self.assertIn("page error in /standings.html: TypeError: x is undefined (/standings.js:42)", out)
        self.assertIn("render@/standings.js:42:7", out)
        _, again = self.logged(lambda: self.post("/api/client_error", err))
        self.assertEqual(again, "")  # the same one straight after: counted, not logged again

    def test_a_request_that_fails_is_logged_and_answered(self):
        def boom(**_):
            raise RuntimeError("something broke")
        self.app.cmd_overlay_boom = boom  # (overlay_*: works without iRacing)
        (status, body), out = self.logged(lambda: self.post("/api/cmd", {"action": "overlay_boom", "params": {}}))
        self.assertEqual(status, 500)
        self.assertIn("something broke", body["error"])
        self.assertIn("POST /api/cmd error", out)
        self.assertIn("Traceback", out)
        self.assertIn("RuntimeError: something broke", out)

    def test_a_command_that_trips_over_its_parameters_is_logged(self):
        def picky(n):
            return {"n": int(n)}
        self.app.cmd_overlay_picky = picky
        (status, _), out = self.logged(lambda: self.post("/api/cmd", {"action": "overlay_picky", "params": {"n": "x"}}))
        self.assertEqual(status, 400)
        self.assertIn("/api/cmd overlay_picky error", out)
        self.assertIn("ValueError", out)


class ShowLogTests(unittest.TestCase):
    def test_opens_the_folder_with_the_log(self):
        from pathlib import Path
        from unittest import mock

        from apex.core import CommandError
        with tempfile.TemporaryDirectory() as tmp:
            app = App(MockSource(seed=7, clock=FakeClock()), dict(DEFAULTS), LeagueStore(tmp))
            with mock.patch("apex.core.USER_DIR", Path(tmp)), mock.patch("apex.desktop.reveal", return_value=True) as reveal:
                with self.assertRaises(CommandError):  # none yet (run from source: it's the console)
                    app.command("show_log", {})
                (Path(tmp) / "apex.log").write_text("x")
                self.assertEqual(app.command("show_log", {})["path"], str(Path(tmp) / "apex.log"))
                reveal.assert_called_once_with(Path(tmp) / "apex.log")


if __name__ == "__main__":
    unittest.main()
