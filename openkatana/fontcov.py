"""Glyph coverage from a font's character map (audit F-FONT-001), without extra dependencies: reads the `cmap` table
(formats 4 and 12; for a TTC collection the first face, the one browsers load) of TTF/OTF/TTC files. WOFF/WOFF2 are
compressed and reported as `unknown`."""
import struct
from functools import lru_cache
from pathlib import Path


def _face_offset(data):
    if data[:4] == b'ttcf':
        return struct.unpack('>I', data[12:16])[0]
    return 0


@lru_cache(maxsize=64)
def codepoints(path):
    """The set of code points the font maps, or None when the format is not readable here."""
    p = Path(path)
    if p.suffix.lower() not in ('.ttf', '.otf', '.ttc'):
        return None
    data = p.read_bytes()
    try:
        base = _face_offset(data)
        num = struct.unpack('>H', data[base + 4:base + 6])[0]
        cmap = None
        for i in range(num):
            tag, _, off, _ = struct.unpack('>4sIII', data[base + 12 + 16 * i: base + 28 + 16 * i])
            if tag == b'cmap':
                cmap = off
        if cmap is None:
            return None
        n = struct.unpack('>H', data[cmap + 2:cmap + 4])[0]
        subtables = [struct.unpack('>HHI', data[cmap + 4 + 8 * i: cmap + 12 + 8 * i]) for i in range(n)]
        # prefer full Unicode (format 12), then BMP Unicode (format 4)
        best = None
        for plat, enc, off in subtables:
            fmt = struct.unpack('>H', data[cmap + off:cmap + off + 2])[0]
            if (plat, fmt) in ((3, 12), (0, 12)) or (fmt == 12 and best is None):
                best = (12, cmap + off); break
            if fmt == 4 and (plat == 3 and enc in (1, 0) or plat == 0) and (best is None or best[0] != 12):
                best = (4, cmap + off)
        if best is None:
            return None
        fmt, o = best
        out = set()
        if fmt == 4:
            seg2 = struct.unpack('>H', data[o + 6:o + 8])[0]; seg = seg2 // 2
            ends = struct.unpack(f'>{seg}H', data[o + 14:o + 14 + seg2])
            starts = struct.unpack(f'>{seg}H', data[o + 16 + seg2:o + 16 + 2 * seg2])
            deltas = struct.unpack(f'>{seg}h', data[o + 16 + 2 * seg2:o + 16 + 3 * seg2])
            ro = o + 16 + 3 * seg2
            ranges = struct.unpack(f'>{seg}H', data[ro:ro + seg2])
            for i in range(seg):
                for c in range(starts[i], ends[i] + 1):
                    if c == 0xFFFF:
                        continue
                    if ranges[i] == 0:
                        g = (c + deltas[i]) & 0xFFFF
                    else:
                        addr = ro + 2 * i + ranges[i] + 2 * (c - starts[i])
                        g = struct.unpack('>H', data[addr:addr + 2])[0]
                        g = (g + deltas[i]) & 0xFFFF if g else 0
                    if g:
                        out.add(c)
        else:
            ngroups = struct.unpack('>I', data[o + 12:o + 16])[0]
            for i in range(ngroups):
                s, e, g = struct.unpack('>III', data[o + 16 + 12 * i: o + 28 + 12 * i])
                out.update(range(s, e + 1))
        return frozenset(out)
    except (struct.error, IndexError):
        return None


def missing(path, text):
    """Characters of `text` the font does not map (whitespace ignored); None when coverage cannot be read."""
    cps = codepoints(str(path))
    if cps is None:
        return None
    return sorted({ch for ch in text if not ch.isspace() and ord(ch) not in cps})
