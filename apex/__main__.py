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
from pathlib import Path

from . import __version__, desktop
from .config import ROOT, load_config
from .overlays import OverlaySettings
from .settings import UserSettings
from .core import App
from .cutout import Cutout
from .league import IRacingDataClient, LeagueStore
from .paths import APP_DIR, FROZEN, iracing_screenshots_dir
from .photobooth import PhotoBooth
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
    client = IRacingDataClient(
        cfg["iracing_username"], cfg["iracing_password"],
        cfg["iracing_client_id"], cfg["iracing_client_secret"],
    )
    app = App(source, cfg, LeagueStore(cfg["leagues_dir"], client))
    app.overlays = OverlaySettings(ROOT / "data" / "overlays.json")
    app.settings = UserSettings(ROOT / "data" / "settings.json")
    if mock:
        # The mock "iRacing" writes its screenshots here.
        source.screenshots_dir = ROOT / "data" / "mock-screenshots"
        shots = source.screenshots_dir
    else:
        shots = Path(cfg["screenshots_dir"]) if cfg["screenshots_dir"] else iracing_screenshots_dir()
    app.photobooth = PhotoBooth(app, shots, ROOT / "data" / "photobooth", Cutout(ROOT / "data" / "models"),
                                settle_s=float(cfg["photobooth_settle_s"]))
    if app.settings.get("screenshots_dir") and not mock:
        app.photobooth.set_folder(app.settings.get("screenshots_dir"))
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
        for path, expect in (("/", b"Apex"), ("/gridwalk.html", b"gridwalk.js"), ("/standings.html", b"standings.js"), ("/laps.html", b"laps.js"), ("/logos/pro.svg", b"data-apex-fill"),
                             ("/api/state", b'"connected": true')):
            with urllib.request.urlopen(base + path, timeout=10) as resp:
                body = resp.read()
            if expect not in body:
                raise AssertionError(f"{path} did not contain {expect!r}")
        if FROZEN:
            from .cutout import dependencies_available
            if not dependencies_available():
                raise AssertionError("photo booth cut-out libraries (onnxruntime, numpy, Pillow) aren't bundled")
        print(f"smoke test passed (v{__version__})")
        return 0
    except Exception as e:
        print(f"smoke test FAILED: {e!r}")
        return 1
    finally:
        app.stop()
        server.shutdown()
        server.server_close()


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
