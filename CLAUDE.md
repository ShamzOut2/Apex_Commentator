# Notes for working on Apex Commentator

## Every change gets a changelog line

Any change a user would notice gets a line in `CHANGELOG.md` under
`## Unreleased`, in the format described at the top of that file:
`### New features`, `### Improvements`, `### Fixes`, one short plain line
each. Then run `python -m apex.changelog` so the README's "What's new" matches
(`tests/test_changelog.py` fails otherwise).

## Releasing

1. Rename `## Unreleased` in `CHANGELOG.md` to `## vX.Y.Z`.
2. Set `__version__` in `apex/__init__.py` to `X.Y.Z`.
3. Run `python -m apex.changelog` and the tests.
4. Merge to `main`. The release workflow builds the Windows installer and
   publishes the release with that changelog section as its notes; installed
   apps show them in the update pop-up.
