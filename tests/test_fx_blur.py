"""The Blur & Sharpen pack (web/fx_blur.js): After Effects' Gaussian, Directional, Radial and Camera Lens Blur, Channel
Blur, Unsharp Mask and a tilt-shift focus band."""
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


class BlurPackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        rng = np.random.default_rng(3)
        self.images = {'N': rng.integers(0, 256, (H, W, 3), dtype=np.uint8)}   # every pixel distinct: any change shows
        yy, xx = np.mgrid[0:H, 0:W]
        self.images['M'] = np.repeat(((xx * 255) // (W - 1)).astype(np.uint8)[..., None], 3, 2)   # a left-to-right ramp
        for name, a in self.images.items():
            (self.root / name).mkdir()
            Image.fromarray(a).save(self.root / name / '00000.png')

    def plate(self, a):
        self.images['N'] = a
        Image.fromarray(a).save(self.root / 'N' / '00000.png')

    def edit(self, name, fx, frames=1, where='fx'):
        shot = {'f0': 0, 'f1': frames, 'clip': 'N', 'speed': 0}
        if where == 'fx':
            shot['fx'] = {name: fx}
        elif where == 'layer':
            shot['layers'] = [{'type': name, **fx}]
        e = {'canvas': {'w': W, 'h': H, 'fps': 30, 'frames': frames},
             'clips': {c: {'frames_dir': c, 'n': 1, 'fps': 30, 'w': W, 'h': H} for c in self.images}, 'shots': [shot]}
        if where == 'post':
            e['post'] = {name: fx}
        return e

    def render(self, name, fx, frames=1):
        from openkatana.render import render
        (self.root / 't.json').write_text(json.dumps(self.edit(name, fx, frames)))
        out = self.root / 'o'
        shutil.rmtree(out, ignore_errors=True)
        render(self.root / 't.json', out)
        f = [np.asarray(Image.open(out / 'frames' / f'{i:05d}.png').convert('RGB')).astype(int) for i in range(frames)]
        shutil.rmtree(out, ignore_errors=True)
        return f

    def test_validation(self):
        good = [
            ('local_gaussian_blur', {'blurriness': [[0, 0], [1, 40, 'ease']], 'dimensions': 'horizontal', 'repeat_edge_pixels': False,
                                     'region': [.1, .1, .6, .9], 'feather': .05, 'at': .5}),
            ('local_directional_blur', {'direction': [[0, 0], [1, 90]], 'blur_length': [[0, 0], [.5, 60]]}),
            ('local_radial_blur', {'amount': [[0, 0], [1, 40]], 'center': [[0, [.3, .4]], [1, [.6, .5]]], 'type': 'zoom', 'quality': 'high'}),
            ('local_camera_lens_blur', {'blur_radius': [[0, 0], [1, 30]], 'iris_shape': 'pentagon', 'iris_rotation': 15, 'iris_roundness': 40,
                                        'highlight_gain': 30, 'highlight_threshold': 200, 'map': 'radial', 'center': [.5, .4],
                                        'focal_distance': 0, 'invert': True}),
            ('local_camera_lens_blur', {'clip': 'M', 'src': 0, 'speed': 1, 'loop': 'clamp', 'focal_distance': 128}),
            ('local_camera_lens_blur', {'map': 'clip', 'clip': 'M'}),
            ('local_unsharp_mask', {'amount': [[0, 0], [1, 150]], 'radius': 3, 'threshold': 10}),
            ('local_channel_blur', {'red_blurriness': 10, 'green_blurriness': [[0, 0], [1, 5]], 'blue_blurriness': 0, 'dimensions': 'vertical',
                                    'repeat_edge_pixels': True}),
            ('local_tilt_shift', {'center': .6, 'angle': 10, 'band': .2, 'feather': .2, 'blur_radius': [[0, 0], [1, 40]], 'saturation': 1.3}),
            ('local_tilt_shift', {'center': [[0, [.5, .3]], [1, [.5, .7]]]}),
            ('local_tilt_shift', {'center': [[0, .3], [1, .7]]}),
        ]
        for name, fx in good:
            validate(self.edit(name, fx), self.root)
            validate(self.edit(name, {}), self.root)
        validate(self.edit('local_gaussian_blur', {}, where='post'), self.root)
        validate(self.edit('local_tilt_shift', {'band': .3}, where='layer'), self.root)
        bad = [('local_gaussian_blur', {'blurriness': -1}, 'out of range'), ('local_gaussian_blur', {'dimensions': 'both_ways'}, 'one of both'),
               ('local_gaussian_blur', {'repeat_edge_pixels': 1}, 'boolean'), ('local_gaussian_blur', {'radius': 3}, 'unsupported fields: radius'),
               ('local_gaussian_blur', {'blurriness': [[0, 1], [0, 2]]}, 'must increase'),
               ('local_gaussian_blur', {'region': [.5, .1, .2, .9]}, 'greater than'),
               ('local_directional_blur', {'blur_length': 2000}, 'out of range'),
               ('local_radial_blur', {'amount': 101}, 'out of range'), ('local_radial_blur', {'type': 'twist'}, 'one of spin'),
               ('local_radial_blur', {'center': [1.5, .5]}, 'out of range'), ('local_radial_blur', {'center': .5}, r'\[x, y\]'),
               ('local_camera_lens_blur', {'iris_shape': 'circle'}, 'one of triangle'),
               ('local_camera_lens_blur', {'iris_roundness': 120}, 'out of range'),
               ('local_camera_lens_blur', {'map': 'clip'}, 'needs clip'),
               ('local_camera_lens_blur', {'clip': 'M', 'map': 'radial'}, 'goes with map "clip"'),
               ('local_camera_lens_blur', {'clip': 'Z'}, "'Z' is not in clips"),
               ('local_camera_lens_blur', {'focal_distance': 40}, 'set map'),
               ('local_camera_lens_blur', {'center': [.5, .5]}, 'goes with map "radial"'),
               ('local_unsharp_mask', {'threshold': 300}, 'out of range'), ('local_unsharp_mask', {'amount': 600}, 'out of range'),
               ('local_channel_blur', {'alpha_blurriness': 3}, 'unsupported fields: alpha_blurriness'),
               ('local_tilt_shift', {'band': 2}, 'out of range'), ('local_tilt_shift', {'feather': -.1}, 'out of range'),
               ('local_tilt_shift', {'center': [.5]}, r'\[x, y\]'), ('local_tilt_shift', {'region': [0, 0, 1, 1]}, 'unsupported fields: region')]
        for name, fx, error in bad:
            with self.assertRaisesRegex(ContractError, error, msg=f'{name} {fx}'):
                validate(self.edit(name, fx), self.root)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_zero_amounts_and_before_at_are_identity(self):
        a = self.images['N']
        for name, fx in (('local_gaussian_blur', {'blurriness': 0}), ('local_gaussian_blur', {'blurriness': 0, 'dimensions': 'horizontal'}),
                         ('local_directional_blur', {'blur_length': 0}), ('local_radial_blur', {'amount': 0}),
                         ('local_radial_blur', {'amount': 0, 'type': 'zoom'}), ('local_camera_lens_blur', {'blur_radius': 0}),
                         ('local_unsharp_mask', {'amount': 0}), ('local_channel_blur', {}), ('local_tilt_shift', {'blur_radius': 0}),
                         ('local_gaussian_blur', {'at': 5}), ('local_camera_lens_blur', {'at': 5}),
                         ('local_unsharp_mask', {'amount': 300, 'threshold': 255})):
            f = self.render(name, fx)[0]
            self.assertEqual(np.abs(f - a).max(), 0, msg=f'{name} {fx}')

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_one_axis_blurs_never_mix_rows_or_columns(self):
        # rows of different flat colours: a horizontal blur leaves every row exactly as it was
        a = np.zeros((H, W, 3), np.uint8); a[:] = np.random.default_rng(1).integers(0, 256, (H, 1, 3), dtype=np.uint8)
        self.plate(a)
        cases = (('local_gaussian_blur', {'blurriness': 30, 'dimensions': 'horizontal'}),
                 ('local_directional_blur', {'blur_length': 25, 'direction': 90}),
                 ('local_channel_blur', {'red_blurriness': 20, 'blue_blurriness': 40, 'dimensions': 'horizontal'}))
        for name, fx in cases:   # each row stays flat at its own level
            f = self.render(name, fx)[0]
            self.assertEqual(np.abs(f - a).max(), 0, msg=name)
            self.assertEqual(np.ptp(f, axis=1).max(), 0, msg=name)
        # changing one row of a noise plate changes that row of the result and no other
        noise = np.random.default_rng(2).integers(0, 256, (H, W, 3), dtype=np.uint8)
        other = noise.copy(); other[50] = 255 - other[50]
        for name, fx in cases:
            self.plate(noise); f = self.render(name, fx)[0]
            self.plate(other); g = self.render(name, fx)[0]
            rows = np.nonzero(np.abs(f - g).max(axis=(1, 2)))[0]
            self.assertEqual(list(rows), [50], msg=name)
        # and the noise plate is blurred along rows only: each row's mean stays, columns lose their contrast
        noise = np.random.default_rng(2).integers(0, 256, (H, W, 3), dtype=np.uint8)
        self.plate(noise)
        f = self.render('local_gaussian_blur', {'blurriness': 100, 'dimensions': 'horizontal'})[0]
        inner = slice(20, W - 20)
        self.assertLess(np.abs(f[:, inner].mean(axis=1) - noise[:, inner].astype(int).mean(axis=1)).max(), 4)
        self.assertLess(abs(f.mean() - noise.mean()), .3)   # no drift
        self.assertLess(f[:, inner].std(axis=1).mean(), noise[:, inner].std(axis=1).mean() / 3)
        # vertical: columns stay apart
        a = np.zeros((H, W, 3), np.uint8); a[:] = np.random.default_rng(4).integers(0, 256, (1, W, 3), dtype=np.uint8)
        self.plate(a)
        f = self.render('local_gaussian_blur', {'blurriness': 30, 'dimensions': 'vertical'})[0]
        self.assertEqual(np.abs(f - a).max(), 0)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_gaussian_spreads_by_sigma_and_repeat_edge_pixels_keeps_the_border(self):
        # a vertical white line: the blurred profile's spread is sigma = blurriness / 2 (at 1080; here x 108 / 1080)
        a = np.zeros((H, W, 3), np.uint8); a[:, 96] = 255
        self.plate(a)
        for dims in ('both', 'horizontal'):
            f = self.render('local_gaussian_blur', {'blurriness': 400, 'dimensions': dims})[0][54, :, 1].astype(float)
            x = np.arange(W); m = (f * x).sum() / f.sum(); sd = np.sqrt((f * (x - m) ** 2).sum() / f.sum())
            self.assertLess(abs(m - 96), .6, msg=dims); self.assertLess(abs(sd - 20) / 20, .12, msg=f'{dims} {sd}')
            self.assertLess(abs(f.sum() - 255) / 255, .12, msg=dims)   # energy kept
        # a flat plate stays flat to the edges with repeat_edge_pixels, darkens at them without
        self.plate(np.full((H, W, 3), 200, np.uint8))
        for dims in ('both', 'horizontal', 'vertical'):
            f = self.render('local_gaussian_blur', {'blurriness': 120, 'dimensions': dims})[0]
            self.assertLess(np.abs(f - 200).max(), 2, msg=dims)
        f = self.render('local_gaussian_blur', {'blurriness': 120, 'repeat_edge_pixels': False})[0]
        self.assertLess(f[0, 0].mean(), 120); self.assertLess(f[54, 0].mean(), 160); self.assertGreater(f[54, 96].mean(), 190)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_directional_and_radial_geometry(self):
        a = np.zeros((H, W, 3), np.uint8); a[54, 96] = 255
        self.plate(a)
        # a dot under a vertical directional blur (direction 0) becomes a vertical streak +-blur_length long
        f = self.render('local_directional_blur', {'blur_length': 200})[0].sum(axis=2)   # 20 px at this size
        ys = np.nonzero(f[:, 96] > 0)[0]
        self.assertLessEqual(abs(ys.min() - 34), 1); self.assertLessEqual(abs(ys.max() - 74), 1)
        self.assertEqual(f[:, :94].sum() + f[:, 99:].sum(), 0)
        # a spin blur around the frame centre moves a dot along its circle, never out from it
        a = np.zeros((H, W, 3), np.uint8); a[54, 136:140] = 255   # 40 px right of the centre
        self.plate(a)
        f = self.render('local_radial_blur', {'amount': 40, 'quality': 'high'})[0].sum(axis=2).astype(float)
        yy, xx = np.nonzero(f > 3)
        r = np.hypot(xx + .5 - 96, yy + .5 - 54)
        self.assertGreater(yy.max() - yy.min(), 20)              # spread along the arc
        self.assertGreater(r.min(), 37); self.assertLess(r.max(), 46)   # but on its radius (the dot spans 40..44)
        # zoom streaks it outward (away from the centre), not around
        f = self.render('local_radial_blur', {'amount': 60, 'type': 'zoom', 'quality': 'high'})[0].sum(axis=2)
        xs = np.nonzero(f[54] > 3)[0]
        self.assertGreater(xs.max(), 145); self.assertGreaterEqual(xs.min(), 134)
        self.assertEqual(f[:50].sum() + f[59:].sum(), 0)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_unsharp_increases_edge_contrast(self):
        a = np.zeros((H, W, 3), np.uint8); a[:] = 80; a[:, 96:] = 170
        self.plate(a)
        f = self.render('local_unsharp_mask', {'amount': 100, 'radius': 30})[0]
        self.assertLess(f[54, 94].mean(), 75); self.assertGreater(f[54, 97].mean(), 175)   # overshoot both sides
        self.assertEqual(np.abs(f[:, :60] - 80).max(), 0); self.assertEqual(np.abs(f[:, 140:] - 170).max(), 0)   # flat parts kept
        # threshold above the edge's local difference: nothing sharpened
        f = self.render('local_unsharp_mask', {'amount': 100, 'radius': 30, 'threshold': 100})[0]
        self.assertEqual(np.abs(f - a).max(), 0)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_tilt_shift_keeps_the_band_sharp(self):
        a = self.images['N']
        f = self.render('local_tilt_shift', {'center': .5, 'band': .3, 'feather': .2, 'blur_radius': 300})[0]
        band = slice(int(54 - .15 * H) + 1, int(54 + .15 * H) - 1)
        self.assertEqual(np.abs(f[band] - a[band]).max(), 0)
        self.assertLess(f[:10].std(axis=1).mean(), a[:10].std(axis=1).mean() / 3)     # top blurred
        self.assertLess(f[-10:].std(axis=1).mean(), a[-10:].std(axis=1).mean() / 3)   # bottom blurred
        # a tilted band through a point: the sharp pixel set follows the angle
        f = self.render('local_tilt_shift', {'center': [.5, .5], 'angle': 90, 'band': .2, 'blur_radius': 300})[0]
        self.assertEqual(np.abs(f[:, 90:102] - a[:, 90:102]).max(), 0)
        self.assertGreater(np.abs(f[:, :40] - a[:, :40]).mean(), 20)
        # saturation boost, no blur: greys stay grey, colours move away from grey
        g = np.zeros((H, W, 3), np.uint8); g[:, :96] = 128; g[:, 96:] = (180, 120, 100)
        self.plate(g)
        f = self.render('local_tilt_shift', {'blur_radius': 0, 'saturation': 1.5})[0]
        self.assertEqual(np.abs(f[:, :90] - 128).max(), 0)
        self.assertGreater(f[54, 150, 0] - f[54, 150, 2], 80 + 20)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_channel_blur_blurs_only_its_channel(self):
        a = self.images['N']
        f = self.render('local_channel_blur', {'green_blurriness': 100})[0]
        self.assertEqual(np.abs(f[..., [0, 2]] - a[..., [0, 2]]).max(), 0)
        self.assertLess(f[..., 1].std(), a[..., 1].std() / 3)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_lens_blur_makes_shaped_bokeh_and_follows_its_map(self):
        a = np.zeros((H, W, 3), np.uint8); a[53:55, 95:97] = 255
        self.plate(a)
        def disc(fx):
            f = self.render('local_camera_lens_blur', {'blur_radius': 200, 'highlight_gain': 100, 'highlight_threshold': 200, **fx})[0]
            return f.mean(axis=2) > 20
        sq = disc({'iris_shape': 'square', 'iris_rotation': 45})   # a corner up, rotated 45: an axis-aligned square
        ys, xs = np.nonzero(sq)
        self.assertLess(abs(xs.max() - xs.min() - (ys.max() - ys.min())), 3)
        self.assertGreater(xs.max() - xs.min(), 20); self.assertLess(xs.max() - xs.min(), 34)   # radius 20 px: a square 28 px wide
        self.assertGreater(sq[ys.min() + 1, xs.min() + 1:xs.max()].mean(), .9)   # flat-topped
        tri = disc({'iris_shape': 'triangle'})   # a corner points up: narrow top, wide bottom
        ys, xs = np.nonzero(tri)
        top, bottom = tri[ys.min() + 2].sum(), tri[ys.max() - 2].sum()
        self.assertGreater(bottom, 3 * top)
        circ = disc({'iris_shape': 'square', 'iris_roundness': 100})   # roundness 100: a circle
        ys, xs = np.nonzero(circ)
        self.assertLess(circ[ys.min() + 1].sum(), (xs.max() - xs.min()) / 2)
        # a horizontal map: sharp on the left, blurred on the right
        noise = self.images['M'].copy(); noise[:] = np.random.default_rng(5).integers(0, 256, (H, W, 3), dtype=np.uint8)
        self.plate(noise)
        f = self.render('local_camera_lens_blur', {'blur_radius': 100, 'map': 'horizontal'})[0]
        self.assertEqual(np.abs(f[:, :1] - noise[:, :1]).max(), 0)
        self.assertLess(np.abs(f[:, :8] - noise[:, :8]).mean(), 8)
        self.assertLess(f[:, -40:].std(), noise[:, -40:].std() / 2.5)
        # the clip map M is the same ramp: the same result; inverted with focal distance 255 too
        g = self.render('local_camera_lens_blur', {'blur_radius': 100, 'clip': 'M'})[0]
        self.assertLess(np.abs(g - f).mean(), 1.5)
        g = self.render('local_camera_lens_blur', {'blur_radius': 100, 'map': 'horizontal', 'invert': True, 'focal_distance': 255})[0]
        self.assertLess(np.abs(g - f).mean(), 1.5)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_region_confines_the_blur(self):
        a = self.images['N']
        f = self.render('local_gaussian_blur', {'blurriness': 100, 'region': [.25, .25, .75, .75], 'feather': 0})[0]
        self.assertEqual(np.abs(f[:20] - a[:20]).max(), 0); self.assertEqual(np.abs(f[:, :40] - a[:, :40]).max(), 0)
        self.assertLess(f[35:70, 55:135].std(), a[35:70, 55:135].std() / 3)


if __name__ == '__main__':
    unittest.main()
