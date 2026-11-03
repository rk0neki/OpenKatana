"""Timeline overlays (clip plates and adjustment layers) and the non-finite number guard."""
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from openkatana.contracts import ContractError, validate


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path()) and bool(shutil.which('ffmpeg'))
    except Exception:
        return False


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        (self.root / 'base').mkdir(); (self.root / 'tex').mkdir()
        Image.new('RGB', (64, 36), (100, 100, 100)).save(self.root / 'base' / '00000.png')
        for i in range(8):   # texture plate: frame i is a flat grey of 10 * (i + 1) ... except frame 0, which is 60
            Image.new('RGB', (64, 36), (60, 60, 60) if i == 0 else (10 * (i + 1),) * 3).save(self.root / 'tex' / f'{i:05d}.png')

    def edit(self, overlays, frames=6, **top):
        e = {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': frames},
             'clips': {'A': {'frames_dir': 'base', 'n': 1, 'fps': 30, 'w': 64, 'h': 36},
                       'T': {'frames_dir': 'tex', 'n': 8, 'fps': 30, 'w': 64, 'h': 36}},
             'shots': [{'f0': 0, 'f1': frames, 'clip': 'A', 'speed': 0}], 'overlays': overlays}
        e.update(top); return e

    def test_validation(self):
        ok = validate(self.edit([{'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'blend': 'add', 'opacity': [[0, 0], [3, 1]],
                                  'floor': .2, 'tint': '$accent', 'fps': 10, 'speed': .8, 'loop': 'pingpong', 'fit': 'contain'},
                                 {'type': 'adjust', 't0': 0, 't1': .1, 'look': {'type': 'filter', 'filter': 'grayscale(1)'}, 'amt': .5}]), self.root)
        self.assertEqual(ok['overlays'][0]['tint'], '#b6ff1f')                  # palette colours resolve
        self.assertEqual((ok['overlays'][1]['f0'], ok['overlays'][1]['f1']), (0, 3))   # t0/t1 become frames
        for overlay, error in (({'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'glow': 1}, 'unsupported fields: glow'),
                               ({'type': 'clip', 'clip': 'Z', 'f0': 0, 'f1': 6}, 'a clip id'),
                               ({'type': 'clip', 'clip': 'T', 'f0': 4, 'f1': 4}, 'f1: out of range'),
                               ({'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'blend': 'glow'}, 'blend'),
                               ({'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'opacity': [[3, 1], [2, 0]]}, 'must increase'),
                               ({'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'opacity': 1.5}, 'out of range'),
                               ({'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'src': 1, 'srcf': 2}, 'src or srcf'),
                               ({'type': 'adjust', 'f0': 0, 'f1': 6}, 'needs a look'),
                               ({'type': 'adjust', 'f0': 0, 'f1': 6, 'look': 'none'}, 'changes the picture'),
                               ({'type': 'blur', 'f0': 0, 'f1': 6}, 'type "clip" or "adjust"'),
                               ({'type': 'clip', 'clip': 'T'}, 'f0 and f1')):
            with self.assertRaisesRegex(ContractError, error, msg=json.dumps(overlay)):
                validate(self.edit([overlay]), self.root)

    def test_non_finite_numbers_are_rejected_anywhere(self):
        e = self.edit([{'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'opacity': math.nan}])
        with self.assertRaisesRegex(ContractError, r'overlays\[0\]\.opacity: nan is not a finite number'):
            validate(e, self.root)
        (self.root / 'h.js').write_text("OpenKatanaHooks.layer('k', {draw(){}});", encoding='utf-8')
        e = self.edit([], hooks={'src': 'h.js', 'layers': ['k']})
        e['shots'][0]['fx'] = {'k': {'items': [{'g': [0.1, math.inf]}]}}       # free-form hook params
        with self.assertRaisesRegex(ContractError, r'items\[0\]\.g\[1\]: inf is not a finite'):
            validate(e, self.root)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_blends_floor_tint_keyframes_steps_and_adjustment(self):
        from openkatana.render import render
        cases = {
            'screen': [{'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'speed': 0}],
            'add': [{'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'speed': 0, 'blend': 'add'}],
            'floor': [{'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'speed': 0, 'blend': 'add', 'floor': .2}],
            'tint': [{'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'speed': 0, 'blend': 'add', 'tint': '#ff0000'}],
            'keys': [{'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'speed': 0, 'blend': 'add', 'opacity': [[0, 0], [3, 1]]}],
            'steps': [{'type': 'clip', 'clip': 'T', 'f0': 0, 'f1': 6, 'blend': 'normal', 'fps': 10}],
            'adjust': [{'type': 'adjust', 'f0': 2, 'f1': 6, 'look': {'type': 'filter', 'filter': 'brightness(0)'}, 'amt': .25}],
        }
        px = {}
        for name, overlays in cases.items():
            (self.root / f'{name}.json').write_text(json.dumps(self.edit(overlays)))
            render(self.root / f'{name}.json', self.root / f'out-{name}')
            px[name] = [Image.open(self.root / f'out-{name}' / 'frames' / f'{f:05d}.png').convert('RGB').getpixel((32, 18)) for f in range(6)]
        near = lambda got, want, tol=2: self.assertTrue(all(abs(a - b) <= tol for a, b in zip(got, want)), f'{got} != {want}')
        near(px['screen'][0], (137,) * 3)            # 1 - (1 - 100/255)(1 - 60/255)
        near(px['add'][0], (160,) * 3)               # 100 + 60
        near(px['floor'][0], (111,) * 3, 3)          # 100 + 255 (60/255 - .2) / .8
        near(px['tint'][0], (160, 100, 100))         # the plate multiplied by red, added
        near(px['keys'][0], (100,) * 3); near(px['keys'][1], (120,) * 3); near(px['keys'][4], (160,) * 3)
        # stepped to 10 fps on a 30 fps canvas: frames 0-2 show plate frame 1 (20), frames 3-5 plate frame 4 (50)
        self.assertEqual([p[0] for p in px['steps']], [20, 20, 20, 50, 50, 50])
        near(px['adjust'][0], (100,) * 3); near(px['adjust'][3], (75,) * 3)   # 25 % of the way to black


class FlatFrameTests(unittest.TestCase):
    def test_flat_frames_are_flagged_unless_a_flat_special_is_scheduled(self):
        from openkatana.preview import flat_frames
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, (c, noisy) in enumerate((((0, 0, 0), False), ((10, 200, 30), True), ((255, 255, 255), False), ((0, 0, 0), False))):
                im = Image.new('RGB', (16, 9), c)
                if noisy:
                    im.putpixel((3, 3), (90, 90, 90))
                paths.append(str(Path(tmp) / f'{i}.png')); im.save(paths[-1])
            edit = {'shots': [{'f0': 0, 'f1': 20, 'clip': 'A'}, {'f0': 20, 'f1': 30, 'special': {'type': 'white'}}],
                    'specials': [{'f0': 30, 'f1': 31, 'type': 'black'}]}
            self.assertEqual(flat_frames(edit, [0, 5, 25, 30], paths), [{'frame': 0, 'rgb': [0, 0, 0]}])


if __name__ == '__main__':
    unittest.main()
