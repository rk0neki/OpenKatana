"""Hosted identity, queue, transport and file-isolation contracts. No paid calls."""
import asyncio
import io
import json
from pathlib import Path
import tarfile
import tempfile
import time
from types import SimpleNamespace
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
        invite = self.a['access_key']
        self.assertEqual(self.store.authenticate(invite, {'login'}, consume=True), self.a['user'])
        self.assertIsNone(self.store.authenticate(invite, {'login'}, consume=True))

    def test_oauth_signature_issuer_audience_expiry_and_scope(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from openkatana.hosted.auth import Identity
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        config = Settings(Path(self.tmp.name), 'https://studio.example.org',
                          issuer='https://identity.example.org', jwks_url='https://identity.example.org/jwks',
                          client_id='browser', authorize_url='https://identity.example.org/authorize',
                          token_url='https://identity.example.org/token')
        identity = Identity(config, self.store)
        identity.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
        claims = dict(exp=time.time()+60, iat=time.time(), sub='one', iss=config.issuer,
                      aud=config.audience, scope='openid openkatana')
        encode = lambda data: jwt.encode(data, private, algorithm='RS256')
        first = identity.jwt_user(encode(claims))
        self.assertEqual(first, identity.jwt_user(encode(claims)))
        self.assertNotEqual(first, identity.jwt_user(encode({**claims, 'sub': 'two'})))
        for changed in ({'exp': time.time()-60}, {'aud': 'another-api'}, {'iss': 'https://wrong.example.org'}, {'scope': 'openid'}):
            with self.subTest(changed=changed), self.assertRaises((jwt.PyJWTError, ValueError)):
                identity.jwt_user(encode({**claims, **changed}))
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with self.assertRaises(jwt.InvalidSignatureError):
            identity.jwt_user(jwt.encode(claims, other, algorithm='RS256'))

    def test_models_cannot_share_tenant_networks(self):
        from dataclasses import replace
        with self.assertRaisesRegex(ValueError, 'separate'):
            replace(self.config, comfy_proxy='http://comfy:8000', comfy_native='http://comfy:8188', model_network='shared')
        config = replace(self.config, comfy_proxy='http://comfy-{user}:8000', comfy_native='http://comfy-{user}:8188', model_network='models-{user}')
        a = command(config, {'id': 'a', 'user': self.a['user'], 'tool': 'submit_workflow'}, Path(self.tmp.name))
        b = command(config, {'id': 'b', 'user': self.b['user'], 'tool': 'submit_workflow'}, Path(self.tmp.name))
        self.assertNotEqual(a[a.index('--network')+1], b[b.index('--network')+1])
        self.assertNotIn(self.b['user'], ' '.join(a))

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

    def test_clip_processing_uses_account_model_service(self):
        from dataclasses import replace
        user = self.a['user']
        arguments = {'project_id': 'film', 'clip_id': 'shot', 'kind': 'interpolation', 'directory': 'smooth',
                     'endpoint': 'http://untrusted:8000', 'native_endpoint': 'http://untrusted:8188'}
        with self.assertRaisesRegex(ValueError, 'Comfy model service'):
            Service(self.config).submit(user, 'process_clip', arguments)
        config = replace(self.config, comfy_proxy='http://comfy-{user}:8000', comfy_native='http://comfy-{user}:8188', model_network='models-{user}')
        service = Service(config)
        queued = service.submit(user, 'process_clip', arguments)
        job = service.store.claim()
        self.assertEqual(job['id'], queued['id'])
        actual = json.loads(job['arguments'])
        self.assertEqual(actual['endpoint'], f'http://comfy-{user}:8000')
        self.assertEqual(actual['native_endpoint'], f'http://comfy-{user}:8188')
        cmd = command(config, job, Path(self.tmp.name))
        self.assertEqual(cmd[cmd.index('--network')+1], 'models-' + user)
        self.assertNotIn('untrusted', ' '.join(cmd))

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
