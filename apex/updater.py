"""Update checks and in-app updates from GitHub releases.

On start (and every few hours) the app asks GitHub for the newest release of
``update_repo``. If it's newer than the running version, the control panel
shows a pop-up offering to install it.

Installing downloads the release's source archive, checks it is an Apex
Commentator tree, and copies it over the install, leaving ``config.json`` and
``data/`` (leagues, logos, photos) alone. The app then restarts itself.

A git checkout is never overwritten: it is told to ``git pull`` instead, so a
developer's working tree is never clobbered.

Releases are published by pushing a version tag (``v0.2.0``): the
``release`` GitHub Actions workflow turns it into a release. If a repository
has tags but no releases, the newest version tag is used instead.
"""

import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.github.com"
CHECK_EVERY_S = 6 * 3600
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
# Never overwritten by an update: the user's settings and league data.
KEEP = {"config.json", "data", ".git"}
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class UpdateError(Exception):
    """A user-facing update problem."""


def parse_version(text):
    """'v1.2.3' / '1.2.3' -> (1, 2, 3), or None for anything else."""
    m = VERSION_RE.match(str(text or "").strip())
    return tuple(int(p) for p in m.groups()) if m else None


class Updater:
    def __init__(self, current, repo, root, state_file, token="", enabled=True, opener=None):
        self.current = current
        self.repo = repo.strip().strip("/")
        self.root = Path(root)
        self.state_file = Path(state_file)
        self.token = token
        self.enabled = enabled and bool(self.repo)
        self._open = opener or urllib.request.urlopen
        self._lock = threading.Lock()
        self.latest = None        # {"version", "tag", "notes", "url", "zip_url", "published_at"}
        self.checked_at = None
        self.error = None
        self.installing = False
        self.installed = None     # version installed and awaiting restart

    # -- GitHub ----------------------------------------------------------------

    def _get(self, url, accept="application/vnd.github+json"):
        headers = {"Accept": accept, "User-Agent": "ApexCommentator-Updater"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return self._open(urllib.request.Request(url, headers=headers), timeout=20)

    def _get_json(self, url):
        with self._get(url) as resp:
            return json.load(resp)

    def _newest_release(self):
        """Newest stable release, or failing that the newest version tag."""
        try:
            rel = self._get_json(f"{API}/repos/{self.repo}/releases/latest")
            if parse_version(rel.get("tag_name")):
                return {
                    "version": ".".join(map(str, parse_version(rel["tag_name"]))),
                    "tag": rel["tag_name"],
                    "notes": rel.get("body") or "",
                    "url": rel.get("html_url") or f"https://github.com/{self.repo}/releases",
                    "zip_url": rel.get("zipball_url") or f"{API}/repos/{self.repo}/zipball/{rel['tag_name']}",
                    "published_at": rel.get("published_at"),
                }
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
        tags = self._get_json(f"{API}/repos/{self.repo}/tags?per_page=100")
        versions = [(parse_version(t.get("name")), t["name"]) for t in tags if parse_version(t.get("name"))]
        if not versions:
            return None
        version, tag = max(versions)
        return {
            "version": ".".join(map(str, version)),
            "tag": tag,
            "notes": "",
            "url": f"https://github.com/{self.repo}/releases/tag/{tag}",
            "zip_url": f"{API}/repos/{self.repo}/zipball/{tag}",
            "published_at": None,
        }

    def check(self):
        """Ask GitHub for the newest version. Never raises; errors go in ``error``."""
        if not self.enabled:
            return self.status()
        try:
            latest = self._newest_release()
            with self._lock:
                self.latest, self.error = latest, None
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            reason = getattr(e, "reason", None) or e
            with self._lock:
                self.error = f"Couldn't check for updates: {reason}"
        self.checked_at = time.time()
        return self.status()

    def start(self):
        """Check now and then every few hours, in the background."""
        if not self.enabled:
            return

        def loop():
            while True:
                self.check()
                time.sleep(CHECK_EVERY_S)

        threading.Thread(target=loop, name="updater", daemon=True).start()

    # -- state -----------------------------------------------------------------

    def _skipped(self):
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8")).get("skip_version")
        except (OSError, ValueError):
            return None

    def skip(self, version):
        """Don't pop up for this version again (a newer one still will)."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({"skip_version": str(version)}), encoding="utf-8")

    def status(self):
        latest = self.latest
        available = bool(latest and parse_version(latest["version"]) > (parse_version(self.current) or (0, 0, 0)))
        return {
            "enabled": self.enabled,
            "current": self.current,
            "latest": latest and {k: latest[k] for k in ("version", "tag", "notes", "url", "published_at")},
            "available": available,
            "skipped": available and self._skipped() == latest["version"],
            "can_install": available and not self.is_git_checkout(),
            "git_checkout": self.is_git_checkout(),
            "installing": self.installing,
            "installed": self.installed,
            "checked_at": self.checked_at,
            "error": self.error,
        }

    def is_git_checkout(self):
        return (self.root / ".git").exists()

    # -- installing --------------------------------------------------------------

    def install(self):
        """Download the newest release and copy it over this install."""
        status = self.status()
        if not status["available"]:
            raise UpdateError("You're already on the newest version.")
        if status["git_checkout"]:
            raise UpdateError("This is a git checkout: update it with `git pull` instead.")
        with self._lock:
            if self.installing:
                raise UpdateError("An update is already being installed.")
            self.installing = True
        try:
            latest = self.latest
            with self._get(latest["zip_url"], accept="application/octet-stream") as resp:
                data = resp.read(MAX_ARCHIVE_BYTES + 1)
            if len(data) > MAX_ARCHIVE_BYTES:
                raise UpdateError("The update archive is unexpectedly large.")
            self._apply(data, latest["version"])
            self._install_requirements()
            self.installed = latest["version"]
            return latest["version"]
        except urllib.error.URLError as e:
            raise UpdateError(f"Couldn't download the update: {getattr(e, 'reason', e)}") from e
        finally:
            self.installing = False

    def _apply(self, data, version):
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise UpdateError("The update archive is damaged.") from e
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            for member in archive.infolist():
                target = (tmp / member.filename).resolve()
                if tmp not in target.parents and target != tmp:
                    raise UpdateError("The update archive contains unsafe paths.")
            archive.extractall(tmp)
            # GitHub archives hold one top folder: <owner>-<repo>-<sha>/
            tops = [p for p in tmp.iterdir() if p.is_dir()]
            src = tops[0] if len(tops) == 1 else tmp
            init = src / "apex" / "__init__.py"
            if not init.is_file():
                raise UpdateError("The update archive isn't an Apex Commentator release.")
            found = re.search(r'__version__\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"))
            if not found or parse_version(found.group(1)) != parse_version(version):
                raise UpdateError("The update archive's version doesn't match the release.")
            for path in sorted(src.rglob("*")):
                rel = path.relative_to(src)
                if rel.parts[0] in KEEP or path.is_dir():
                    continue
                dest = self.root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)

    def _install_requirements(self):
        req = self.root / "requirements.txt"
        if req.is_file():
            # Best effort: the app still runs in --mock without them.
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)],
                           check=False, timeout=600)


# Set after an update is installed; __main__ shuts down and relaunches.
restart_requested = threading.Event()


def request_restart(delay=1.0):
    """Ask the app to restart shortly (giving the HTTP response time to go out)."""
    threading.Timer(delay, restart_requested.set).start()
