"""Credentials of the Comfy SDK client for local and cloud endpoints.

These tests build the real comfy_sdk.Comfy client. httpx's transport is stubbed, so
requests are recorded instead of sent: nothing leaves the process and no job is submitted.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from openkatana import comfy
from openkatana.render import write_json

KEY = 'test-only-not-a-real-key'
LOCAL = 'http://127.0.0.1:8189'
CLOUD = 'https://cloud.comfy.org'


def running_job():
    urls = {'self': '/api/v2/jobs/job-1', 'events': '/api/v2/jobs/job-1/events', 'cancel': '/api/v2/jobs/job-1/cancel'}
    return {'id': 'job-1', 'status': 'running', 'created_at': '2026-10-23T00:00:00Z', 'started_at': None,
            'completed_at': None, 'expires_at': '2026-10-30T00:00:00Z', 'queue_position': None, 'progress': None,
            'outputs': [], 'error': None, 'urls': urls}


class ClientCredentialTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'COMFY_API_KEY': KEY})
        env.start(); self.addCleanup(env.stop)
        for name in ('COMFY_BASE_URL', 'COMFY_ROUTER_BASE_URL', 'OPENKATANA_PRIVATE_COMFY_ENDPOINTS'):
            os.environ.pop(name, None)
        self.requests = []

        def record(transport, request):
            self.requests.append(request)
            return httpx.Response(200, json=running_job())
        wire = patch.object(httpx.HTTPTransport, 'handle_request', autospec=True, side_effect=record)
        wire.start(); self.addCleanup(wire.stop)
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.job = Path(tmp.name) / 'job'

    def collect(self, endpoint, execution='local'):
        """Run comfy.collect on a submitted job and return the one request it made."""
        write_json(self.job / 'job.json', {'schema': 1, 'endpoint': endpoint, 'execution': execution,
                                           'job_id': 'job-1', 'state': 'submitted'})
        self.assertEqual(comfy.collect(self.job)['state'], 'running')
        self.assertEqual(len(self.requests), 1)
        return self.requests[0]

    def test_local_client_has_no_credentials(self):
        with comfy.client_at(LOCAL) as client:
            self.assertIn('authenticated=False', repr(client))
            # The key is hidden only while the client is built.
            self.assertEqual(os.environ['COMFY_API_KEY'], KEY)
        self.assertEqual(os.environ['COMFY_API_KEY'], KEY)

    def test_local_requests_carry_no_authorization(self):
        request = self.collect(LOCAL)
        self.assertEqual(str(request.url), LOCAL + '/api/v2/jobs/job-1')
        self.assertNotIn('authorization', request.headers)

    def test_private_endpoint_requests_carry_no_authorization(self):
        os.environ['OPENKATANA_PRIVATE_COMFY_ENDPOINTS'] = '["http://comfy-worker:8189"]'
        request = self.collect('http://comfy-worker:8189')
        self.assertEqual(str(request.url), 'http://comfy-worker:8189/api/v2/jobs/job-1')
        self.assertNotIn('authorization', request.headers)

    def test_key_is_restored_when_the_body_raises(self):
        with self.assertRaisesRegex(RuntimeError, 'body failed'):
            with comfy.client_at(LOCAL):
                raise RuntimeError('body failed')
        self.assertEqual(os.environ['COMFY_API_KEY'], KEY)
        self.assertNotIn('COMFY_BASE_URL', os.environ)

    def test_key_is_restored_when_the_client_cannot_be_built(self):
        # The SDK rejects this router URL after it has resolved the key.
        os.environ['COMFY_ROUTER_BASE_URL'] = 'ftp://router.invalid'
        with self.assertRaisesRegex(ValueError, 'COMFY_ROUTER_BASE_URL'):
            with comfy.client_at(LOCAL):
                self.fail('the client should not have been built')
        self.assertEqual(os.environ['COMFY_API_KEY'], KEY)
        self.assertNotIn('COMFY_BASE_URL', os.environ)

    def test_unset_key_stays_unset(self):
        del os.environ['COMFY_API_KEY']
        with comfy.client_at(LOCAL) as client:
            self.assertIn('authenticated=False', repr(client))
        self.assertNotIn('COMFY_API_KEY', os.environ)

    def test_cloud_client_keeps_the_key(self):
        with comfy.client_at(CLOUD, 'cloud') as client:
            self.assertIn('authenticated=True', repr(client))
        request = self.collect(CLOUD, 'cloud')
        self.assertEqual(str(request.url), CLOUD + '/api/v2/jobs/job-1')
        self.assertEqual(request.headers['authorization'], 'Bearer ' + KEY)
        self.assertEqual(os.environ['COMFY_API_KEY'], KEY)


if __name__ == '__main__':
    unittest.main()
