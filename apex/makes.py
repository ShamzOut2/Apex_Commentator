"""Car manufacturers ("makes") and their badges.

The badges in ``web/makes/`` and the name matching below come from the
Apex Overlays project (see THIRD_PARTY_NOTICES.md). A car's make is worked
out from iRacing's car name and path, e.g. "Porsche 911 GT3 R (992)" ->
Porsche, "Corvette C8.R" -> Chevrolet.
"""

import functools
import re
import unicodedata

from .paths import WEB_DIR

# (text found in the car's name or path, make), longest first where they overlap.
MAKES = (
    ("acura", "Acura"), ("alpine", "Alpine"), ("aston", "Aston Martin"), ("audi", "Audi"), ("bmw", "BMW"),
    ("cadillac", "Cadillac"), ("camaro", "Chevrolet"), ("chevrolet", "Chevrolet"), ("chevy", "Chevrolet"),
    ("corvette", "Chevrolet"), ("dallara", "Dallara"), ("dodge", "Dodge"), ("ferrari", "Ferrari"),
    ("ford", "Ford"), ("mustang", "Ford"), ("formula vee", "Volkswagen"), ("genesis", "Genesis"),
    ("holden", "Holden"), ("honda", "Honda"), ("hyundai", "Hyundai"), ("kia", "Kia"),
    ("lamborghini", "Lamborghini"), ("ligier", "Ligier"), ("lotus", "Lotus"), ("mazda", "Mazda"),
    ("mx-5", "Mazda"), ("mclaren", "McLaren"), ("mercedes", "Mercedes-AMG"), ("amg", "Mercedes-AMG"),
    ("mini", "Mini"), ("nissan", "Nissan"), ("oreca", "Oreca"), ("peugeot", "Peugeot"), ("pontiac", "Pontiac"),
    ("porsche", "Porsche"), ("radical", "Radical"), ("renault", "Renault"), ("riley", "Riley"),
    ("skip barber", "Skip Barber"), ("subaru", "Subaru"), ("super formula", "Super Formula"),
    ("toyota", "Toyota"), ("gr86", "Toyota"), ("supra", "Toyota"), ("volkswagen", "Volkswagen"),
    ("vw", "Volkswagen"), ("williams", "Williams"), ("ruf", "Ruf"), ("tatuus", "Tatuus"), ("fia f4", "Tatuus"),
    ("formula 4", "Tatuus"),
)


def slug(make):
    """'Mercedes-AMG' -> 'mercedes-amg', 'Aston Martin' -> 'aston-martin'."""
    text = unicodedata.normalize("NFKD", str(make or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def make_for(car_name, car_path=""):
    """The make of an iRacing car, from its screen name and path ("" if unknown)."""
    hay = f" {str(car_name or '').lower()} {re.sub(r'[_/]', ' ', str(car_path or '').lower())} "
    for key, make in MAKES:
        if key in hay:
            return make
    return ""


@functools.lru_cache(maxsize=1)
def badge_files():
    """{slug: file name} of the badges that ship with the app (they don't change while it runs)."""
    folder = WEB_DIR / "makes"
    return {p.stem: p.name for p in folder.glob("*.png")} if folder.is_dir() else {}


def catalogue():
    """Every make the app knows, with its badge URL (None without one), sorted by name."""
    files = badge_files()
    names = {m for _, m in MAKES}
    out = [{"name": n, "logo": f"/makes/{files[slug(n)]}" if slug(n) in files else None} for n in names]
    return sorted(out, key=lambda m: m["name"].lower())


def logo_for(make):
    """Badge URL for a make, or None."""
    files = badge_files()
    s = slug(make)
    return f"/makes/{files[s]}" if s in files else None
