"""The live snapshot as sent down the event stream (/api/stream), encoded once
for every page listening.

Most of a snapshot doesn't change from one to the next: the overlay settings,
the grid walk, the race log, the championship. Every page open (each overlay
in OBS, the app, pop-outs) reads each snapshot it's sent, several times a
second, so those parts are only sent when they've changed. A snapshot that
leaves some out starts with ``"_same": [...]``, naming them (``"events"``, or
``"overlays.settings"`` for one inside ``overlays``): the page keeps what it
had for those (``liveStream`` in common.js). A page gets that only if it had
the snapshot just before; otherwise, and every ``FULL_EVERY`` snapshots for
everyone (so a page that's just opened catches up), the whole thing.
"""

import json

NESTED = ("overlays",)  # parts whose own parts are looked at one by one
MIN_SAME = 200          # parts smaller than this (bytes) are always sent: hardly worth it
FULL_EVERY = 16         # every so many snapshots, a whole one for every page


def _dumps(value):
    return json.dumps(value, separators=(",", ":"))


class Payloads:
    def __init__(self):
        self._version = None   # the snapshot encoded last
        self._base = None      # the one before it (what "_same" is relative to)
        self._parts = []       # [(key, json) or (key, [(path, key json, json)])]
        self._seen = {}        # path -> json, the last snapshot's
        self._same = set()     # parts unchanged since the one before
        self._count = 0
        self._full = None
        self._lean = None

    def get(self, version, snap, last_version):
        """The snapshot (``version``) as JSON bytes for a page that had
        ``last_version``: only what's changed if that's the one before it."""
        if version != self._version:
            self._encode(version, snap)
        if self._same and last_version is not None and last_version == self._base:
            if self._lean is None:
                self._lean = self._join(self._same)
            return self._lean
        if self._full is None:
            self._full = self._join(())
        return self._full

    def _encode(self, version, snap):
        parts, seen = [], {}
        for key, value in snap.items():  # (the snapshot's own keys are all words)
            if key in NESTED and isinstance(value, dict) and all(isinstance(k, str) for k in value):
                inner = []
                for sub, v in value.items():
                    path = f"{key}.{sub}"
                    seen[path] = _dumps(v)
                    inner.append((path, _dumps(sub), seen[path]))
                parts.append((key, inner))
            else:
                seen[key] = _dumps(value)
                parts.append((key, seen[key]))
        self._count += 1
        full_now = self._count % FULL_EVERY == 0
        self._same = set() if full_now else {
            path for path, enc in seen.items() if len(enc) >= MIN_SAME and self._seen.get(path) == enc}
        self._base, self._version = self._version, version
        self._parts, self._seen = parts, seen
        self._full = self._lean = None

    def _join(self, same):
        items = [f'"_same":{_dumps(sorted(same))}'] if same else []
        for key, enc in self._parts:
            if isinstance(enc, list):
                inner = ",".join(f"{k}:{v}" for path, k, v in enc if path not in same)
                items.append(f"{_dumps(key)}:{{{inner}}}")
            elif key not in same:
                items.append(f"{_dumps(key)}:{enc}")
        return ("{" + ",".join(items) + "}").encode("utf-8")
