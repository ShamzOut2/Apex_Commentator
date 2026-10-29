import re
import unittest

from apex import changelog

SECTIONS = ["New features", "Improvements", "Fixes"]


class ChangelogTests(unittest.TestCase):
    def setUp(self):
        self.text = (changelog.ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    def test_readme_shows_the_newest_notes(self):
        readme = (changelog.ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(changelog.whats_new(self.text), readme,
                      "README's What's new is out of date: run python -m apex.changelog")

    def test_newest_entry_uses_the_simple_sections(self):
        title, body = changelog.sections(self.text)[0]
        self.assertRegex(title, r"^(Unreleased|v\d+\.\d+\.\d+)$")
        found = re.findall(r"(?m)^### (.+)$", body)
        self.assertTrue(found, "the newest entry needs at least one of: " + ", ".join(SECTIONS))
        self.assertTrue(set(found) <= set(SECTIONS), found)
        self.assertEqual(found, sorted(found, key=SECTIONS.index))  # in the usual order

    def test_release_notes(self):
        text = "# Changelog\n\nintro\n\n## Unreleased\n\n### Fixes\n\n- a\n\n## v1.0.0\n\n### New features\n\n- b\n"
        self.assertEqual(changelog.release_notes(text, "v1.0.0"), "### New features\n\n- b")
        self.assertEqual(changelog.release_notes(text, "v1.1.0"), "### Fixes\n\n- a")  # not renamed yet
        self.assertEqual(changelog.notes_for(text, "1.0.0"), "### New features\n\n- b")
