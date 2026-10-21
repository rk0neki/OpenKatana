"""F-NAT-008: sticker events and assets, font CSS strings / font_stacks, text sfx cues, the sfx block, audio_tracks and
on_specials (validation and normalisation; rendering is covered by work/claude-fix/scripts/verify_f_nat_008.py)."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from openkatana.contracts import ContractError, validate
from openkatana.native import normalize


class StickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root / 'x.ttf').write_bytes(b'')   # placeholder; text cases validate without a root (font files unread)
        for d in ('f', 'm', 'st'):
            (self.root / d).mkdir()
        for i in range(10):
            Image.new('RGB', (64, 36)).save(self.root / 'f' / f'{i:05d}.png')
            Image.new('RGBA', (64, 36)).save(self.root / 'm' / f'{i:05d}.png')
        for i in (1, 2):
            Image.new('RGBA', (20, 20), (255, 0, 0, 255)).save(self.root / 'st' / f's{i:02d}.png')
        (self.root / 'song.wav').write_bytes(b'RIFF')
        (self.root / 'project.json').write_text(json.dumps({'assets': [{'id': 'a1', 'kind': 'audio', 'path': 'song.wav'}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, **extra):
        e = {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': 30},
             'clips': {'A': {'frames_dir': 'f', 'n': 10, 'fps': 30, 'w': 64, 'h': 36, 'mask_dir': 'm'}, 'B': {'frames_dir': 'f', 'n': 10, 'fps': 30, 'w': 64, 'h': 36}},
             'shots': [{'f0': 0, 'f1': 30, 'clip': 'B'}]}
        if 'text' in extra:
            e['fonts'] = [{'family': 'F', 'url': 'x.ttf'}]
        e.update(extra)
        return e

    def test_sticker_events(self):
        assets = {'stickers': {'dir': 'st', 'n': 2, 'pattern': 's%02d.png'}, 'cutouts': [{'clip': 'A', 't': .1}], 'cutout_border': 4}
        e = normalize(self.edit(assets=assets, stickers=[{'t0': 0, 't1': .5, 'kind': 'graphic', 'n': 2, 'mode': 'burst'},
                                                         {'t0': .5, 't1': 1, 'kind': 'cutout', 'slots': [[.8, .2]], 'shadow': False}], beat={'bpm': 120}))
        self.assertEqual(e['assets']['stickers'], ['st/s01.png', 'st/s02.png'])
        self.assertEqual((e['stickers'][0]['f0'], e['stickers'][0]['f1'], e['stickers'][0]['step']), (0, 15, .125))   # 1/16 note at 120 BPM
        validate(e, self.root)
        validate(self.edit(assets={'stickers': ['st/s01.png']}, stickers=[{'f0': 0, 'f1': 5}], shots=[{'f0': 0, 'f1': 30, 'clip': 'B', 'fx': {'stickers': False}}]), self.root)

    def test_sticker_errors(self):
        bad = [({'stickers': ['st/missing.png']}, [{'f0': 0, 'f1': 5}], 'missing file'),
               ({'cutouts': [{'clip': 'B', 't': 0}]}, [{'f0': 0, 'f1': 5, 'kind': 'cutout'}], 'mask_dir'),
               ({'stickers': ['st/s01.png']}, [{'f0': 0, 'f1': 5, 'kind': 'cutout'}], 'needs assets.cutouts'),
               ({'stickers': ['st/s01.png']}, [{'f0': 0, 'f1': 5, 'n': 3, 'slots': [[.1, .1]]}], 'at least n'),
               ({'stickers': ['st/s01.png']}, [{'f0': 0, 'f1': 5, 'ids': [2]}], 'ids'),
               ({'stickers': ['st/s01.png']}, [{'f0': 0, 'f1': 5, 'hero': True}], 'unsupported'),
               ({'cutouts': [{'clip': 'A', 't': 5}]}, [{'f0': 0, 'f1': 5, 'kind': 'cutout'}], 't')]
        for assets, events, msg in bad:
            with self.subTest(msg=msg), self.assertRaisesRegex(ContractError, msg):
                validate(self.edit(assets=assets, stickers=events), self.root)
        with self.assertRaisesRegex(ContractError, 'only supports false'):
            validate(self.edit(shots=[{'f0': 0, 'f1': 30, 'clip': 'B', 'fx': {'stickers': True}}]), self.root)

    def test_font_css_and_stacks(self):
        e = normalize(self.edit(text=[{'type': 'font', 'text': 'A', 'font': 'italic 700 {S}px "F", sans-serif', 'size': 40, 'f0': 0, 'f1': 5},
                                      {'type': 'font', 'text': 'B', 'font': '48px F', 'f0': 0, 'f1': 5},
                                      {'type': 'font', 'text': 'C', 'kind': 'heavy', 'f0': 0, 'f1': 5}],
                                font_stacks={'heavy': '"Missing", "F", sans-serif'}))
        a, b, c = e['text']
        self.assertEqual((a['family'], a['weight'], a['style'], a['size']), ('F', 700, 'italic', 40))
        self.assertEqual((b['family'], b['size']), ('F', 48.0))
        self.assertEqual((c['family'], c['kind']), ('F', 'heavy')); self.assertNotIn('font_stacks', e)
        validate(e)
        with self.assertRaisesRegex(ContractError, 'CSS shorthand'):
            normalize(self.edit(text=[{'type': 'font', 'text': 'A', 'font': 'big F', 'f0': 0, 'f1': 5}]))
        with self.assertRaisesRegex(ContractError, 'names no declared font'):
            normalize(self.edit(text=[{'type': 'font', 'text': 'A', 'f0': 0, 'f1': 5}], font_stacks={'sans': 'Arial, sans-serif'}))

    def test_sfx_audio_tracks_and_on_specials(self):
        e = normalize(self.edit(text=[{'type': 'font', 'family': 'F', 'text': 'HIT', 'sfx': 'hit', 't0': .5, 't1': 1, 'on_specials': False}],
                                sfx={'auto': False, 'hits': False, 'cues': [{'sfx': 'pop', 'at': .2}]},
                                audio_tracks=[{'asset_id': 'a1', 'start': 1, 'at': 0, 'gain_db': -6}]), self.root)
        self.assertEqual(e['audio']['tracks'], [{'start': 1, 'at': 0, 'src': 'song.wav', 'volume': 0.501187}])
        self.assertEqual(e['audio']['cues'], [{'sfx': 'hit', 'at': .5}, {'sfx': 'pop', 'at': .2}])
        self.assertNotIn('sfx', e['text'][0]); self.assertFalse(e['text'][0]['on_specials'])
        self.assertNotIn('audio', normalize(self.edit(audio_tracks=[])))   # [] is silence
        for extra, msg in (({'sfx': {'auto': True}}, 'automatic SFX placement'), ({'audio_tracks': [{'asset_id': 'zz'}]}, 'asset with sound'),
                           ({'audio_tracks': [], 'audio': {'mode': 'mix', 'tracks': []}}, 'not both')):
            with self.subTest(msg=msg), self.assertRaisesRegex(ContractError, msg):
                normalize(self.edit(**extra), self.root)
        with self.assertRaisesRegex(ContractError, 'on_specials'):
            validate(self.edit(text=[{'type': 'graffiti', 'word': 'TAG', 'f0': 0, 'f1': 5, 'on_specials': 'no'}]))


if __name__ == '__main__':
    unittest.main()
