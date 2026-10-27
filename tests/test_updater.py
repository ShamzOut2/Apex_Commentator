import io
import json
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path

from apex.updater import Updater, UpdateError, parse_version

REPO = "ShamzOut2/Apex_Commentator"


def archive(version, extra=None, top="ShamzOut2-Apex_Commentator-abc123"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{top}/apex/__init__.py", f'__version__ = "{version}"\n')
        z.writestr(f"{top}/web/app.js", "// new\n")
        z.writestr(f"{top}/config.json", '{"port": 1}')
        z.writestr(f"{top}/data/leagues/x.json", "{}")
        for name, body in (extra or {}).items():
            z.writestr(name, body)
    return buf.getvalue()


class FakeGitHub:
    """Stands in for urllib.request.urlopen."""

    def __init__(self, release=None, tags=(), zip_bytes=b"", fail=None):
        self.release, self.tags, self.zip_bytes, self.fail = release, list(tags), zip_bytes, fail
        self.requests = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.requests.append(url)
        if self.fail:
            raise self.fail
        if url.endswith("/releases/latest"):
            if self.release is None:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return io.BytesIO(json.dumps(self.release).encode())
        if "/tags" in url:
            return io.BytesIO(json.dumps([{"name": t} for t in self.tags]).encode())
        if "zipball" in url:
            return io.BytesIO(self.zip_bytes)
        raise AssertionError(url)


RELEASE = {
    "tag_name": "v0.2.0", "body": "- New stuff", "html_url": "https://github.com/x/releases/v0.2.0",
    "zipball_url": "https://api.github.com/repos/x/zipball/v0.2.0", "published_at": "2026-11-01T00:00:00Z",
}


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "apex").mkdir()
        (self.root / "apex" / "__init__.py").write_text('__version__ = "0.1.0"\n')
        (self.root / "config.json").write_text('{"port": 8180}')
        (self.root / "data" / "leagues").mkdir(parents=True)
        (self.root / "data" / "leagues" / "mine.json").write_text('{"name": "Mine"}')

    def tearDown(self):
        self.tmp.cleanup()

    def updater(self, gh):
        return Updater("0.1.0", REPO, self.root, self.root / "data" / "update.json", opener=gh)

    def test_parse_version(self):
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("0.10.0"), (0, 10, 0))
        self.assertIsNone(parse_version("v1.2"))
        self.assertIsNone(parse_version("latest"))
        self.assertGreater(parse_version("0.10.0"), parse_version("0.9.9"))

    def test_newer_release_is_offered(self):
        u = self.updater(FakeGitHub(release=RELEASE))
        s = u.check()
        self.assertTrue(s["available"])
        self.assertEqual((s["latest"]["version"], s["latest"]["notes"]), ("0.2.0", "- New stuff"))
        self.assertTrue(s["can_install"])
        u.skip("0.2.0")
        self.assertTrue(u.status()["skipped"])

    def test_same_or_older_is_not_offered(self):
        self.assertFalse(self.updater(FakeGitHub(release=dict(RELEASE, tag_name="v0.1.0"))).check()["available"])
        self.assertFalse(self.updater(FakeGitHub(release=dict(RELEASE, tag_name="v0.0.9"))).check()["available"])

    def test_falls_back_to_tags_without_releases(self):
        s = self.updater(FakeGitHub(tags=["v0.1.0", "v0.3.1", "nightly", "v0.10.0"])).check()
        self.assertEqual(s["latest"]["version"], "0.10.0")
        self.assertTrue(s["available"])

    def test_network_errors_are_reported_not_raised(self):
        s = self.updater(FakeGitHub(fail=urllib.error.URLError("offline"))).check()
        self.assertFalse(s["available"])
        self.assertIn("offline", s["error"])

    def test_install_keeps_settings_and_leagues(self):
        u = self.updater(FakeGitHub(release=RELEASE, zip_bytes=archive("0.2.0")))
        u._install_requirements = lambda: None
        u.check()
        self.assertEqual(u.install(), "0.2.0")
        self.assertIn('"0.2.0"', (self.root / "apex" / "__init__.py").read_text())
        self.assertEqual((self.root / "web" / "app.js").read_text(), "// new\n")
        self.assertEqual((self.root / "config.json").read_text(), '{"port": 8180}')
        self.assertEqual((self.root / "data" / "leagues" / "mine.json").read_text(), '{"name": "Mine"}')
        self.assertFalse((self.root / "data" / "leagues" / "x.json").exists())
        self.assertEqual(u.status()["installed"], "0.2.0")

    def test_install_refuses_bad_archives(self):
        cases = {
            "damaged": b"not a zip",
            "wrong version": archive("0.1.5"),
            "unsafe path": archive("0.2.0", {"../../evil.txt": "x"}),
            "not apex": self._zip({"x/readme.md": "hi"}),
        }
        for name, data in cases.items():
            with self.subTest(name):
                u = self.updater(FakeGitHub(release=RELEASE, zip_bytes=data))
                u._install_requirements = lambda: None
                u.check()
                with self.assertRaises(UpdateError):
                    u.install()
                self.assertIn('"0.1.0"', (self.root / "apex" / "__init__.py").read_text())
        self.assertFalse((self.root.parent / "evil.txt").exists())

    @staticmethod
    def _zip(files):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, body in files.items():
                z.writestr(name, body)
        return buf.getvalue()

    def test_git_checkout_is_never_overwritten(self):
        (self.root / ".git").mkdir()
        u = self.updater(FakeGitHub(release=RELEASE, zip_bytes=archive("0.2.0")))
        s = u.check()
        self.assertTrue(s["available"])
        self.assertFalse(s["can_install"])
        with self.assertRaises(UpdateError):
            u.install()

    def test_nothing_to_install(self):
        u = self.updater(FakeGitHub(release=dict(RELEASE, tag_name="v0.1.0")))
        u.check()
        with self.assertRaises(UpdateError):
            u.install()

    def test_disabled(self):
        u = Updater("0.1.0", REPO, self.root, self.root / "u.json", enabled=False, opener=FakeGitHub(fail=AssertionError()))
        self.assertFalse(u.check()["available"])


if __name__ == "__main__":
    unittest.main()
