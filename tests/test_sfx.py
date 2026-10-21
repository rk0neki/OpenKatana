"""F-SFX-001: synthesised sound effects and audio cues."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from openkatana.contracts import ContractError, validate
from openkatana.sfx import LIBRARY, ensure, generate


class SfxTests(unittest.TestCase):
    def test_deterministic_and_normalised(self):
        for name in LIBRARY:
            a, b = generate(name, 2), generate(name, 2)
            self.assertTrue(np.array_equal(a, b)); self.assertAlmostEqual(float(np.abs(a).max()), .9, places=5)
            self.assertFalse(np.array_equal(generate(name, 1), a) and name not in ('pop', 'ding'))

    def test_cues_validate_and_generate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'f').mkdir()
            from PIL import Image; Image.new('RGB', (32, 18)).save(root / 'f' / '00000.png')
            edit = {'canvas': {'w': 32, 'h': 18, 'fps': 30, 'frames': 60}, 'clips': {'A': {'frames_dir': 'f', 'n': 1, 'fps': 30, 'w': 32, 'h': 18}},
                    'shots': [{'f0': 0, 'f1': 60, 'clip': 'A', 'speed': 0}], 'audio': {'mode': 'mix', 'cues': [{'sfx': 'hit', 'at': .5}, {'sfx': 'whoosh', 'at': 1, 'level_db': -20}]}}
            validate(edit, root)
            self.assertTrue((root / '.openkatana' / 'sfx' / 'hit-1-v1.wav').is_file())
            for cue, error in (({'sfx': 'boing', 'at': 0}, 'one of'), ({'sfx': 'hit', 'at': 0, 'variant': 9}, 'variant'), ({'sfx': 'hit'}, 'at')):
                bad = {**edit, 'audio': {'mode': 'mix', 'cues': [cue]}}
                with self.assertRaisesRegex(ContractError, error):
                    validate(bad, root)
            self.assertEqual(ensure(root, 'pop', 3), root / '.openkatana' / 'sfx' / 'pop-3-v1.wav')


if __name__ == '__main__':
    unittest.main()
