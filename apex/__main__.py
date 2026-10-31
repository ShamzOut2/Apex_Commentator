"""Run the app: ``python -m apex`` (add ``--mock`` to try it without iRacing).

The control panel opens in its own window when pywebview is available (always
in the packaged Windows app), otherwise in the default browser.
"""

import argparse
import subprocess
import sys
import time
import urllib.request
import webbrowser

from . import __version__, desktop
from .config import ROOT, load_config
from .backgrounds import Backgrounds
from .overlays import OverlaySettings
from .settings import UserSettings
from .tracks import TrackCatalogue
from .core import App
from .league import LeagueStore
from .paths import APP_DIR, FROZEN
from .server import make_server, serve_in_thread
from .updater import Updater, restart_options, restart_requested


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="apex", description="Apex Commentator overlay suite for iRacing")
    parser.add_argument("--mock", action="store_true", help="simulate a race instead of connecting to iRacing")
    parser.add_argument("--mock-session", choices=("race", "qualify"), default="race",
                        help="with --mock: simulate a race (default) or a qualifying session")
    parser.add_argument("--mock-laps", type=int, default=0,
                        help="with --mock: the race ends after this many laps (default: never)")
    parser.add_argument("--mock-sectors", type=int, default=3,
                        help="with --mock: how many split points the track has (real tracks often have many)")
    parser.add_argument("--mock-speed", type=float, default=1.0, help="mock time multiplier (e.g. 5 for a busier demo)")
    parser.add_argument("--config", help="path to config.json")
    parser.add_argument("--host", help="interface to listen on (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="port to listen on (default 8180)")
    parser.add_argument("--no-window", action="store_true", help="use the browser instead of the app window")
    parser.add_argument("--no-browser", action="store_true", help="with --no-window: don't open a browser either")
    parser.add_argument("--smoke-test", action="store_true", help="start up, check the app responds, then exit")
    return parser.parse_args(argv)


def build_app(cfg, mock, mock_speed=1.0, mock_session="race", mock_laps=0, mock_sectors=3):
    if mock:
        from .sources import MockSource
        source = MockSource(time_scale=mock_speed, session=mock_session, race_laps=mock_laps, retirements=True,
                            sectors=mock_sectors)
    else:
        from .sources import IRacingSource  # ImportError when pyirsdk is missing
        source = IRacingSource()
    app = App(source, cfg, LeagueStore(cfg["leagues_dir"]))
    app.overlays = OverlaySettings(ROOT / "data" / "overlays.json")
    app.settings = UserSettings(ROOT / "data" / "settings.json")
    app.tracks = TrackCatalogue(ROOT / "data" / "tracks.json")
    app.backgrounds = Backgrounds(ROOT / "data" / "backgrounds")
    try:
        # The grid walk's car pictures: the folder picked last time.
        app.thumbnails.set_folder(app.settings.get("gridwalk_thumbs_dir") or "")
    except ValueError as e:
        print(f"[apex] grid walk pictures: {e}")
    from .hotkeys import IS_WINDOWS, GlobalHotkeys
    if IS_WINDOWS:
        # Keys with Ctrl / Alt work whichever program is in front (see hotkeys.py).
        app.global_hotkeys = GlobalHotkeys(lambda action: app.command("hotkey", {"action": action}))
        app.global_hotkeys.set(app.settings.get("global_hotkeys", {}))
    app.updater = Updater(
        __version__, cfg["update_repo"], APP_DIR, ROOT / "data" / "update.json",
        token=cfg["github_token"] or app.settings.get("github_token", ""), enabled=cfg["update_check"],
        installer_mode=FROZEN, settings=app.settings,
    )
    return app


def smoke_test(cfg):
    """Start a mock session, check the UI and API answer, exit 0 on success."""
    cfg = dict(cfg, update_check=False, host="127.0.0.1")
    app = build_app(cfg, mock=True)
    app.start()
    server = make_server(app, "127.0.0.1", 0)
    serve_in_thread(server)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        import irsdk  # noqa: F401  (bundled for live iRacing sessions)
        time.sleep(1.5)
        for path, expect in (("/", b"Apex"), ("/gridwalk.html", b"gridwalk.js"), ("/standings.html", b"standings.js"), ("/laps.html", b"laps.js"), ("/board.html", b"board.js"), ("/sponsors.html", b"sponsors.js"), ("/driver.html", b"driver.js"), ("/battle.html", b"battle.js"), ("/pits.html", b"pits.js"), ("/makes/porsche.png", b"PNG"), ("/logos/pro.svg", b"data-apex-fill"),
                             ("/api/state", b'"connected": true')):
            with urllib.request.urlopen(base + path, timeout=10) as resp:
                body = resp.read()
            if expect not in body:
                raise AssertionError(f"{path} did not contain {expect!r}")
        print(f"smoke test passed (v{__version__})")
        return 0
    except Exception as e:
        print(f"smoke test FAILED: {e!r}")
        return 1
    finally:
        app.stop()
        server.shutdown()
        server.server_close()


class OnScreen:
    """On-screen overlays, for the App (see desktop.py). Screens are listed once
    (and again when an overlay goes up), not on every snapshot."""

    def __init__(self, base, title):
        self.base, self.title, self._screens = base, title, None

    def screens(self):
        if self._screens is None:
            self._screens = desktop.screens() or None
        return self._screens or []

    def show(self, page, path, name, screen):
        self._screens = None
        return desktop.show_overlay(page, self.base + path, f"{name} – {self.title}", screen)

    def hide(self, page=None):
        desktop.hide_overlay(page)

    def region(self, page, rects):
        desktop.set_region(page, rects)

    def on_screen(self):
        return desktop.overlays_on_screen()


def main(argv=None):
    desktop.log_to_file()
    args = parse_args(argv)
    cfg = load_config(args.config)
    if args.host:
        cfg["host"] = args.host
    if args.port:
        cfg["port"] = args.port
    print(f"--- Apex Commentator {__version__} starting {time.strftime('%Y-%m-%d %H:%M:%S')}")

    if args.smoke_test:
        return smoke_test(cfg)

    if not desktop.claim_single_instance():
        desktop.alert("Apex Commentator is already running.")
        return 0

    try:
        app = build_app(cfg, args.mock, args.mock_speed, args.mock_session, args.mock_laps, args.mock_sectors)
    except ImportError:
        desktop.alert("pyirsdk is not installed. Run: pip install -r requirements.txt\n"
                      "(or start with --mock to try the app without iRacing)", error=True)
        return 1
    try:
        server = make_server(app, cfg["host"], cfg["port"])
    except OSError as e:
        desktop.alert(f"Couldn't start on port {cfg['port']}: {e.strerror or e}.\n"
                      "Is another program using it? Change \"port\" in config.json.", error=True)
        return 1
    app.updater.start()
    app.start()
    serve_in_thread(server)

    shown_host = "localhost" if cfg["host"] in ("127.0.0.1", "0.0.0.0") else cfg["host"]
    url = f"http://{shown_host}:{cfg['port']}/"
    title = f"Apex Commentator {__version__}" + (" (demo mode)" if args.mock else "")
    print(f"{title} running at {url}")

    app.popout = lambda page, name: desktop.open_popout(page, f"{url}?popout={page}", f"{name} – {title}")
    if not args.no_window and desktop.window_available():
        app.desktop = OnScreen(url.rstrip("/"), title)
    try:
        opened = (not args.no_window and desktop.window_available()
                  and desktop.run_window(url, title, restart_requested))
        if not opened:
            if not args.no_browser:
                webbrowser.open(url)
            if FROZEN and desktop.IS_WINDOWS and not args.no_window:
                # No console to Ctrl+C in: the message box is the app's "window".
                desktop.alert(f"Apex Commentator is running in your browser at {url}\n\n"
                              "(The app window couldn't open: is the Microsoft Edge WebView2 Runtime installed?)\n\n"
                              "Click OK to quit Apex Commentator.")
            else:
                print("Press Ctrl+C to stop.")
                while not restart_requested.wait(1):
                    pass
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        server.shutdown()
        server.server_close()

    if restart_requested.is_set() and restart_options["relaunch"]:
        # Relaunch the updated code in this console, on the same port.
        print("Restarting with the update…")
        relaunch = [a for a in (argv if argv is not None else sys.argv[1:]) if a != "--no-browser"] + ["--no-browser"]
        return subprocess.call([sys.executable, "-m", "apex", *relaunch])
    return 0


if __name__ == "__main__":
    sys.exit(main())
