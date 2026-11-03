"""local_turbulent_displace and local_displacement_map: After Effects-style displacement by fractal noise or by another
clip's channels."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from openkatana.contracts import ContractError, validate

W, H = 192, 108


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path()) and bool(shutil.which('ffmpeg'))
    except Exception:
        return False


class TurbulentDisplaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        (self.root / 'f').mkdir()
        a = np.zeros((H, W, 3), np.uint8); a[:, :] = (20, 20, 30)
        a[:, ::8] = (80, 170, 255); a[::8, :] = (255, 120, 60)         # a grid: any move shows
        self.source = a
        Image.fromarray(a).save(self.root / 'f' / '00000.png')

    def edit(self, fx, frames=4, where='fx'):
        shot = {'f0': 0, 'f1': frames, 'clip': 'A', 'speed': 0}
        if where == 'fx':
            shot['fx'] = {'local_turbulent_displace': fx}
        elif where == 'layer':
            shot['layers'] = [{'type': 'local_turbulent_displace', 'phase': 'subject', **fx}]
        e = {'canvas': {'w': W, 'h': H, 'fps': 30, 'frames': frames},
             'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': W, 'h': H}}, 'shots': [shot]}
        if where == 'post':
            e['post'] = {'local_turbulent_displace': fx}
        return e

    def render(self, fx, frames=4):
        from openkatana.render import render
        (self.root / 't.json').write_text(json.dumps(self.edit(fx, frames)))
        out = self.root / 'o'
        shutil.rmtree(out, ignore_errors=True)
        render(self.root / 't.json', out)
        return [np.asarray(Image.open(out / 'frames' / f'{i:05d}.png').convert('RGB')).astype(int) for i in range(frames)]

    def test_validation(self):
        validate(self.edit({'displacement': 'twist', 'amount': [[0, 0], [.5, 30]], 'size': 80, 'complexity': 3, 'evolution': .2,
                            'speed': 1, 'offset': [5, 0], 'drift': [10, -4], 'every': 2, 'pin': 'none',
                            'region': [.2, .3, .8, .7], 'feather': .05, 'seed': 4, 'at': .2}), self.root)
        validate(self.edit({}, where='post'), self.root)
        validate(self.edit({'amount': 12}, where='layer'), self.root)
        for fx, error in (({'displacement': 'wave'}, 'one of turbulent'), ({'amount': 2000}, 'out of range'),
                          ({'amount': [[0, 1], [0, 2]]}, 'must increase'), ({'amount': [[0]]}, r'\[seconds, px\]'),
                          ({'complexity': 1.5}, 'integer'), ({'complexity': 9}, 'out of range'), ({'pin': 'top'}, 'one of all'),
                          ({'region': [.5, .5, .4, .9]}, 'greater than'), ({'region': [0, 0, 1]}, r'\[x0, y0, x1, y1\]'),
                          ({'drift': 3}, r'\[x, y\]'), ({'octaves': 2}, 'unsupported fields: octaves'),
                          ({'amount': float('nan')}, '')):
            with self.assertRaisesRegex(ContractError, error, msg=str(fx)):
                validate(self.edit(fx), self.root)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_rendered_displacement(self):
        # frames sample at their centres: frame 0 at 1/60 s (amount 0), frame 2 at 5/60 s (300)
        f = self.render({'amount': [[0, 0], [.02, 0], [.05, 300]], 'size': 300, 'speed': 0, 'pin': 'all'}, frames=3)
        self.assertEqual(np.abs(f[0] - self.source).max(), 0)             # amount 0: untouched
        moved = np.abs(f[2] - self.source).sum(2) > 30
        self.assertGreater(moved.mean(), .05)                              # the grid bends
        for y, x in ((0, 0), (0, W - 1), (H - 1, 0), (H - 1, W - 1)):      # pinned: the corners stay put
            self.assertLess(np.abs(f[2][y, x] - self.source[y, x]).max(), 3)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_region_evolution_and_boil(self):
        f = self.render({'amount': 300, 'size': 300, 'speed': 3, 'every': 2, 'pin': 'none',
                         'region': [.25, .25, .75, .75], 'feather': 0}, frames=3)
        outside = np.ones((H, W), bool); outside[int(H * .25) - 1:int(H * .75) + 2, int(W * .25) - 1:int(W * .75) + 2] = False
        self.assertEqual(np.abs(f[2] - self.source)[outside].max(), 0)    # nothing moves outside the region
        self.assertGreater((np.abs(f[2] - self.source).sum(2) > 30).mean(), .03)
        self.assertEqual(np.abs(f[1] - f[0]).max(), 0)                    # every 2: the field holds for two frames
        self.assertGreater(np.abs(f[2] - f[1]).max(), 30)                 # then evolves

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_horizontal_moves_only_sideways(self):
        f = self.render({'displacement': 'horizontal', 'amount': 300, 'size': 300, 'pin': 'none'}, frames=1)[0]
        self.assertGreater((np.abs(f - self.source).sum(2) > 30).mean(), .05)   # the vertical lines bend
        orange = (np.abs(f - np.array([255, 120, 60])).sum(2) < 40)
        for y in range(0, H, 8):                                          # sideways moves keep each grid row whole
            self.assertGreater(orange[y].mean(), .6, msg=f'row {y}')



class DisplacementMapTests(unittest.TestCase):
    """local_displacement_map: another clip's channels move the pixels (After Effects' Displacement Map)."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        (self.root / 'f').mkdir(); (self.root / 'm').mkdir()
        a = np.zeros((H, W, 3), np.uint8); a[:, :, 0] = np.arange(W)[None, :]; a[:, :, 1] = np.arange(H)[:, None] * 2
        self.source = a.astype(int)
        Image.fromarray(a).save(self.root / 'f' / '00000.png')
        for i, c in enumerate([(255, 128, 128), (128, 128, 128), (128, 255, 0)]):   # map frames: right, still, down
            Image.new('RGB', (32, 18), c).save(self.root / 'm' / f'{i:05d}.png')

    def edit(self, fx, frames=3):
        return {'canvas': {'w': W, 'h': H, 'fps': 30, 'frames': frames},
                'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': W, 'h': H},
                          'M': {'frames_dir': 'm', 'n': 3, 'fps': 30, 'w': 32, 'h': 18}},
                'shots': [{'f0': 0, 'f1': frames, 'clip': 'A', 'speed': 0, 'fx': {'local_displacement_map': fx}}]}

    def test_validation(self):
        validate(self.edit({'clip': 'M', 'src': .5, 'speed': .5, 'loop': 'pingpong', 'amount': [[0, 0], [1, 40]], 'x': 'luma',
                            'y': 'none', 'smooth': 4, 'region': [0, 0, .5, 1], 'feather': .1, 'at': .1}), self.root)
        for fx, error in (({}, 'clip .* is required'), ({'clip': 'Z'}, "clip 'Z' is not in clips"), ({'clip': 'M', 'x': 'hue'}, 'one of red'),
                          ({'clip': 'M', 'loop': 'bounce'}, 'loop, pingpong or clamp'), ({'clip': 'M', 'smooth': -1}, 'out of range'),
                          ({'clip': 'M', 'size': 3}, 'unsupported fields: size')):
            with self.assertRaisesRegex(ContractError, error, msg=str(fx)):
                validate(self.edit(fx), self.root)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_channels_move_the_picture(self):
        from openkatana.render import render
        (self.root / 't.json').write_text(json.dumps(self.edit({'clip': 'M', 'amount': 100})))   # 100 px at 1080 = 10 px here
        render(self.root / 't.json', self.root / 'o')
        f = [np.asarray(Image.open(self.root / 'o' / 'frames' / f'{i:05d}.png').convert('RGB')).astype(int) for i in range(3)]
        inner = (slice(12, H - 12), slice(12, W - 12))
        # map frame 0, red 255: every pixel shows the source 10 px to its right; green 128 keeps the rows
        self.assertEqual(np.abs(f[0][inner][:, :, 0] - (self.source[inner][:, :, 0] + 10)).max(), 0)
        self.assertEqual(np.abs(f[0][inner][:, :, 1] - self.source[inner][:, :, 1]).max(), 0)
        self.assertEqual(np.abs(f[1] - self.source).max(), 0)             # map frame 1, mid grey: nothing moves
        self.assertEqual(np.abs(f[2][inner][:, :, 1] - (self.source[inner][:, :, 1] + 20)).max(), 0)   # 10 rows down


if __name__ == '__main__':
    unittest.main()
