"""Hosted identity, queue, transport and file-isolation contracts. No paid calls."""
import asyncio
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from openkatana.agent_api import TOOLS
from openkatana.hosted.config import Settings
from openkatana.hosted.files import pack, unpack, safe_path
from openkatana.hosted.store import Store
from openkatana.hosted.dispatch import schemas
from openkatana.hosted.runner import command
from openkatana.hosted.service import Service


class HostedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.config = Settings(Path(self.tmp.name), 'http://127.0.0.1:8090', development=True, runtime='',
                               workspace_bytes=1024 * 1024, upload_bytes=1024)
        self.store = Store(self.config)
        self.a = self.store.add_user('A'); self.b = self.store.add_user('B')

    def test_queue_idempotency_isolation_cancellation_and_recovery(self):
        a, b = self.a['user'], self.b['user']
        first = self.store.submit(a, 'create_project', {'name': 'film'}, 'request')
        self.assertEqual(first['id'], self.store.submit(a, 'create_project', {'name': 'film'}, 'request')['id'])
        with self.assertRaisesRegex(ValueError, 'different arguments'):
            self.store.submit(a, 'create_project', {'name': 'other'}, 'request')
        with self.assertRaisesRegex(ValueError, 'not found'):
            self.store.job(b, first['id'])
        claimed = self.store.claim(); self.assertEqual(claimed['id'], first['id'])
        second = self.store.submit(a, 'get_capabilities', {}, 'two')
        self.assertIsNone(self.store.claim())
        self.store.recover()
        self.assertEqual(self.store.job(a, first['id'])['state'], 'interrupted')
        self.store.cancel(a, second['id']); self.assertIsNone(self.store.claim())
        self.assertEqual(self.store.submit(a, 'create_project', {'name': 'film'}, 'request')['state'], 'interrupted')

    def test_credentials_are_hashed_expiring_and_revocable(self):
        token = self.store.issue(self.a['user'], 'api', 60)
        self.assertEqual(self.store.authenticate(token, {'api'}), self.a['user'])
        self.assertIsNone(self.store.authenticate(token, {'session'}))
        with self.store.connect() as db:
            self.assertNotIn(token, str([dict(r) for r in db.execute('SELECT * FROM tokens')]))
        self.store.revoke_api_keys(self.a['user']); self.assertIsNone(self.store.authenticate(token, {'api'}))
        expired = self.store.issue(self.a['user'], 'api', -1)
        self.assertIsNone(self.store.authenticate(expired, {'api'}))

    def test_archive_roundtrip_and_escape_rejection(self):
        root = Path(self.tmp.name) / 'source'; root.mkdir(); (root / 'asset.txt').write_text('mine')
        out = io.BytesIO(); pack(root, out, 100); out.seek(0)
        dest = Path(self.tmp.name) / 'dest'; unpack(out, dest, 100)
        self.assertEqual((dest / 'asset.txt').read_text(), 'mine')
        for name, kind in [('../escape', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)]:
            with self.subTest(name=name):
                data = io.BytesIO()
                with tarfile.open(fileobj=data, mode='w') as t:
                    member = tarfile.TarInfo(name); member.type = kind; member.linkname = '/etc/passwd'
                    t.addfile(member)
                data.seek(0)
                with self.assertRaises(ValueError):
                    unpack(data, Path(self.tmp.name) / 'rejected', 100)
        with self.assertRaises(ValueError):
            safe_path(root, 'C:\\secret')
        with self.assertRaisesRegex(ValueError, 'quota'):
            pack(root, io.BytesIO(), 2)

    def test_all_local_tools_have_hosted_schemas(self):
        catalog = {row['name']: row for row in schemas()}
        self.assertTrue(set(TOOLS).issubset(catalog))
        self.assertTrue(all(row['inputSchema']['additionalProperties'] is False for row in catalog.values()))
        service = Service(self.config)
        with self.assertRaises(Exception):
            service.submit(self.a['user'], 'get_capabilities', {'unexpected': True})
        with self.assertRaisesRegex(ValueError, 'Comfy model service'):
            service.submit(self.a['user'], 'check_workflow', {'project_id': 'film', 'workflow': 'wf.json'})

    def test_worker_has_bounded_tmpfs_and_no_writable_host_mount(self):
        args = command(self.config, {'id': 'abc', 'tool': 'render_blender'}, Path(self.tmp.name))
        self.assertIn('--read-only', args); self.assertIn('none', args)
        self.assertIn('ALL', args); self.assertIn('1000:1000', args)
        mounts = [args[i + 1] for i, x in enumerate(args) if x == '--mount']
        self.assertEqual(len(mounts), 1); self.assertTrue(mounts[0].endswith(',readonly'))
        self.assertNotIn('/var/run/docker.sock', str(args))
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            Settings(Path(self.tmp.name), 'http://example.org')
        with self.assertRaisesRegex(ValueError, 'runsc'):
            Settings(Path(self.tmp.name), 'https://example.org', runtime='runc')

    def test_http_and_real_mcp_transport_isolate_accounts(self):
        from starlette.testclient import TestClient
        from openkatana.hosted.app import create_app
        app = create_app(self.config)
        origin = self.config.public_url
        headers = {'Origin': origin}
        with TestClient(app, base_url=origin) as client:
            self.assertEqual(client.get('/api/tools').status_code, 401)
            self.assertEqual(client.get('/healthz', headers={'Host': 'evil.example'}).status_code, 403)
            login = client.post('/auth/session', json={'access_key': self.a['access_key']}, headers=headers)
            self.assertEqual(login.status_code, 200)
            self.assertIn('HttpOnly', login.headers['set-cookie'])
            self.assertEqual(client.post('/auth/session', json={'access_key': self.a['access_key']}, headers=headers).status_code, 401)
            self.assertIn('hosted-bridge.js', client.get('/').text)
            self.assertEqual(client.post('/api/call', json={}, headers={'Origin': 'https://evil.example'}).status_code, 403)
            self.assertEqual(client.post('/api/upload', content=b'x' * 1025, headers={**headers, 'X-File-Name': 'a.png'}).status_code, 413)
            upload = client.post('/api/upload', content=b'my private file', headers={**headers, 'X-File-Name': 'a.txt'})
            self.assertEqual(upload.status_code, 200)
            path = upload.json()['source'].removeprefix('workspace://')
            own = client.get('/files/' + path); self.assertEqual(own.content, b'my private file')
            self.assertIn('attachment', own.headers['content-disposition'])
            token = self.store.issue(self.a['user'], 'api', 60)
            mh = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream'}
            request = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}}
            self.assertEqual(client.post('/mcp', json=request, headers=mh).status_code, 200)
            listed = client.post('/mcp', json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, headers=mh).json()
            self.assertTrue(set(TOOLS).issubset({t['name'] for t in listed['result']['tools']}))
            job = client.post('/api/call', json={'tool': 'create_project', 'arguments': {'name': 'film'}, 'request_id': 'web'}, headers=headers).json()['_hosted_job']
            other = self.store.issue(self.b['user'], 'api', 60)
            self.assertEqual(client.get('/files/' + path, headers={'Authorization': 'Bearer ' + other}).status_code, 404)
            self.assertEqual(client.get('/api/tool-jobs/' + job['id'], headers={'Authorization': 'Bearer ' + other}).status_code, 400)
            self.assertEqual(client.post('/auth/api-key', json={}, headers=mh).status_code, 403)
            self.store.revoke(token)
            self.assertEqual(client.post('/mcp', json=request, headers=mh).status_code, 401)


if __name__ == '__main__':
    unittest.main()
