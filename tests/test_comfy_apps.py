import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from openkatana.agent_api import AgentAPI, TOOLS
from openkatana.comfy_apps import catalog, call, dispatch, job_status, start_background
from openkatana.comfy_app_templates import templates

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('openkatana_node_bridge', ROOT / 'comfy_nodes/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class ComfyAppsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_every_shared_tool_is_exposed_and_catalog_current(self):
        self.assertEqual(set(TOOLS), set(bridge.TOOLS))
        self.assertEqual(catalog(), bridge.CATALOG)
        for name in TOOLS:
            node = bridge.NODE_CLASS_MAPPINGS['OpenKatana_' + name]()
            with patch.object(bridge, 'invoke', return_value={'checked': name}) as invoke, patch.object(bridge, 'result_media', return_value=[]), patch.dict(sys.modules, {'folder_paths': types.SimpleNamespace(get_temp_directory=lambda: str(self.root))}):
                result = node.execute('', '{}')
                self.assertEqual(json.loads(result['result'][0]), {'checked': name})
                invoke.assert_called_once_with('call', tool=name, arguments={})

    def test_project_and_unknown_arguments_are_not_silently_changed(self):
        result = call(self.root, 'create_project', {'name': 'App', 'project_id': 'film'})
        self.assertEqual(result['project_id'], 'film')
        self.assertEqual(AgentAPI(self.root).get_project('film')['name'], 'App')
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            call(self.root, 'get_project', {'project_id': 'film', 'extra': True})
        with self.assertRaisesRegex(ValueError, 'disagree'):
            bridge.arguments_for('get_project', 'film', '{"project_id":"other"}')
        with self.assertRaises(ValueError):
            call(self.root, 'create_project', {'name': 'Escape', 'project_id': '../escape'})

    def test_paid_and_remote_calls_fail_before_execution(self):
        for args in ({'execution': 'cloud'}, {'allow_paid': True}, {'endpoint': 'https://cloud.comfy.org'},
                     {'native_endpoint': 'http://example.com:8188'}):
            with patch.object(AgentAPI, 'call') as method, self.assertRaises(ValueError):
                call(self.root, 'submit_workflow', args)
            method.assert_not_called()

    def test_old_cloud_receipts_cannot_be_collected(self):
        api = AgentAPI(self.root)
        api.create_project('App', 'film')
        folder = self.root / 'film' / 'model-job'
        folder.mkdir()
        (folder / 'job.json').write_text(json.dumps({'execution': 'cloud', 'endpoint': 'https://cloud.comfy.org'}))
        with self.assertRaisesRegex(ValueError, 'Cloud receipts'):
            call(self.root, 'collect_workflow', {'project_id': 'film', 'directory': 'model-job'})

    def test_background_job_process_finishes_and_does_not_repeat(self):
        result = start_background(self.root, 'create_project', {'project_id': 'film', 'name': 'Background'})
        deadline = time.monotonic() + 20
        while result['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(.1)
            result = job_status(self.root, result['job_id'])
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(result, job_status(self.root, result['job_id']))
        self.assertEqual(AgentAPI(self.root).get_project('film')['name'], 'Background')

    def test_queue_blocking_model_operations_are_dispatched_in_background(self):
        for tool in ('process_clip', 'run_model_workflow', 'collect_workflow'):
            with patch('openkatana.comfy_apps.start_background', return_value={'state': 'running'}) as start:
                self.assertEqual(dispatch({'action': 'call', 'workspace': str(self.root), 'tool': tool, 'arguments': {}}), {'state': 'running'})
                start.assert_called_once()

    def test_result_preview_stays_in_workspace(self):
        from PIL import Image
        import types
        inside = self.root / 'project' / 'picture.png'
        inside.parent.mkdir()
        Image.new('RGB', (10, 10)).save(inside)
        preview = self.root / 'previews'
        module = types.SimpleNamespace(get_temp_directory=lambda: str(preview))
        with patch.dict(sys.modules, {'folder_paths': module}), patch.object(bridge, 'configuration', return_value={'workspace': str(inside.parent)}):
            result = bridge.result_media({'preview_images': [str(inside), str(ROOT / 'openkatana/web/openkatana-logo.jpg')]})
        self.assertEqual(len(result), 1)
        self.assertEqual((preview / result[0]['subfolder'] / result[0]['filename']).read_bytes(), inside.read_bytes())

    def test_templates_have_real_nodes_and_portable_bindings(self):
        for name, workflow in templates().items():
            self.assertTrue(name.endswith('.app.json'))
            self.assertTrue(workflow['extra']['linearMode'])
            self.assertEqual(workflow['extra']['linearData']['outputs'], [1, 2])
            for node in workflow['nodes']:
                self.assertTrue(node['type'] in bridge.NODE_CLASS_MAPPINGS or node['type'] == 'PreviewAny')
            node = workflow['nodes'][0]
            fields = bridge.NODE_CLASS_MAPPINGS[node['type']].INPUT_TYPES()['required']
            for widget, field in workflow['extra']['linearData']['inputs']:
                self.assertIn(field, fields)
                self.assertEqual(widget, workflow['id'] + ':1:' + field)

    def test_text_result_is_a_downloadable_app_output(self):
        import types
        module = types.SimpleNamespace(get_temp_directory=lambda: str(self.root))
        with patch.dict(sys.modules, {'folder_paths': module}), patch.object(bridge, 'configuration', return_value={'workspace': str(self.root)}):
            result = bridge.response({'state': 'succeeded', 'message': '<script>plain text</script>'})
        item = result['ui']['files'][0]
        self.assertEqual(item['content'], result['result'][0])
        self.assertEqual((self.root / item['subfolder'] / item['filename']).read_text(encoding='utf8'), item['content'])


if __name__ == '__main__':
    unittest.main()
