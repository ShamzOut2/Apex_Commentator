"""Season rounds from a league's calendar: a scanned calendar image or pasted text.

The text comes in as pieces with a position (``x``, ``y``, ``w``, ``h``), from
OCR (apex/ocr.py) or one per line for pasted text. Each piece is searched for

* a **track**, matched against the track list (apex/tracks.py) by its
  distinctive words ("Spa", "Monza", "Road Atlanta") or a common nickname
  ("Imola", "COTA", "Le Mans"), and its layout when one is named;
* a **date** ("22/11/26", "22nd November", "Sun 22 Nov 2026", "Nov 22",
  "2026-11-22"), a **start time** ("19:30", "7:30pm", "8PM GMT"), a **race
  length** ("60 min", "30 laps", "2h") and a **round number** ("Round 3",
  "R3", "Rd. 3").

Every track found is a round. The other details go to the nearest track,
weighing distance across less than distance up and down, so it works for
tables (a round per row), lists and grids of cards. Nothing is final: the
app shows the rounds for checking before it creates them.
"""

import difflib
import re
import unicodedata
from datetime import date, timedelta

MONTHS = {m: i for i, names in enumerate((
    ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
    ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
    ("dec", "december")), start=1) for m in names}
MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
ORD = r"(?:st|nd|rd|th)?"

ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
NUM_DATE = re.compile(r"\b(\d{1,2})([/.\-])(\d{1,2})(?:\2(\d{4}|\d{2}))?\b")
DAY_MONTH = re.compile(rf"\b(\d{{1,2}}){ORD}\s*(?:of\s+)?({MONTH})\b\.?(?:,?\s*(\d{{4}}))?", re.I)
MONTH_DAY = re.compile(rf"\b({MONTH})\b\.?\s*(\d{{1,2}}){ORD}\b(?:,?\s*(\d{{4}}))?", re.I)
TIME_24 = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(a\.?m\.?|p\.?m\.?)?(?![\d.:/])", re.I)
TIME_12 = re.compile(r"\b(1[0-2]|0?[1-9])\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", re.I)
LAPS = re.compile(r"\b(\d{1,4})\s*laps?\b", re.I)
HOURS = re.compile(r"\b(\d{1,2}(?:\.\d)?)\s*(?:hours|hour|hrs|hr|h)(?![a-z])(?:\s*(\d{1,2})\s*(?:m|min|mins|minutes)?\b)?", re.I)
MINUTES = re.compile(r"\b(\d{1,3})\s*(?:m|min|mins|minutes|mn)\b", re.I)
ROUND = re.compile(r"\b(?:round|rnd|rd|r|event|week|wk)\s*\.?\s*#?\s*(\d{1,2})\b", re.I)

# Words in track names that say nothing about which track it is.
STOP = {
    "circuit", "circuito", "international", "internazionale", "internacional", "raceway", "speedway", "motor",
    "motorsport", "motorsports", "racing", "course", "race", "track", "the", "de", "des", "du", "di", "e", "of",
    "at", "and", "autodromo", "nazionale", "sports", "car", "grand", "prix", "gp", "park", "superspeedway",
    "heures", "24", "street", "city", "parc", "ring",
}
# Words that only count alongside another one ("Road" alone isn't Road America).
WEAK = {"road", "long", "beach", "red", "bull", "mount", "new", "world", "wide", "technology", "fair", "grounds",
        "national", "lime", "rock", "south", "north", "dirt", "oval", "mile", "short"}
# Names people use for tracks, and the track they mean (if it's in the list).
ALIASES = {
    "imola": "Autodromo Internazionale Enzo e Dino Ferrari",
    "interlagos": "Autodromo Jose Carlos Pace",
    "mosport": "Canadian Tire Motorsport Park",
    "ctmp": "Canadian Tire Motorsport Park",
    "cota": "Circuit of the Americas",
    "austin": "Circuit of the Americas",
    "vir": "Virginia International Raceway",
    "le mans": "Circuit des 24 Heures du Mans",
    "lemans": "Circuit des 24 Heures du Mans",
    "la sarthe": "Circuit des 24 Heures du Mans",
    "portimao": "Algarve International Circuit",
    "mexico city": "Autódromo Hermanos Rodríguez",
    "montreal": "Circuit Gilles Villeneuve",
    "the glen": "Watkins Glen International",
    "laguna": "WeatherTech Raceway at Laguna Seca",
    "catalunya": "Circuit de Barcelona Catalunya",
    "magny cours": "Circuit de Nevers Magny-Cours",
    "spielberg": "Red Bull Ring",
    "motegi": "Mobility Resort Motegi",
    "barber": "Barber Motorsports Park",
    "gateway": "World Wide Technology Raceway",
    "belle isle": "Detroit Grand Prix at Belle Isle",
    "nordschleife": "Nürburgring Nordschleife",
    "petit le mans": "Road Atlanta",
    "green hell": "Nürburgring Nordschleife",
}


def fold(text):
    """Lower case, without accents, punctuation as spaces."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


# -- tracks ---------------------------------------------------------------------


class TrackMatcher:
    """Finds the tracks (and layouts) named in a piece of text."""

    def __init__(self, grouped):
        """``grouped``: [{track, configs: [{config, id}]}] (TrackCatalogue.grouped())."""
        self.tracks = []
        by_name = {}
        for g in grouped:
            words = [w for w in fold(g["track"]).split() if w not in STOP]
            entry = {"track": g["track"], "words": words, "configs": g["configs"]}
            self.tracks.append(entry)
            by_name[fold(g["track"])] = entry
        # Longest first: "Petit Le Mans" is Road Atlanta, not Le Mans.
        self.aliases = sorted(((fold(a).split(), by_name[fold(t)]) for a, t in ALIASES.items() if fold(t) in by_name),
                              key=lambda a: -len(a[0]))

    @staticmethod
    def _has(word, tokens):
        if word in tokens:
            return True
        # Scanned text has the odd wrong letter: close enough counts for long words.
        return len(word) >= 7 and any(len(t) >= 6 and difflib.SequenceMatcher(None, word, t).ratio() >= 0.85 for t in tokens)

    def find(self, text):
        """The best track named in ``text``: {"track", "config", "id"} or None."""
        tokens = fold(text).split()
        if not tokens:
            return None
        token_set = set(tokens)
        best, best_score = None, (0, 0.0)
        for t in self.tracks:
            if not t["words"]:
                continue
            hit = [w for w in t["words"] if self._has(w, token_set)]
            if not hit or (len(hit) < 2 and all(w in WEAK for w in hit)):
                continue
            score = (len(hit), len(hit) / len(t["words"]))
            if score > best_score:
                best, best_score = t, score
        joined = f" {' '.join(tokens)} "
        for words, t in self.aliases:
            if f" {' '.join(words)} " in joined:
                if best is None or best_score < (len(words) + 1, 1.0):
                    best, best_score = t, (len(words) + 1, 1.0)
                break
        if best is None:
            return None
        config, cid = self._config(best, token_set)
        return {"track": best["track"], "config": config, "id": cid}

    def _config(self, track, tokens):
        configs = track["configs"]
        if len(configs) == 1:
            return configs[0]["config"], configs[0]["id"]
        if "gp" in tokens:
            tokens = tokens | {"grand", "prix"}
        best, best_n = ("", None), 0
        for c in configs:
            words = [w for w in fold(c["config"]).split() if w not in ("course", "the")]
            if words and all(w in tokens for w in words) and len(words) > best_n:
                best, best_n = (c["config"], c["id"]), len(words)
        return best


# -- dates, times, lengths ---------------------------------------------------------


def _year(y):
    if y is None:
        return None
    y = int(y)
    return y + 2000 if y < 100 else y


def _make_date(y, m, d):
    try:
        return date(y or 2000, m, d), y is not None
    except ValueError:
        return None, False


def find_date(text, day_first=True):
    """(date, has_year, matched span) for the first date in ``text``, or None."""
    for rx, kind in ((ISO_DATE, "iso"), (DAY_MONTH, "dm"), (MONTH_DAY, "md"), (NUM_DATE, "num")):
        for m in rx.finditer(text):
            if kind == "iso":
                d, has = _make_date(int(m[1]), int(m[2]), int(m[3]))
            elif kind == "dm":
                d, has = _make_date(_year(m[3]), MONTHS[m[2].lower()], int(m[1]))
            elif kind == "md":
                d, has = _make_date(_year(m[3]), MONTHS[m[1].lower()], int(m[2]))
            else:
                a, sep, b, y = int(m[1]), m[2], int(m[3]), m[4]
                if sep == "." and not y:
                    continue  # "19.30" is a time, "22.11" too likely one
                day, month = (a, b) if day_first else (b, a)
                d, has = _make_date(_year(y), month, day)
            if d:
                return d, has, m.span()
    return None


def numeric_order(texts):
    """Day first (22/11) or month first (11/22), from dates that can only be one."""
    for t in texts:
        for m in NUM_DATE.finditer(t):
            a, b = int(m[1]), int(m[3])
            if m[2] == "." and not m[4]:
                continue
            if a > 12 >= b:
                return True
            if b > 12 >= a:
                return False
    return None


def find_time(text):
    """"HH:MM" for the first time of day in ``text``, or None."""
    m = TIME_24.search(text)
    if m:
        h, mins, ampm = int(m[1]), int(m[2]), (m[3] or "").lower()
    else:
        m = TIME_12.search(text)
        if not m:
            return None
        h, mins, ampm = int(m[1]), 0, m[2].lower()
    if ampm.startswith("p") and h < 12:
        h += 12
    elif ampm.startswith("a") and h == 12:
        h = 0
    return f"{h:02d}:{mins:02d}"


def find_length(text):
    """"30 laps", "60 min" or "2 h"... for a race length in ``text``, or None."""
    m = LAPS.search(text)
    if m:
        return f"{int(m[1])} laps"
    m = HOURS.search(text)
    if m:
        hours = float(m[1])
        mins = int(hours * 60) + int(m[2] or 0)
        return f"{mins} min" if mins % 60 else f"{mins // 60} h"
    m = MINUTES.search(text)
    if m:
        return f"{int(m[1])} min"
    return None


def _without(text, span):
    return text[:span[0]] + " " + text[span[1]:] if span else text


# -- putting it together ---------------------------------------------------------------


def lines_to_pieces(text):
    """Pasted text: one piece per line, a blank line a bigger gap."""
    pieces, y = [], 0.0
    for line in str(text or "").splitlines():
        if not line.strip():
            y += 1.5
            continue
        pieces.append({"text": line.strip(), "x": 0.0, "y": y, "w": 40.0, "h": 0.8})
        y += 1.0
    return pieces


DX_WEIGHT = 3  # outside tables, a card's details sit under its track, not beside another card's


def _gaps(a, b):
    """Space between two boxes, across and up-and-down (0 where they overlap)."""
    dx = max(0.0, max(a["x"], b["x"]) - min(a["x"] + a["w"], b["x"] + b["w"]))
    dy = max(0.0, max(a["y"], b["y"]) - min(a["y"] + a["h"], b["y"] + b["h"]))
    return dx, dy


def _gap(a, b):
    """Distance between two boxes, with across weighing more than up and down
    (and how far apart their middles are, to settle ties)."""
    dx, dy = _gaps(a, b)
    mx = (a["x"] + a["w"] / 2) - (b["x"] + b["w"] / 2)
    my = (a["y"] + a["h"] / 2) - (b["y"] + b["h"] / 2)
    return ((DX_WEIGHT * dx) ** 2 + dy * dy) ** 0.5 + 0.01 * ((DX_WEIGHT * mx) ** 2 + my * my) ** 0.5


def _same_row(a, b):
    """Two pieces on the same line (overlapping by half the smaller one's height)."""
    overlap = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return overlap >= 0.5 * min(a["h"], b["h"])


def _is_table(anchors, line_h):
    """Tracks one under the other on close lines: a table (or a list), a round
    a line. Cards have their dates and times between the tracks. (A track's
    name over two lines doesn't count.)"""
    gaps = []
    for fa in anchors:
        a = fa["piece"]
        below = [_gaps(a, fb["piece"])[1] for fb in anchors
                 if fb is not fa and fb["piece"]["y"] > a["y"] and _gaps(a, fb["piece"])[0] == 0
                 and fb.get("track", {}).get("track") != fa.get("track", {}).get("track")]
        if below:
            gaps.append(min(below))
    gaps.sort()
    return bool(gaps) and gaps[len(gaps) // 2] < 1.5 * line_h


def _assign(found, rounds, table):
    """Give each round the nearest date, time, length and round number. In a
    table, a round's own row comes first."""
    for r in rounds:
        r["best"] = {}

    def dist(f, r):
        a = r["anchor"]["piece"]
        if table:
            return _gaps(f["piece"], a)[0] if _same_row(f["piece"], a) else 1e9 + _gap(f["piece"], a)
        return _gap(f["piece"], a)

    for f in found:
        for key in ("date", "time", "length", "number"):
            if key not in f:
                continue
            d, rd = min(((dist(f, r), r) for r in rounds), key=lambda x: x[0])
            if key not in rd["best"] or d < rd["best"][key][0]:
                rd["best"][key] = (d, f[key], f["piece"])


def _merge_split(rounds, line_h):
    """One track's name over two lines ("SPA-" / "FRANCORCHAMPS"), or named
    twice in one card: one round, unless each has its own date or number."""
    i = 0
    while i < len(rounds):
        a = rounds[i]
        for b in rounds[i + 1:]:
            ta, tb = a["anchor"].get("track"), b["anchor"].get("track")
            if not ta or not tb or ta["track"] != tb["track"]:
                continue
            dx, dy = _gaps(a["anchor"]["piece"], b["anchor"]["piece"])
            if dx > 0 or dy > line_h:
                continue
            if any(k in a["best"] and k in b["best"] and a["best"][k][1] != b["best"][k][1] for k in ("date", "number")):
                continue
            if ta.get("unknown") or tb.get("unknown"):
                continue
            for k, v in b["best"].items():
                if k not in a["best"] or v[0] < a["best"][k][0]:
                    a["best"][k] = v
            if not ta["config"] and tb["config"]:
                a["anchor"]["track"] = tb
            rounds.remove(b)
            break
        else:
            i += 1
    return rounds


def _guess_year(d, today):
    """A date without a year: this year's, or next year's if this year's is long gone."""
    try:
        this = d.replace(year=today.year)
    except ValueError:  # 29 Feb
        this = d.replace(year=today.year, day=28)
    if this < today - timedelta(days=120):
        try:
            return this.replace(year=today.year + 1)
        except ValueError:
            return this.replace(year=today.year + 1, day=28)
    return this


def rounds_from_pieces(pieces, grouped_tracks, day_first=True, today=None):
    """Rounds found in positioned text: [{number, name, track, config, track_id, date, time, length, text}]."""
    today = today or date.today()
    matcher = TrackMatcher(grouped_tracks)
    texts = [p["text"] for p in pieces]
    order = numeric_order(texts)
    if order is not None:
        day_first = order
    found = []
    for p in pieces:
        text = p["text"]
        info = {"piece": p}
        dt = find_date(text, day_first)
        rest = text
        if dt:
            info["date"] = dt[:2]
            rest = _without(text, dt[2])
        tm = find_time(rest)
        if tm:
            info["time"] = tm
        length = find_length(rest)
        if length:
            info["length"] = length
        rn = ROUND.search(rest)
        if rn:
            info["number"] = int(rn[1])
        tr = matcher.find(rest)
        if tr:
            info["track"] = tr
        if len(info) > 1:
            found.append(info)
    anchors = [f for f in found if "track" in f] or [f for f in found if "date" in f]
    if not anchors:
        return []
    rounds = [{"anchor": a, "best": {}} for a in anchors]
    heights = sorted(p["h"] for p in pieces)
    line_h = heights[len(heights) // 2]
    table = _is_table([r["anchor"] for r in rounds], line_h)
    dated = [f for f in found if "date" in f]
    _assign(found, rounds, table)
    # A date no round took is a round whose track isn't in the list (named
    # by the nearest text that isn't a date, time or the like).
    taken = {id(r["best"]["date"][2]) for r in rounds if "date" in r["best"]}
    orphans = [f for f in dated if id(f["piece"]) not in taken and "track" not in f]
    if orphans:
        plain = [p for p in pieces if not any(p is f["piece"] for f in found) and re.search(r"[A-Za-z]{3}", p["text"])]
        for f in orphans:
            near = min(plain, key=lambda p: _gap(p, f["piece"]), default=None)
            name = near["text"].strip(" -–:|").title() if near else ""
            rounds.append({"anchor": dict(f, track={"track": name, "config": "", "id": None, "unknown": True}), "best": {}})
        _assign(found, rounds, table)
    rounds = _merge_split(rounds, line_h)
    out = []
    for r in rounds:
        a, best = r["anchor"], {k: v[1] for k, v in r["best"].items()}
        track = a.get("track") or {}
        d = best.get("date")
        when = (d[0] if d[1] else _guess_year(d[0], today)) if d else None
        out.append({
            "number": best.get("number"), "track": track.get("track", ""), "config": track.get("config", ""),
            "track_id": track.get("id"), "unknown_track": bool(track.get("unknown")), "date": when.isoformat() if when else "", "time": best.get("time", ""),
            "length": best.get("length", ""), "text": a["piece"]["text"], "_pos": (a["piece"]["y"], a["piece"]["x"]),
        })
    # Round numbers first, then dates, then where they are on the page.
    numbered = all(r["number"] for r in out) and len({r["number"] for r in out}) == len(out)
    if numbered:
        out.sort(key=lambda r: r["number"])
    elif all(r["date"] for r in out):
        out.sort(key=lambda r: (r["date"], r["_pos"]))
    else:
        band = min((p["h"] for p in pieces), default=1) or 1
        out.sort(key=lambda r: (round(r["_pos"][0] / band), r["_pos"][1]))
    for i, r in enumerate(out, start=1):
        del r["_pos"]
        r["name"] = f"Round {r['number'] if numbered else i}"
    return out


def rounds_from_text(text, grouped_tracks, day_first=True, today=None):
    return rounds_from_pieces(lines_to_pieces(text), grouped_tracks, day_first, today)


def races_per_event(rounds, races, name="Race"):
    """Each calendar entry as a race meeting of ``races`` races: one round per
    race, sharing the meeting's track, date and time. Its rounds carry the
    meeting's name as ``event``."""
    races = max(1, min(10, int(races or 1)))
    if races == 1:
        return [dict(r, event="") for r in rounds]
    out = []
    for r in rounds:
        for k in range(1, races + 1):
            out.append(dict(r, event=r["name"], name=f"{name} {k}"))
    return out
