"""The Stylize effect pack (web/fx_stylize.js): an RGB split and After Effects' Motion Tile, Find Edges, Emboss, Mosaic
and Scatter."""
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


class StylizePackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        rng = np.random.default_rng(11)
        noise = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)                    # every pixel distinct: any move shows
        cols = np.repeat(rng.integers(0, 256, (1, W, 3), dtype=np.uint8), H, 0)   # changes only along x
        rows = np.repeat(rng.integers(0, 256, (H, 1, 3), dtype=np.uint8), W, 1)   # changes only along y
        yy, xx = np.mgrid[0:H, 0:W]
        ramp = np.stack([xx, np.full_like(xx, 100), xx], 2).astype(np.uint8)       # red = blue = x
        flat = np.full((H, W, 3), 120, np.uint8)
        step = flat.copy(); step[:, W // 2:] = 220
        self.images = {'N': noise, 'C': cols, 'R': rows, 'X': ramp, 'F': flat, 'S': step}
        for name, a in self.images.items():
            (self.root / name).mkdir()
            Image.fromarray(a).save(self.root / name / '00000.png')

    def edit(self, shots):
        """shots: [(effect, params, clip, frames)] one after another; each starts its own clock."""
        out, f = [], 0
        for name, fx, clip, n in shots:
            out.append({'f0': f, 'f1': f + n, 'clip': clip, 'speed': 0, 'fx': {name: fx}})
            f += n
        return {'canvas': {'w': W, 'h': H, 'fps': 30, 'frames': f, 'bg': '#000000'},
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
            ('local_rgb_split', {'mode': 'radial', 'amount': [[0, 0], [.2, 40, 'out3'], [.6, 0]], 'angle': 30,
                                 'center': [[0, [.4, .5]], [1, [.6, .5]]], 'edges': 'clamp', 'quality': 'high',
                                 'region': [.1, .1, .9, .9], 'feather': .05, 'at': .5}),
            ('local_rgb_split', {'mode': 'linear', 'amount': -12, 'angle': [[0, 0], [1, 360]]}),
            ('local_motion_tile', {'tile_center': [[0, [.5, .5]], [2, [1.5, .5]]], 'tile_width': 33.3, 'tile_height': [[0, 100], [1, 25]],
                                   'output_width': 150, 'output_height': 80, 'mirror_edges': True, 'phase': [[0, 0], [1, 360]],
                                   'horizontal_phase_shift': True}),
            ('local_find_edges', {'invert': True, 'blend_with_original': [[0, 1], [.5, 0]], 'region': [0, 0, .5, 1]}),
            ('local_emboss', {'direction': 135, 'relief': [[0, 1], [1, 6]], 'contrast': 250, 'blend_with_original': .3}),
            ('local_mosaic', {'horizontal_blocks': [[0, 64], [.5, 8, 'in2']], 'vertical_blocks': 6, 'sharp_colors': True}),
            ('local_scatter', {'scatter_amount': [[0, 0], [.3, 60]], 'grain': 'horizontal', 'randomize_every_frame': True, 'seed': 42}),
        ]
        for name, fx in good:
            validate(self.edit([(name, fx, 'N', 1)]), self.root)
            validate(self.edit([(name, {}, 'N', 1)]), self.root)
        bad = [('local_rgb_split', {'mode': 'spiral'}, 'one of linear'), ('local_rgb_split', {'amount': 2000}, 'out of range'),
               ('local_rgb_split', {'center': [.5]}, r'\[x, y\]'), ('local_rgb_split', {'center': [[0, [.2, 1.3]]]}, 'out of range'),
               ('local_rgb_split', {'edges': 'mirror'}, 'one of reflect'), ('local_rgb_split', {'quality': 'best'}, 'one of low'),
               ('local_rgb_split', {'amount': [[0, 1], [0, 2]]}, 'must increase'), ('local_rgb_split', {'grain': 'both'}, 'unsupported fields'),
               ('local_motion_tile', {'tile_width': 0}, 'out of range'), ('local_motion_tile', {'mirror_edges': 1}, 'boolean'),
               ('local_motion_tile', {'horizontal_phase_shift': 'yes'}, 'boolean'), ('local_motion_tile', {'edges': 'wrap'}, 'unsupported fields'),
               ('local_find_edges', {'blend_with_original': 1.5}, 'out of range'), ('local_find_edges', {'invert': 0}, 'boolean'),
               ('local_emboss', {'relief': -1}, 'out of range'), ('local_emboss', {'contrast': 'high'}, 'finite number'),
               ('local_mosaic', {'horizontal_blocks': 0}, 'out of range'), ('local_mosaic', {'sharp_colors': None}, 'boolean'),
               ('local_scatter', {'grain': 'diagonal'}, 'one of both'), ('local_scatter', {'seed': 1.5}, 'integer'),
               ('local_scatter', {'scatter_amount': -3}, 'out of range'), ('local_scatter', {'at': -1}, 'out of range'),
               ('local_mosaic', {'region': [.5, .5, .4, .9]}, 'greater than')]
        for name, fx, error in bad:
            with self.assertRaisesRegex(ContractError, error, msg=f'{name} {fx}'):
                validate(self.edit([(name, fx, 'N', 1)]), self.root)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_identities(self):
        N, C, R = (self.images[k].astype(int) for k in 'NCR')
        shots = [('local_rgb_split', {'amount': 0}, 'N', 1),
                 ('local_rgb_split', {'mode': 'radial', 'amount': [[0, 0], [1, 0], [2, 50]]}, 'N', 1),   # keyframed: 0 for the first second
                 ('local_motion_tile', {}, 'N', 1),
                 ('local_motion_tile', {'mirror_edges': True, 'phase': 90, 'output_width': 120}, 'N', 1),
                 ('local_find_edges', {'blend_with_original': 1}, 'N', 1),
                 ('local_emboss', {'blend_with_original': 1}, 'N', 1),
                 ('local_mosaic', {'horizontal_blocks': W, 'vertical_blocks': H}, 'N', 1),
                 ('local_scatter', {'scatter_amount': 0}, 'N', 1),
                 ('local_scatter', {'scatter_amount': 300, 'grain': 'vertical'}, 'C', 1),      # a vertical scatter of columns
                 ('local_scatter', {'scatter_amount': 300, 'grain': 'horizontal'}, 'R', 1),    # a horizontal scatter of rows
                 ('local_rgb_split', {'amount': 50, 'at': 5}, 'N', 1)]                          # before `at`
        f = self.render(shots)
        for i, ref in enumerate([N] * 8 + [C, R, N]):
            self.assertEqual(np.abs(f[i] - ref).max(), 0, msg=shots[i])

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_rgb_split_geometry(self):
        X, N = self.images['X'].astype(int), self.images['N'].astype(int)
        f = self.render([('local_rgb_split', {'amount': 100}, 'X', 1),                 # 10 px at 108
                         ('local_rgb_split', {'amount': 100, 'angle': 180}, 'X', 1),
                         ('local_rgb_split', {'amount': 100, 'angle': 90}, 'N', 1),
                         ('local_rgb_split', {'mode': 'radial', 'amount': 200}, 'X', 1),
                         ('local_rgb_split', {'amount': 100, 'region': [.25, .25, .75, .75], 'feather': 0}, 'N', 1)])
        inner = slice(10, W - 10)
        xs = np.arange(W)[inner]
        self.assertEqual(np.abs(f[0][:, inner, 0] - (xs - 10)).max(), 0)          # red moves right by exactly 10 px
        self.assertEqual(np.abs(f[0][:, inner, 2] - (xs + 10)).max(), 0)          # blue left by 10 px
        self.assertEqual(np.abs(f[0][..., 1] - X[..., 1]).max(), 0)               # green stays
        self.assertEqual(np.abs(f[1][:, inner, 0] - (xs + 10)).max(), 0)          # 180: the other way round
        self.assertEqual(np.abs(f[1][:, inner, 2] - (xs - 10)).max(), 0)
        self.assertEqual(np.abs(f[2][10:, :, 0] - N[:-10, :, 0]).max(), 0)        # 90: red down, blue up
        self.assertEqual(np.abs(f[2][:-10, :, 2] - N[10:, :, 2]).max(), 0)
        self.assertEqual(np.abs(f[2][..., 1] - N[..., 1]).max(), 0)
        cx = W // 2                                                                # radial: none at the centre, outward with distance
        self.assertLessEqual(abs(f[3][H // 2, cx, 0] - X[H // 2, cx, 0]), 1)
        self.assertLess(f[3][H // 2, W - 20, 0], X[H // 2, W - 20, 0] - 5)        # right side: red comes from nearer the centre
        self.assertGreater(f[3][H // 2, 20, 0], X[H // 2, 20, 0] + 5)
        self.assertGreater(f[3][H // 2, W - 20, 2], X[H // 2, W - 20, 2] + 5)
        outside = np.ones((H, W), bool); outside[int(H * .25) - 1:int(H * .75) + 2, int(W * .25) - 1:int(W * .75) + 2] = False
        self.assertEqual(np.abs(f[4] - N)[outside].max(), 0)                      # region: nothing outside it
        self.assertGreater((np.abs(f[4] - N).sum(2) > 30).mean(), .1)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_tiles_blocks_edges(self):
        N, F, S = (self.images[k].astype(int) for k in 'NFS')
        f = self.render([('local_motion_tile', {'tile_width': 50, 'tile_height': 50}, 'N', 1),
                         ('local_motion_tile', {'tile_width': 50, 'tile_height': 50, 'mirror_edges': True}, 'N', 1),
                         ('local_motion_tile', {'tile_width': 50, 'tile_height': 50, 'phase': 180}, 'N', 1),
                         ('local_mosaic', {'horizontal_blocks': 10, 'vertical_blocks': 6}, 'N', 1),
                         ('local_mosaic', {'horizontal_blocks': 7, 'vertical_blocks': 5, 'sharp_colors': True}, 'N', 1),
                         ('local_find_edges', {}, 'F', 1),
                         ('local_find_edges', {'invert': True}, 'F', 1),
                         ('local_find_edges', {}, 'S', 1),
                         ('local_emboss', {}, 'F', 1),
                         ('local_emboss', {'relief': 20, 'direction': 270}, 'S', 1),
                         ('local_scatter', {'scatter_amount': 50, 'seed': 3}, 'N', 2),
                         ('local_scatter', {'scatter_amount': 50, 'seed': 3, 'randomize_every_frame': True}, 'N', 2)])
        tile = f[0]                                                    # tiles 96 x 54 from (48, 27): periodic
        self.assertEqual(np.abs(tile[:, :W - 96] - tile[:, 96:]).max(), 0)
        self.assertEqual(np.abs(tile[:H - 54] - tile[54:]).max(), 0)
        small = np.asarray(Image.fromarray(self.images['N']).resize((96, 54), Image.BILINEAR)).astype(int)
        self.assertLess(np.abs(tile[27:81, 48:144] - small).mean(), 40)   # the whole frame, shrunk (noise: loose)
        m = f[1]                                                       # mirrored: the tile right of the centre one is flipped
        self.assertEqual(np.abs(m[27:81, 144:] - m[27:81, 96:144][:, ::-1]).max(), 0)
        self.assertEqual(np.abs(m[:27] - m[27:54][::-1]).max(), 0)
        self.assertEqual(np.abs(m[27:81, 48:144] - tile[27:81, 48:144]).max(), 0)
        ph = f[2]                                                      # phase 180: the column right of centre moves down 27 px
        self.assertEqual(np.abs(ph[:, 48:144] - tile[:, 48:144]).max(), 0)
        self.assertEqual(np.abs(ph[27:, 144:] - tile[:-27, 144:]).max(), 0)
        for k, (nx, ny) in ((3, (10, 6)), (4, (7, 5))):                # mosaic: every block one colour
            for j in range(ny):
                for i in range(nx):
                    b = f[k][j * H // ny:(j + 1) * H // ny, i * W // nx:(i + 1) * W // nx]
                    self.assertEqual(np.abs(b - b[0, 0]).max(), 0, msg=(k, i, j))
        b = N[0:H // 6, 0:W // 10].reshape(-1, 3).mean(0)
        self.assertLessEqual(np.abs(f[3][0, 0] - b).max(), 1)          # the block's average
        x0, x1, y0, y1 = 2 * W // 7, 3 * W // 7, H // 5, 2 * H // 5
        self.assertEqual(np.abs(f[4][y0, x0] - N[(y0 + y1 - 1) // 2, (x0 + x1 - 1) // 2]).max(), 0)   # sharp: the centre pixel
        self.assertEqual(f[5].min(), 255)                              # find edges: white where flat
        self.assertEqual(f[6].max(), 0)                                # inverted: black
        self.assertLess(f[7][:, W // 2 - 1:W // 2 + 1].max(), 160)     # a dark line along the step
        self.assertEqual(f[7][:, :W // 2 - 2].min(), 255)
        self.assertEqual(np.abs(f[8] - 128).max(), 0)                  # emboss: mid grey where flat
        e = f[9]                                                       # lit from the left: the step up faces it
        self.assertGreater(e[H // 2, W // 2 - 1, 0], 160)
        self.assertEqual(np.abs(e[:, :W // 2 - 4] - 128).max(), 0)
        sc = f[10:14]                                                  # scatter: pixels come from within 5 px
        for frame in sc:
            self.assertGreater((np.abs(frame - N).sum(2) > 0).mean(), .8)
        self.assertEqual(np.abs(sc[0] - sc[1]).max(), 0)               # a fixed pattern
        self.assertGreater(np.abs(sc[2] - sc[3]).max(), 0)             # or boiling
        hist = lambda a: np.sort(a.reshape(-1, 3), axis=0)
        self.assertLess(np.abs(hist(sc[0]).mean(0) - hist(N).mean(0)).max(), 6)


if __name__ == '__main__':
    unittest.main()
