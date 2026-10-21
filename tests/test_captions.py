"""F-CAP-001: caption grouping, karaoke validation, SRT/VTT export."""
import json
import tempfile
import unittest
from pathlib import Path

from openkatana.captions import make, read_words, srt, vtt
from openkatana.contracts import ContractError, validate

WORDS = [[0.0, .4, 'Hello'], [.4, .8, 'there.'], [1.0, 1.3, 'This'], [1.3, 1.5, 'is'], [1.5, 2.0, 'fine'], [3.5, 3.9, 'later']]


class CaptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.dir = Path(self.tmp.name)
        (self.dir / 'w.json').write_text(json.dumps(WORDS))

    def test_grouping_and_export(self):
        ev, cues = make(self.dir / 'w.json', 30, 'F')
        self.assertEqual([e['text'] for e in ev], ['Hello there.', 'This is fine', 'later'])   # sentence end, then the 1.5 s gap
        self.assertEqual((ev[0]['f0'], ev[1]['f0'], ev[2]['f0']), (0, 30, 105))
        self.assertLessEqual(ev[0]['f1'], ev[1]['f0'])
        self.assertIn('00:00:01,000 --> ', srt(cues)); self.assertTrue(vtt(cues).startswith('WEBVTT'))
        (self.dir / 'c.srt').write_text(srt(cues))
        words, groups = read_words(self.dir / 'c.srt')
        self.assertEqual(len(groups), 3); self.assertEqual(words[0][2], 'Hello')
        (self.dir / 'w2.json').write_text(json.dumps({'words': [{'start': 0, 'end': .5, 'word': 'a'}]}))
        self.assertEqual(make(self.dir / 'w2.json', 30, 'F')[0][0]['text'], 'a')

    def test_karaoke_events_validate(self):
        ev, _ = make(self.dir / 'w.json', 30, 'F', style='karaoke')
        self.assertEqual([w['text'] for w in ev[1]['karaoke']['words']], ['This', 'is', 'fine'])
        self.assertEqual(ev[1]['karaoke']['words'][0]['t0'], 0.0)
        edit = {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': 150}, 'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': 64, 'h': 36}},
                'fonts': [{'family': 'F', 'url': 'f.ttf'}], 'shots': [{'f0': 0, 'f1': 150, 'clip': 'A', 'speed': 0}], 'text': ev}
        validate(edit)
        bad = json.loads(json.dumps(edit)); bad['text'][0]['karaoke']['words'][0]['text'] = 'Goodbye'
        with self.assertRaisesRegex(ContractError, 'does not occur'):
            validate(bad)
        with self.assertRaisesRegex(ContractError, 'style'):
            make(self.dir / 'w.json', 30, 'F', style='neon')


if __name__ == '__main__':
    unittest.main()
