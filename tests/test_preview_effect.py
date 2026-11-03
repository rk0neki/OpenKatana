"""preview_effect: one shot effect rendered on a test card or a project picture, for agents and ComfyUI."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from openkatana.agent_api import TOOLS, AgentAPI
from openkatana.contracts import ContractError


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path()) and bool(shutil.which('ffmpeg'))
    except Exception:
        return False


class PreviewEffectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.api = AgentAPI(self.tmp.name); self.api.create_project('p', 'p')
        self.root = Path(self.tmp.name) / 'p'

    def previews(self):
        folder = self.root / '.openkatana' / 'effect-previews'
        return list(folder.iterdir()) if folder.is_dir() else []

    def test_registered(self):
        self.assertIn('preview_effect', TOOLS)
        from openkatana.effect_preview import effect_names
        names = effect_names()
        for name in ('local_turbulent_displace', 'local_displacement_map', 'invert', 'glow', 'zoom'):
            self.assertIn(name, names)
        self.assertNotIn('text', names)

    def test_validation(self):
        (self.root / 'notes.txt').write_text('x')
        cases = (({'effect': 'nope'}, 'docs/TIMELINE.md'),
                 ({'effect': 'local_turbulnt_displace'}, 'Did you mean local_turbulent_displace'),
                 ({'effect': 'local_turbulent_displace', 'params': {'amount': 5000}}, 'amount: out of range'),
                 ({'effect': 'local_turbulent_displace', 'params': {'octaves': 2}}, 'unsupported fields: octaves'),
                 ({'effect': 'local_turbulent_displace', 'params': [1]}, 'params: an object'),
                 ({'effect': 'invert', 'source': 'missing.png'}, 'no file at'),
                 ({'effect': 'invert', 'source': 'notes.txt'}, 'expected an image'),
                 ({'effect': 'invert', 'source': '../outside.png'}, 'leaves the project'),
                 ({'effect': 'invert', 'seconds': 10, 'fps': 30}, '300 frames'),
                 ({'effect': 'invert', 'max_width': 4000}, 'max_width'),
                 ({'effect': 'invert', 'fps': 0}, 'fps'))
        for args, error in cases:
            with self.assertRaisesRegex(ContractError, error, msg=str(args)):
                self.api.call('preview_effect', {'project_id': 'p', **args})
        self.assertEqual(self.previews(), [])           # nothing was left behind
        with self.assertRaisesRegex(ContractError, 'unsupported arguments: colour'):
            self.api.call('preview_effect', {'project_id': 'p', 'effect': 'invert', 'colour': 1})

    def test_test_card(self):
        from openkatana.effect_preview import test_card
        a = np.asarray(test_card(192, 108)).astype(int)
        self.assertEqual(a.shape, (108, 192, 3))
        self.assertEqual(a.max(), 255)                  # the light spot clips
        self.assertGreater(a.std(), 25)                 # real detail, not a flat card

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_preview_on_test_card(self):
        r = self.api.preview_effect('p', 'local_turbulent_displace', {'amount': 40, 'size': 60}, seconds=.2, max_width=192)
        self.assertEqual((r['frames'], r['width'], r['height'], r['effect'], r['source']), (6, 192, 108, 'local_turbulent_displace', 'test card'))
        self.assertTrue(Path(r['video']).is_file() and Path(r['contact_sheet']).is_file())
        self.assertEqual(r['preview_images'], [r['contact_sheet']])
        with Image.open(r['contact_sheet']) as sheet:
            self.assertEqual(sheet.size[0], 960)
        from openkatana.render import probe
        video = next(s for s in probe(Path(r['video']))['streams'] if s['codec_type'] == 'video')
        self.assertEqual((int(video['nb_read_frames']), video['width'], video['height']), (6, 192, 108))
        self.assertFalse((Path(r['video']).parent / 'frames').exists())   # PNG frames are not kept

    def test_card_moves(self):
        from openkatana.effect_preview import card_frame, test_card
        base = np.asarray(test_card(192, 108)).astype(np.float32)
        a, b = (np.asarray(card_frame(base, i, 15)).astype(int) for i in (0, 6))
        self.assertGreater(np.abs(a - b).max(), 100)    # the ball moved: time effects have motion to act on

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_time_effect_on_moving_card(self):
        # stutter n 3 step 2 loops source frames 0, 2, 4: output frames 0 and 3 match, 0 and 1 differ
        r = self.api.preview_effect('p', 'stutter', {'n': 3, 'step': 2}, seconds=.4, fps=15, max_width=192)
        with Image.open(r['contact_sheet']) as sheet:
            a = np.asarray(sheet.convert('RGB')).astype(int)
        tile = lambda i: a[44 + i // 3 * 202:224 + i // 3 * 202, i % 3 * 320:(i % 3 + 1) * 320]
        self.assertGreater(np.abs(tile(0) - tile(1)).mean(), .3)
        self.assertLess(np.abs(tile(0) - tile(3)).mean(), .3)
        self.assertEqual(r['warnings'], [])
        folder = Path(r['timeline']).parent / 'source'
        self.assertEqual(list(folder.glob('*.jpg')), [])  # generated card frames are deleted after encoding

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_font_effects(self):
        args = dict(seconds=.1, fps=15, max_width=128)
        r = self.api.preview_effect('p', 'big', {'text': 'HI'}, **args)
        self.assertEqual(r['params'], {'text': 'HI', 'family': 'Inter'})
        self.assertEqual([w['code'] for w in r['warnings']], ['font_default'])
        r = self.api.preview_effect('p', 'local_scramble_text', {'text': 'HI', 'family': 'Anton'}, **args)
        self.assertEqual(r['warnings'], [])
        self.assertFalse((Path(r['timeline']).parent / 'fonts').exists())
        # a font the project's own timeline declares
        from openkatana.bundled_fonts import FOLDER
        (self.root / 'type').mkdir(); shutil.copyfile(FOLDER / 'anton_Anton-Regular.ttf', self.root / 'type' / 'house.ttf')
        (self.root / 'timeline.json').write_text('{"fonts": [{"family": "House", "url": "type/house.ttf"}]}')
        r = self.api.preview_effect('p', 'word', {'text': 'HI', 'family': 'House'}, **args)
        self.assertEqual(json.loads(Path(r['timeline']).read_text())['fonts'], [{'family': 'House', 'url': 'fonts/house.ttf'}])
        with self.assertRaisesRegex(ContractError, 'neither a font declared'):
            self.api.preview_effect('p', 'word', {'text': 'HI', 'family': 'Nope'}, **args)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_still_and_matte_warnings(self):
        Image.new('RGB', (64, 36), (40, 90, 160)).save(self.root / 'still.png')
        r = self.api.preview_effect('p', 'trail', source='still.png', seconds=.1, max_width=64)
        self.assertIn('still_source', [w['code'] for w in r['warnings']])
        r = self.api.preview_effect('p', 'cutout', seconds=.1, max_width=64)
        matte = [w for w in r['warnings'] if w['code'] == 'needs_matte']
        self.assertEqual(len(matte), 1)
        self.assertIn('subject matte', matte[0]['message'])

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_preview_on_project_image(self):
        a = np.zeros((100, 160, 3), np.uint8); a[:, :80] = (250, 20, 20); a[:, 80:] = (20, 20, 250)
        (self.root / 'media').mkdir(); Image.fromarray(a).save(self.root / 'media' / 'card.png')
        r = self.api.preview_effect('p', 'invert', source='media/card.png', seconds=.1, max_width=96)
        self.assertEqual((r['frames'], r['width'], r['height']), (3, 96, 60))
        self.assertTrue(r['source'].endswith('card.png'))
        with Image.open(r['contact_sheet']) as sheet:     # inverted: the red half reads cyan, the blue half yellow
            left, right = sheet.convert('RGB').getpixel((90, 134)), sheet.convert('RGB').getpixel((230, 134))
        self.assertTrue(left[0] < 60 and left[1] > 200 and left[2] > 200, left)
        self.assertTrue(right[0] > 200 and right[1] > 200 and right[2] < 60, right)


if __name__ == '__main__':
    unittest.main()
