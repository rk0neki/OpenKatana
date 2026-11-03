"""The Generate effect pack (web/fx_generate.js): local_fractal_noise, local_cell_pattern, local_gradient_ramp,
local_four_color_gradient, local_grid, local_radio_waves and local_lightning."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from openkatana.contracts import ContractError, validate

W, H = 192, 108
NAMES = ('local_fractal_noise', 'local_cell_pattern', 'local_gradient_ramp', 'local_four_color_gradient', 'local_grid',
         'local_radio_waves', 'local_lightning')


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path()) and bool(shutil.which('ffmpeg'))
    except Exception:
        return False


class GeneratePackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        (self.root / 'f').mkdir()
        a = np.zeros((H, W, 3), np.uint8); a[:] = (40, 60, 80); a[::7, :] = (150, 120, 90); a[:, ::11] = (90, 170, 60)
        self.plate(a)

    def plate(self, a):
        self.source = a.astype(int)
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
        ok = [('local_fractal_noise', {'fractal_type': 'turbulent_sharp', 'noise_type': 'spline', 'invert': True,
                                       'contrast': [[0, 100], [1, 300, 'ease']], 'brightness': -20, 'overflow': 'wrap',
                                       'rotation': 45, 'scale': [[0, 100], [2, 400]], 'offset': [[0, [0, 0]], [1, [200, -50]]],
                                       'complexity': 4.5, 'sub_influence': 60, 'sub_scaling': 50, 'sub_rotation': 30,
                                       'evolution': [[0, 0], [2, 3]], 'speed': .5, 'cycle': 3, 'seed': 9, 'tint': '#ff8800',
                                       'blend': 'screen', 'opacity': [[0, 0], [1, .6]], 'at': .5}),
              ('local_fractal_noise', {'tint': 'none', 'offset': [10, 20]}),
              ('local_cell_pattern', {'cell_pattern': 'tubular', 'invert': False, 'contrast': 150, 'overflow': 'soft_clamp',
                                      'disperse': .5, 'size': [[0, 40], [1, 80]], 'offset': [5, 5], 'evolution': 1,
                                      'speed': .25, 'seed': 3, 'blend': 'add', 'opacity': .5}),
              ('local_gradient_ramp', {'start': [[0, [0, .5]], [1, [.2, .5]]], 'start_color': 'rgb(10,20,30)',
                                       'end': [1, .5], 'end_color': '#ffffff', 'shape': 'radial', 'ramp_scatter': .3,
                                       'blend': 'overlay'}),
              ('local_four_color_gradient', {'point_1': [.2, .2], 'color_1': [255, 0, 0], 'point_4': [[0, [.9, .9]], [1, [.5, .5]]],
                                             'color_4': '#00ffff', 'blend_amount': 300, 'jitter': .2, 'blend': 'soft_light'}),
              ('local_grid', {'anchor': [.25, .25], 'width': 80, 'height': 40, 'border': [[0, 1], [1, 6]], 'feather': 4,
                              'invert': True, 'color': '#00ff00', 'blend': 'multiply'}),
              ('local_radio_waves', {'producer': [[0, [.2, .5]], [2, [.8, .5]]], 'frequency': 4, 'expansion': 600,
                                     'lifespan': 2, 'shape': 'polygon', 'sides': 6, 'stroke_color': '#40e0ff',
                                     'start_width': 12, 'end_width': 1, 'fade_in': .1, 'fade_out': .5, 'blend': 'add'}),
              ('local_lightning', {'origin': [.5, -.2], 'direction': [[0, [.5, .9]], [1, [.2, .9]]],
                                   'lightning_type': 'breaking', 'conductivity': [[0, 0], [1, 4]], 'core_radius': 2,
                                   'core_color': '#ffffff', 'glow_radius': 80, 'glow_opacity': .7, 'glow_color': '#8040ff',
                                   'forking': .5, 'decay': .4, 'turbulence': 2, 'seed': 4, 'flicker': 3, 'blend': 'normal'})]
        for name, fx in ok:
            validate(self.edit(name, fx), self.root)
        validate(self.edit('local_fractal_noise', {}, where='post'), self.root)
        validate(self.edit('local_lightning', {}, where='layer'), self.root)
        bad = [('local_fractal_noise', {'fractal_type': 'dynamic'}, 'one of basic'),
               ('local_fractal_noise', {'noise_type': 'cubic'}, 'one of block'),
               ('local_fractal_noise', {'overflow': 'hdr'}, 'one of clip'),
               ('local_fractal_noise', {'complexity': 30}, 'out of range'),
               ('local_fractal_noise', {'cycle': 0}, 'out of range'),
               ('local_fractal_noise', {'invert': 1}, 'boolean'),
               ('local_fractal_noise', {'tint': 'orange'}, 'rrggbb'),
               ('local_fractal_noise', {'blend': 'plus'}, 'one of normal'),
               ('local_fractal_noise', {'opacity': 2}, 'out of range'),
               ('local_fractal_noise', {'scale': [[0, 10], [0, 20]]}, 'must increase'),
               ('local_fractal_noise', {'detail': 1}, 'unsupported fields: detail'),
               ('local_cell_pattern', {'cell_pattern': 'pillow'}, 'one of bubbles'),
               ('local_gradient_ramp', {'shape': 'circle'}, 'one of linear'),
               ('local_gradient_ramp', {'start': .5}, r'\[x, y\]'),
               ('local_gradient_ramp', {'end': [3, 0]}, 'out of range'),
               ('local_gradient_ramp', {'start_color': [255, 0, 0, .5]}, 'opaque'),
               ('local_four_color_gradient', {'blend_amount': 0}, 'out of range'),
               ('local_grid', {'width': 0}, 'out of range'),
               ('local_radio_waves', {'shape': 'radial'}, 'one of circle'),
               ('local_radio_waves', {'sides': 2}, 'out of range'), ('local_radio_waves', {'sides': 4.5}, 'integer'),
               ('local_radio_waves', {'frequency': 0}, 'out of range'),
               ('local_lightning', {'lightning_type': 'vertical'}, 'one of strike'),
               ('local_lightning', {'forking': 1.5}, 'out of range'), ('local_lightning', {'flicker': 1.5}, 'integer'),
               ('local_lightning', {'origin': [[0, .5], [1, .6]]}, r'\[x, y\]')]
        for name, fx, error in bad:
            with self.assertRaisesRegex(ContractError, error, msg=f'{name} {fx}'):
                validate(self.edit(name, fx), self.root)
        # colours take every colour syntax, canonicalised to "#rrggbb" for the renderer
        for name, key, value in (('local_fractal_noise', 'tint', 'rgb(255,0,0)'), ('local_lightning', 'glow_color', [255, 0, 0]),
                                 ('local_gradient_ramp', 'end_color', '#FF0000'), ('local_grid', 'color', [255, 0, 0])):
            out = validate(self.edit(name, {key: value}), self.root)
            self.assertEqual(out['shots'][0]['fx'][name][key], '#ff0000', msg=name)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_zero_opacity_and_before_at_untouched(self):
        for name in NAMES:
            for fx in ({'opacity': 0}, {'at': 5}):
                f = self.render(name, fx)
                self.assertEqual(np.abs(f[0] - self.source).max(), 0, msg=f'{name} {fx}')

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_fractal_noise_deterministic_and_cycle_loops(self):
        a = self.render('local_fractal_noise', {'seed': 3})[0]
        b = self.render('local_fractal_noise', {'seed': 3})[0]
        c = self.render('local_fractal_noise', {'seed': 4})[0]
        self.assertEqual(np.abs(a - b).max(), 0)
        self.assertGreater(np.abs(a - c).mean(), 10)
        self.assertGreater(a.std(), 20)                              # a texture, not a flat grey
        self.assertLess(abs(a.mean() - 128), 30)                     # basic noise sits round mid grey
        self.assertEqual(np.abs(a[..., 0] - a[..., 2]).max(), 0)     # grey without a tint
        for noise in ('soft_linear', 'spline', 'block'):
            # cycle 1 at 15 revolutions a second: frame 2 (z = 1) is frame 0 again; frame 1 differs
            f = self.render('local_fractal_noise', {'noise_type': noise, 'cycle': 1, 'speed': 15, 'fractal_type': 'turbulent_sharp'}, frames=3)
            self.assertLessEqual(np.abs(f[2] - f[0]).max(), 1, msg=noise)
            self.assertGreater(np.abs(f[1] - f[0]).mean(), 5, msg=noise)
        # tint: black to the colour; screen over the picture only brightens it
        t = self.render('local_fractal_noise', {'tint': '#ff0000', 'seed': 3})[0]
        self.assertEqual(t[..., 1:].max(), 0)
        self.assertLessEqual(np.abs(t[..., 0] - a[..., 0]).max(), 1)
        s = self.render('local_fractal_noise', {'blend': 'screen', 'seed': 3})[0]
        self.assertTrue((s >= self.source - 1).all())

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_cell_pattern_loops_every_revolution(self):
        f = self.render('local_cell_pattern', {'speed': 15, 'cell_pattern': 'crystals'}, frames=3)
        self.assertLessEqual(np.abs(f[2] - f[0]).max(), 1)
        self.assertGreater(np.abs(f[1] - f[0]).mean(), 2)
        p = self.render('local_cell_pattern', {'cell_pattern': 'plates', 'disperse': 0, 'size': 270})[0][..., 0]
        # disperse 0: square cells of 27 px, one flat grey each (cells meet on the grid round the frame centre)
        self.assertEqual(np.ptp(p[60:78, 100:118]), 0)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_gradient_ramp_ends(self):
        f = self.render('local_gradient_ramp', {'start': [0, .5], 'start_color': '#ff2000', 'end': [1, .5], 'end_color': '#0040ff'})[0]
        self.assertLessEqual(np.abs(f[54, 0] - [255, 32, 0]).max(), 3)
        self.assertLessEqual(np.abs(f[54, W - 1] - [0, 64, 255]).max(), 3)
        self.assertLessEqual(np.abs(f[54, 96] - [128, 48, 128]).max(), 4)
        self.assertLessEqual(np.ptp(f[:, 40], axis=0).max(), 1)         # linear: constant across the ramp (Chrome dithers by 1)
        r = self.render('local_gradient_ramp', {'shape': 'radial', 'start': [.5, .5], 'end': [.5, 1]})[0]
        self.assertLessEqual(r[54, 96].max(), 3)                         # black at the centre
        self.assertGreaterEqual(r[0, 0].min(), 252)                      # white beyond the end distance
        # multiply by white is the identity
        m = self.render('local_gradient_ramp', {'start_color': '#ffffff', 'end_color': '#ffffff', 'blend': 'multiply'})[0]
        self.assertEqual(np.abs(m - self.source).max(), 0)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_four_color_gradient_colours_at_points(self):
        f = self.render('local_four_color_gradient', {'point_1': [.25, .25], 'point_2': [.75, .25], 'point_3': [.25, .75],
                                                      'point_4': [.75, .75], 'blend_amount': 20})[0]
        for (x, y), c in (((.25, .25), (255, 255, 0)), ((.75, .25), (0, 255, 0)), ((.25, .75), (255, 0, 255)), ((.75, .75), (0, 0, 255))):
            self.assertLessEqual(np.abs(f[int(y * H), int(x * W)] - c).max(), 12, msg=c)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_grid_lines_where_the_anchor_says(self):
        self.plate(np.zeros((H, W, 3), np.uint8))
        f = self.render('local_grid', {'width': 270, 'border': 20})[0][..., 0]   # 27 px cells, 2 px lines, through 96, 54
        for x in (96 - 27, 96, 96 + 27):
            self.assertGreater(f[20, x - 1:x + 1].min(), 200, msg=x)
        self.assertEqual(f[20, 96 + 13], 0)
        self.assertGreater(f[54 - 1:54 + 1, 10].min(), 200)
        self.assertEqual(f[54 + 13, 10], 0)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_radio_wave_ring_radius(self):
        self.plate(np.zeros((H, W, 3), np.uint8))
        # born at t 0, 3000 px/s at 1080 = 300 px/s here: frame 3 is sampled at t 3.5 / 30, a ring 35 px round the producer
        f = self.render('local_radio_waves', {'producer': [.5, .5], 'expansion': 3000, 'frequency': .5, 'start_width': 20,
                                              'end_width': 20, 'fade_out': 0}, frames=4)[3][..., 0]
        self.assertGreater(f[54, 96 + 35], 200); self.assertGreater(f[54 - 35, 96], 200); self.assertGreater(f[54, 96 - 35], 200)
        self.assertEqual(f[54, 96], 0); self.assertEqual(f[54, 96 + 45], 0); self.assertEqual(f[54, 96 + 25], 0)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_lightning_runs_from_origin_toward_direction(self):
        self.plate(np.zeros((H, W, 3), np.uint8))
        fx = {'origin': [.15, .5], 'direction': [.85, .5], 'forking': 0, 'glow_radius': 0, 'core_radius': 10, 'turbulence': .5}
        f = self.render('local_lightning', fx)[0].max(axis=2)
        lit = f > 128
        self.assertTrue(lit[44:65, 26:33].any())                         # at the origin
        self.assertTrue(lit[44:65, 160:167].any())                       # at the direction point
        cols = lit[:, 30:163].any(axis=0)
        self.assertTrue(cols.all())                                      # a continuous path between
        self.assertFalse(lit[:, :20].any()); self.assertFalse(lit[:, 175:].any())
        ys = np.nonzero(lit)[0]
        self.assertLess(abs(ys.mean() - 54), 12)
        # deterministic per seed and conductivity; conductivity changes it
        g = self.render('local_lightning', fx)[0].max(axis=2)
        self.assertEqual(np.abs(f - g).max(), 0)
        h = self.render('local_lightning', {**fx, 'conductivity': .5})[0].max(axis=2)
        self.assertGreater(np.abs(f - h).sum(), 0)
        for kind in ('breaking', 'bouncy', 'omni', 'anywhere'):
            k = self.render('local_lightning', {'lightning_type': kind, 'origin': [.5, .5], 'direction': [.8, .5]})[0]
            self.assertGreater(k.max(), 200, msg=kind)


    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_lightning_glow_reaches_its_radius(self):
        # a straight bolt on grey: the default glow (radius 50 at 1080, opacity .5) still shows a blue halo at its
        # radius (5 px here); glow_opacity 0 leaves only the core
        self.plate(np.full((H, W, 3), 128, np.uint8))
        fx = {'origin': [.05, .5], 'direction': [.95, .5], 'forking': 0, 'turbulence': .01}
        f = self.render('local_lightning', fx)[0]
        row = int(np.argmax(f[:, 96, 0])); halo = f[:, 96, 2] - 128
        self.assertGreater(min(halo[row - 5], halo[row + 5]), 7)
        self.assertGreater(min(halo[row - 2], halo[row + 2]), 25)
        g = self.render('local_lightning', {**fx, 'glow_opacity': 0})[0]
        self.assertLessEqual(np.abs(g[:, 96] - 128)[[row - 5, row + 5]].max(), 1)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_fractal_noise_evolves_at_a_steady_pace(self):
        # at a constant speed the texture changes as much from frame to frame near a whole revolution as midway
        # between (value noise once eased in and out every revolution)
        for kind in ('soft_linear', 'block'):
            fr = self.render('local_fractal_noise', {'speed': 2, 'noise_type': kind}, frames=16)
            d = [np.abs(fr[i + 1] - fr[i]).mean() for i in range(15)]
            self.assertLess(max(d) / min(d), 1.25, msg=f'{kind}: {d}')


if __name__ == '__main__':
    unittest.main()
