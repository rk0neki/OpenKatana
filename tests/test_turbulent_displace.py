"""local_turbulent_displace and local_displacement_map: displacement by fractal noise or by another
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
        validate(self.edit({'displacement': 'bulge_smoother', 'amount': [[0, 0, 'ease'], [.5, 30, [.42, 0, .58, 1]], [1, 10, 'hold'], [2, 5]],
                            'size': [[0, 80, 'out3'], [1, 120]], 'complexity': [[0, 1.5], [1, 9.5]], 'evolution': [[0, 0], [2, 3, 'inout']],
                            'cycle': 3, 'offset': [[0, [0, 0]], [1, [40, -20], 'in2']], 'pin': 'horizontal_locked', 'edges': 'wrap',
                            'quality': 'high'}), self.root)
        validate(self.edit({}, where='post'), self.root)
        validate(self.edit({'amount': 12}, where='layer'), self.root)
        for fx, error in (({'displacement': 'wave'}, 'one of turbulent'), ({'amount': 2000}, 'out of range'),
                          ({'amount': [[0, 1], [0, 2]]}, 'must increase'), ({'amount': [[0]]}, r'\[seconds, value\]'),
                          ({'amount': [[0, 1, 'bounce'], [1, 2]]}, 'one of lin'), ({'amount': [[0, 1, [2, 0, 1, 1]], [1, 2]]}, 'out of range'),
                          ({'amount': [[i, 1] for i in range(65)]}, 'at most 64'), ({'offset': [[0, 5], [1, [0, 0]]]}, r'\[x, y\]'),
                          ({'complexity': 11}, 'out of range'), ({'cycle': 0}, 'out of range'), ({'pin': 'top'}, 'one of all'),
                          ({'edges': 'mirror'}, 'one of reflect'), ({'quality': 'best'}, 'one of low'),
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

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_cycle_evolution_loops(self):
        # 10 revolutions a second at 30 fps: frame 3 is revolution 1, which a cycle of 1 makes revolution 0 again
        f = self.render({'amount': 300, 'size': 300, 'speed': 10, 'cycle': 1, 'pin': 'none'}, frames=4)
        self.assertGreater((np.abs(f[0] - self.source).sum(2) > 30).mean(), .05)
        self.assertGreater(np.abs(f[1] - f[0]).max(), 30)                 # it evolves
        self.assertLessEqual(np.abs(f[3] - f[0]).max(), 1)                # and comes back round

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_hold_keyframe(self):
        # frames at 1/60, 3/60, 5/60 s: a hold keeps amount 0 until the key at .07 s; linear would move frame 1
        f = self.render({'amount': [[0, 0, 'hold'], [.07, 300]], 'size': 300, 'speed': 0, 'pin': 'none'}, frames=3)
        self.assertEqual(np.abs(f[0] - self.source).max(), 0)
        self.assertEqual(np.abs(f[1] - self.source).max(), 0)
        self.assertGreater((np.abs(f[2] - self.source).sum(2) > 30).mean(), .05)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_smoother_high_quality_and_locked_pins(self):
        for fx in ({'displacement': 'turbulent_smoother', 'quality': 'high'}, {'displacement': 'twist_smoother', 'pin': 'all_locked'},
                   {'complexity': 2.5, 'quality': 'high', 'region': [.25, .25, .75, .75], 'feather': 0}):
            f = self.render({'amount': 300, 'size': 300, 'speed': 0, **fx}, frames=1)[0]
            self.assertGreater((np.abs(f - self.source).sum(2) > 30).mean(), .03, msg=str(fx))
            if 'region' in fx:                                            # high quality still copies what stays put
                outside = np.ones((H, W), bool); outside[int(H * .25) - 1:int(H * .75) + 2, int(W * .25) - 1:int(W * .75) + 2] = False
                self.assertEqual(np.abs(f - self.source)[outside].max(), 0)
            else:                                                         # pinned: the corners stay put
                for y, x in ((0, 0), (0, W - 1), (H - 1, 0), (H - 1, W - 1)):
                    self.assertLess(np.abs(f[y, x] - self.source[y, x]).max(), 3, msg=str(fx))


class DisplacementMapTests(unittest.TestCase):
    """local_displacement_map: another clip's channels move the pixels (a displacement map)."""
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
        for x in ('hue', 'lightness', 'saturation', 'luminance', 'full', 'half', 'off'):
            validate(self.edit({'clip': 'M', 'x': x, 'amount_x': [[0, 10, 'ease'], [1, 50]], 'amount_y': 5, 'fit': 'tile',
                                'edges': 'clamp', 'quality': 'high'}), self.root)
        for fx, error in (({}, 'clip .* is required'), ({'clip': 'Z'}, "clip 'Z' is not in clips"), ({'clip': 'M', 'x': 'chroma'}, 'one of red'),
                          ({'clip': 'M', 'loop': 'bounce'}, 'one of loop, pingpong, clamp'), ({'clip': 'M', 'fit': 'cover'}, 'one of stretch'), ({'clip': 'M', 'smooth': -1}, 'out of range'),
                          ({'clip': 'M', 'size': 3}, 'unsupported fields: size'), ({'clip': 'M', 'neutral': 'median'}, 'a level 0..255 or "mean"'),
                          ({'clip': 'M', 'neutral': 300}, 'out of range')):
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

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_neutral_level(self):
        from openkatana.render import render
        for i in range(3):                                                # a dark plate, as shot on black
            Image.new('RGB', (32, 18), (40, 40, 40)).save(self.root / 'm' / f'{i:05d}.png')
        for neutral, still in (('mean', True), (40, True), (None, False)):
            fx = {'clip': 'M', 'amount': 100, **({'neutral': neutral} if neutral is not None else {})}
            (self.root / 't.json').write_text(json.dumps(self.edit(fx, frames=1)))
            out = self.root / f'o-{neutral}'; render(self.root / 't.json', out)
            f = np.asarray(Image.open(out / 'frames' / '00000.png').convert('RGB')).astype(int)
            self.assertEqual(np.abs(f - self.source).max() == 0, still, msg=str(neutral))   # 128 shifts the picture

    def frames(self, fx, name, n=1):
        from openkatana.render import render
        (self.root / 't.json').write_text(json.dumps(self.edit(fx, frames=n)))
        render(self.root / 't.json', self.root / name)
        return [np.asarray(Image.open(self.root / name / 'frames' / f'{i:05d}.png').convert('RGB')).astype(int) for i in range(n)]

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_edges_full_half_and_axis_amounts(self):
        # map frame 0 is red 255: every pixel shows the source 10 px to its right; the last 10 columns reach past the edge
        x = np.arange(W - 10, W)
        for edges, want in (('wrap', x + 10 - W), ('clamp', np.full(10, W - 1)), ('reflect', 2 * (W - 1) - (x + 10))):
            f = self.frames({'clip': 'M', 'amount': 100, 'edges': edges}, edges)[0]
            self.assertEqual(np.abs(f[50, W - 10:, 0] - want).max(), 0, msg=edges)
        inner = (slice(12, H - 12), slice(12, W - 12))
        f = self.frames({'clip': 'M', 'amount': 100, 'x': 'full', 'y': 'half'}, 'full')[0]
        self.assertEqual(np.abs(f[inner][:, :, 0] - (self.source[inner][:, :, 0] + 10)).max(), 0)    # full: the whole amount
        self.assertEqual(np.abs(f[inner][:, :, 1] - self.source[inner][:, :, 1]).max(), 0)           # half: none
        f = self.frames({'clip': 'M', 'x': 'full', 'y': 'full', 'amount_x': 50, 'amount_y': 100}, 'axes')[0]
        self.assertEqual(np.abs(f[inner][:, :, 0] - (self.source[inner][:, :, 0] + 5)).max(), 0)     # 5 px across
        self.assertEqual(np.abs(f[inner][:, :, 1] - (self.source[inner][:, :, 1] + 20)).max(), 0)    # 10 rows down

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_center_and_tile_fit(self):
        stripes = np.full((18, 32, 3), 128, np.uint8); stripes[:, :16, 0] = 255   # left half moves right, right half stays
        for i in range(3):
            Image.fromarray(stripes).save(self.root / 'm' / f'{i:05d}.png')
        f = self.frames({'clip': 'M', 'amount': 100, 'fit': 'center'}, 'center')[0]
        x0, y0 = (W - 32) // 2, (H - 18) // 2
        moved = np.abs(f - self.source).max(2) > 0
        self.assertFalse(moved[:y0].any() or moved[y0 + 18:].any() or moved[:, :x0].any() or moved[:, x0 + 32:].any())
        self.assertEqual(np.abs(f[y0:y0 + 18, x0:x0 + 16, 0] - (self.source[y0:y0 + 18, x0:x0 + 16, 0] + 10)).max(), 0)
        self.assertEqual(np.abs(f[y0:y0 + 18, x0 + 16:x0 + 32] - self.source[y0:y0 + 18, x0 + 16:x0 + 32]).max(), 0)
        f = self.frames({'clip': 'M', 'amount': 100, 'fit': 'tile'}, 'tile')[0]
        cols = np.arange(W - 12)
        shift = f[40, :W - 12, 0] - self.source[40, :W - 12, 0]
        self.assertEqual(np.abs(shift - np.where(cols % 32 < 16, 10, 0)).max(), 0)   # the 32 px tile repeats

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_eased_amount(self):
        # frames at 1/60 and 3/60 s, keys at 1/60 s (0, in2) and 5/60 s (200): halfway, in2 gives a quarter: 50, 5 px here
        f = self.frames({'clip': 'M', 'x': 'full', 'y': 'half', 'amount': [[1 / 60, 0, 'in2'], [5 / 60, 200]]}, 'eased', n=2)
        self.assertEqual(np.abs(f[0] - self.source).max(), 0)                                    # on the first key
        inner = (slice(12, H - 12), slice(12, W - 12))
        self.assertEqual(np.abs(f[1][inner][:, :, 0] - (self.source[inner][:, :, 0] + 5)).max(), 0)


if __name__ == '__main__':
    unittest.main()
