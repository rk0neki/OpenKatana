"""Bundled third-party files: OFL fonts (each with its licence and a manifest row), the YuNet face model (MIT, known
release hash), presets resolving to recipe families, and transcription refusing models that are not cached."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class BundledAssetTests(unittest.TestCase):
    def test_every_bundled_font_has_its_ofl_text_and_hash(self):
        from openkatana.bundled_fonts import FOLDER, manifest
        rows = manifest()
        self.assertGreaterEqual(len(rows), 20)
        self.assertEqual(sorted(p.name for p in FOLDER.glob('*.ttf')), sorted(rows))
        for name, row in rows.items():
            self.assertEqual(hashlib.sha256((FOLDER / name).read_bytes()).hexdigest(), row['sha256'], name)
            text = (FOLDER / row['license_file']).read_text(encoding='utf-8').upper()
            self.assertIn('SIL OPEN FONT LICENSE', text, name)
            self.assertEqual(row['license'], 'OFL-1.1')
        notices = (ROOT / 'THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8')
        self.assertTrue(all(f'`{name}`' in notices for name in rows))

    def test_importing_a_bundled_font_copies_its_licence(self):
        from openkatana import projects
        from openkatana.bundled_fonts import FOLDER
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'project.json').write_text(json.dumps({'name': 'x', 'assets': []}))
            asset = projects.import_asset(root, FOLDER / 'anton_Anton-Regular.ttf')
            self.assertEqual(asset['kind'], 'font'); self.assertEqual(asset['license']['id'], 'OFL-1.1')
            self.assertTrue((root / 'media' / asset['license']['file']).is_file())
            self.assertEqual(json.loads((root / 'project.json').read_text())['assets'][0]['license']['file'], asset['license']['file'])

    def test_yunet_model_is_the_published_release(self):
        from openkatana.vision import YUNET
        self.assertEqual(hashlib.sha256(YUNET.read_bytes()).hexdigest(), '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4')
        self.assertIn('MIT License', (YUNET.parent / 'face_detection_yunet-LICENSE.txt').read_text(encoding='utf-8'))

    def test_presets_resolve_to_recipe_families(self):
        from openkatana.contracts import ContractError
        from openkatana.presets import PRESETS, catalog, finish, resolve
        from openkatana.recipes import FAMILIES
        self.assertEqual(len(catalog()), len(PRESETS))
        for name, p in PRESETS.items():
            self.assertIn(resolve(name)[0], FAMILIES)
        self.assertEqual(resolve('mono_noir'), ('mono_noir', None))
        edit = finish({'look': 'mono_noir', 'post': {'letterbox': {'v': .1}}}, PRESETS['travel-diary'])
        self.assertEqual(edit, {'look': 'golden_hour'})
        with self.assertRaises(ContractError):
            resolve('vaporwave')

    def test_transcription_never_reaches_for_an_uncached_model(self):
        from openkatana import transcribe
        from openkatana.contracts import ContractError
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {'HF_HUB_CACHE': tmp}):
            self.assertEqual(transcribe.installed(), [])
            snap = Path(tmp) / 'models--Systran--faster-whisper-tiny.en' / 'snapshots' / 'abc'; snap.mkdir(parents=True)
            (snap / 'model.bin').write_bytes(b'x'); (snap / 'config.json').write_text('{}')
            self.assertEqual(transcribe.installed(), ['tiny.en'])
            if transcribe.available():
                with self.assertRaises(ContractError) as ctx:
                    transcribe.transcribe(Path(tmp) / 'a.wav', Path(tmp) / 'out', model='medium')
                self.assertIn('not in the local cache', str(ctx.exception))
                with self.assertRaises(ContractError):
                    transcribe.transcribe(Path(tmp) / 'a.wav', Path(tmp) / 'out2', model='tiny.en', language='fr')


if __name__ == '__main__':
    unittest.main()
