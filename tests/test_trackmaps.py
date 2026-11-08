import json
import math
import tempfile
import unittest
from pathlib import Path

from apex import trackmaps
from apex.trackmaps import BINS, TrackMaps, build

# A square track, 100 x 100, drawn clockwise on screen from the top-left
# corner; the start/finish line half way along the top; turn 1 on the right
# side, turn 2 at the bottom.
ACTIVE = '<svg><g transform="translate(10,10)"><path d="M0,0 L100,0 L100,100 L0,100 Z"/></g></svg>'
START = '<svg><rect x="58" y="5" width="4" height="10"/></svg>'
TURNS_CW = '<svg><text x="110" y="60">1</text><text x="60" y="110">2</text></svg>'
TURNS_CCW = '<svg><text x="10" y="60">1</text><text x="60" y="110">2</text></svg>'


class BuildTests(unittest.TestCase):
    def test_outline_from_the_start_line_in_the_direction_of_travel(self):
        pts = build(ACTIVE, START, TURNS_CW)
        self.assertEqual(len(pts), BINS)
        # Starts at the start line, top middle (screen coordinates: the top is y = 0).
        self.assertAlmostEqual(pts[0][0], 0.5, places=2)
        self.assertAlmostEqual(pts[0][1], 0.0, places=2)
        # Clockwise on screen: next it heads right, and a quarter lap on it's on the right side.
        self.assertGreater(pts[10][0], pts[0][0])
        self.assertAlmostEqual(pts[BINS // 4][0], 1.0, places=2)

    def test_turn_numbers_turn_it_round(self):
        pts = build(ACTIVE, START, TURNS_CCW)
        self.assertLess(pts[10][0], pts[0][0])  # heading left: turn 1 is on the left side
        self.assertAlmostEqual(pts[BINS // 4][0], 0.0, places=2)

    def test_a_track_drawn_as_a_ribbon_uses_its_centre_line(self):
        # A loop 1.5 units wide (a track at map scale): out along the outer edge, back along the inner.
        outer = [(50 + 40 * math.cos(a / 60 * 2 * math.pi), 50 + 40 * math.sin(a / 60 * 2 * math.pi)) for a in range(61)]
        inner = [(50 + 38.5 * math.cos(a / 60 * 2 * math.pi), 50 + 38.5 * math.sin(a / 60 * 2 * math.pi)) for a in range(60, -1, -1)]
        d = "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in outer + inner) + " Z"
        closed = []
        pts = build(f'<svg><path d="{d}"/></svg>', None, None, closed)
        self.assertIsNotNone(pts)
        # The centre line: a circle, every point at the same distance from the middle.
        r = [math.hypot(x - 0.5, y - 0.5) for x, y in pts]
        self.assertLess(max(r) - min(r), 0.02)

    def test_symbols_placed_by_use(self):
        svg = ('<svg><defs><symbol id="trk" viewBox="0 0 100 100"><path d="M0,0 L100,0 L100,100 L0,100 Z"/></symbol></defs>'
               '<use xlink:href="#trk" x="10" y="10" width="100" height="100"/></svg>')
        self.assertEqual(len(build(svg, START, TURNS_CW)), BINS)

    def test_turn_numbers(self):
        from apex.trackmaps import _turn_numbers
        nums = _turn_numbers([("T3", (5, 50)), ("Turn 4", (90, 60)), ("1", (20, 0)), ("1", (27, 0)), ("1º Curva", (0, 0))])
        self.assertEqual(sorted(n for n, _ in nums), [3, 4, 11])  # "1" "1" side by side: 11; a corner name isn't a number

    def test_curves_and_relative_paths(self):
        pts = build('<svg><path d="m0,0 c50,-20 100,0 100,0 l0,100 h-100 z"/></svg>')
        self.assertEqual(len(pts), BINS)
        self.assertIsNone(build("<svg></svg>"))


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shared_library_outline(self):
        road_atlanta = (Path(__file__).parent / "data" / "trackmap-127.json").read_bytes()
        urls = []

        def fetch(url):
            urls.append(url)
            if url == trackmaps.INDEX_URL:
                raise OSError("not published yet")
            if url.endswith("/index.json"):
                return json.dumps({"tracks": {"127": "Road Atlanta"}}).encode()
            if url.endswith("/127.json"):
                return road_atlanta
            raise OSError(url)

        maps = TrackMaps(self.dir / "cache", fetch=fetch, local_dirs=[])
        m = maps.get(127, wait=True)
        self.assertEqual((m["source"], len(m["points"])), ("library", BINS))
        self.assertIsNone(maps.get(999, wait=True))  # not in the library: none (the round map)
        # Cached: no more downloads for it.
        again = TrackMaps(self.dir / "cache", fetch=lambda u: (_ for _ in ()).throw(OSError("offline")), local_dirs=[])
        self.assertEqual(again.get(127, wait=True)["source"], "library")

    def test_official_map_from_the_published_index(self):
        # iRacing's server doesn't answer: the mirror's copy is used.
        files = {"https://mirror.example/1/active.svg": ACTIVE, "https://mirror.example/1/start-finish.svg": START,
                 "https://mirror.example/1/turns.svg": TURNS_CW}

        def fetch(url):
            if url == trackmaps.INDEX_URL:
                return json.dumps({"55": {"track_map": "https://maps.example/1/", "mirror": "https://mirror.example/1/",
                                          "track_map_layers": {"active": "active.svg", "start-finish": "start-finish.svg",
                                                               "turns": "turns.svg"}}}).encode()
            if url not in files:
                raise OSError(url)
            return files[url].encode()

        m = TrackMaps(self.dir, fetch=fetch, local_dirs=[]).get(55, wait=True)
        self.assertEqual(m["source"], "iracing")
        self.assertAlmostEqual(m["points"][0][0], 0.5, places=2)

    def test_apex_overlays_recording_comes_first(self):
        local = self.dir / "Apex Overlays"
        (local / "trackmaps").mkdir(parents=True)
        (local / "trackmaps" / "7.json").write_text(json.dumps({"trackId": 7, "points": [[i / 100, 0.5] for i in range(100)]}))
        m = TrackMaps(self.dir / "cache", fetch=lambda u: (_ for _ in ()).throw(OSError("offline")), local_dirs=[local]).get(7, wait=True)
        self.assertEqual(m["source"], "recorded")

    def test_offline_tries_again_later(self):
        maps = TrackMaps(self.dir, fetch=lambda u: (_ for _ in ()).throw(OSError("offline")), local_dirs=[])
        self.assertIsNone(maps.get(127, wait=True))
        self.assertNotIn(127, maps._maps)  # not remembered as "no map": tried again after RETRY_S
