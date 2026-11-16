"""The snapshot as sent down the event stream: parts that haven't changed are
left out for pages that had the one before, and pages put them back."""

import json
import unittest

from apex.payload import FULL_EVERY, Payloads

BIG = {"rows": list(range(100))}


def snap(n, settings=BIG, events=None):
    return {"version": "1", "session": {"time": n}, "events": events if events is not None else [{"id": 1, "text": "x" * 300}],
            "overlays": {"settings": settings, "standings": [{"gap": n}]}}


def whole(had, data):
    """What the page makes of it (as wholeSnapshots in common.js)."""
    s = json.loads(data)
    for path in s.pop("_same", []):
        key, _, sub = path.partition(".")
        if sub:
            s[key][sub] = had[key][sub]
        else:
            s[key] = had[key]
    return s


class PayloadTests(unittest.TestCase):
    def test_unchanged_parts_left_out_and_put_back(self):
        p = Payloads()
        first = json.loads(p.get(1, snap(1), None))
        self.assertEqual(first, snap(1))                      # a page just joined: all of it
        data = p.get(2, snap(2), 1)
        lean = json.loads(data)
        self.assertEqual(sorted(lean["_same"]), ["events", "overlays.settings"])
        self.assertNotIn("events", lean)
        self.assertNotIn("settings", lean["overlays"])
        self.assertEqual(lean["overlays"]["standings"], [{"gap": 2}])
        self.assertEqual(whole(first, data), snap(2))
        # A page that missed one (or just joined) gets the whole of it.
        self.assertEqual(json.loads(p.get(2, snap(2), None)), snap(2))
        self.assertEqual(json.loads(p.get(3, snap(3), 1)), snap(3))

    def test_changes_always_sent(self):
        p = Payloads()
        had = json.loads(p.get(1, snap(1), None))
        changed = snap(2, settings={"rows": [1, 2, 3] * 50}, events=[{"id": 2, "text": "y" * 300}])
        data = p.get(2, changed, 1)
        self.assertNotIn("_same", json.loads(data))
        self.assertEqual(whole(had, data), changed)
        # Settings changed in place (the same object): still seen as changed.
        live = snap(3)
        had = json.loads(p.get(3, live, 2))
        live["overlays"]["settings"]["rows"].append(1000)
        data = p.get(4, live, 3)
        self.assertEqual(whole(had, data)["overlays"]["settings"]["rows"][-1], 1000)

    def test_a_whole_one_every_so_often_and_once_encoded(self):
        p = Payloads()
        p.get(1, snap(1), None)
        wholes = 0
        for n in range(2, 2 + FULL_EVERY * 2):
            data = p.get(n, snap(n), n - 1)
            self.assertIs(p.get(n, snap(n), n - 1), data)  # the same bytes for every page in step
            wholes += "_same" not in json.loads(data)
        self.assertEqual(wholes, 2)


if __name__ == "__main__":
    unittest.main()
