"""The Time effect pack (web/fx_time.js): After Effects' Echo, Time Displacement, Posterize Time and frame blending,
each reading other frames of its own shot."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from openkatana.contracts import ContractError, validate

W, H, N = 96, 54, 12
STEP, SIZE = 8, 6                       # the square moves 8 px right per frame (no overlap)


def _chrome():
    try:
        from openkatana.render import chrome_path
        return bool(chrome_path()) and bool(shutil.which('ffmpeg'))
    except Exception:
        return False


class TimeEffectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        (self.root / 'f').mkdir(); (self.root / 'm').mkdir()
        for i in range(N):                # a white square moving right over black
            a = np.zeros((H, W, 3), np.uint8); x = 4 + STEP * i
            a[20:20 + SIZE, x:x + SIZE] = 255
            Image.fromarray(a).save(self.root / 'f' / f'{i:05d}.png')
        Image.new('RGB', (W, H), (255, 255, 255)).save(self.root / 'm' / '00000.png')   # an all-white map

    def edit(self, fx, frames=N, extra=None):
        shot = {'f0': 0, 'f1': frames, 'clip': 'A', 'fx': fx, **(extra or {})}
        return {'canvas': {'w': W, 'h': H, 'fps': 30, 'frames': frames, 'bg': '#000000'},
                'clips': {'A': {'frames_dir': 'f', 'n': N, 'fps': 30, 'w': W, 'h': H},
                          'M': {'frames_dir': 'm', 'n': 1, 'fps': 30, 'w': W, 'h': H}},
                'shots': [shot]}

    def render(self, edit, name='o'):
        from openkatana.render import render
        (self.root / 't.json').write_text(json.dumps(edit))
        out = self.root / name
        shutil.rmtree(out, ignore_errors=True)
        render(self.root / 't.json', out)
        n = edit['canvas']['frames']
        return [np.asarray(Image.open(out / 'frames' / f'{i:05d}.png').convert('RGB')).astype(int) for i in range(n)]

    def square(self, frame):
        return (slice(20, 20 + SIZE), slice(4 + STEP * frame, 4 + STEP * frame + SIZE))

    def test_validation(self):
        validate(self.edit({'local_echo': {'echo_time': -.1, 'number_of_echoes': 16, 'starting_intensity': .8, 'decay': .5,
                                           'operator': 'composite_back', 'at': .2}}), self.root)
        validate(self.edit({'local_time_displacement': {'map': 'radial', 'center': [.3, .6], 'max_displacement': [[0, 0], [1, .5, 'ease']],
                                                        'levels': 16, 'invert': True}}), self.root)
        validate(self.edit({'local_time_displacement': {'clip': 'M', 'src': .5, 'speed': 2, 'loop': 'pingpong'}}), self.root)
        validate(self.edit({'local_posterize_time': {'fps': 8}, 'local_frame_blend': {'samples': 16, 'shutter': 1}}), self.root)
        validate(self.edit({'local_echo': True, 'local_posterize_time': True, 'local_time_displacement': True}), self.root)
        for fx, error in (({'local_echo': {'operator': 'difference'}}, 'one of add'), ({'local_echo': {'number_of_echoes': 17}}, 'out of range'),
                          ({'local_echo': {'number_of_echoes': 1.5}}, 'integer'), ({'local_echo': {'decay': 2}}, 'out of range'),
                          ({'local_echo': {'echo_frames': 2}}, 'unsupported fields: echo_frames'),
                          ({'local_time_displacement': {'map': 'noise'}}, 'one of horizontal'),
                          ({'local_time_displacement': {'map': 'clip'}}, 'needs clip'),
                          ({'local_time_displacement': {'map': 'self', 'clip': 'M'}}, 'goes with map "clip"'),
                          ({'local_time_displacement': {'clip': 'Z'}}, "clip 'Z' is not in clips"),
                          ({'local_time_displacement': {'levels': 1}}, 'out of range'),
                          ({'local_time_displacement': {'max_displacement': [[0, 1], [0, 2]]}}, 'must increase'),
                          ({'local_time_displacement': {'invert': 1}}, 'boolean'),
                          ({'local_posterize_time': {'fps': 0}}, 'out of range'), ({'local_frame_blend': {'samples': 1}}, 'out of range'),
                          ({'local_frame_blend': {'shutter': float('inf')}}, '')):
            with self.assertRaisesRegex(ContractError, error, msg=str(fx)):
                validate(self.edit(fx), self.root)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_echo(self):
        plain = self.render(self.edit({}), 'plain')
        # decay 0: the echoes have no intensity, the frame is untouched
        f = self.render(self.edit({'local_echo': {'number_of_echoes': 1, 'starting_intensity': 1, 'decay': 0}}), 'id')
        for i in range(N):
            self.assertEqual(np.abs(f[i] - plain[i]).max(), 0, msg=f'frame {i}')
        # two echoes a frame apart, halving: the square at full, the frame before at 1/2, two before at 1/4
        f = self.render(self.edit({'local_echo': {'number_of_echoes': 2, 'decay': .5}}), 'echo')
        for back, level in ((0, 255), (1, 128), (2, 64)):
            self.assertLessEqual(np.abs(f[6][self.square(6 - back)] - level).max(), 2, msg=f'{back} back')
        self.assertEqual(f[6][self.square(3)].max(), 0)                   # three back: not echoed
        self.assertLessEqual(np.abs(f[0][self.square(0)] - 255).max(), 2)  # frame 0 echoes itself (clamped): added, still white
        # maximum: the trail keeps the brightest; minimum of a moving square on black is black
        f = self.render(self.edit({'local_echo': {'number_of_echoes': 2, 'decay': .5, 'operator': 'maximum'}}), 'max')
        self.assertLessEqual(np.abs(f[6][self.square(5)] - 128).max(), 2)
        f = self.render(self.edit({'local_echo': {'number_of_echoes': 1, 'operator': 'minimum'}}, frames=4), 'min')
        self.assertEqual(f[3].max(), 0)                                   # a square never overlaps its last place: all black
        # composite_back with a full-intensity frame on top: identity
        f = self.render(self.edit({'local_echo': {'number_of_echoes': 3, 'operator': 'composite_back'}}, frames=4), 'cb')
        self.assertEqual(np.abs(f[3] - plain[3]).max(), 0)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_echo_excludes_later_items(self):
        # a grey tint (post, order 51) comes after the echo: washed once over the result. Were it inside the echoes, adding
        # them would brighten the black background by the tint 1.75 times over.
        tint = {'tint': {'color': '#808080', 'v': .5}}
        plain = self.render(self.edit(tint), 'plain')
        bg = plain[5][0, 0]
        self.assertTrue((bg > 30).all() and (bg < 100).all())
        for name, e in (('post', self.edit({**tint, 'local_echo': {'number_of_echoes': 2, 'decay': .5}})),
                        ('subject', self.edit(tint, extra={'layers': [{'type': 'local_echo', 'phase': 'subject', 'number_of_echoes': 2,
                                                                       'decay': .5}]}))):
            validate(e, self.root)
            f = self.render(e, name)
            self.assertLessEqual(np.abs(f[5][:, :3] - bg).max(), 1, msg=name)     # the background keeps one wash
            self.assertGreater(np.abs(f[5] - plain[5]).max(), 50, msg=name)       # while the square echoes

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_posterize_time(self):
        plain = self.render(self.edit({}), 'plain')
        f = self.render(self.edit({'local_posterize_time': {'fps': 15}}), 'pt')
        for i in range(0, N, 2):
            self.assertEqual(np.abs(f[i] - plain[i]).max(), 0, msg=f'frame {i}')
            self.assertEqual(np.abs(f[i + 1] - f[i]).max(), 0, msg=f'pair {i}')
        f = self.render(self.edit({'local_posterize_time': {'fps': 10}}), 'pt10')   # held for three frames
        for i in range(N):
            self.assertEqual(np.abs(f[i] - plain[i - i % 3]).max(), 0, msg=f'frame {i}')

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_time_displacement(self):
        plain = self.render(self.edit({}), 'plain')
        f = self.render(self.edit({'local_time_displacement': {'max_displacement': 0}}), 'zero')
        for i in range(N):
            self.assertEqual(np.abs(f[i] - plain[i]).max(), 0, msg=f'frame {i}')
        # horizontal, 5 frames either way in 11 slices (one frame apart): column x shows frame 6 + round(10 x / 95 - 5)
        f = self.render(self.edit({'local_time_displacement': {'max_displacement': 5 / 30, 'levels': 11}}), 'h')[6]
        self.assertGreater(np.abs(f - plain[6]).max(), 100)
        for x in (10, 40, 60, 80):
            u = x / (W - 1) * 10; a = int(u); w = u - a
            want = (1 - w) * plain[min(N - 1, max(0, 1 + a))][:, x] + w * plain[min(N - 1, max(0, 2 + a))][:, x]
            self.assertLessEqual(np.abs(f[:, x] - want).max(), 2, msg=f'column {x}')
        # an all-white clip map with invert: every pixel 5 frames back
        f = self.render(self.edit({'local_time_displacement': {'clip': 'M', 'max_displacement': 5 / 30, 'invert': True}}), 'clip')
        self.assertEqual(np.abs(f[8] - plain[3]).max(), 0)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_frame_blend(self):
        plain = self.render(self.edit({}), 'plain')
        f = self.render(self.edit({'local_frame_blend': {'samples': 3, 'shutter': 1}}), 'fb')
        self.assertLessEqual(np.abs(f[6] - (plain[6] + plain[5] + plain[4]) / 3).max(), 2)
        f = self.render(self.edit({'local_frame_blend': {'samples': 3, 'shutter': .5}}), 'fb2')   # 0, -.5, -1 frames
        self.assertLessEqual(np.abs(f[6] - (plain[6] * 1.5 + plain[5] * 1.5) / 3).max(), 2)

    @unittest.skipUnless(_chrome(), 'needs Chrome and ffmpeg')
    def test_transition_and_special(self):
        # a time effect on both sides of a transition, and next to a special shot, renders
        e = self.edit({}, frames=10)
        e['shots'] = [{'f0': 0, 'f1': 4, 'clip': 'A', 'fx': {'local_echo': {'number_of_echoes': 2}}},
                      {'f0': 4, 'f1': 7, 'clip': 'A', 'srcf': 2, 'transition': {'type': 'dissolve', 'd': 2 / 30},
                       'fx': {'local_posterize_time': {'fps': 10}, 'local_time_displacement': {'map': 'self', 'max_displacement': .1}}},
                      {'f0': 7, 'f1': 10, 'special': {'type': 'color', 'color': '#ff0000'}, 'fx': {'local_echo': True}}]
        validate(e, self.root)
        f = self.render(e, 'tr')
        self.assertEqual(len(f), 10)
        self.assertLessEqual(np.abs(f[8] - [255, 0, 0]).max(), 2)


if __name__ == '__main__':
    unittest.main()
