"""local_curve: per-frame scale / offset / blur / glow / exposure from the shot start (measured transitions)."""
import json
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


class LocalCurveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        (self.root / 'f').mkdir()
        im = Image.new('RGB', (64, 36), (100, 100, 100))
        for x in range(32):                       # left half lighter: a mirrored edge must repeat it, not show black
            for y in range(36):
                im.putpixel((x, y), (200, 200, 200))
        im.save(self.root / 'f' / '00000.png')

    def edit(self, curve, frames=4, where='fx'):
        shot = {'f0': 0, 'f1': frames, 'clip': 'A', 'speed': 0}
        if where == 'fx':
            shot['fx'] = {'local_curve': curve}
        e = {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': frames},
             'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': 64, 'h': 36}}, 'shots': [shot]}
        if where == 'post':
            e['post'] = {'local_curve': curve}
        return e

    def test_validation(self):
        validate(self.edit({'scale': [.9, .95, 1], 'dx': [0, .01], 'dy': [-.05], 'blur': [.04, .02, 0], 'glow': [.3, 0],
                            'exposure': [2.2, 1.5, 1], 'glow_radius': .02, 'glow_mode': 'add', 'mirror': False, 'at': .1}), self.root)
        validate(self.edit({'exposure': [2, 1]}, where='post'), self.root)       # every shot opens with it
        for curve, error in (({'scale': 1}, 'array of 1..600'), ({'scale': [0]}, r'scale\[0\]: out of range'),
                             ({'blur': [.1] * 601}, 'array of 1..600'), ({'glow_mode': 'lighten'}, 'screen or add'),
                             ({'mirror': 1}, 'boolean'), ({'spin': [1]}, 'unsupported fields: spin')):
            with self.assertRaisesRegex(ContractError, error, msg=json.dumps(curve)):
                validate(self.edit(curve), self.root)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_rendered_curve(self):
        from openkatana.render import render
        (self.root / 't.json').write_text(json.dumps(self.edit({'exposure': [2, 1.5], 'scale': [1, 1, .5]})))
        render(self.root / 't.json', self.root / 'o')
        px = lambda f, x, y: Image.open(self.root / 'o' / 'frames' / f'{f:05d}.png').convert('RGB').getpixel((x, y))
        self.assertEqual(px(0, 48, 18)[0], 200)            # exposure 2: 100 -> 200
        self.assertEqual(px(1, 48, 18)[0], 150)            # exposure 1.5
        # frame 2: half size about the centre with mirrored edges; the far left column mirrors the light half (no black)
        self.assertEqual(px(2, 40, 18)[0], 100)            # the picture's dark half now sits right of centre
        self.assertGreater(px(2, 1, 18)[0], 150)           # left border: reflected light half, not black
        self.assertEqual(px(3, 48, 18)[0], 100)            # past the arrays: identity


if __name__ == '__main__':
    unittest.main()
