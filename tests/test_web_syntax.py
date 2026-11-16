"""Every page's script parses (a syntax error stops a whole overlay loading).
Needs Node.js on the PATH; skipped without it."""

import shutil
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


@unittest.skipUnless(shutil.which("node"), "Node.js not installed")
class WebSyntaxTests(unittest.TestCase):
    def test_every_script_parses(self):
        scripts = sorted(WEB.glob("*.js")) + sorted((WEB / "live").glob("*.js"))
        self.assertTrue(scripts)
        for path in scripts:
            with self.subTest(script=path.name):
                done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
