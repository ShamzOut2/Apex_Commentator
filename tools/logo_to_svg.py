"""Convert a two-tone class logo (a dark badge with light lettering) to SVG.

The SVG has two layers the overlay knows how to recolour:

* ``data-apex-fill="class"``: the badge, painted in the class colour
* ``data-apex-fill="ink"``: the lettering, kept white unless the class
  colour is too light for it, when it turns dark

Anything fully transparent in the source stays transparent.

Usage (development only, needs ``pip install pillow potracer``)::

    python tools/logo_to_svg.py logo.png [more.png ...] --out-dir web/logos
    python tools/logo_to_svg.py pro.png --name "PRO"   # sets the SVG <title>
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import potrace
from PIL import Image

# Trace at this multiple of the source size: the up-scaled anti-aliasing
# gives potrace sub-pixel edges, so curves come out smooth.
SCALE = 4


def trace_mask(mask, scale):
    """Trace a boolean mask (True = shape) into SVG path data."""
    # potrace.Bitmap inverts its input, so hand it the background.
    bitmap = potrace.Bitmap(~mask)
    # potracer's curve optimiser can hit a float rounding error (sqrt of a
    # tiny negative) on some shapes; nudge the tolerance, then skip it.
    for options in ({"opttolerance": 0.2}, {"opttolerance": 0.23}, {"opticurve": False}):
        try:
            curves = bitmap.trace(turdsize=8, alphamax=1.0, **options)
            break
        except ValueError:
            continue

    def pt(p):
        return f"{p.x / scale:.2f} {p.y / scale:.2f}"

    parts = []
    for curve in curves:
        parts.append(f"M{pt(curve.start_point)}")
        for seg in curve:
            if seg.is_corner:
                parts.append(f"L{pt(seg.c)}L{pt(seg.end_point)}")
            else:
                parts.append(f"C{pt(seg.c1)} {pt(seg.c2)} {pt(seg.end_point)}")
        parts.append("Z")
    return "".join(parts)


def _edge(alpha_row, from_left):
    """Sub-pixel x where a row's alpha first crosses 50% from one side."""
    row = alpha_row if from_left else alpha_row[::-1]
    idx = np.nonzero(row >= 128)[0]
    if not len(idx):
        return None
    i = idx[0]
    if i == 0:
        return None  # touches the image edge: clipped there, not a true edge
    a0, a1 = float(row[i - 1]), float(row[i])
    x = i - 1 + (128 - a0) / max(1e-6, a1 - a0) + 0.5
    return x if from_left else len(row) - x


def _clip_x(poly, lo, hi):
    """Clip a polygon to lo <= x <= hi (Sutherland-Hodgman, two edges)."""
    for keep, bound in ((lambda x: x >= lo, lo), (lambda x: x <= hi, hi)):
        out = []
        for i, (x1, y1) in enumerate(poly):
            x0, y0 = poly[i - 1]
            if keep(x1):
                if not keep(x0):
                    out.append((bound, y0 + (y1 - y0) * (bound - x0) / (x1 - x0)))
                out.append((x1, y1))
            elif keep(x0):
                out.append((bound, y0 + (y1 - y0) * (bound - x0) / (x1 - x0)))
        poly = out
    return poly


def fit_parallelogram(alpha):
    """Straight-edged badge path if the shape's sides are straight lines, else None.

    Fits a line to the left and right edge of every row, then runs them
    from the top to the bottom of the image, clipped to its width.
    """
    h, w = alpha.shape
    if not ((alpha[0] >= 128).any() and (alpha[-1] >= 128).any()):
        return None  # badge must span the full height
    sides = []
    for from_left in (True, False):
        ys, xs = [], []
        for y in range(h):
            x = _edge(alpha[y], from_left)
            if x is not None:
                ys.append(y + 0.5)
                xs.append(x)
        if len(ys) < h * 0.3:
            return None
        slope, icept = np.polyfit(ys, xs, 1)
        if np.abs(np.polyval((slope, icept), ys) - xs).max() > 1.5:
            return None  # curved or notched edge: leave it to the tracer
        sides.append((slope, icept))
    (ls, li), (rs, ri) = sides
    poly = [(li, 0.0), (ri, 0.0), (rs * h + ri, float(h)), (ls * h + li, float(h))]
    poly = _clip_x(poly, 0.0, float(w))
    return "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in poly) + "Z"


def convert(src, title, badge_color="#111111"):
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    big = img.resize((w * SCALE, h * SCALE), Image.LANCZOS)
    rgba = np.asarray(big).astype(np.float32)
    alpha = rgba[..., 3]
    lum = rgba[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    shape = alpha >= 128
    ink = shape & (lum >= 128)
    if not ink.any():
        raise ValueError(f"{src}: no light lettering found")
    badge = fit_parallelogram(np.asarray(img)[..., 3]) or trace_mask(shape, SCALE)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
        f"  <title>{title}</title>\n"
        f'  <path data-apex-fill="class" fill="{badge_color}" fill-rule="evenodd" d="{badge}"/>\n'
        f'  <path data-apex-fill="ink" fill="#ffffff" fill-rule="evenodd" d="{trace_mask(ink, SCALE)}"/>\n'
        f"</svg>\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    parser.add_argument("--name", help="SVG title (single image only; defaults to the file name)")
    args = parser.parse_args(argv)
    if args.name and len(args.images) > 1:
        parser.error("--name only works with a single image")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for src in args.images:
        title = args.name or src.stem.upper()
        out = args.out_dir / f"{src.stem.lower()}.svg"
        out.write_text(convert(src, title), encoding="utf-8")
        print(f"{src} -> {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
