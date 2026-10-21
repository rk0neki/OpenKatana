import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

from openkatana.comfy_apps import dispatch
from openkatana.comfy_media import transfer_directory
from openkatana.render import chrome_path

ROOT = Path(__file__).resolve().parents[1]


class PrelaunchTests(unittest.TestCase):
    def test_public_receipt_export_decodes_escaped_paths_and_rejects_unknown_roots(self):
        from scripts.export_validation import portable
        private = 'C:' + chr(92) + 'Users' + chr(92) + 'example' + chr(92) + 'project'
        data = json.loads(json.dumps({'output': private + chr(92) + 'work' + chr(92) + 'video.mp4'}))
        self.assertEqual(portable(data, [private]), {'output': 'work/video.mp4'})
        with self.assertRaisesRegex(ValueError, 'Unmapped personal path'):
            portable(data, [])

    def test_still_source_preview_does_not_seek_an_image_stream(self):
        from PIL import Image
        from openkatana.preview import source_frames
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'photo.jpg'
            Image.new('RGB', (1600, 800), '#2277aa').save(source)
            result = source_frames(source, root / 'preview', [0])
            with Image.open(result['preview_images'][0]) as image:
                self.assertEqual(image.size, (768, 384))

    def test_chromium_fallback_works_inside_an_existing_event_loop(self):
        import asyncio
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'chromium'
            exe.touch()
            runtime = types.SimpleNamespace(chromium=types.SimpleNamespace(executable_path=str(exe)))
            from contextlib import nullcontext
            with patch('openkatana.render.shutil.which', return_value=None), patch.dict('os.environ', {'OPENKATANA_CHROME': ''}), \
                 patch('openkatana.render.Path.is_file', lambda p: p == exe), \
                 patch('openkatana.render.playwright', return_value=lambda: nullcontext(runtime)):
                async def check():
                    self.assertEqual(chrome_path(), str(exe))
                asyncio.run(check())

    def test_optical_flow_worker_runs_without_comfy_dependencies(self):
        import uuid
        with tempfile.TemporaryDirectory() as temp:
            key = uuid.uuid4().hex
            folder = transfer_directory(temp, key); folder.mkdir(parents=True)
            a = np.zeros((2, 48, 64, 3), dtype='uint8')
            a[0, 16:32, 12:28] = 255; a[1, 16:32, 16:32] = 255
            np.save(folder / 'input.npy', a)
            result = dispatch({'action': 'interpolate_frames', 'workspace': temp,
                               'transfer_id': key, 'multiplier': 2})
            b = np.load(result['output'], allow_pickle=False)
            self.assertEqual(b.shape, (4, 48, 64, 3))
            np.testing.assert_array_equal(b[0], a[0])
            np.testing.assert_array_equal(b[-1], a[-1])
            self.assertFalse(np.array_equal(b[0], b[1]))
            with self.assertRaises(ValueError):
                transfer_directory(temp, '../escape')

    def test_comfy_runtime_config_passes_browser_and_drops_credentials(self):
        spec = importlib.util.spec_from_file_location('bridge_under_test', ROOT/'comfy_nodes/bridge.py')
        bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)
        config = {'python': sys.executable, 'workspace': '.', 'checkout': str(ROOT), 'chrome': 'test-browser'}
        reply = types.SimpleNamespace(stdout='{"ok":true,"result":{}}', stderr='')
        with patch.object(bridge, 'configuration', return_value=config), \
             patch.object(bridge.subprocess, 'run', return_value=reply) as run, \
             patch.dict('os.environ', {'COMFY_API_KEY': 'test-not-a-real-key'}):
            bridge.invoke('catalog')
        self.assertEqual(run.call_args.kwargs['env']['OPENKATANA_CHROME'], 'test-browser')
        self.assertNotIn('COMFY_API_KEY', run.call_args.kwargs['env'])

    def test_bundle_rejects_json_escaped_personal_paths(self):
        from scripts import release_bundle
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); (path/'docs').mkdir()
            private = 'C:' + chr(92) + 'Users' + chr(92) + 'private-user' + chr(92) + 'work'
            (path/'docs/receipt.json').write_text(json.dumps({'output':private}))
            with patch.object(release_bundle, 'ROOT', path), self.assertRaisesRegex(ValueError, 'Personal absolute path'):
                release_bundle.entries()


if __name__ == '__main__':
    unittest.main()
