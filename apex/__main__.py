"""Run the overlay: ``python -m apex`` (add ``--mock`` to try it without iRacing)."""

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .config import ROOT, load_config
from .core import App
from .league import IRacingDataClient, LeagueStore
from .server import make_server, serve_in_thread
from .updater import Updater, restart_requested


def main(argv=None):
    parser = argparse.ArgumentParser(prog="apex", description="Apex Commentator overlay suite for iRacing")
    parser.add_argument("--mock", action="store_true", help="simulate a race instead of connecting to iRacing")
    parser.add_argument("--mock-speed", type=float, default=1.0, help="mock time multiplier (e.g. 5 for a busier demo)")
    parser.add_argument("--config", help="path to config.json")
    parser.add_argument("--host", help="interface to listen on (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="port to listen on (default 8180)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the overlay in a browser")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.host:
        cfg["host"] = args.host
    if args.port:
        cfg["port"] = args.port

    if args.mock:
        from .sources import MockSource
        source = MockSource(time_scale=args.mock_speed)
    else:
        try:
            from .sources import IRacingSource
            source = IRacingSource()
        except ImportError:
            print("pyirsdk is not installed. Run: pip install -r requirements.txt")
            print("(or start with --mock to try the overlay without iRacing)")
            return 1

    client = IRacingDataClient(
        cfg["iracing_username"], cfg["iracing_password"],
        cfg["iracing_client_id"], cfg["iracing_client_secret"],
    )
    app = App(source, cfg, LeagueStore(cfg["leagues_dir"], client))
    app.updater = Updater(
        __version__, cfg["update_repo"], ROOT, Path(cfg["leagues_dir"]).parent / "update.json",
        token=cfg["github_token"], enabled=cfg["update_check"],
    )
    app.updater.start()
    app.start()
    server = make_server(app, cfg["host"], cfg["port"])
    serve_in_thread(server)

    shown_host = "localhost" if cfg["host"] in ("127.0.0.1", "0.0.0.0") else cfg["host"]
    url = f"http://{shown_host}:{cfg['port']}/"
    print(f"Apex Commentator {__version__} ({source.name}) running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while not restart_requested.wait(1):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        server.shutdown()
        server.server_close()
    if restart_requested.is_set():
        # Relaunch the updated code in this console, on the same port.
        print("Restarting with the update…")
        relaunch = [a for a in sys.argv[1:] if a != "--no-browser"] + ["--no-browser"]
        return subprocess.call([sys.executable, "-m", "apex", *relaunch])
    return 0


if __name__ == "__main__":
    sys.exit(main())
