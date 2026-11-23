"""The lap tracker's small trackers (laps.js pickSmall): the laps nearest the
line, not whoever started a lap first. Needs Node.js on the PATH; skipped
without it."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"

HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[1], "utf8");
const body = src.slice(src.indexOf("const SWAP_LAP"), src.indexOf("function render() {"));
const shown = new Map();
const pickSmall = new Function("shown", body + "; return pickSmall;")(shown);
const run = (idx, progress, elapsed) => ({ car_idx: idx, lap: { state: "running", progress, elapsed } });
const fin = (idx, shown_for) => ({ car_idx: idx, lap: { state: "finished", shown_for, elapsed: 90 } });
const up = (l) => { shown.clear(); for (const i of l) shown.set(i, { kind: "small" }); };
const ids = (l) => l.map((t) => t.car_idx).sort((a, b) => a - b);
const out = {};
up([]);
let tr = [run(1, 0.10, 80), run(2, 0.95, 70), run(3, 0.60, 60), run(4, 0.05, 5), run(5, 0.80, 40)];
out.nearest = ids(pickSmall(tr, 2));
up([2, 5]); tr.push(run(6, 0.01, 1)); out.new_lap = ids(pickSmall(tr, 2));
up([1, 2]); out.far_gives_way = ids(pickSmall(tr, 2));
up([2, 9]); out.no_flip_flop = ids(pickSmall([run(2, 0.95, 70), run(9, 0.78, 50), run(5, 0.80, 40)], 2));
up([2, 9]); out.finished_stays = ids(pickSmall([fin(2, 3), run(9, 0.78, 50), run(5, 0.30, 40), fin(7, 4)], 2));
up([9, 5]); out.just_finished = ids(pickSmall([fin(7, 0.4), run(9, 0.78, 50), run(5, 0.30, 40)], 2));
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "Node.js not installed")
class SmallTrackerPickTests(unittest.TestCase):
    def test_the_laps_nearest_the_line(self):
        done = subprocess.run(["node", "-e", HARNESS, str(WEB / "laps.js")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["nearest"], [2, 5])          # 95% and 80% round, not the longest on a lap
        self.assertEqual(out["new_lap"], [2, 5])          # a lap just started never takes a place
        self.assertEqual(out["far_gives_way"], [2, 5])    # one up but far from the line gives way
        self.assertEqual(out["no_flip_flop"], [2, 9])     # 78% up, 80% waiting: no swap
        self.assertEqual(out["finished_stays"], [2, 9])   # a lap up that finished stays for its seconds
        self.assertEqual(out["just_finished"], [7, 9])    # a lap just finished takes the furthest one's place


if __name__ == "__main__":
    unittest.main()
