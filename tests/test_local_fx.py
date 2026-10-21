"""Local layer contracts and validation regressions."""
import unittest

from openkatana.contracts import ContractError, validate


def edit(fx=None, cam=None, layers=None, post=None, fonts=None):
    shot = {'f0': 0, 'f1': 30, 'clip': 'A'}
    if fx is not None:
        shot['fx'] = fx
    if cam is not None:
        shot['cam'] = cam
    if layers is not None:
        shot['layers'] = layers
    e = {'canvas': {'w': 320, 'h': 180, 'fps': 30, 'frames': 30}, 'clips': {'A': {'frames_dir': 'f', 'n': 30, 'fps': 30, 'w': 320, 'h': 180}}, 'shots': [shot]}
    if post is not None:
        e['post'] = post
    if fonts is not None:
        e['fonts'] = fonts
    return e


class LocalFxTests(unittest.TestCase):
    def test_accepted_forms(self):
        good = [{'local_whip': {'amount': .3, 'd': .4}}, {'local_whip': {'dir': 'up'}}, {'local_zoom_blur': {'amount': 1, 'center': [.2, .8]}},
                {'local_halftone': {'spacing': 10, 'mix': .9, 'ink': '#000000', 'paper': '#ffffff'}}, {'local_speed_lines': {'count': 64, 'opacity': .5, 'every': 2}},
                {'local_frame_slices': {'amount': .12, 'continuous': True, 'n': 12}}, {'local_selective_color': {'hue': 10, 'tolerance': 25, 'soft': 0}},
                {'local_posterize': {'levels': 4}}, {'local_paper_frame': {'mode': 'filmstrip'}}, {'local_paper_frame': True}]
        for fx in good:
            with self.subTest(fx=fx):
                validate(edit(fx=fx))
        validate(edit(post={'local_posterize': {'levels': 3}}))
        validate(edit(layers=[{'type': 'local_halftone', 'spacing': 6, 'phase': 'final'}]))
        validate(edit(cam={'local_measured': {'f0': 0, 'f1': 30, 'pan_x': .08, 'pan_y': 0, 'zoom': .2, 'roll_deg': 5}}))
        validate(edit(cam={'local_measured': {'f0': 5, 'f1': 6, 'zoom': -.2}}))

    def test_rejected_forms(self):
        bad = [{'local_whip': {'amount': 2}}, {'local_whip': {'dir': 'diagonal'}}, {'local_halftone': {'spacing': 1}}, {'local_speed_lines': {'count': 1.5}},
               {'local_frame_slices': {'continuous': 'yes'}}, {'local_selective_color': {'hue': 400}}, {'local_posterize': {'levels': 1}},
               {'local_paper_frame': {'mode': 'polaroid'}}, {'local_zoom_blur': {'center': [.5]}}, {'local_whip': {'speed': 3}}]
        for fx in bad:
            with self.subTest(fx=fx), self.assertRaises(ContractError):
                validate(edit(fx=fx))
        for cam in ({'local_measured': {'f0': 10, 'f1': 5}}, {'local_measured': {'f1': 5}}, {'local_measured': {'f0': 0, 'f1': 5, 'roll': 3}},
                    {'local_measured': {'f0': 0, 'f1': 5, 'pan_x': 2}}):
            with self.subTest(cam=cam), self.assertRaises(ContractError):
                validate(edit(cam=cam))

    def test_scramble_text_needs_declared_font(self):
        with self.assertRaisesRegex(ContractError, 'text and family'):
            validate(edit(fx={'local_scramble_text': {'text': 'HI'}}))
        with self.assertRaisesRegex(ContractError, 'declared font'):
            validate(edit(fx={'local_scramble_text': {'text': 'HI', 'family': 'Nope'}}))
        validate(edit(fx={'local_scramble_text': {'text': 'HI', 'family': 'F', 'd': .5, 'pos': [.5, .8]}}, fonts=[{'family': 'F', 'url': 'f.ttf'}]))


if __name__ == '__main__':
    unittest.main()
