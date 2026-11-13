"""The car badges that ship with the app sit on nothing: no white box behind them."""

import struct
import unittest
import zlib

from apex.paths import WEB_DIR


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def read_png(path):
    """(width, height, rows of RGBA tuples) for an 8-bit, non-interlaced RGBA or palette PNG."""
    data = path.read_bytes()
    pos, idat, palette, alpha = 8, b"", [], b""
    while pos < len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + size]
        if kind == b"IHDR":
            width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif kind == b"tRNS":
            alpha = body
        elif kind == b"IDAT":
            idat += body
        pos += size + 12
    if depth != 8 or interlace or colour not in (3, 6):
        raise ValueError(f"{path.name}: unsupported PNG (depth {depth}, colour {colour}, interlace {interlace})")
    bpp = 4 if colour == 6 else 1
    raw, stride = zlib.decompress(idat), width * bpp
    rows, prev = [], bytearray(stride)
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + (0, a, b, (a + b) // 2, _paeth(a, b, c))[kind]) & 0xFF
        prev = line
        if colour == 6:
            rows.append([tuple(line[i:i + 4]) for i in range(0, stride, 4)])
        else:
            rows.append([palette[i] + ((alpha[i] if i < len(alpha) else 255),) for i in line])
    return width, height, rows


class MakeBadgeTests(unittest.TestCase):
    def test_no_badge_has_a_white_background(self):
        badges = sorted((WEB_DIR / "makes").glob("*.png"))
        self.assertTrue(badges)
        for path in badges:
            with self.subTest(badge=path.name):
                width, height, rows = read_png(path)
                border = rows[0] + rows[-1] + [r[0] for r in rows] + [r[-1] for r in rows]
                corners = (rows[0][0], rows[0][-1], rows[-1][0], rows[-1][-1])
                # A badge can run to the edge (Genesis's wing tips), but a box behind it fills the
                # corners and most of the edge.
                self.assertTrue(all(p[3] < 32 for p in corners), "a corner isn't see-through")
                white = sum(p[3] > 128 and min(p[:3]) > 200 for p in border) / len(border)
                self.assertLess(white, 0.1, "white along the edge: a white background")
                opaque = sum(p[3] > 128 for p in border) / len(border)
                self.assertLess(opaque, 0.2, "most of the edge is solid: a background box")


if __name__ == "__main__":
    unittest.main()
