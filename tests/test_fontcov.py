"""F-FONT-001: glyph coverage from the cmap (formats 4 and 12, TTC first face) and the missing-glyph warning."""
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from openkatana.contracts import validate
from openkatana.fontcov import codepoints, missing
from openkatana.warnings import timeline_warnings


def sfnt(cmap_sub, base=0):
    """A minimal font holding only a cmap; `base` = where this face starts in the file (table offsets are absolute)."""
    cmap = struct.pack('>HHHHI', 0, 1, 3, 10 if cmap_sub[:2] == b'\x00\x0c' else 1, 12) + cmap_sub
    head = struct.pack('>IHHHH', 0x00010000, 1, 16, 0, 0)
    return head + struct.pack('>4sIII', b'cmap', 0, base + 12 + 16, len(cmap)) + cmap


def fmt4(start, end):
    seg = 2; seg2 = 4
    body = struct.pack('>HHHH', seg2, 4, 1, 0) + struct.pack('>HH', end, 0xFFFF) + b'\0\0' + struct.pack('>HH', start, 0xFFFF)
    body += struct.pack('>hh', 1 - start, 1) + struct.pack('>HH', 0, 0)
    return struct.pack('>HHH', 4, 6 + len(body), 0) + body


def fmt12(start, end):
    return struct.pack('>HHIII', 12, 0, 16 + 12, 0, 1) + struct.pack('>III', start, end, 1)


class FontCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root / 'abc.ttf').write_bytes(sfnt(fmt4(0x41, 0x43)))
        (self.root / 'emoji.ttf').write_bytes(sfnt(fmt12(0x1F600, 0x1F602)))
        face = sfnt(fmt4(0x41, 0x43), base=16)
        (self.root / 'pair.ttc').write_bytes(b'ttcf' + struct.pack('>HHII', 1, 0, 1, 16) + face)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cmap_formats(self):
        self.assertEqual(codepoints(str(self.root / 'abc.ttf')), frozenset({0x41, 0x42, 0x43}))
        self.assertEqual(codepoints(str(self.root / 'emoji.ttf')), frozenset({0x1F600, 0x1F601, 0x1F602}))
        self.assertEqual(missing(self.root / 'pair.ttc', 'AB C D'), ['D'])
        self.assertIsNone(missing(self.root / 'x.woff2', 'A'))

    def test_missing_glyph_warning(self):
        (self.root / 'f').mkdir(); Image.new('RGB', (64, 36)).save(self.root / 'f' / '00000.png')
        e = {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': 10}, 'fonts': [{'family': 'ABC', 'url': 'abc.ttf'}],
             'clips': {'C': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': 64, 'h': 36}}, 'shots': [{'f0': 0, 'f1': 10, 'clip': 'C', 'speed': 0}],
             'text': [{'type': 'font', 'family': 'ABC', 'text': 'CAB', 'f0': 0, 'f1': 5}, {'type': 'font', 'family': 'ABC', 'text': 'CAD!', 'f0': 5, 'f1': 10}]}
        canon = {**e, 'fonts': e['fonts']}
        w = [x for x in timeline_warnings(validate(canon), self.root) if x['code'] == 'missing_glyphs']
        self.assertEqual(len(w), 1); self.assertIn("'!D'", w[0]['message'])
        self.assertEqual([x for x in timeline_warnings(validate(canon)) if x['code'] == 'missing_glyphs'], [])   # no root: not checked


if __name__ == '__main__':
    unittest.main()
