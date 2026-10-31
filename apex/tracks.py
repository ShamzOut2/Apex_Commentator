"""iRacing tracks and configurations, for the season calendar.

Three sources, merged:

1. **iRacing's Data API** (``/data/track/get``): the official, complete list.
   Used when API credentials are set; fetched on demand and kept in
   ``data/tracks.json``.
2. **Tracks seen in sessions**: every track (and layout) the app connects to
   is remembered in the same file.
3. **A built-in list** of iRacing's tracks and their main layouts, so the
   calendar works without API credentials. It's compiled by hand and may
   miss newer content or odd layouts; anything can also be typed in.
"""

import json
import re
import threading
from pathlib import Path

# "Track | layout; layout; ..." (an empty layout list means the track has one).
BUILTIN = """
Adelaide Street Circuit |
Algarve International Circuit | Grand Prix; Grand Prix Chicane; National; Moto
Atlanta Motor Speedway | Oval; Legends Oval; Road Course; Legends Road Course
Auto Club Speedway | Oval; Competition; Interior; Infield
Autodromo Internazionale Enzo e Dino Ferrari | Grand Prix; Moto
Autodromo Nazionale Monza | Grand Prix; Combined; Combined without chicanes; Grand Prix without first chicane; Junior; Oval
Autodromo Internazionale del Mugello | Grand Prix
Autodromo Jose Carlos Pace | Grand Prix; Moto; Historic
Autódromo Hermanos Rodríguez | Grand Prix; Grand Prix without bus stop; National; Oval
Barber Motorsports Park | Full Course; Short A; Short B
Bathurst - Mount Panorama Circuit |
Bristol Motor Speedway | Single Layer; Dual Pit Roads; Dirt
Brands Hatch Circuit | Grand Prix; Indy
Canadian Tire Motorsport Park |
Charlotte Motor Speedway | Oval; Legends Oval; Roval; Roval Long; Infield Road Course; Legends RC Long; Legends RC Short
Chicago Street Course |
Chicagoland Speedway |
Chili Bowl |
Circuit de Barcelona Catalunya | Grand Prix; Grand Prix without chicane; National; Club; Rallycross; Historic; Moto
Circuit de Nevers Magny-Cours | Grand Prix; Club; Moto
Circuit de Spa-Francorchamps | Grand Prix Pits; Endurance; Classic Pits; Combined
Circuit des 24 Heures du Mans | 24 Heures du Mans; Historic
Circuit Gilles Villeneuve |
Circuit of the Americas | Grand Prix; East; West; Moto
Circuit Park Zandvoort | Grand Prix; Chicane; Club; National; Oostelijk
Circuit Zolder | Grand Prix; Alternate
Circuito de Navarra | Speed Circuit; Club; Moto
Concord Speedway |
Daytona International Speedway | Oval; Road Course; Moto; Nascar Road; Rallycross; Rallycross Long
Darlington Raceway |
Detroit Grand Prix at Belle Isle |
Dirt Track at Charlotte |
Donington Park Racing Circuit | Grand Prix; National
Dover Motor Speedway |
Eldora Speedway |
Fair Grounds Speedway | Oval; Dirt
Fuji International Speedway | Grand Prix; Grand Prix (No Chicane)
Hockenheimring Baden-Württemberg | Grand Prix; National A; National B; Outer
Homestead Miami Speedway | Oval; Road Course A; Road Course B; Indycar Oval
Hungaroring |
Indianapolis Motor Speedway | Oval; Road Course; Moto; Legacy Oval
Iowa Speedway | Oval; Legends; Infield Road Course
Irwindale Speedway | Outer; Inner; Figure Eight
Kansas Speedway | Oval; Infield Road Course
Kentucky Speedway |
Knockhill Racing Circuit | International; National; Rallycross
Knoxville Raceway | 1/2 Mile; 1/4 Mile; 3/8 Mile
Kyalami Grand Prix Circuit | Grand Prix
Lanier National Speedway | Asphalt; Dirt
Las Vegas Motor Speedway | Oval; Infield Road Course; Infield Legends Oval; Dirt
Lime Rock Park | Grand Prix; Classic; Chicane; West Bend Chicane
Lincoln Speedway |
Long Beach Street Circuit |
Lucas Oil Raceway | Oval; Road Course
Martinsville Speedway |
Michigan International Speedway |
Misano World Circuit Marco Simoncelli | Grand Prix
Mid-Ohio Sports Car Course | Full Course; Chicane; Short
Mobility Resort Motegi | Grand Prix; East; West; Superspeedway; Moto
Mount Washington Hillclimb |
MotorLand Aragón | Grand Prix; Motorcycle; Outer; National
Myrtle Beach Speedway |
Nashville Fairgrounds Speedway | Oval; Figure 8
Nashville Superspeedway |
New Hampshire Motor Speedway | Oval; Road Course; Legends Oval
New Smyrna Speedway |
Nürburgring Combined | Gesamtstrecke VLN; Gesamtstrecke 24h; Gesamtstrecke Long
Nürburgring Grand-Prix-Strecke | Grand Prix; BES/WEC; Sprint; Sprint without arena; Müllenbachschleife; Kurzanbindung
Nürburgring Nordschleife | Industriefahrten; Touristenfahrten
Okayama International Circuit | Full Course; Short
Oran Park Raceway | Grand Prix; North; South; Moto; North A; North B
Oulton Park Circuit | International; Fosters; Island; Island Historic; Intl with no Chicanes
Oxford Plains Speedway |
Phoenix Raceway | Oval; Oval w/open dogleg; Road Course; 1998 Oval
Phillip Island Circuit |
Pocono Raceway | Oval; East; International; North; South
Port Royal Speedway |
Red Bull Ring | Grand Prix; National; South
Richmond Raceway |
Road America | Full Course; Bend
Road Atlanta | Full Course; Club
Rockingham Speedway | Oval; Road Course
Sachsenring |
Sandown International Motor Raceway |
Sebring International Raceway | International; Club; Modified
Silverstone Circuit | Grand Prix; International; National; Historical Grand Prix
Snetterton Circuit | 300; 200; 100
Sonoma Raceway | Cup; Long; IndyCar 2008-2011; IndyCar 2012-; Club; Drift
South Boston Speedway |
Southern National Motorsports Park |
Suzuka International Racing Course | Grand Prix; East; West; Moto
Summit Point Raceway | Summit Point Raceway; Jefferson Circuit; School Circuit; Short
Talladega Superspeedway |
Texas Motor Speedway | Oval; Legends Oval; Road Course
The Bullring | Oval; Road Course
Thompson Speedway Motorsports Park | Oval; Road Course
Thruxton Circuit |
Tsukuba Circuit | 2000 Full; 2000 Short; 1000 Full
USA International Speedway | Asphalt; Dirt
Virginia International Raceway | Full Course; Grand East; Grand West; North; Patriot; South
Volusia Speedway Park |
Watkins Glen International | Boot; Classic; Cup; Short
Weedsport Speedway |
WeatherTech Raceway at Laguna Seca |
Williams Grove Speedway |
Winton Motor Raceway | National; Club
Willow Springs International Raceway | Big Willow; Horse Thief Mile; Streets of Willow Springs
World Wide Technology Raceway | Oval; Road Course
"""


def _parse_builtin():
    out = []
    for line in BUILTIN.strip().splitlines():
        name, _, configs = line.partition("|")
        name = name.strip()
        layouts = [c.strip() for c in configs.split(";") if c.strip()] or [""]
        out += [{"id": None, "track": name, "config": c, "source": "builtin"} for c in layouts]
    return out


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _key(t):
    return (_norm(t["track"]), _norm(t["config"]))


class TrackCatalogue:
    def __init__(self, path=None, client=None):
        self.path = Path(path) if path else None
        self.client = client
        self._lock = threading.Lock()
        self.saved = {"iracing": [], "seen": [], "fetched_at": None}
        if self.path:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.saved.update({k: data.get(k) or v for k, v in self.saved.items()})
            except (OSError, ValueError):
                pass

    def _write(self):
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.saved, indent=1), encoding="utf-8")
        except OSError as e:
            print(f"[apex] couldn't save the track list: {e}")

    def all(self):
        """Every known track layout, official data first; duplicates merged."""
        merged = {}
        for t in self.saved["iracing"] + self.saved["seen"] + _parse_builtin():
            merged.setdefault(_key(t), t)
        return sorted(merged.values(), key=lambda t: (_norm(t["track"]), _norm(t["config"])))

    def grouped(self):
        """[{track, configs: [{config, id}]}]: for a track list and a layout list."""
        out = {}
        for t in self.all():
            g = out.setdefault(_norm(t["track"]), {"track": t["track"], "configs": []})
            g["configs"].append({"config": t["config"], "id": t["id"]})
        return sorted(out.values(), key=lambda g: _norm(g["track"]))

    def search(self, query="", limit=60):
        words = _norm(query).split()
        hits = [t for t in self.all() if all(w in _norm(f"{t['track']} {t['config']}") for w in words)]
        return hits[:limit]

    def status(self):
        return {"official": len(self.saved["iracing"]), "seen": len(self.saved["seen"]),
                "builtin": len(_parse_builtin()), "fetched_at": self.saved["fetched_at"],
                "api": bool(self.client and self.client.configured)}

    def remember(self, track_id, track, config):
        """Note a track the app has seen in a session."""
        if not track:
            return
        entry = {"id": track_id, "track": track, "config": config or "", "source": "session"}
        with self._lock:
            if any(_key(t) == _key(entry) for t in self.saved["seen"] + self.saved["iracing"]):
                return
            self.saved["seen"].append(entry)
            self._write()

    def refresh(self, now):
        """Fetch the official list from iRacing's Data API. Returns how many layouts."""
        if not (self.client and self.client.configured):
            raise ValueError("iRacing API credentials aren't set, so the official list can't be fetched.")
        data = self.client.get("/data/track/get")
        tracks = [{"id": t.get("track_id"), "track": t.get("track_name", ""), "config": t.get("config_name") or "",
                   "source": "iracing"} for t in data or [] if isinstance(t, dict) and t.get("track_name")]
        with self._lock:
            self.saved["iracing"] = tracks
            self.saved["fetched_at"] = now
            self._write()
        return len(tracks)
