"""Comfy preflight checks.

F-GEN-001: a submission to an unreachable local Comfy API proxy fails with a structured, actionable error and
writes nothing (checked on a closed loopback port, so no job can be submitted).

Required V3 autogrow containers: workflow preflight accepts their flattened ports and leaves the port count to the
graph check."""
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def closed_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close(); return port


class ComfyPreflightTests(unittest.TestCase):
    def test_unreachable_proxy_is_named_and_nothing_written(self):
        from openkatana.comfy import submit
        with tempfile.TemporaryDirectory() as tmp:
            wf = Path(tmp) / 'wf.json'
            wf.write_text(json.dumps({'1': {'class_type': 'EmptyImage', 'inputs': {'width': 8, 'height': 8, 'batch_size': 1, 'color': 0}},
                                      '2': {'class_type': 'SaveImage', 'inputs': {'images': ['1', 0], 'filename_prefix': 'x'}}}))
            port = closed_port(); out = Path(tmp) / 'job'
            with self.assertRaises(ConnectionError) as ctx:
                submit(wf, out, f'http://127.0.0.1:{port}')
            message = str(ctx.exception)
            self.assertIn(f'http://127.0.0.1:{port}', message); self.assertIn('comfy-api-proxy', message); self.assertIn('Nothing was submitted', message)
            self.assertFalse(out.exists())


# Input contract served at /object_info by ComfyUI 0.42.0 for the core BatchImagesNode
# (comfy_extras/nodes_post_processing.py). Its autogrow container is required and needs at least one image.
BATCH_IMAGES = {'input': {'required': {'images': ['COMFY_AUTOGROW_V3', {'template': {
    'input': {'required': {'image': ['IMAGE', {}]}}, 'prefix': 'image', 'min': 1, 'max': 50}}]}},
    'output': ['IMAGE']}


class RequiredAutogrowTests(unittest.TestCase):
    """An API workflow carries a required autogrow container only as its flattened ports (images.image0, ...)."""
    def setUp(self):
        self.info = {'BatchImagesNode': BATCH_IMAGES,
                     'LoadImage': {'input': {'required': {'image': [['first.png', 'second.png'], {'image_upload': True}]}},
                                   'output': ['IMAGE', 'MASK']}}
        self.ports = {'images.image0': ['1', 0], 'images.image1': ['2', 0]}
        self.graph = {'1': {'class_type': 'LoadImage', 'inputs': {'image': 'first.png'}},
                      '2': {'class_type': 'LoadImage', 'inputs': {'image': 'second.png'}},
                      '3': {'class_type': 'BatchImagesNode', 'inputs': self.ports}}

    def check(self):
        from openkatana.workflows import preflight
        with patch('openkatana.workflows.capabilities', return_value=self.info):
            return preflight(self.graph, 'local', ['BatchImagesNode'])

    def test_flattened_ports_satisfy_the_container(self):
        result = self.check()
        self.assertEqual(result['errors'], []); self.assertTrue(result['ready'])

    def test_no_ports_reported_once_as_too_few(self):
        self.ports.clear()
        self.assertEqual(self.check()['errors'], ['3.images: too few references'])

    def test_wrong_port_type_and_literal_container_key_still_rejected(self):
        self.ports['images.image1'] = ['2', 1]
        self.assertEqual(self.check()['errors'], ['3.images.image1: MASK output cannot feed IMAGE'])
        self.ports.clear(); self.ports['images'] = ['1', 0]
        self.assertEqual(self.check()['errors'], ['3.images: too few references', '3.images: unknown input'])


if __name__ == '__main__':
    unittest.main()
