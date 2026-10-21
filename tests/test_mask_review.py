"""F-MSK-001: matte refine (grow, fill holes, keep largest, smooth), review sheet sampling and the strict matte gate."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from openkatana import gates
from openkatana.vision import mask_digest, refine_masks, review_masks


class MaskReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root / 'f').mkdir(); (self.root / 'm').mkdir()
        for i in range(12):
            Image.new('RGB', (80, 60), (30, 60, 90)).save(self.root / 'f' / f'{i:05d}.png')
            m = Image.new('L', (80, 60), 0); d = ImageDraw.Draw(m)
            d.ellipse((20, 10, 60, 50), fill=255); d.ellipse((36, 26, 44, 34), fill=0)   # subject with a hole
            d.rectangle((2, 2, 5, 5), fill=255)                                           # a stray island
            if i % 2: d.rectangle((68, 50, 72, 54), fill=255)                             # flicker (a separate region)
            im = Image.new('RGBA', (80, 60), 'white'); im.putalpha(m); im.save(self.root / 'm' / f'{i:05d}.png')
        self.clip = {'frames_dir': 'f', 'n': 12, 'fps': 30, 'w': 80, 'h': 60, 'mask_dir': 'm'}
        (self.root / 'timeline.json').write_text(json.dumps({'canvas': {'w': 80, 'h': 60, 'fps': 30, 'frames': 12}, 'clips': {'A': self.clip},
                                                             'shots': [{'f0': 0, 'f1': 12, 'clip': 'A', 'fx': {'cutout': True}}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_refine(self):
        r = refine_masks(self.root / 'timeline.json', 'A', self.root / 'r', fill_holes=True, keep_largest=True)
        a = np.asarray(Image.open(self.root / 'r' / '00000.png'))[:, :, 3]
        self.assertEqual((a[30, 40], a[3, 3]), (255, 0))              # hole filled, island dropped
        self.assertEqual(r['clip_update'], {'mask_dir': 'r'})
        refine_masks(self.root / 'timeline.json', 'A', self.root / 'g', grow=2)
        self.assertGreater((np.asarray(Image.open(self.root / 'g' / '00000.png'))[:, :, 3] > 127).sum(), ((a > 127).sum()) - 64)

    def test_review_sampling_and_flags(self):
        r = review_masks(self.root / 'timeline.json', 'A', self.root / 'rv', step=.1)
        self.assertEqual(r['frames'], [0, 3, 6, 9, 11])                 # every 0.1 s plus the last frame
        self.assertTrue(any('separate regions' in f for f in r['flags']))
        self.assertEqual(r['mask_sha256'], mask_digest(self.root, 'm', 12))

    def test_strict_matte_gate(self):
        state = {'timeline': json.loads((self.root / 'timeline.json').read_text()), 'revision': 'r1', 'assets': []}
        gates.set_strict(self.root, True); gates.record_preview(self.root, 'r1', [0])
        self.assertEqual(gates.matte_clips(state['timeline']), ['A'])
        self.assertTrue(any('review the matte of clip A' in m for m in gates.missing(self.root, state)))
        sha = mask_digest(self.root, 'm', 12)
        gates.record_matte(self.root, sha, 'A', False)
        self.assertTrue(any('rejected' in m for m in gates.missing(self.root, state)))
        gates.record_matte(self.root, sha, 'A', True)
        self.assertEqual(gates.missing(self.root, state), [])


if __name__ == '__main__':
    unittest.main()
