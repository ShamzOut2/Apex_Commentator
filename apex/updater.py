"""Update checks and in-app updates from GitHub releases.

On start (and every few hours) the app asks GitHub for the newest release of
``update_repo``. If it's newer than the running version, the control panel
shows a pop-up offering to install it.

How an update is installed depends on how the app was installed:

* **Windows app** (the packaged ``.exe``): download the release's
  ``ApexCommentator-Setup-<version>.exe`` asset and run it silently. The app
  closes, the installer replaces it and reopens it. User data lives in
  ``%APPDATA%`` and is never touched.
* **From source**: download the release's source archive, check it is an Apex
  Commentator tree, and copy it over the install, leaving ``config.json`` and
  ``data/`` alone. The app then restarts itself. A git checkout is never
  overwritten: it is told to ``git pull`` instead.

Releases are published by the ``release`` GitHub Actions workflow when a new
version lands on main (or a version tag is pushed). If a repository has tags
but no releases, the newest version tag is used instead.

A private repository needs a GitHub access token (read access to its
contents), which can be pasted into the app (Home → Updates). Without one,
GitHub answers "not found", and the app says so instead of staying quiet.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.github.com"
CHECK_EVERY_S = 6 * 3600
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_INSTALLER_BYTES = 300 * 1024 * 1024
INSTALLER_RE = re.compile(r"^ApexCommentator-Setup-.*\.exe$", re.IGNORECASE)
# Never overwritten by an update: the user's settings and league data.
KEEP = {"config.json", "data", ".git"}
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class UpdateError(Exception):
    """A user-facing update problem."""


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """GitHub sends downloads on to a storage host with a signed URL; sending
    the GitHub token there too makes it refuse the request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).hostname != urllib.parse.urlsplit(req.full_url).hostname:
            new.remove_header("Authorization")
        return new


_default_open = urllib.request.build_opener(_DropAuthOnRedirect).open


def parse_version(text):
    """'v1.2.3' / '1.2.3' -> (1, 2, 3), or None for anything else."""
    m = VERSION_RE.match(str(text or "").strip())
    return tuple(int(p) for p in m.groups()) if m else None


class Updater:
    def __init__(self, current, repo, root, state_file, token="", enabled=True, opener=None,
                 installer_mode=False, launcher=None, settings=None):
        self.current = current
        self.repo = repo.strip().strip("/")
        self.root = Path(root)
        self.state_file = Path(state_file)
        self.token = token
        self.enabled = enabled and bool(self.repo)
        self._open = opener or _default_open
        self.settings = settings  # where a token pasted into the app is kept
        self._lock = threading.Lock()
        self.latest = None        # {"version", "tag", "notes", "url", "zip_url", "published_at"}
        self.checked_at = None
        self.error = None
        self.installing = False
        self.installed = None     # version installed and awaiting restart
        # Packaged app: update by running the release's installer.
        self.installer_mode = installer_mode
        self._launch = launcher or _launch_detached

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
                    "installer": next((
                        # The API address works for private repositories too (with a token).
                        {"name": a["name"], "url": a.get("url") or a["browser_download_url"], "size": a.get("size", 0)}
                        for a in rel.get("assets") or []
                        if INSTALLER_RE.match(a.get("name", "")) and a.get("browser_download_url")
                    ), None),
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
            "installer": None,
        }

    def _notes_since(self, latest):
        """What's new since this copy's version: the newest release's notes, or
        (when versions were skipped) every newer release's, newest first."""
        try:
            releases = self._get_json(f"{API}/repos/{self.repo}/releases?per_page=30")
        except (urllib.error.URLError, OSError, ValueError):
            return latest["notes"]  # the newest one's notes will do
        mine, newest = parse_version(self.current) or (0, 0, 0), parse_version(latest["version"])
        newer = sorted(
            ((parse_version(r.get("tag_name")), r.get("body") or "") for r in releases
             if isinstance(r, dict) and not r.get("draft") and not r.get("prerelease")
             and parse_version(r.get("tag_name")) and mine < parse_version(r.get("tag_name")) <= newest),
            reverse=True)
        if len(newer) < 2:
            return latest["notes"]
        return "\n\n".join(f"## v{'.'.join(map(str, v))}\n\n{body.strip()}" for v, body in newer)

    def check(self):
        """Ask GitHub for the newest version. Never raises; errors go in ``error``."""
        if not self.enabled:
            return self.status()
        try:
            latest = self._newest_release()
            if latest and parse_version(latest["version"]) > (parse_version(self.current) or (0, 0, 0)):
                latest["notes"] = self._notes_since(latest)
            with self._lock:
                self.latest, self.error = latest, None
        except urllib.error.HTTPError as e:
            with self._lock:
                self.error = self._http_problem(e)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            reason = getattr(e, "reason", None) or e
            with self._lock:
                self.error = f"Couldn't check for updates: {reason}"
        self.checked_at = time.time()
        return self.status()

    def _http_problem(self, e):
        if e.code in (403, 429) and e.headers and e.headers.get("X-RateLimit-Remaining") == "0":
            return "GitHub's limit on update checks was reached; it will check again later."
        if e.code in (401, 403) and self.token:
            return "GitHub turned down the access token: it may have expired or lack read access to the repository."
        if e.code == 403:
            return f"GitHub refused access to {self.repo}. If the repository is private, add a GitHub access token below."
        if e.code == 404:
            if self.token:
                return (f"GitHub can't find {self.repo} with this access token. Check it has read access "
                        "to the repository's contents.")
            return (f"GitHub can't find {self.repo}. If the repository is private, add a GitHub access token "
                    "below (or make the repository public).")
        return f"Couldn't check for updates: GitHub answered {e.code} {e.reason}"

    def set_token(self, token):
        """Use (and keep) a GitHub access token; "" removes it. Checks again straight away."""
        self.token = str(token or "").strip()
        if self.settings is not None:
            self.settings.set("github_token", self.token)
        return self.check()

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
            "can_install": available and self._can_install(latest),
            "mode": "installer" if self.installer_mode else "files",
            "git_checkout": not self.installer_mode and self.is_git_checkout(),
            "installing": self.installing,
            "installed": self.installed,
            "checked_at": self.checked_at,
            "error": self.error,
            "repo": self.repo,
            "has_token": bool(self.token),
        }

    def _can_install(self, latest):
        if self.installer_mode:
            return bool(latest.get("installer"))
        return not self.is_git_checkout()

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
        if not status["can_install"]:
            raise UpdateError("This release has no Windows installer: download it from the release page.")
        with self._lock:
            if self.installing:
                raise UpdateError("An update is already being installed.")
            self.installing = True
        try:
            latest = self.latest
            if self.installer_mode:
                self._run_installer(latest)
                self.installed = latest["version"]
                return latest["version"]
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

    def _run_installer(self, latest):
        """Download the release's installer and start it; it replaces and reopens the app."""
        asset = latest["installer"]
        with self._get(asset["url"], accept="application/octet-stream") as resp:
            data = resp.read(MAX_INSTALLER_BYTES + 1)
        if len(data) > MAX_INSTALLER_BYTES:
            raise UpdateError("The installer is unexpectedly large.")
        if not data.startswith(b"MZ") or (asset.get("size") and len(data) != asset["size"]):
            raise UpdateError("The installer download is incomplete or damaged.")
        folder = Path(tempfile.mkdtemp(prefix="apex-update-"))
        path = folder / asset["name"]
        path.write_bytes(data)
        # The installer waits for this app to exit, updates it, then reopens it.
        self._launch([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH"])

    def _install_requirements(self):
        req = self.root / "requirements.txt"
        if req.is_file():
            # Best effort: the app still runs in --mock without them.
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)],
                           check=False, timeout=600)


def _launch_detached(args):
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, creationflags=flags, close_fds=True)


# Set after an update is installed; __main__ shuts down, then relaunches
# itself unless an installer is going to do that.
restart_requested = threading.Event()
restart_options = {"relaunch": True}


def request_restart(delay=1.0, relaunch=True):
    """Ask the app to restart shortly (giving the HTTP response time to go out)."""
    restart_options["relaunch"] = relaunch
    threading.Timer(delay, restart_requested.set).start()
