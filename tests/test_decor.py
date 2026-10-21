"""F-NAT-006 / F-NAT-007: decorative and face graphics layer contract (rendering is checked by
work/claude-fix/scripts/verify_f_nat_006.py)."""
import unittest

from openkatana.contracts import ContractError, validate
from openkatana.native import normalize


def edit(fx=None, layers=None, fonts=True, **top):
    shot = {'f0': 0, 'f1': 30, 'clip': 'A'}
    if fx is not None:
        shot['fx'] = fx
    if layers is not None:
        shot['layers'] = layers
    e = {'canvas': {'w': 320, 'h': 180, 'fps': 30, 'frames': 30}, 'clips': {'A': {'frames_dir': 'f', 'n': 30, 'fps': 30, 'w': 320, 'h': 180, 'faces': 'faces.json'}},
         'shots': [shot], **top}
    if fonts:
        e['fonts'] = [{'family': 'F', 'url': 'f.ttf'}]
    return e


class DecorTests(unittest.TestCase):
    def test_accepted(self):
        good = [{'stairs': True}, {'stairs': {'cells': [[0, 0], [1, 1]], 'size': 12, 'color': '#ff00ff'}}, {'glow': .4}, {'glow': {'amt': .4, 'blur': 5}},
                {'glint': {'at': 0, 'd': .6, 'from': [.1, .1], 'to': [.5, .5], 'r': 40}}, {'doodles': 2}, {'doodles': {'n': 6, 'types': ['zig', 'bolt'], 'mono': True}},
                {'face_doodles': {'n': 4}}, {'face_doodles': {'items': [{'t': 'heart', 'o': [1, -1], 's': .5, 'at': .1}]}},
                {'doodle': {'t': 'heart', 'pos': [.3, .3], 'size': 60}}, {'word': {'text': 'HANA', 'at': .05, 'family': 'F'}}, {'word': {'v': 'HI', 'family': 'F'}},
                {'type': {'parts': [['NEW', 'bold'], [' WAVE', 'thin']], 'family': 'F'}}, {'slash': {'at': 0, 'n': 3}}, {'sparkle': {'pos': [.5, .5], 'r': 60}},
                {'splat': {'items': [{'pos': [.5, .5], 'r': 80}]}}, {'bw': {'bars': [20, 20]}}, {'bw': {'filter': 'grayscale(1) contrast(1.2) hue-rotate(10deg)'}},
                {'tag': {'text': '@handle', 'family': 'F', 'pos': 'bottom'}}, {'border': True}, {'cheeks': {'force': True}}, {'fangs': {'len': .4}},
                {'ears': True}, {'whisk': True}, {'blush': {'size': 1.2}}, {'ast': True}]
        for fx in good:
            with self.subTest(fx=fx):
                validate(edit(fx=fx))
        validate(edit(layers=[{'type': 'doodle', 't': 'star', 'phase': 'final'}, {'type': 'word', 'text': 'X', 'family': 'F'}]))

    def test_rejected(self):
        bad = [({'doodle': {'t': 'unicorn'}}, 'one of'), ({'doodles': {'types': ['heart']}}, 'a list of'), ({'word': {'text': 'X'}}, 'declared font'),
               ({'word': {'at': 0, 'family': 'F'}}, 'needs text'), ({'type': {'parts': [['A', 'medium']], 'family': 'F'}}, 'bold|thin|heavy'),
               ({'bw': {'filter': 'url(#x)'}}, 'CSS filter'), ({'glow': {'amt': 2}}, 'amt'), ({'face_doodles': {'n': 2, 'items': [{'t': 'heart'}]}}, 'not both'),
               ({'tag': {'text': '@a', 'family': 'F', 'pos': 'top'}}, 'expected'), ({'stairs': {'cells': [[0.5, 1]]}}, 'cells'), ({'ears': {'colors': {'line': '#fff', 'glow': '#000'}}}, 'unsupported')]
        for fx, msg in bad:
            with self.subTest(fx=fx), self.assertRaisesRegex(ContractError, msg):
                validate(edit(fx=fx))

    def test_font_stacks_fill_decorative_text(self):
        e = normalize(edit(fx={'word': {'text': 'HANA'}, 'tag': {'v': '@me', 'kind': 'heavy'}}, font_stacks={'sans': '"F", sans-serif'}))
        self.assertEqual((e['shots'][0]['fx']['word']['family'], e['shots'][0]['fx']['tag']['family']), ('F', 'F'))
        validate(e)


if __name__ == '__main__':
    unittest.main()
