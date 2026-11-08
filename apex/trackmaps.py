"""Track outlines for the spectators' live timing map.

The same method as Apex Overlays (github.com/ShamzOut2/Apex_Overlays): an
outline is a list of BINS points, point i sitting at lap fraction i / BINS,
x / y in 0..1. A car's lap distance (``CarIdxLapDistPct``, the one position
iRacing gives for every car, spectating too) puts it straight on the map.

Where an outline comes from, best first:

1. Apex Overlays on this PC: an outline it recorded from a clean lap.
2. iRacing's official track map: its SVG layers (the racing line, the
   start/finish line and the turn numbers, for the direction of travel),
   located through the index Apex Overlays publishes (the SVG files are
   public; only iRacing's index of them needs a login), converted here.
3. The shared library of recorded outlines Apex Overlays publishes.

Nothing found: no outline, and the page draws its round map. Downloads run
in the background and are cached (``USER_DIR/trackmaps``).
"""

import json
import math
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

BINS = 500
REPO = "https://raw.githubusercontent.com/ShamzOut2/Apex_Overlays/main/data"
INDEX_URL = f"{REPO}/iracing-track-maps.json"
LIBRARY_URL = f"{REPO}/trackmaps"
# The public catalogue of iRacing's track maps kept by the racing-track-maps-vector
# project (for tracks newer than the published index), and its copy of the SVG files
# (used when iRacing's own server doesn't answer).
CATALOGUE_URL = "https://raw.githubusercontent.com/meowmachine/racing-track-maps-vector/main/from-iracing/iracing-tracks-metadata.json"
MIRROR_URL = "https://raw.githubusercontent.com/meowmachine/racing-track-maps-vector/main/from-iracing"
LAYERS = ("active", "start-finish", "turns")
INDEX_MAX_AGE_S = 7 * 86400
RETRY_S = 600


# -- iRacing's SVG track maps -> an outline --------------------------------------

_ID = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _mul(a, b):
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def _apply(m, p):
    return (m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5])


def _numbers(s):
    return [float(x) for x in _NUM.findall(s or "")]


def _transform(s):
    """``transform="translate(..) matrix(..) scale(..) rotate(..)"``."""
    m = _ID
    for name, args in re.findall(r"([a-zA-Z]+)\s*\(([^)]*)\)", s or ""):
        v = _numbers(args)
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate":
            t = (1.0, 0.0, 0.0, 1.0, v[0] if v else 0.0, v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            sx = v[0] if v else 1.0
            t = (sx, 0.0, 0.0, v[1] if len(v) > 1 else sx, 0.0, 0.0)
        elif name == "rotate":
            a = math.radians(v[0] if v else 0.0)
            r = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0.0, 0.0)
            if len(v) >= 3:
                cx, cy = v[1], v[2]
                r = _mul(_mul((1.0, 0.0, 0.0, 1.0, cx, cy), r), (1.0, 0.0, 0.0, 1.0, -cx, -cy))
            t = r
        else:
            t = _ID
        m = _mul(m, t)
    return m


def _path(d):
    """Subpaths of an SVG path, curves flattened."""
    subs, cur = [], []
    pos, start, ctrl = (0.0, 0.0), (0.0, 0.0), None

    def flush():
        nonlocal cur
        if len(cur) > 1:
            subs.append(cur)
        cur = []

    def cubic(p0, c1, c2, p):
        for k in range(1, 13):
            t = k / 12
            u = 1 - t
            cur.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p[0],
                        u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p[1]))

    for cmd, args in re.findall(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)", d or ""):
        v = _numbers(args)
        rel = cmd.islower()

        def off(p):
            return (p[0] + pos[0], p[1] + pos[1]) if rel else p

        c = cmd.upper()
        if c == "M":
            flush()
            for i in range(0, len(v) - 1, 2):
                pos = off((v[i], v[i + 1]))
                if i == 0:
                    start = pos
                cur.append(pos)
            ctrl = None
        elif c in "LT":
            for i in range(0, len(v) - 1, 2):
                pos = off((v[i], v[i + 1]))
                cur.append(pos)
            ctrl = None
        elif c == "H":
            for x in v:
                pos = (pos[0] + x if rel else x, pos[1])
                cur.append(pos)
            ctrl = None
        elif c == "V":
            for y in v:
                pos = (pos[0], pos[1] + y if rel else y)
                cur.append(pos)
            ctrl = None
        elif c == "C":
            for i in range(0, len(v) - 5, 6):
                c1, c2, p = off((v[i], v[i + 1])), off((v[i + 2], v[i + 3])), off((v[i + 4], v[i + 5]))
                cubic(pos, c1, c2, p)
                ctrl, pos = c2, p
        elif c == "S":
            for i in range(0, len(v) - 3, 4):
                c1 = (2 * pos[0] - ctrl[0], 2 * pos[1] - ctrl[1]) if ctrl else pos
                c2, p = off((v[i], v[i + 1])), off((v[i + 2], v[i + 3]))
                cubic(pos, c1, c2, p)
                ctrl, pos = c2, p
        elif c == "Q":
            for i in range(0, len(v) - 3, 4):
                q, p = off((v[i], v[i + 1])), off((v[i + 2], v[i + 3]))
                c1 = (pos[0] + 2 / 3 * (q[0] - pos[0]), pos[1] + 2 / 3 * (q[1] - pos[1]))
                c2 = (p[0] + 2 / 3 * (q[0] - p[0]), p[1] + 2 / 3 * (q[1] - p[1]))
                cubic(pos, c1, c2, p)
                ctrl, pos = None, p
        elif c == "A":
            for i in range(0, len(v) - 6, 7):  # arcs are rare in track maps: a straight line will do
                pos = off((v[i + 5], v[i + 6]))
                cur.append(pos)
            ctrl = None
        elif c == "Z":
            if not cur or cur[0] != pos:
                cur.append(start)
            pos = start
            flush()
            ctrl = None
    flush()
    return subs


def _attr(tag, name):
    m = re.search(r'(?:^|\s)%s\s*=\s*("([^"]*)"|\'([^\']*)\')' % re.escape(name), tag)
    if not m:
        return None
    return m.group(2) if m.group(2) is not None else m.group(3)


def _element_by_id(doc, eid):
    """The element (a symbol, say) with this id: (its tag, its content)."""
    at = doc.find(f'id="{eid}"')
    if at < 0:
        at = doc.find(f"id='{eid}'")
    if at < 0:
        return None
    start = doc.rfind("<", 0, at)
    end_tag = doc.find(">", start)
    if start < 0 or end_tag < 0:
        return None
    tag = doc[start + 1:end_tag]
    if tag.endswith("/"):
        return tag, ""
    name = re.match(r"[A-Za-z0-9]*", tag).group(0)
    close = doc.find(f"</{name}", end_tag)
    return (tag, doc[end_tag + 1:close]) if close >= 0 else None


def _parse_svg(svg):
    """(shapes, texts): every shape's points and every text label's position, in document coordinates."""
    shapes, texts = [], []
    _parse_into(svg, svg, _ID, 0, shapes, texts)
    return shapes, texts


def _parse_into(doc, svg, base, depth, shapes, texts):
    stack = [base]
    i = 0
    while True:
        s = svg.find("<", i)
        if s < 0:
            break
        e = svg.find(">", s)
        if e < 0:
            break
        tag = svg[s + 1:e]
        i = e + 1
        if tag.startswith("/"):
            if tag[1:].lstrip().startswith("g") and len(stack) > 1:
                stack.pop()
            continue
        name = re.match(r"[A-Za-z0-9]*", tag).group(0)
        selfclose = tag.endswith("/")
        m = _mul(stack[-1], _transform(_attr(tag, "transform")))

        def f(k, default=0.0):
            v = _numbers(_attr(tag, k) or "")
            return v[0] if v else default

        def tr(pts):
            return [_apply(m, p) for p in pts]

        if name == "g" and not selfclose:
            stack.append(m)
        elif name in ("defs", "symbol") and not selfclose:
            k = svg.find(f"</{name}", i)  # definitions are only drawn where a <use> places them
            if k >= 0:
                i = k
        elif name == "use" and depth < 4:
            href = _attr(tag, "xlink:href") or _attr(tag, "href") or ""
            found = _element_by_id(doc, href[1:]) if href.startswith("#") else None
            if not found:
                continue
            target, content = found
            # At (x, y), the symbol's viewBox fitted into width x height (centred).
            place = _mul(m, (1.0, 0.0, 0.0, 1.0, f("x"), f("y")))
            vb = _numbers(_attr(target, "viewBox") or "")
            w, h = _numbers(_attr(tag, "width") or ""), _numbers(_attr(tag, "height") or "")
            if len(vb) >= 4 and w and h and vb[2] > 0 and vb[3] > 0:
                k = min(w[0] / vb[2], h[0] / vb[3])
                place = _mul(place, (k, 0.0, 0.0, k, (w[0] - vb[2] * k) / 2 - vb[0] * k, (h[0] - vb[3] * k) / 2 - vb[1] * k))
            _parse_into(doc, content or f"<{target}>", place, depth + 1, shapes, texts)
        elif name == "path":
            shapes.extend(tr(sub) for sub in _path(_attr(tag, "d")))
        elif name in ("polygon", "polyline"):
            v = _numbers(_attr(tag, "points") or "")
            pts = [(v[k], v[k + 1]) for k in range(0, len(v) - 1, 2)]
            if name == "polygon" and len(pts) > 2:
                pts.append(pts[0])
            shapes.append(tr(pts))
        elif name == "line":
            shapes.append(tr([(f("x1"), f("y1")), (f("x2"), f("y2"))]))
        elif name == "rect":
            x, y, w, h = f("x"), f("y"), f("width"), f("height")
            shapes.append(tr([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]))
        elif name in ("circle", "ellipse"):
            shapes.append(tr([(f("cx"), f("cy"))]))
        elif name == "text" and not selfclose:
            end = svg.find("</text", i)
            end = end if end >= 0 else i
            inner = svg[i:end]
            content = re.sub(r"<[^>]*>", "", inner).strip()
            pos = (f("x"), f("y"))
            if pos == (0.0, 0.0):
                t = re.search(r"<tspan[^>]*>", inner)
                if t:
                    tv = lambda k: (_numbers(_attr(t.group(0)[1:-1], k) or "") or [0.0])[0]  # noqa: E731
                    pos = (tv("x"), tv("y"))
            texts.append((content, _apply(m, pos)))
            i = end


def _length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _cumulative(line):
    cum = [0.0]
    for a, b in zip(line, line[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return cum


def _nearest(line, cum, p, skip=None):
    """(distance from the line, the distance along it of the nearest point); ``skip(mid)`` leaves segments out."""
    best = (float("inf"), 0.0)
    for k in range(len(line) - 1):
        if skip and skip((cum[k] + cum[k + 1]) / 2):
            continue
        a, b = line[k], line[k + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        t = min(1.0, max(0.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) if l2 > 0 else 0.0
        d = math.hypot(p[0] - (a[0] + dx * t), p[1] - (a[1] + dy * t))
        if d < best[0]:
            best = (d, cum[k] + t * math.sqrt(l2))
    return best


def _project(line, cum, p):
    """Arc position (0..length) of the point on the line nearest ``p``."""
    return _nearest(line, cum, p)[1]


def _at(line, cum, s):
    """The point ``s`` along a closed line (wrapping round)."""
    total = cum[-1]
    s %= total
    lo, hi = 1, len(cum) - 1
    while lo < hi:  # the first k with cum[k] > s
        mid = (lo + hi) // 2
        if cum[mid] <= s:
            lo = mid + 1
        else:
            hi = mid
    k = lo
    a, b = line[k - 1], line[k]
    seg = cum[k] - cum[k - 1]
    t = (s - cum[k - 1]) / seg if seg > 0 else 0.0
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _at_open(line, cum, s):
    """The point ``s`` along a line that isn't a loop (clamped to its ends)."""
    if s >= cum[-1]:
        return line[-1]
    return _at(line, cum, max(s, 0.0))


def _mean(pts):
    n = max(len(pts), 1)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def _start_line(line, cum, shapes):
    """The start/finish layer: (where it crosses the line, and whether travel
    follows the line's own order when the layer has iRacing's direction arrow, else None)."""
    total = cum[-1]
    found = sorted(((*_nearest(line, cum, _mean(sh)), sh) for sh in shapes if sh), key=lambda f: f[0])
    if not found:
        return None
    s0 = found[0][1]
    forward = None
    arrow = next((f for f in found[1:] if len(f[2]) >= 3), None)
    if arrow:
        _, s, pts = arrow
        c = _mean(pts)
        tip = max(pts, key=lambda q: math.hypot(q[0] - c[0], q[1] - c[1]))  # the arrow's tip: furthest from its middle
        v = (tip[0] - c[0], tip[1] - c[1])
        a, b = _at(line, cum, s - total * 0.005), _at(line, cum, s + total * 0.005)
        t = (b[0] - a[0], b[1] - a[1])
        cos = (v[0] * t[0] + v[1] * t[1]) / max(math.hypot(*v) * math.hypot(*t), 1e-9)
        if abs(cos) > 0.5:  # only an arrow pointing along the track says anything
            forward = cos > 0
    return s0, forward


def _ribbon(line):
    """Whether the closed line outlines a ribbon (the track drawn as a thin
    filled shape: along one edge and back along the other): ("line", None),
    ("mixed", None) or ("ribbon", (its centre line, whether that's a loop))."""
    cum = _cumulative(line)
    total = cum[-1]
    xs, ys = [p[0] for p in line], [p[1] for p in line]
    size = max(max(xs) - min(xs), max(ys) - min(ys))
    if total <= 0 or size <= 0:
        return "line", None
    # On a ribbon every point has the other edge right beside it, and the two
    # edges mirror each other about the ends: s and its partner add up to the same.
    n = 240
    near, cx, cy = 0, 0.0, 0.0
    for i in range(n):
        s = total * i / n
        gap = total * 0.04

        def skip(mid, s=s, gap=gap):
            apart = (mid - s) % total
            return min(apart, total - apart) < gap

        d, other = _nearest(line, cum, _at(line, cum, s), skip)
        if d < size * 0.03:
            near += 1
        a = 2 * math.pi * (s + other) / total
        cx += math.cos(a)
        cy += math.sin(a)
    mirrored = math.hypot(cx, cy) / n
    if not (near >= n * 9 // 10 and mirrored >= 0.8):
        # Edges mirrored over much of the lap but not all: no reliable line.
        # Narrow ovals and hairpins have the line close by too, but nothing mirrored.
        return ("mixed", None) if near >= n // 2 and mirrored >= 0.4 else ("line", None)
    end = (math.atan2(cy, cx) / (2 * math.pi)) % 1.0 * total / 2
    m_ = 1500
    half = total / 2
    back = [_at(line, cum, end + half + half * k / m_) for k in range(m_ + 1)]
    back_cum = _cumulative(back)
    centre = []
    for k in range(m_ + 1):
        a = _at(line, cum, end + half * k / m_)
        b = _at_open(back, back_cum, _nearest(back, back_cum, a)[1])
        centre.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    length = _cumulative(centre)[-1]
    first, last = centre[0], centre[-1]
    # A circuit drawn as one stroke has its two ends at (or near) the same place.
    return "ribbon", (centre, math.hypot(first[0] - last[0], first[1] - last[1]) < length * 0.1)


def _turn_numbers(texts):
    """Turn numbers and where they're drawn: labels that are just a number
    ("7", "T7", "Turn 7"), not corner names with a number in them; a number
    drawn as separate digits side by side ("1" "1" for 11) is read as one."""
    nums = []
    for t, p in texts:
        low = t.strip().lower()
        d = low[4:] if low.startswith("turn") else low[1:] if low.startswith("t") else low
        d = d.strip()
        if d and len(d) <= 3 and d.isdigit():
            nums.append((d, p))
    nums.sort(key=lambda x: x[1][0])
    out, used = [], [False] * len(nums)
    for i in range(len(nums)):
        if used[i]:
            continue
        used[i] = True
        text, p = nums[i]
        last = p
        while len(text) < 3:  # single digits on the same baseline just to the right continue it
            j = next((j for j in range(len(nums)) if not used[j] and len(nums[j][0]) == 1
                      and abs(nums[j][1][1] - last[1]) < 6 and 0 < nums[j][1][0] - last[0] < 30), None)
            if j is None:
                break
            used[j] = True
            text += nums[j][0]
            last = nums[j][1]
        out.append((int(text), p))
    return out


def normalise(pts):
    """Fit points (y up) into 0..1, keeping the shape, as Apex Overlays stores
    them: screen coordinates, y down (the top of the circuit is 0)."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny, 1e-9)
    ox, oy = (span - (maxx - minx)) / 2, (span - (maxy - miny)) / 2
    return [[round((p[0] - minx + ox) / span, 4), round(1 - (p[1] - miny + oy) / span, 4)] for p in pts]


def build(active, start_finish=None, turns=None, closed_out=None):
    """The outline (BINS points from the start/finish line in the direction
    of travel) from iRacing's SVG layers, or None. As Apex Overlays 0.9.2:
    a track drawn as a ribbon uses its centre line; a point-to-point track
    (a hillclimb) runs from its start to the other end, not round a loop
    (``closed_out``, a list, gets False appended for one)."""
    shapes, _ = _parse_svg(active)
    if not shapes:
        return None
    line = max(shapes, key=_length)
    if len(line) < 4:
        return None
    if line[0] != line[-1]:
        line = line + [line[0]]
    kind, ribbon = _ribbon(line)
    if kind == "mixed":
        return None
    is_open = False
    if kind == "ribbon":
        line, is_loop = ribbon
        is_open = not is_loop
        if not is_open and line[0] != line[-1]:
            line = line + [line[0]]
    cum = _cumulative(line)
    total = cum[-1]
    if total <= 0:
        return None
    sf_shapes = [sh for sh in (_parse_svg(start_finish)[0] if start_finish else []) if sh]
    sf = _start_line(line, cum, sf_shapes)
    if is_open:
        # Point to point: the layer marks the start and the finish, with an
        # arrow by the start (the shape furthest off the track).
        if len(sf_shapes) >= 3:
            far = max(sf_shapes, key=lambda sh: _nearest(line, cum, _mean(sh))[0])
            start = _nearest(line, cum, _mean(far))[1]
        else:
            start = sf[0] if sf else None
        from_end = start is not None and start > total / 2
        pts = []
        for i in range(BINS):
            d = total * i / (BINS - 1)
            p = _at_open(line, cum, total - d if from_end else d)
            pts.append((p[0], -p[1]))
        if closed_out is not None:
            closed_out.append(False)
        return normalise(pts)
    s0, arrow = sf if sf else (0.0, None)
    labels = sorted(_turn_numbers(_parse_svg(turns)[1]) if turns else [], key=lambda x: x[0])

    def ahead(p):
        return ((_project(line, cum, p) - s0) % total) / total

    # Each turn and the next vote on which way the numbers run round (a stray label is outvoted).
    votes_for = votes_against = 0
    for (n1, p1), (n2, p2) in zip(labels, labels[1:]):
        if n2 == n1 + 1:
            if (ahead(p2) - ahead(p1)) % 1.0 < 0.5:
                votes_for += 1
            else:
                votes_against += 1

    def one(n):
        found = [p for k, p in labels if k == n]
        return found[0] if len(found) == 1 else None

    clear = abs(votes_for - votes_against) >= 3 and min(votes_for, votes_against) * 3 <= max(votes_for, votes_against)
    if clear:
        forward = votes_for > votes_against
    elif one(1) is not None and one(2) is not None:
        forward = (ahead(one(2)) - ahead(one(1))) % 1.0 < 0.5
    elif votes_for != votes_against:
        forward = votes_for > votes_against
    elif labels:
        forward = ahead(labels[0][1]) < 0.5
    else:
        forward = True if arrow is None else arrow
    d = 1.0 if forward else -1.0
    pts = []
    for i in range(BINS):
        p = _at(line, cum, s0 + d * total * i / BINS)
        pts.append((p[0], -p[1]))  # SVG y points down; normalise takes y up
    if closed_out is not None:
        closed_out.append(True)
    return normalise(pts)


def index_from_catalogue(catalogue):
    """The racing-track-maps-vector catalogue (every iRacing track and layout,
    read from iRacing's site, with a copy of each SVG) in the index's format."""
    out = {}
    for track in (catalogue or {}).get("tracks") or []:
        for config in (track or {}).get("configurations") or []:
            try:
                tid = int(config.get("track_id"))
            except (TypeError, ValueError):
                continue
            folder = str(config.get("svg_folder_url") or "").rstrip("/")
            urls = config.get("svg_urls") or {}
            if not folder or not isinstance(urls, dict):
                continue
            layers = {}
            for k in LAYERS:
                url = urls.get(k)
                if isinstance(url, str):
                    rest = url[len(folder):].lstrip("/") if url.startswith(folder) else ""
                    layers[k] = rest if rest and "/" not in rest else url
            if "active" not in layers:
                continue
            entry = {"track_map": folder + "/", "track_map_layers": layers}
            local = str(config.get("svg_local_path") or "").strip("/")
            if local and ".." not in local:
                entry["mirror"] = f"{MIRROR_URL}/{urllib.parse.quote(local, safe='/-._~')}/"
            out[str(tid)] = entry
    return out


# -- where outlines come from --------------------------------------------------------


def _apex_overlays_dirs():
    """Apex Overlays' data folder(s) on this PC, if it's installed."""
    out = []
    for base in (os.environ.get("APPDATA"), os.environ.get("XDG_DATA_HOME"), str(Path.home() / ".local" / "share")):
        if base:
            out.append(Path(base) / "Apex Overlays")
    return out


def _valid(points):
    return (isinstance(points, list) and len(points) >= 50
            and all(isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(c, (int, float)) for c in p)
                    for p in points))


class TrackMaps:
    """Finds and caches the outline of the track on now (see the module's notes).

    ``get(track_id)`` never waits: it returns what's known ({id, points,
    source} or None) and looks for it in the background the first time."""

    def __init__(self, cache_dir, fetch=None, local_dirs=None):
        self.dir = Path(cache_dir)
        self._fetch = fetch or self._download
        self._local = local_dirs if local_dirs is not None else _apex_overlays_dirs()
        self._maps = {}       # track id -> map or None (looked for, not found)
        self._busy = set()
        self._tried = {}      # track id -> when a download last failed
        self._lock = threading.Lock()

    @staticmethod
    def _download(url):
        req = urllib.request.Request(url, headers={"User-Agent": "Apex-Commentator"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()

    def get(self, track_id, wait=False):
        try:
            track_id = int(track_id)
        except (TypeError, ValueError):
            return None
        if track_id <= 0:
            return None
        with self._lock:
            if track_id in self._maps:
                return self._maps[track_id]
            if track_id in self._busy or time.monotonic() - self._tried.get(track_id, -1e9) < RETRY_S:
                return None
            self._busy.add(track_id)
        if wait:
            self._find(track_id)
        else:
            threading.Thread(target=self._find, args=(track_id,), name="trackmap", daemon=True).start()
        with self._lock:
            return self._maps.get(track_id)

    def _find(self, track_id):
        found, failed = None, False
        try:
            found = self._recorded(track_id)
            if found is None:
                found, failed = self._official(track_id)
            if found is None:
                lib, lib_failed = self._library(track_id)
                found, failed = lib, failed or lib_failed
        except Exception as e:  # noqa: BLE001 - no map is no map; the page draws its round one
            print(f"[apex] track map for {track_id}: {e!r}")
            failed = True
        with self._lock:
            self._busy.discard(track_id)
            if found is not None or not failed:
                self._maps[track_id] = found
            else:
                self._tried[track_id] = time.monotonic()  # try again in a while

    def _cached(self, path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data.get("points") if isinstance(data, dict) and _valid(data.get("points")) else None

    def _keep(self, kind, track_id, points, closed=True):
        path = self.dir / kind / f"{track_id}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"trackId": track_id, "points": points, "closed": closed}), encoding="utf-8")
        except OSError:
            pass

    def _recorded(self, track_id):
        """An outline Apex Overlays recorded on this PC."""
        for d in self._local:
            points = self._cached(d / "trackmaps" / f"{track_id}.json")
            if points:
                return self._map(track_id, "recorded", points)
        return None

    def _index(self, name, url, convert=lambda v: v):
        """A track map index (kept a week): {track id: entry}, or None (unreachable)."""
        path = self.dir / name
        try:
            if time.time() - path.stat().st_mtime < INDEX_MAX_AGE_S:
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        try:
            index = convert(json.loads(self._fetch(url).decode("utf-8-sig")))
        except Exception:  # noqa: BLE001 - offline, or not published
            return None
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(index), encoding="utf-8")
        except OSError:
            pass
        return index

    def _layer(self, entry, key):
        """One SVG layer: from iRacing's own server, else the mirror's copy."""
        file = (entry.get("track_map_layers") or {}).get(key)
        if not file:
            return None
        base = str(entry.get("track_map") or "")
        url = file if str(file).startswith("http") else f"{base.rstrip('/')}/{str(file).lstrip('/')}"
        for u in (url, f"{str(entry['mirror']).rstrip('/')}/{url.rsplit('/', 1)[-1]}" if entry.get("mirror") else None):
            if not u:
                continue
            try:
                return self._fetch(u).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 - the next source
                continue
        return None

    def _official(self, track_id):
        """iRacing's official map, converted: (map or None, whether a download failed)."""
        cached = self.dir / "iracing-v2" / f"{track_id}.json"
        points = self._cached(cached)
        if points:
            return self._map(track_id, "iracing", points, self._closed(cached)), False
        key = str(track_id)
        published = self._index("iracing-track-maps.json", INDEX_URL)
        entry = (published or {}).get(key)
        catalogue = None
        if entry is None:  # newer than the published index: the public catalogue
            catalogue = self._index("track-map-catalogue.json", CATALOGUE_URL, index_from_catalogue)
            entry = (catalogue or {}).get(key)
        if not isinstance(entry, dict) or not entry.get("track_map"):
            return None, published is None and catalogue is None
        active = self._layer(entry, "active")
        if active is None:
            return None, True  # neither iRacing nor the copy answered: try again in a while
        closed = []
        points = build(active, self._layer(entry, "start-finish"), self._layer(entry, "turns"), closed)
        if not points:
            return None, False
        self._keep("iracing-v2", track_id, points, closed=closed[0])
        return self._map(track_id, "iracing", points, closed[0]), False

    @staticmethod
    def _map(track_id, source, points, closed=True):
        return {"id": f"{track_id}:{source}", "points": points, "source": source, "closed": closed}

    def _closed(self, path):
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("closed", True) is not False
        except (OSError, ValueError, AttributeError):
            return True

    def _library(self, track_id):
        """The shared library's recorded outline: (map or None, whether a download failed)."""
        points = self._cached(self.dir / "library" / f"{track_id}.json")
        if points:
            return self._map(track_id, "library", points), False
        try:
            index = json.loads(self._fetch(f"{LIBRARY_URL}/index.json"))
        except Exception:  # noqa: BLE001
            return None, True
        if str(track_id) not in ((index or {}).get("tracks") or {}):
            return None, False
        try:
            data = json.loads(self._fetch(f"{LIBRARY_URL}/{track_id}.json"))
        except Exception:  # noqa: BLE001
            return None, True
        points = data.get("points") if isinstance(data, dict) else None
        if not _valid(points) or int(data.get("trackId", track_id)) != track_id:
            return None, False
        points = [[round(float(x), 4), round(float(y), 4)] for x, y in points]
        self._keep("library", track_id, points)
        return self._map(track_id, "library", points), False
