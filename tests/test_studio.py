"""F-STU-001 / F-STU-003: studio look validation, presets and named camera moves."""
import json
import unittest

from openkatana.contracts import ContractError, validate
from openkatana.native import normalize
from openkatana.studio_looks import FX, PRESETS

BASE = {'canvas': {'w': 64, 'h': 36, 'fps': 30, 'frames': 60}, 'clips': {'A': {'frames_dir': 'f', 'n': 30, 'fps': 30, 'w': 64, 'h': 36}}}


def shot(**f):
    return {**json.loads(json.dumps(BASE)), 'shots': [{'f0': 0, 'f1': 60, 'clip': 'A', **f}]}


class StudioLookTests(unittest.TestCase):
    def test_presets_and_effects_validate(self):
        self.assertEqual(len(PRESETS), 13)
        for name in PRESETS:
            validate(shot(look=name))
        self.assertEqual(normalize(shot(look='mono_noir'))['shots'][0]['look']['type'], 'studio')
        for fx in FX:
            if fx != 'contour_glow':
                validate(shot(look={'type': 'studio', 'fx': [{'type': fx}]}))
        validate(shot(look={'type': 'studio', 'grade': {'sat': 1.2, 'split': [[.4, .5, .6], [.6, .5, .4], .5]}, 'fx': [{'type': 'grain', 'amt': .5}]}))

    def test_errors(self):
        cases = [({'type': 'studio', 'fx': [{'type': 'sparkle'}]}, 'effect type'), ({'type': 'studio', 'fx': [{'type': 'blur', 'radius': 3}]}, 'unsupported fields'),
                 ({'type': 'studio', 'grade': {'contrast': 9}}, 'out of range'), ({'type': 'studio', 'grade': {'split': [[.5, .5, .5]]}}, 'split'),
                 ({'type': 'studio', 'fx': [{'type': 'contour_glow'}]}, 'subject matte'), ({'type': 'studio', 'fx': [{'type': 'tape', 'amt': 2}]}, 'amt')]
        for look, error in cases:
            with self.assertRaisesRegex(ContractError, error, msg=look):
                validate(shot(look=look))


class CameraMoveTests(unittest.TestCase):
    def cam(self, cam, **top):
        return normalize({**shot(cam=cam), **top})['shots'][0]['cam']

    def test_moves_map_to_camera_keys(self):
        beat = {'beat': {'bpm': 120, 't0': 0}}
        self.assertEqual(self.cam({'zoom.crash': {'scale': 3, 'dur': .4}}), {'crash': {'v': 3, 'd': .4, 'at': .4, 'ease': 'inout3'}, 'shutter': .5})
        self.assertEqual(self.cam({'zoom.punch': {'times': 'beats'}}, **beat)['punch']['hits'], [0.0, .5, 1.0, 1.5])
        self.assertEqual(self.cam({'shake.beat': {'times': 'snare'}}, **beat)['shake']['hits'], [.5, 1.5])
        self.assertEqual(self.cam({'zoom.in_out': {'times': 'offbeat'}}, **beat)['pulse']['hits'], [.25, .75, 1.25, 1.75])
        self.assertEqual(self.cam({'zoom.punch': {'times': [0.5, 9]}})['punch']['hits'], [.5])
        roll = self.cam({'roll': {'angle': [0, 90], 'dir': 'cw'}})
        self.assertAlmostEqual(roll['roll']['to'], 1.5708, places=3); self.assertTrue(roll['cover'])
        self.assertEqual(self.cam({'handheld': {'profile': 'calm'}})['handheld']['amp'], 4)
        d = self.cam({'drift': {'dx': .1, 'zoom': 1.2}})
        self.assertEqual((d['pan']['dx'], d['zoom']['z1'], d['cover']), (.05, 1.2, True))
        validate({**shot(cam={'zoom.crash': {'scale': 3}, 'zoom.in_out': {'times': 'beats'}}), 'beat': {'bpm': 120, 't0': 0}})

    def test_move_errors(self):
        for cam, error, top in (({'zoom.punch': {'times': 'beats'}}, 'needs a top-level beat', {}), ({'zoom.punch': {'mode': 'ladder'}}, 'only bounce', {}),
                                ({'shake.beat': {'profile': 'quake'}}, 'profile', {}), ({'zoom.crash': {'speed': 2}}, 'unsupported fields', {}),
                                ({'handheld': {'profile': 'drunk'}}, 'profile', {})):
            with self.assertRaisesRegex(ContractError, error, msg=cam):
                validate({**shot(cam=cam), **top})
        with self.assertRaisesRegex(ContractError, 'shot camera'):
            normalize({**shot(), 'cam': {'zoom.punch': {'times': 'beats'}}, 'beat': {'bpm': 120, 't0': 0}})


if __name__ == '__main__':
    unittest.main()
