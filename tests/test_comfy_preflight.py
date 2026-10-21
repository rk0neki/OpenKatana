"""F-GEN-001: a submission to an unreachable local Comfy API proxy fails with a structured, actionable error and
writes nothing (checked on a closed loopback port, so no job can be submitted)."""
import json
import socket
import tempfile
import unittest
from pathlib import Path


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


if __name__ == '__main__':
    unittest.main()
