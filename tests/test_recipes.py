"""F-PRE-001: recipe families build valid timelines from supplied clips (no rendering); face-track provenance fields
written by analyze_clip faces are accepted (regression found while verifying facelock_strobe)."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from openkatana.contracts import ContractError, validate
from openkatana.recipes import FAMILIES, build


def analysis(bpm=120, dur=8.0):
    P = 60 / bpm; beats = [round(k * P, 4) for k in range(int(dur / P))]
    return {'duration': dur, 'period': P, 'phase': 0.0, 'bpm': bpm, 'beats': beats, 'downbeats': beats[::4],
            'sections': [{'t0': 0.0, 't1': 4.0, 'label': 'mid', 'step_db': None}, {'t0': 4.0, 't1': dur, 'label': 'loud', 'step_db': 6.0}]}


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        for d, n in (('a', 60), ('b', 60), ('s', 1)):
            (self.root / d).mkdir()
            for i in range(n):
                Image.new('RGB', (64, 36), (i * 4, 40, 90)).save(self.root / d / f'{i:05d}.png')
        rows = [{'f': i, 'box': [20, 8, 16, 16], 'src': 'det' if i % 2 else 'track', 'detector': 'frontal', 'eyes': [[25, 13], [31, 13]],
                 'eyes_src': ('det', 'track', 'estimate')[i % 3]} for i in range(60)]
        (self.root / 'faces.json').write_text(json.dumps(rows))
        (self.root / 'song.wav').write_bytes(b'')
        self.clips = [('A', {'frames_dir': 'a', 'n': 60, 'fps': 30, 'w': 64, 'h': 36, 'faces': 'faces.json'}),
                      ('B', {'frames_dir': 'b', 'n': 60, 'fps': 30, 'w': 64, 'h': 36}),
                      ('S', {'frames_dir': 's', 'n': 1, 'fps': 30, 'w': 64, 'h': 36})]

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_family_validates(self):
        for fam in FAMILIES:
            with self.subTest(fam=fam):
                kw = {'music': 'song.wav', 'analysis': analysis()} if fam == 'beat_cut_punch' else {}
                if fam == 'timed_type':
                    kw = {'text': 'one two three four', 'family_font': 'F'}
                edit, _ = build(fam, self.clips, 30, 180, 320, 4, **kw)
                if fam == 'timed_type':
                    edit['fonts'] = [{'family': 'F', 'url': 'x.ttf'}]
                    validate(edit)   # without a root the font file is not opened; the text structure is still checked
                else:   # the placeholder song is not real audio: check everything but the mix
                    validate({k: v for k, v in edit.items() if k != 'audio'}, self.root)
                self.assertEqual(edit['shots'][0]['f0'], 0)
                self.assertEqual(edit['shots'][-1]['f1'], edit['canvas']['frames'])

    def test_family_specifics(self):
        e, _ = build('speed_ramp_freeze', self.clips[1:], 30, 180, 320, 4)
        ramp, freeze = e['shots']
        self.assertEqual((ramp['speed'], ramp['speed1'], freeze['speed']), (1, .35, 0))
        self.assertEqual(freeze['srcf'], round((ramp['f1'] - 1) * 1.35 / 2))   # holds the frame the ramp ends on
        e, _ = build('facelock_strobe', self.clips, 30, 180, 320, 4)
        self.assertEqual(list(e['clips']), ['A']); self.assertEqual(e['shots'][0]['cam']['type'], 'facelock')
        e, _ = build('timed_type', self.clips, 30, 180, 320, 4, text='a b c d e f g', family_font='F')
        self.assertEqual([t['text'] for t in e['text']], ['a b c', 'd e f', 'g'])
        e, notes = build('cutout_collage', self.clips, 30, 180, 320, 4)
        self.assertEqual(e['shots'][0]['special']['type'], 'collage'); self.assertTrue(notes)
        e, _ = build('glitch_hits', self.clips, 30, 180, 320, 4, analysis=analysis())
        self.assertTrue(all(s['in']['type'] == 'glitch' for s in e['shots'][1:]))
        self.assertEqual(e['shots'][1]['f0'], 30)   # two beats at 120 BPM

    def test_errors(self):
        with self.assertRaisesRegex(ContractError, 'recipe: one of'):
            build('vaporwave', self.clips)
        with self.assertRaisesRegex(ContractError, 'needs music'):
            build('beat_cut_punch', self.clips)
        with self.assertRaisesRegex(ContractError, 'face track'):
            build('facelock_strobe', self.clips[1:])
        with self.assertRaisesRegex(ContractError, 'font'):
            build('timed_type', self.clips)

    def test_face_track_provenance_fields(self):
        edit = {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': 10}, 'clips': dict(self.clips[:1]),
                'shots': [{'f0': 0, 'f1': 10, 'clip': 'A', 'cam': {'type': 'facelock'}}]}
        validate(edit, self.root)
        rows = json.loads((self.root / 'faces.json').read_text()); rows[3]['eyes_src'] = 'guess'
        (self.root / 'faces.json').write_text(json.dumps(rows))
        with self.assertRaisesRegex(ContractError, 'eyes_src'):
            validate(edit, self.root)


if __name__ == '__main__':
    unittest.main()
