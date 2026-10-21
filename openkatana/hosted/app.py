"""Authenticated hosted UI, file transfer and shared MCP/API tool queue."""
import base64
from collections import OrderedDict
from contextlib import asynccontextmanager
import json
import mimetypes
import tempfile
from pathlib import Path
import time
import uuid
from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from .auth import Identity, current_user
from .dispatch import schemas, HostedAPI
from .files import inventory, safe_path
from .mcp import create as create_mcp
from .service import Service
from .. import projects
from ..agent_api import AgentAPI

WEB = Path(__file__).resolve().parents[1] / 'web'
COOKIE = 'openkatana_session'


class Gate:
    def __init__(self, app, service, identity):
        self.app, self.service, self.identity = app, service, identity
        self.rates = OrderedDict()
        self.uploads = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        config = self.service.settings
        if request.headers.get('host') != urlsplit(config.public_url).netloc:
            return await JSONResponse({'error': 'Invalid host'}, 403)(scope, receive, send)
        origin = request.headers.get('origin')
        if origin and origin != config.public_url:
            return await JSONResponse({'error': 'Invalid origin'}, 403)(scope, receive, send)
        path = scope['path']
        if path == '/auth/session' and not self.allow('login', 20, 60):
            return await JSONResponse({'error': 'Sign-in rate limit; try again shortly'}, 429)(scope, receive, send)
        public = path in ('/healthz', '/login', '/auth/callback', '/auth/config', '/auth/session',
                          '/.well-known/oauth-protected-resource/mcp') or path.startswith('/app/')
        auth = request.headers.get('authorization', '')
        bearer = auth[7:] if auth.startswith('Bearer ') else ''
        user = await self.identity.bearer(bearer) if bearer else self.service.store.authenticate(request.cookies.get(COOKIE, ''), {'session'})
        if not public and not user:
            response = RedirectResponse('/login', 303) if path == '/' else JSONResponse({'error': 'Authentication required'}, 401, headers={'WWW-Authenticate': self.identity.challenge()})
            return await response(scope, receive, send)
        if user and not self.allow(user, 300, 60):
            return await JSONResponse({'error': 'Request rate limit; try again shortly'}, 429)(scope, receive, send)
        uploading = path == '/api/upload'
        if uploading and self.uploads >= 4:
            return await JSONResponse({'error': 'Upload capacity is busy; retry shortly'}, 429)(scope, receive, send)
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and not bearer and origin != config.public_url:
            return await JSONResponse({'error': 'Same-origin browser request required'}, 403)(scope, receive, send)
        # Bound bodies before JSON parsing and enforce the bound while receiving.
        limit = config.upload_bytes if path == '/api/upload' else 5 * 1024**2
        try:
            if int(request.headers.get('content-length', '0')) > limit:
                raise ValueError()
        except ValueError:
            return await JSONResponse({'error': 'Request too large'}, 413)(scope, receive, send)
        received = 0
        async def bounded():
            nonlocal received
            message = await receive()
            received += len(message.get('body', b''))
            if received > limit:
                raise ValueError('Request too large')
            return message
        async def headers(message):
            if message['type'] == 'http.response.start':
                connect = "'self'"
                if path in ('/login', '/auth/callback') and config.token_url:
                    endpoint = urlsplit(config.token_url)
                    connect += ' ' + endpoint.scheme + '://' + endpoint.netloc
                message.setdefault('headers', []).extend([
                    (b'x-content-type-options', b'nosniff'), (b'referrer-policy', b'no-referrer'),
                    (b'cache-control', b'no-store'),
                    (b'content-security-policy', ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; connect-src " + connect + "; frame-ancestors 'none'; object-src 'none'; base-uri 'none'").encode())])
            await send(message)
        scope['state'] = {'user': user, 'browser_session': bool(user and not bearer)}
        token = current_user.set(user)
        if uploading:
            self.uploads += 1
        try:
            await self.app(scope, bounded, headers)
        finally:
            if uploading:
                self.uploads -= 1
            current_user.reset(token)

    def allow(self, key, capacity, seconds):
        now = time.monotonic()
        tokens, last = self.rates.pop(key, (float(capacity), now))
        tokens = min(capacity, tokens + (now - last) * capacity / seconds)
        accepted = tokens >= 1
        self.rates[key] = (tokens - 1 if accepted else tokens, now)
        while len(self.rates) > 1024:
            self.rates.popitem(last=False)
        return accepted


def create_app(settings):
    service = Service(settings); store = service.store; identity = Identity(settings, store)
    mcp = create_mcp(service); mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    async def json_body(request):
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise ValueError('JSON required')
        value = await request.json()
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value

    def queued(user, tool, args, key=None):
        return JSONResponse({'_hosted_job': service.submit(user, tool, args, key)}, 202)

    async def public_config(request):
        return JSONResponse({'mcp_url': settings.audience, 'issuer': settings.issuer,
                             'client_id': settings.client_id, 'authorize_url': settings.authorize_url,
                             'token_url': settings.token_url, 'redirect_uri': settings.public_url + '/auth/callback'})

    async def login(request):
        return FileResponse(WEB / 'hosted-login.html')

    async def session(request):
        body = await json_body(request)
        key = body.get('access_key', '')
        user = store.authenticate(key, {'login'}, consume=True) if key else await identity.bearer(body.get('access_token', ''))
        if not user:
            return JSONResponse({'error': 'Invalid or expired sign-in credential'}, 401)
        session_token = store.issue(user, 'session', 12 * 3600)
        response = JSONResponse({'ready': True})
        response.set_cookie(COOKIE, session_token, httponly=True, secure=not settings.development, samesite='strict', max_age=12 * 3600)
        return response

    async def logout(request):
        store.revoke(request.cookies.get(COOKIE, ''))
        response = JSONResponse({'signed_out': True}); response.delete_cookie(COOKIE)
        return response

    async def key(request):
        if not request.state.browser_session:
            return JSONResponse({'error': 'Use your signed-in browser to manage API keys'}, 403)
        store.revoke_api_keys(request.state.user)
        if request.method == 'DELETE':
            return JSONResponse({'revoked': True})
        return JSONResponse({'token': store.issue(request.state.user, 'api', 7 * 86400), 'expires_in': 7 * 86400, 'url': settings.audience})

    async def metadata(request):
        if not settings.issuer:
            return JSONResponse({'error': 'This pilot uses explicit bearer keys; OAuth issuer is not configured'}, 404)
        return JSONResponse({'resource': settings.audience, 'authorization_servers': [settings.issuer],
                             'scopes_supported': ['openkatana'], 'bearer_methods_supported': ['header']})

    async def home(request):
        html = (WEB / 'studio.html').read_text(encoding='utf-8')
        html = html.replace('<script src="/app/studio.js">', '<script src="/app/hosted-bridge.js"></script><script src="/app/studio.js">')
        return HTMLResponse(html)

    async def static(request):
        p = safe_path(WEB, request.path_params['path'])
        if not p.is_file():
            return Response(status_code=404)
        return FileResponse(p)

    async def file(request):
        user = request.state.user
        root = store.workspace(user)
        if request.url.path.startswith('/project/'):
            _, root = service.project(user)
        p = safe_path(root, request.path_params['path'])
        if not p.is_file():
            return Response(status_code=404)
        inline = p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm', '.mp3', '.wav', '.ogg')
        return FileResponse(p, media_type=mimetypes.guess_type(p.name)[0] if inline else 'application/octet-stream',
                            filename=None if inline else p.name, content_disposition_type='attachment')

    async def upload(request):
        user = request.state.user
        if store.busy(user):
            return JSONResponse({'error': 'Wait for the current workspace job before uploading'}, 409)
        name = request.headers.get('x-file-name', 'asset.bin')
        if name.startswith('.') or len(name) > 180 or any(c in name for c in ('/', '\\', ':', '\x00')):
            raise ValueError('Invalid upload filename')
        root = store.workspace(user)
        folder = root / (store.selected(user) or 'incoming') / 'uploads'
        target = safe_path(folder, uuid.uuid4().hex + '-' + name)
        count = 0
        # Spool outside the workspace; hold no database lock during the upload.
        with tempfile.TemporaryFile(dir=settings.data) as staged:
            async for chunk in request.stream():
                count += len(chunk)
                if count > settings.upload_bytes:
                    raise ValueError('Upload size limit exceeded')
                staged.write(chunk)
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if store.busy(user):
                    return JSONResponse({'error': 'A workspace job started; retry the upload after it finishes'}, 409)
                used = sum(size for _, size in inventory(root, settings.workspace_bytes))
                if used + count > settings.workspace_bytes:
                    raise ValueError('Workspace storage limit exceeded')
                folder.mkdir(parents=True, exist_ok=True)
                staged.seek(0)
                try:
                    with target.open('xb') as out:
                        while chunk := staged.read(1024 * 1024):
                            out.write(chunk)
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise
        return JSONResponse({'source': 'workspace://' + target.relative_to(root).as_posix(), 'bytes': count})

    async def api(request):
        user = request.state.user; route = request.path_params['route']
        body = await json_body(request) if request.method == 'POST' else {}
        if route == 'tools':
            return JSONResponse(schemas())
        if route == 'guide':
            return JSONResponse(HostedAPI('.').read_guide(request.query_params.get('topic', 'agent')))
        if route == 'tool-jobs':
            return JSONResponse(store.jobs(user))
        if route.startswith('tool-jobs/'):
            key = route.split('/')[-1]
            return JSONResponse(store.cancel(user, key) if request.method == 'POST' else store.job(user, key))
        if route == 'call':
            return queued(user, body['tool'], body.get('arguments', {}), body.get('request_id'))
        if route == 'projects':
            root = store.workspace(user)
            rows = [{'id': p.parent.name, 'name': json.loads(p.read_text())['name']} for p in root.glob('*/project.json')]
            return JSONResponse({'projects': rows, 'selected': store.selected(user)})
        if route == 'select-project':
            return JSONResponse({'selected': store.selected(user, body['project_id'])})
        if route == 'studio-info':
            return JSONResponse({'hosted': True, 'project_id': store.selected(user), 'workspace': 'workspace://',
                                 'mcp_url': settings.audience, 'oauth': bool(settings.issuer),
                                 'upload_bytes': settings.upload_bytes, 'workspace_bytes': settings.workspace_bytes,
                                 'model_service': bool(settings.comfy_proxy)})
        key, root = service.project(user)
        if route == 'state':
            return JSONResponse(projects.state(root))
        if route == 'jobs':
            rows = []
            for p in root.glob('.openkatana/jobs/*/job.json'):
                rows.append(json.loads(p.read_text()))
            return JSONResponse(sorted(rows, key=lambda r: r['created_at']))
        mapped = {'save': ('save_timeline', body), 'plan': ('plan_edit', body),
                  'render': ('start_render', {'request_id': body.get('request_id', uuid.uuid4().hex)}),
                  'preview-edit': ('preview_edit', body),
                  'review': ('review_render', {'job_id': body.get('job_id'), 'decision': body.get('decision'), 'notes': body.get('notes', '')})}
        if route in mapped:
            tool, arguments = mapped[route]
            return queued(user, tool, {'project_id': key, **arguments})
        return JSONResponse({'error': 'Use the shared tool runner for this hosted operation'}, 404)

    async def error(request, exc):
        return JSONResponse({'error': str(exc)}, 400)

    async def health(request):
        return JSONResponse({'status': 'ok'})

    routes = [Route('/healthz', health),
              Route('/login', login), Route('/auth/callback', login), Route('/auth/config', public_config),
              Route('/auth/session', session, methods=['POST']), Route('/auth/logout', logout, methods=['POST']),
              Route('/auth/api-key', key, methods=['POST', 'DELETE']),
              Route('/.well-known/oauth-protected-resource/mcp', metadata),
              Route('/', home), Route('/app/{path:path}', static),
              Route('/files/{path:path}', file), Route('/project/{path:path}', file),
              Route('/api/upload', upload, methods=['POST']),
              Route('/api/{route:path}', api, methods=['GET', 'POST']), Mount('/', mcp_app)]
    app = Starlette(routes=routes, lifespan=lifespan, exception_handlers={ValueError: error, KeyError: error})
    app.state.service = service
    return Gate(app, service, identity)
