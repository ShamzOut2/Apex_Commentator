"""CHANGELOG.md: each version's notes, and the README's "What's new" copy of the newest.

The changelog's format is described at the top of CHANGELOG.md. Run
``python -m apex.changelog`` after editing it to refresh the README, and
``python -m apex.changelog --notes v1.2.3`` to print a version's notes (the
release workflow does: a version without its own section yet gets the
"Unreleased" one).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- whats-new:start -->", "<!-- whats-new:end -->"


def sections(text):
    """[(title, notes)] for each "## " section, newest first."""
    out = []
    for block in re.split(r"(?m)^## ", text)[1:]:
        title, _, body = block.partition("\n")
        out.append((title.strip(), body.strip()))
    return out


def notes_for(text, version):
    """A version's notes ("0.4.2" or "v0.4.2"), or None."""
    want = version.lstrip("v")
    for title, body in sections(text):
        if title.strip("[]").lstrip("v") == want:
            return body
    return None


def whats_new(text):
    """The README's "What's new": the newest section of the changelog."""
    title, body = sections(text)[0]
    heading = "Coming in the next update" if title.lower() == "unreleased" else title
    return f"{START}\n**{heading}**\n\n{body}\n\nEvery version's notes: [CHANGELOG.md](CHANGELOG.md).\n{END}"


def refresh_readme(changelog=ROOT / "CHANGELOG.md", readme=ROOT / "README.md"):
    """Copy the newest changelog section into the README. Returns True if it changed."""
    text = readme.read_text(encoding="utf-8")
    block = whats_new(changelog.read_text(encoding="utf-8"))
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    if new == text:
        return False
    readme.write_text(new, encoding="utf-8")
    return True


def release_notes(text, version):
    """Notes for releasing ``version``: its own section, else "Unreleased"."""
    return notes_for(text, version) or next((b for t, b in sections(text) if t.lower() == "unreleased"), "")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--notes"] and len(sys.argv) == 3:
        print(release_notes((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), sys.argv[2]))
    else:
        print("README.md updated." if refresh_readme() else "README.md is up to date.")
