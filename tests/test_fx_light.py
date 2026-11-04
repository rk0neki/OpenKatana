"""The light effect pack (web/fx_light.js): local_deep_glow, local_lens_flare, local_light_rays and local_light_sweep."""
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


class LightPackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        (self.root / 'f').mkdir()
        self.plate(np.full((H, W, 3), 40, np.uint8))

    def plate(self, a):
        self.source = a
        Image.fromarray(a).save(self.root / 'f' / '00000.png')

    def edit(self, name, fx, frames=1, where='fx'):
        shot = {'f0': 0, 'f1': frames, 'clip': 'A', 'speed': 0}
        if where == 'fx':
            shot['fx'] = {name: fx}
        elif where == 'layer':
            shot['layers'] = [{'type': name, **fx}]
        e = {'canvas': {'w': W, 'h': H, 'fps': 30, 'frames': frames},
             'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': W, 'h': H}}, 'shots': [shot]}
        if where == 'post':
            e['post'] = {name: fx}
        return e

    def render(self, name, fx, frames=1):
        from openkatana.render import render
        (self.root / 't.json').write_text(json.dumps(self.edit(name, fx, frames)))
        out = self.root / 'o'
        shutil.rmtree(out, ignore_errors=True)
        render(self.root / 't.json', out)
        return [np.asarray(Image.open(out / 'frames' / f'{i:05d}.png').convert('RGB')).astype(int) for i in range(frames)]

    def test_validation(self):
        ok = [('local_deep_glow', {'threshold': [[0, .8], [1, .5, 'ease']], 'radius': [[0, 40], [2, 200]], 'exposure': 1.5,
                                   'layers': 8, 'tint': '#ffaa66', 'saturation': .5, 'blend': 'screen', 'at': .5}),
              ('local_deep_glow', {'tint': 'none'}),
              ('local_lens_flare', {'position': [[0, [.1, .2]], [2, [.9, .4], 'inout']], 'brightness': [[0, 0], [.5, 1.4]],
                                    'lens': '105mm_prime', 'tint': '#88ccff', 'streak': .6, 'flicker': .3, 'seed': 7}),
              ('local_lens_flare', {'position': [1.2, -.3], 'lens': '35mm_prime'}),
              ('local_light_rays', {'center': [[0, [.5, .3]], [1, [.6, .3]]], 'intensity': [[0, 0], [1, 3]], 'length': .7,
                                    'threshold': .4, 'tint': '#ffe0a0', 'blend': 'add'}),
              ('local_light_sweep', {'angle': -20, 'width': 120, 'softness': .8, 'intensity': 2, 'color': '#fff2cc', 'd': 1.5,
                                     'ease': [.42, 0, .58, 1], 'reception': 'luma', 'at': 1}),
              ('local_light_sweep', {'position': [[0, -.2], [1, 1.2, 'ease']]})]
        for name, fx in ok:
            validate(self.edit(name, fx), self.root)
        validate(self.edit('local_deep_glow', {}, where='post'), self.root)
        validate(self.edit('local_light_sweep', {'d': 2}, where='layer'), self.root)
        bad = [('local_deep_glow', {'threshold': 1.5}, 'out of range'), ('local_deep_glow', {'layers': 9}, 'out of range'),
               ('local_deep_glow', {'layers': 3.5}, 'integer'), ('local_deep_glow', {'blend': 'multiply'}, 'one of add'),
               ('local_deep_glow', {'tint': 'red'}, 'rrggbb'), ('local_deep_glow', {'radius': [[0, 10], [0, 20]]}, 'must increase'),
               ('local_deep_glow', {'strength': 1}, 'unsupported fields: strength'),
               ('local_lens_flare', {'lens': '85mm'}, 'one of 50_300mm_zoom'), ('local_lens_flare', {'brightness': 4}, 'out of range'),
               ('local_lens_flare', {'position': .5}, r'\[x, y\]'), ('local_lens_flare', {'position': [3, 0]}, 'out of range'),
               ('local_lens_flare', {'flicker': 2}, 'out of range'),
               ('local_light_rays', {'length': 2}, 'out of range'), ('local_light_rays', {'center': [[0, .5], [1, .6]]}, r'\[x, y\]'),
               ('local_light_sweep', {'reception': 'cutout'}, 'one of add'), ('local_light_sweep', {'ease': 'bounce'}, 'one of lin'),
               ('local_light_sweep', {'color': 'none'}, 'rrggbb'), ('local_light_sweep', {'intensity': float('nan')}, ''),
               ('local_light_sweep', {'ease': 'hold'}, 'hold is for keyframes'),
               ('local_deep_glow', {'tint': [255, 0, 0, .5]}, 'opaque')]
        for name, fx, error in bad:
            with self.assertRaisesRegex(ContractError, error, msg=f'{name} {fx}'):
                validate(self.edit(name, fx), self.root)
        # tint takes every colour syntax the error message offers, canonicalised to "#rrggbb" for the renderer
        for name, tint in (('local_deep_glow', 'rgb(255,0,0)'), ('local_lens_flare', [255, 0, 0]), ('local_light_rays', '#FF0000')):
            out = validate(self.edit(name, {'tint': tint}), self.root)
            self.assertEqual(out['shots'][0]['fx'][name]['tint'], '#ff0000', msg=name)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_below_threshold_and_zero_amounts_untouched(self):
        a = np.zeros((H, W, 3), np.uint8); a[:] = (30, 40, 50); a[::6, :] = (120, 110, 100); a[:, ::9] = (90, 130, 70)
        self.plate(a)   # brightest luma about .5
        for name, fx in (('local_deep_glow', {'threshold': .6}), ('local_light_rays', {'threshold': .6, 'length': .8}),
                         ('local_lens_flare', {'brightness': 0}), ('local_light_sweep', {'intensity': 0}),
                         ('local_deep_glow', {'exposure': 0, 'threshold': 0}), ('local_light_sweep', {'at': 5})):
            f = self.render(name, fx)
            self.assertEqual(np.abs(f[0] - a).max(), 0, msg=f'{name} {fx}')

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_glow_spreads_from_a_bright_dot(self):
        a = np.zeros((H, W, 3), np.uint8); a[46:62, 88:104] = 255
        self.plate(a)
        f = self.render('local_deep_glow', {'radius': 600, 'threshold': .5})[0]
        lum = f.mean(axis=2)
        self.assertGreater(lum[54, 108], 20)    # 4 px off the dot: lit
        self.assertGreater(lum[54, 108], lum[54, 130])    # falling off with distance
        self.assertGreater(lum[54, 130], 1)     # a wide tail (the plate is 0 there)
        self.assertLess(lum[5, 5], 4)           # but not the whole frame
        # tint: the glow takes the colour
        g = self.render('local_deep_glow', {'radius': 600, 'threshold': .5, 'tint': '#ff4000'})[0]
        self.assertGreater(g[54, 108, 0], g[54, 108, 2] + 10)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_glow_defaults_do_not_wash_out_bright_plates(self):
        # a flat area above the threshold gets its thresholded self added about once (exposure 1 = 1x, a standard
        # glow at intensity 1): luma .78 with threshold .6 -> ((.78 - .6) / .4) ** 2 = .21 of 200 added
        self.plate(np.full((H, W, 3), 200, np.uint8))
        f = self.render('local_deep_glow', {})[0]
        self.assertLess(abs(f[54, 96].mean() - 242), 6)
        # a daylight sky: brightened, not clipped to white
        y = np.linspace(0, 1, H)[:, None, None]
        self.plate(((np.array([110, 160, 220]) * (1 - y) + np.array([200, 215, 235]) * y) * np.ones((H, W, 1))).round().astype(np.uint8))
        f = self.render('local_deep_glow', {})[0]
        self.assertLess(f[60, 96, :2].max(), 230)
        self.assertGreater(f[60, 96].sum(), self.source[60, 96].astype(int).sum())
        self.assertLess((f == 255).all(axis=2).mean(), .1)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_thin_sweep_band_still_lands(self):
        # a band under 2 px wide is drawn 3 px wide with its energy kept (it used to vanish between pixel centres)
        e = {}
        for width in (10, 20, 40):
            f = self.render('local_light_sweep', {'angle': 0, 'width': width, 'position': .5, 'softness': .5})[0]
            e[width] = (f - self.source).sum()
        self.assertGreater(e[10], 0)
        self.assertLess(abs(e[10] / e[40] - .25), .08)
        self.assertLess(abs(e[20] / e[40] - .5), .1)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_flare_core_sits_at_its_position(self):
        a = np.zeros((H, W, 3), np.uint8)
        self.plate(a)
        for lens in ('50_300mm_zoom', '35mm_prime', '105mm_prime'):
            f = self.render('local_lens_flare', {'position': [.25, .3], 'lens': lens})[0]
            lum = f.sum(axis=2)
            y, x = np.unravel_index(np.argmax(lum), lum.shape)
            self.assertLess(abs(x - .25 * W), 3, msg=lens); self.assertLess(abs(y - .3 * H), 3, msg=lens)
            self.assertGreater(lum.mean(), 3, msg=lens)   # ghosts and glow beyond the core
        # moving the light moves the core; streak brightens the row through it far to the side
        f = self.render('local_lens_flare', {'position': [.7, .6], 'streak': 1})[0]
        lum = f.sum(axis=2)
        y, x = np.unravel_index(np.argmax(lum), lum.shape)
        self.assertLess(abs(x - .7 * W), 3); self.assertLess(abs(y - .6 * H), 3)
        self.assertGreater(lum[int(.6 * H), 10], lum[int(.6 * H) - 20, 10] + 20)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_rays_streak_away_from_the_centre(self):
        a = np.zeros((H, W, 3), np.uint8); a[50:58, 130:138] = 255     # a bright patch right of the centre
        self.plate(a)
        f = self.render('local_light_rays', {'center': [.5, .5], 'length': .6, 'intensity': 2})[0].mean(axis=2)
        self.assertGreater(f[54, 160], 15)            # outward of the patch: a ray
        self.assertLess(f[54, 110], 3)                # inward of it: nothing
        self.assertLess(f[20, 160], 3)                # off the ray's line: nothing

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_sweep_band_is_where_its_position_says(self):
        for pos in (.25, .5, .75):
            f = self.render('local_light_sweep', {'angle': 0, 'position': pos, 'width': 100, 'softness': .2})[0]
            col = (f - self.source).sum(axis=(0, 2)).astype(float)
            x = (col * np.arange(W)).sum() / col.sum()      # the band's centroid
            self.assertLess(abs(x - pos * W + .5), 1.5, msg=pos)
            self.assertEqual(col[int(pos * W) - 40 if pos < .5 else int(pos * W) + 40], 0)
        # animated: crosses left to right over d seconds, gone after
        f = self.render('local_light_sweep', {'angle': 0, 'd': 2 / 30, 'width': 60, 'ease': 'lin'}, frames=3)
        xs = [np.argmax((g - self.source).sum(axis=(0, 2))) for g in f[:2]]   # leading edge
        self.assertLess(xs[0], xs[1])
        self.assertEqual(np.abs(f[2] - self.source).max(), 0)
        # luma reception: no shine on black, shine on white
        a = np.zeros((H, W, 3), np.uint8); a[:, 96:] = 255; a[:, 96:, 2] = 0
        self.plate(a)
        f = self.render('local_light_sweep', {'angle': 0, 'position': .5, 'width': 120, 'reception': 'luma', 'color': '#0000ff'})[0]
        self.assertEqual(np.abs(f[:, :90] - a[:, :90]).max(), 0)
        self.assertGreater(f[54, 100, 2], 100)


if __name__ == '__main__':
    unittest.main()
