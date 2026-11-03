"""examples/effects_reel.py: the one-command reproduction of the README reel (docs/assets/ae-packs.mp4)."""
import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('effects_reel', ROOT / 'examples/effects_reel.py')
reel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reel)


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path()) and bool(shutil.which('ffmpeg'))
    except Exception:
        return False


class EffectsReelExampleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_arguments(self):
        a = reel.parse_args([])
        self.assertEqual((a.spec, a.out, a.width, a.height, a.fps, a.frames),
                         (ROOT / 'examples/effects_reel.json', Path('work/effects-reel'), 640, 360, 24, 24))
        a = reel.parse_args(['--spec', 'x.json', '--out', 'o', '--width', '96', '--height', '54', '--frames', '3'])
        self.assertEqual((a.spec, a.out, a.width, a.height, a.frames), (Path('x.json'), Path('o'), 96, 54, 3))
        for bad in (['--width', '95'], ['--height', '8'], ['--frames', '0']):
            with self.assertRaises(SystemExit), unittest.mock.patch('sys.stderr'):
                reel.parse_args(bad)

    def test_the_readme_spec_validates(self):
        from openkatana.contracts import validate
        effects = reel.load_spec(ROOT / 'examples/effects_reel.json')
        self.assertEqual(len(effects), 16)
        self.assertEqual(effects[3]['label'], 'Twirl')
        (self.root / 'plate').mkdir()
        reel.draw_plate(64, 36).save(self.root / 'plate' / '00000.png')
        for e in effects:
            validate(reel.segment('plate', 64, 36, 24, 24, e['fx']), self.root)
        (self.root / 'bad.json').write_text('[{"label": "x"}]')
        with self.assertRaisesRegex(ValueError, 'expected'):
            reel.load_spec(self.root / 'bad.json')

    def test_plate(self):
        a = np.asarray(reel.draw_plate(640, 360)).astype(int)
        self.assertEqual(a.shape, (360, 640, 3))
        self.assertGreater(a[79, 499].min(), 230)          # the light spot (.78, .22)
        self.assertLess(a[180, 320].max(), 225)            # the logo stays below the glow thresholds
        self.assertGreater(a[90:270, 230:410].mean(), 120)  # ...and fills the middle
        self.assertLess(a[5, 5].max(), 60)                 # a dark plate around it
        self.assertEqual(reel.draw_plate(96, 54).size, (96, 54))

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_two_effect_reel(self):
        effects = reel.load_spec(ROOT / 'examples/effects_reel.json')
        (self.root / 'two.json').write_text(json.dumps([effects[3], effects[12]]))   # Twirl and Echo
        out = self.root / 'reel'
        with contextlib.redirect_stdout(io.StringIO()):
            mp4, gif = reel.main(['--spec', str(self.root / 'two.json'), '--out', str(out),
                                  '--width', '96', '--height', '54', '--frames', '3'])
        self.assertEqual(sorted(p.name for p in out.iterdir()), ['ae-packs.gif', 'ae-packs.mp4'])   # work files removed
        from openkatana.render import probe
        video = next(s for s in probe(mp4)['streams'] if s['codec_type'] == 'video')
        self.assertEqual((int(video['nb_read_frames']), video['width'], video['height']), (6, 96, 54))
        self.assertGreater(gif.stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
