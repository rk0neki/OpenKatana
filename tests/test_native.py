"""Native authoring syntax (audit F-NAT-001/002/004/005/012): normalisation rules and validation errors."""
import json
import unittest

from openkatana.contracts import ContractError, validate
from openkatana.native import frame_of, normalize

BASE = {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': 60}, 'clips': {'A': {'frames_dir': 'f', 'n': 30, 'fps': 30, 'w': 64, 'h': 36}},
        'shots': [{'f0': 0, 'f1': 60, 'clip': 'A'}]}


def edit(**top):
    e = json.loads(json.dumps(BASE)); e.update(top); return e


def shot(**fields):
    return edit(shots=[{'f0': 0, 'f1': 60, 'clip': 'A', **fields}])


class TimeTests(unittest.TestCase):
    def test_frame_rule_is_frame_centre(self):
        # observed: t0 = 2.3 frames -> frame 2, 2.7 -> frame 3, exactly 2.5 -> frame 2
        self.assertEqual([frame_of(x / 30, 30) for x in (2.3, 2.7, 2.5, 9.7, 9.3, 0)], [2, 3, 2, 10, 9, 0])

    def test_shot_and_text_times(self):
        e = edit(beat={'bpm': 120, 't0': 0}, shots=[{'t0': 0, 'clip': 'A'}, {'t0': 'b2', 'clip': 'A'}],
                 text=[{'type': 'font', 'family': 'X', 'text': 'a', 't0': 'f3', 't1': 1.0}])
        n = normalize(e)
        self.assertEqual([(s['f0'], s['f1']) for s in n['shots']], [(0, 30), (30, 60)])   # t1 defaults to the next start / end
        self.assertEqual((n['text'][0]['f0'], n['text'][0]['f1']), (3, 30))
        self.assertNotIn('beat', n)

    def test_time_errors(self):
        with self.assertRaisesRegex(ContractError, 'beat'):
            normalize(edit(text=[{'t0': 'b1', 't1': 'b2'}]))
        with self.assertRaisesRegex(ContractError, 'not both'):
            normalize(shot(t0=0))
        with self.assertRaisesRegex(ContractError, 'expected seconds'):
            normalize(edit(text=[{'t0': '1s', 't1': 2}]))
        gap = edit(shots=[{'t0': 0, 't1': .5, 'clip': 'A'}, {'t0': 1.0, 'clip': 'A'}])
        with self.assertRaisesRegex(ContractError, 'without gaps'):
            validate(gap)

    def test_specials_timing(self):
        n = normalize(edit(specials=[{'t0': 4 / 30, 'd': .2, 'type': 'color', 'color': '#ff8800'}, {'f0': 20, 'n': 6, 'type': 'black', 'sparkle': False}]))
        self.assertEqual([(s['f0'], s['f1']) for s in n['specials']], [(4, 10), (20, 26)])
        with self.assertRaisesRegex(ContractError, 'exactly one'):
            normalize(edit(specials=[{'f0': 1, 'n': 2, 'd': .1, 'type': 'black'}]))


class ColourTests(unittest.TestCase):
    def test_forms(self):
        n = normalize(shot(fx={'tint': {'color': '$accent', 'v': .5}}, bg=[0, 128, 255]))
        self.assertEqual(n['shots'][0]['fx']['tint']['color'], '#b6ff1f')
        self.assertEqual(n['shots'][0]['bg'], '#0080ff')
        n = normalize(edit(palette={'accent': 'rgb(34,255,136)'}, shots=[{'f0': 0, 'f1': 60, 'clip': 'A', 'fx': {'tint': {'color': 'rgba(255,0,0,0.5)'}}, 'look': 'duo'}]))
        self.assertEqual(n['shots'][0]['fx']['tint']['color'], 'rgba(255,0,0,0.5)')
        self.assertEqual(n['shots'][0]['look'], {'type': 'duotone', 'paper': '#22ff88'})   # paper defaults to $accent
        validate(shot(fx={'tint': {'color': [255, 0, 0, .5], 'v': .6}}))

    def test_colour_errors(self):
        with self.assertRaisesRegex(ContractError, 'unknown palette colour'):
            normalize(shot(bg='$nope'))
        with self.assertRaisesRegex(ContractError, 'must be opaque'):
            validate(shot(bg='rgba(0,0,0,0.5)'))
        with self.assertRaisesRegex(ContractError, 'rgb'):
            validate(shot(bg=[300, 0, 0]))


class LookTests(unittest.TestCase):
    def test_presets_and_tables(self):
        self.assertEqual(normalize(shot(look='bw'))['shots'][0]['look']['filter'], 'grayscale(1) contrast(1.22) brightness(1.04)')
        self.assertEqual(normalize(shot(look='threshold'))['shots'][0]['look'], {'type': 'threshold'})
        self.assertEqual(normalize(shot(look={'preset': 'neg', 'grit': 0}))['shots'][0]['look'], {'type': 'neg', 'grit': 0})
        n = normalize(edit(looks={'mine': {'type': 'xerox', 'white': .5}, 'alias': 'mine'}, look='alias'))
        self.assertEqual(n['look'], {'type': 'xerox', 'white': .5})
        validate(shot(look={'type': 'xerox', 'grit': 0, 'black': {'from': .06, 'to': .5, 'ease': 'in2', 'over': .85}}))
        validate(shot(look={'type': 'xerox', 'grain_every': 2}))

    def test_look_errors(self):
        with self.assertRaisesRegex(ContractError, 'unknown look'):
            normalize(shot(look='sparkly'))
        with self.assertRaisesRegex(ContractError, 'refers to itself'):
            normalize(edit(looks={'a': 'b', 'b': 'a'}, look='a'))
        validate(shot(look='x')); validate(shot(look='xl'))
        validate(shot(look={'type': 'xerox', 'key': {'hue': [300, 345], 'light': '$accent', 'stoch': 0}}))
        with self.assertRaisesRegex(ContractError, 'key.channel'):
            validate(shot(look={'type': 'xerox', 'key': {'channel': 'y'}}))
        with self.assertRaisesRegex(ContractError, 'unsupported fields'):
            validate(shot(look={'type': 'xerox', 'key': {'colour': 'g'}}))
        with self.assertRaisesRegex(ContractError, 'white must exceed'):
            validate(shot(look={'type': 'xerox', 'black': {'from': .1, 'to': .9}}))
        with self.assertRaisesRegex(ContractError, 'looks only'):
            validate(shot(fx={'tint': {'v': {'from': 0, 'to': 1}}}))


class ShotFieldTests(unittest.TestCase):
    def test_shorthand_seed_note_keywords(self):
        n = normalize(shot(fx={'tint': .4, 'grain': True}, seed=13, note='free text'))
        s = n['shots'][0]
        self.assertEqual(s['fx'], {'tint': {'v': .4}, 'grain': {'seed': 13}})
        self.assertNotIn('note', s); self.assertNotIn('seed', s)
        k = normalize(edit(shots=[{'f0': 0, 'f1': 60, 'clip': 'FLASH', 'srcf': 8, 'speed': 0}]))['shots'][0]
        self.assertEqual(k, {'f0': 0, 'f1': 60, 'special': {'type': 'flash', 'color': '#b6ff1f', 'splat': '#0b0b0b'}})

    def test_specials_and_source_fx_validate(self):
        validate(edit(shots=[{'f0': 0, 'f1': 30, 'special': {'type': 'collage', 'panels': [{'clip': 'A', 'srcf': 3, 'rect': [.05, .1, .4, .8]}]}},
                             {'f0': 30, 'f1': 60, 'clip': 'A', 'fx': {'stutter': {'n': 3, 'step': 2}, 'trail': {'n': 2, 'alpha': .5, 'op': 'screen'}}}]))
        for sp, error in (({'type': 'confetti'}, 'needs a type'), ({'type': 'color'}, 'needs color'),
                          ({'type': 'collage', 'panels': [{'clip': 'Z', 'rect': [0, 0, 1, 1]}]}, 'unknown clip'),
                          ({'type': 'collage', 'panels': [{'clip': 'A', 'rect': [0, 0, 0, 1]}]}, 'positive'),
                          ({'type': 'white', 'allow': ['grain']}, 'allow')):
            with self.assertRaisesRegex(ContractError, error, msg=sp):
                validate(edit(shots=[{'f0': 0, 'f1': 60, 'special': sp}]))
        with self.assertRaisesRegex(ContractError, 'without overlap'):
            validate(edit(specials=[{'f0': 0, 'n': 6, 'type': 'black'}, {'f0': 3, 'n': 2, 'type': 'white'}]))
        with self.assertRaisesRegex(ContractError, 'stutter.n'):
            validate(shot(fx={'stutter': {'n': 0}}))


if __name__ == '__main__':
    unittest.main()
