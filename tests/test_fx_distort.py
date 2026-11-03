"""The Distort effect pack (web/fx_distort.js): After Effects' Wave Warp, Ripple, Twirl, Bulge, Polar Coordinates,
Mirror, CC Kaleida and a shockwave ring, each a coordinate map over the shared resampler."""
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


class DistortPackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        rng = np.random.default_rng(7)
        noise = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)            # every pixel distinct: any move shows
        cols = np.repeat(rng.integers(0, 256, (1, W, 3), dtype=np.uint8), H, 0)   # changes only along x
        grey = np.full((H, W, 3), 90, np.uint8); grey[:, ::6] = 230; grey[::6, :] = 230
        self.images = {'N': noise, 'C': cols, 'G': grey}
        for name, a in self.images.items():
            (self.root / name).mkdir()
            Image.fromarray(a).save(self.root / name / '00000.png')

    def edit(self, shots):
        """shots: [(effect, params, clip, frames)] one after another; each starts its own clock."""
        out, f = [], 0
        for name, fx, clip, n in shots:
            out.append({'f0': f, 'f1': f + n, 'clip': clip, 'speed': 0, 'fx': {name: fx}})
            f += n
        return {'canvas': {'w': W, 'h': H, 'fps': 30, 'frames': f},
                'clips': {c: {'frames_dir': c, 'n': 1, 'fps': 30, 'w': W, 'h': H} for c in self.images}, 'shots': out}

    def render(self, shots):
        from openkatana.render import render
        (self.root / 't.json').write_text(json.dumps(self.edit(shots)))
        out = self.root / 'o'
        shutil.rmtree(out, ignore_errors=True)
        render(self.root / 't.json', out)
        n = sum(s[3] for s in shots)
        frames = [np.asarray(Image.open(out / 'frames' / f'{i:05d}.png').convert('RGB')).astype(int) for i in range(n)]
        shutil.rmtree(out, ignore_errors=True)
        return frames

    def test_validation(self):
        good = [
            ('local_wave_warp', {'wave_type': 'smooth_noise', 'wave_height': [[0, 0], [1, 30, 'ease']], 'wave_width': [[0, 40], [2, 90]],
                                 'direction': 45, 'wave_speed': -2, 'phase': 90, 'pinning': 'horizontal', 'edges': 'wrap', 'quality': 'high',
                                 'region': [.1, .1, .9, .5], 'feather': .05, 'at': .5}),
            ('local_ripple', {'center': [[0, [.2, .3]], [1, [.8, .3]]], 'radius': .4, 'wavelength': 60, 'amplitude': [[0, 0], [.5, 25]],
                              'wave_speed': 2, 'phase': 30, 'conversion': 'symmetric'}),
            ('local_shockwave', {'center': [.5, .4], 'at': 1, 'd': .5, 'ease': [.2, .8, .3, 1], 'max_radius': .7, 'width': 120,
                                 'amount': -60, 'split': 12}),
            ('local_twirl', {'angle': [[0, 0], [1, 720, 'inout3']], 'radius': .5, 'center': [.4, .6]}),
            ('local_bulge', {'center': [.5, .5], 'horizontal_radius': 400, 'vertical_radius': 250, 'height': [[0, 0], [.3, -2]],
                             'taper': .5, 'pin': True}),
            ('local_polar', {'interpolation': [[0, 0], [1, 1]], 'conversion': 'polar_to_rect'}),
            ('local_kaleidoscope', {'center': [.5, .5], 'segments': 8, 'rotation': [[0, 0], [4, 90]], 'size': 300, 'mirroring': 'off'}),
            ('local_mirror', {'reflection_center': [.3, .5], 'reflection_angle': [[0, 0], [1, 90]]}),
        ]
        for name, fx in good:
            validate(self.edit([(name, fx, 'N', 1)]), self.root)
            validate(self.edit([(name, {}, 'N', 1)]), self.root)
        bad = [('local_wave_warp', {'wave_type': 'zigzag'}, 'one of sine'), ('local_wave_warp', {'pinning': 'all_locked'}, 'one of none'),
               ('local_wave_warp', {'wave_width': 0}, 'out of range'), ('local_wave_warp', {'wave_height': [[0, 1], [0, 2]]}, 'must increase'),
               ('local_wave_warp', {'amplitude': 3}, 'unsupported fields: amplitude'),
               ('local_ripple', {'conversion': 'radial'}, 'one of asymmetric'), ('local_ripple', {'center': [.5]}, r'\[x, y\]'),
               ('local_ripple', {'center': [1.5, .5]}, 'out of range'), ('local_shockwave', {'ease': 'bounce'}, 'one of lin'),
               ('local_shockwave', {'d': 0}, 'out of range'), ('local_shockwave', {'split': -1}, 'out of range'),
               ('local_twirl', {'angle': 'big'}, 'finite number'), ('local_bulge', {'height': 5}, 'out of range'),
               ('local_bulge', {'pin': 1}, 'boolean'), ('local_polar', {'interpolation': 1.5}, 'out of range'),
               ('local_polar', {'conversion': 'polar'}, 'one of rect_to_polar'), ('local_kaleidoscope', {'segments': 2.5}, 'integer'),
               ('local_kaleidoscope', {'segments': 40}, 'out of range'), ('local_kaleidoscope', {'mirroring': True}, 'one of on'),
               ('local_mirror', {'reflection_angle': float('nan')}, ''), ('local_mirror', {'edges': 'mirror'}, 'one of reflect'),
               ('local_mirror', {'region': [.5, .5, .4, .9]}, 'greater than'), ('local_twirl', {'at': -1}, 'out of range')]
        for name, fx, error in bad:
            with self.assertRaisesRegex(ContractError, error, msg=f'{name} {fx}'):
                validate(self.edit([(name, fx, 'N', 1)]), self.root)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_geometry(self):
        N, C = self.images['N'].astype(int), self.images['C'].astype(int)
        shots = [('local_wave_warp', {'wave_height': 0}, 'N', 1),                                         # 0 identities
                 ('local_twirl', {'angle': 0}, 'N', 1),
                 ('local_bulge', {'height': 0}, 'N', 1),
                 ('local_polar', {'interpolation': 0}, 'N', 1),
                 ('local_ripple', {'amplitude': 0}, 'N', 1),
                 ('local_wave_warp', {'wave_height': 40, 'wave_width': 300, 'direction': 90}, 'C', 1),   # 5 travels right
                 ('local_wave_warp', {'wave_height': 40, 'wave_width': 300, 'direction': 90}, 'N', 1),   # 6
                 ('local_mirror', {}, 'N', 1),                                                           # 7
                 ('local_mirror', {'reflection_angle': 90}, 'N', 1),                                     # 8
                 ('local_twirl', {'angle': 180, 'radius': .4}, 'N', 1),                                  # 9
                 ('local_bulge', {'height': 2, 'horizontal_radius': 500, 'vertical_radius': 300}, 'N', 1),   # 10
                 ('local_kaleidoscope', {'segments': 4, 'size': 2000}, 'N', 1),                          # 11
                 ('local_polar', {'interpolation': 1}, 'N', 1),                                          # 12
                 ('local_ripple', {'amplitude': 30, 'radius': .3, 'wave_speed': 0}, 'N', 1),             # 13
                 ('local_wave_warp', {'wave_height': 60, 'region': [.25, .25, .75, .75], 'feather': 0}, 'N', 1)]   # 14
        f = self.render(shots)
        for i in range(5):
            self.assertEqual(np.abs(f[i] - N).max(), 0, msg=shots[i])
        self.assertLessEqual(np.abs(f[5] - C).max(), 1)                   # a rightward wave moves pixels only vertically
        self.assertGreater((np.abs(f[6] - N).sum(2) > 30).mean(), .5)       # and it does move them
        self.assertEqual(np.abs(f[7][:, W // 2:] - N[:, :W // 2][:, ::-1]).max(), 0)   # 0: left mirrored onto the right
        self.assertEqual(np.abs(f[7][:, :W // 2] - N[:, :W // 2]).max(), 0)
        self.assertEqual(np.abs(f[8][H // 2:] - N[:H // 2][::-1]).max(), 0)            # 90: top onto the bottom
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.hypot(xx - (W / 2 - .5), yy - (H / 2 - .5))
        twirled = np.abs(f[9] - N).sum(2)
        self.assertEqual(twirled[r >= .4 * H + 1].max(), 0)                 # twirl: nothing moves beyond its radius
        self.assertGreater((twirled[r < .3 * H] > 30).mean(), .8)
        e = ((xx - (W / 2 - .5)) / (500 * H / 1080)) ** 2 + ((yy - (H / 2 - .5)) / (300 * H / 1080)) ** 2
        bulged = np.abs(f[10] - N).sum(2)
        self.assertEqual(bulged[e >= 1.02].max(), 0)                        # bulge: only inside its ellipse
        self.assertGreater((bulged[e < .5] > 30).mean(), .5)
        # kaleidoscope, 4 mirrored wedges: symmetric across the diagonal fold through the centre ((dx, dy) -> (-dy, -dx))
        k = f[11]; cx, cy = W / 2 - .5, H / 2 - .5
        diffs = [np.abs(k[y, x] - k[int(cy - (x - cx)), int(cx - (y - cy))]).max()
                 for y in range(4, H - 4, 3) for x in range(int(cx) - 40, int(cx) + 40, 3)
                 if 0 <= cy - (x - cx) < H and 0 <= cx - (y - cy) < W]
        self.assertGreater(len(diffs), 100)
        self.assertLessEqual(np.percentile(diffs, 95), 2)
        self.assertGreater((np.abs(f[11] - N).sum(2) > 30).mean(), .3)
        self.assertGreater((np.abs(f[12] - N).sum(2) > 30).mean(), .8)     # polar: everything moves
        rippled = np.abs(f[13] - N).sum(2)
        self.assertEqual(rippled[r >= .3 * np.hypot(W, H) + 1].max(), 0)
        self.assertGreater((rippled > 30).mean(), .2)
        outside = np.ones((H, W), bool); outside[int(H * .25) - 1:int(H * .75) + 2, int(W * .25) - 1:int(W * .75) + 2] = False
        self.assertEqual(np.abs(f[14] - N)[outside].max(), 0)               # region: nothing moves outside it
        self.assertGreater((np.abs(f[14] - N).sum(2) > 30).mean(), .1)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_shockwave_timing_and_split(self):
        G = self.images['G'].astype(int)
        # frames sample at their centres: 1/60, 3/60, ... s from the shot start
        f = self.render([('local_shockwave', {'at': .05, 'd': .2, 'amount': 80, 'width': 200, 'max_radius': .3}, 'G', 9),
                         ('local_shockwave', {'d': .3, 'amount': 60, 'width': 200, 'split': 20, 'max_radius': .5}, 'G', 3)])
        self.assertEqual(np.abs(f[0] - G).max(), 0)                         # before `at`
        self.assertEqual(np.abs(f[8] - G).max(), 0)                         # after `at` + d
        moving = [(np.abs(f[i] - G).sum(2) > 30).mean() for i in (2, 4)]
        self.assertGreater(min(moving), .02)
        self.assertEqual(np.abs(f[2] - G)[H // 2 - 2:H // 2 + 2, W // 2 - 2:W // 2 + 2].max(), 0)   # the middle stays inside the ring
        fringe = np.abs(f[10][..., 0] - f[10][..., 2])                     # split: red and blue part on a grey picture
        self.assertGreater((fringe > 30).mean(), .01)


if __name__ == '__main__':
    unittest.main()
