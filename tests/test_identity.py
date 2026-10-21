"""F-ID-001: identity references and the strict gate for generated clips; plus the strict inspection gate's handling of
generated assets (no sha256) and imported excerpts (the original source's inspection counts)."""
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from openkatana import gates
from openkatana.contracts import ContractError
from openkatana.identity import asset_key, bind, record_review


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        for d in ('plates/r', 'plates/g', 'plates/e'):
            (self.root / d).mkdir(parents=True)
            Image.new('RGB', (64, 36), (90, 60, 40)).save(self.root / d / '00000.png')
        (self.root / 'plates/g/comfy-origin.json').write_text(json.dumps({'job_id': 'j'}))
        clip = lambda d: {'frames_dir': d, 'n': 1, 'fps': 30, 'w': 64, 'h': 36, 'pattern': '%05d.png'}
        self.ref = {'id': 'r1', 'kind': 'image', 'sha256': 'a' * 64, 'clip': clip('plates/r')}
        self.gen = {'id': 'g1', 'kind': 'image', 'clip': clip('plates/g'), 'provenance': {'job_id': 'j'}}
        self.exc = {'id': 'e1', 'kind': 'video', 'sha256': 'c' * 64, 'name': 'excerpt', 'clip': clip('plates/e')}
        (self.root / '.openkatana/imports').mkdir(parents=True)
        (self.root / '.openkatana/imports/e1.json').write_text(json.dumps({'sha256': 'd' * 64}))
        self.state = {'assets': [self.ref, self.gen, self.exc], 'revision': 'r', 'timeline': {'clips': {'G': clip('plates/g'), 'E': clip('plates/e')}}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_identity_gate(self):
        gates.set_strict(self.root, True); gates.record_preview(self.root, 'r', [0])
        gates.record_inspection(self.root, self.root / 'plates/r/00000.png', 'test')   # unrelated file
        data = gates.load(self.root); data['inspected']['d' * 64] = {'via': 'original source'}; gates.save(self.root, data)
        self.assertEqual(gates.missing(self.root, self.state), [])                        # no references yet; excerpt satisfied via its source; generated asset skipped
        rec = bind(self.root, 'lead', [self.ref])
        self.assertEqual(rec['assets'], [{'id': 'r1', 'sha256': 'a' * 64}])
        self.assertEqual(gates.missing(self.root, self.state), ['inspect generated clip G against identity reference lead with inspect_identity'])
        key = asset_key(self.root, self.gen)
        record_review(self.root, key, [rec], False)
        self.assertIn('rejected', gates.missing(self.root, self.state)[0])
        record_review(self.root, key, [rec], True)
        self.assertEqual(gates.missing(self.root, self.state), [])
        rec2 = bind(self.root, 'lead', [self.ref, self.exc])                               # new digest: review again
        self.assertNotEqual(rec2['digest'], rec['digest']); self.assertEqual(len(gates.missing(self.root, self.state)), 1)

    def test_bind_errors(self):
        with self.assertRaisesRegex(ContractError, 'role'):
            bind(self.root, 'x', [self.ref], role='enemy')
        with self.assertRaisesRegex(ContractError, 'at least one'):
            bind(self.root, 'x', [])


if __name__ == '__main__':
    unittest.main()
