"""Dependency-isolated bridge and Comfy nodes; only stdlib imports at startup."""
import json
import os
from pathlib import Path
import subprocess
import threading

HERE = Path(__file__).resolve().parent
CATALOG = json.loads((HERE / 'catalog.json').read_text(encoding='utf-8'))
TOOLS = {row['name']: row for row in CATALOG}
_LOCK = threading.Lock()


def configuration():
    import folder_paths
    path = Path(folder_paths.get_user_directory()) / 'openkatana' / 'config.json'
    config = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    root = HERE.parent
    python = root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    return {'python': config.get('python', str(python)), 'checkout': config.get('checkout', str(root)),
            'workspace': config.get('workspace', str(Path(folder_paths.get_output_directory()) / 'OpenKatana'))}


def invoke(action, **kwargs):
    config = configuration()
    python = Path(config['python'])
    if not python.is_file():
        raise RuntimeError('OpenKatana runtime not configured. Run scripts/install_comfy_nodes.py with its Python environment.')
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    # Never pass a provider credential to this local-only adapter.
    env.pop('COMFY_API_KEY', None)
    env.pop('OPENKATANA_PRIVATE_COMFY_ENDPOINTS', None)
    request = {'action': action, 'workspace': config['workspace'], **kwargs}
    with _LOCK:
        result = subprocess.run([str(python), '-m', 'openkatana.comfy_apps'],
            input=json.dumps(request), capture_output=True, text=True, encoding='utf-8',
            cwd=config['checkout'], env=env, timeout=3600, shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError('OpenKatana runtime failed: ' + result.stderr[-1500:]) from None
    if not value.get('ok'):
        raise RuntimeError(value.get('error', 'OpenKatana failed'))
    return value['result']


def response(result):
    text = json.dumps(result, ensure_ascii=False, indent=2)
    ui = {'text': [text], 'openkatana': [result]}
    media = result_media(result)
    if media:
        videos = [item for item in media if Path(item['filename']).suffix in ('.mp4', '.webm')]
        ui['images'] = videos or media
        if videos:
            ui['animated'] = [True]
    # App Mode omits legacy ui.text strings from its output gallery. Give it a
    # downloadable text asset as well; STRING/PreviewAny remain compatible.
    import folder_paths
    import hashlib
    name = hashlib.sha256(text.encode('utf8')).hexdigest()[:24] + '.txt'
    dest = Path(folder_paths.get_temp_directory()) / 'openkatana' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding='utf8')
    ui['files'] = [{'filename': name, 'subfolder': 'openkatana', 'type': 'temp',
                    'content': text, 'display_name': 'OpenKatana result'}]
    return {'ui': ui, 'result': (text,)}


def result_media(result):
    """Copy bounded result media into Comfy's previews; never serve arbitrary paths."""
    import folder_paths
    import hashlib
    import shutil
    root = Path(configuration()['workspace']).resolve()
    candidates = []
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('preview_images', 'video', 'video_path', 'preview', 'image'):
                    candidates.extend(item if isinstance(item, list) else [item])
                elif isinstance(item, dict):
                    visit(item)
    visit(result)
    output = []
    for value in candidates[:6]:
        if not isinstance(value, str):
            continue
        path = Path(value).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm'):
            continue
        if path.stat().st_size > 256 * 1024**2:
            continue  # full downloads remain available in Studio
        stat = path.stat()
        name = hashlib.sha256((str(path) + str(stat.st_mtime_ns) + str(stat.st_size)).encode()).hexdigest()[:24] + path.suffix.lower()
        dest = Path(folder_paths.get_temp_directory()) / 'openkatana' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copyfile(path, dest)
        output.append({'filename': name, 'subfolder': 'openkatana', 'type': 'temp'})
    return output


def arguments_for(tool, project_id, arguments):
    if tool not in TOOLS:
        raise ValueError('Unknown OpenKatana tool')
    args = json.loads(arguments)
    if not isinstance(args, dict):
        raise ValueError('Arguments must be a JSON object')
    if project_id and 'project_id' in TOOLS[tool]['parameters']:
        if 'project_id' in args and args['project_id'] != project_id:
            raise ValueError('Project field and JSON project_id disagree')
        args['project_id'] = project_id
    return args


class OpenKatanaTool:
    DESCRIPTION = ('Run any OpenKatana tool locally. Arguments use the same JSON contract as CLI/MCP. '
                   'Model jobs return a job ID so ComfyUI can release its queue. No paid/cloud execution.')
    CATEGORY = 'OpenKatana/Studio'
    FUNCTION = 'execute'
    OUTPUT_NODE = True
    RETURN_TYPES = ('STRING',)
    RETURN_NAMES = ('result_json',)

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'tool': (list(TOOLS),),
            'project_id': ('STRING', {'default': 'my-film'}),
            'arguments': ('STRING', {'default': '{}', 'multiline': True})},
            'optional': {'after': ('STRING', {'forceInput': True})}}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float('nan')  # project state is shared with Studio, CLI and MCP

    def execute(self, tool, project_id, arguments, after=None):
        return response(invoke('call', tool=tool, arguments=arguments_for(tool, project_id, arguments)))


class OpenKatanaWorkspace(OpenKatanaTool):
    DESCRIPTION = 'Create/reopen a local project and its Studio. Copy its CLI/MCP setup to your agent.'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project_id': ('STRING', {'default': 'my-film'}),
            'name': ('STRING', {'default': 'My film'})}}

    def execute(self, project_id, name):
        return response(invoke('studio', project_id=project_id, name=name))


class OpenKatanaJob(OpenKatanaTool):
    DESCRIPTION = 'Read a background job without submitting or retrying it. A tool result may itself contain a pending model receipt.'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'job_id': ('STRING', {'default': ''})}}

    def execute(self, job_id):
        return response(invoke('status', job_id=job_id))


class OpenKatanaScene(OpenKatanaTool):
    DESCRIPTION = 'Create an editable local 3D scene and render it with WebGL. No generation model or credits. Use Studio/AI for further edits.'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project_id': ('STRING', {'default': 'my-film'}),
            'template': (['product', 'morph', 'physics'],),
            'width': ('INT', {'default': 640, 'min': 64, 'max': 3840, 'step': 2}),
            'height': ('INT', {'default': 360, 'min': 64, 'max': 2160, 'step': 2}),
            'frames': ('INT', {'default': 60, 'min': 1, 'max': 1800}),
            'fps': ('INT', {'default': 30, 'min': 1, 'max': 120})}}

    def execute(self, project_id, template, width, height, frames, fps):
        return response(invoke('scene', project_id=project_id, template=template,
                               width=width, height=height, frames=frames, fps=fps))


def tool_class(row):
    tool = row['name']

    class Tool(OpenKatanaTool):
        DESCRIPTION = row['description'] + '\n\n' + row['signature']
        CATEGORY = 'OpenKatana/Tools'

        @classmethod
        def INPUT_TYPES(cls):
            value = OpenKatanaTool.INPUT_TYPES()
            del value['required']['tool']
            return value

        def execute(self, project_id, arguments, after=None):
            return super().execute(tool, project_id, arguments, after)
    return Tool


NODE_CLASS_MAPPINGS = {'OpenKatanaTool': OpenKatanaTool, 'OpenKatanaWorkspace': OpenKatanaWorkspace,
                       'OpenKatanaJob': OpenKatanaJob, 'OpenKatanaScene': OpenKatanaScene}
NODE_DISPLAY_NAME_MAPPINGS = {'OpenKatanaTool': 'OpenKatana · All tools',
    'OpenKatanaWorkspace': 'OpenKatana · Open Studio', 'OpenKatanaJob': 'OpenKatana · Job status',
    'OpenKatanaScene': 'OpenKatana · 3D starter'}
for _row in CATALOG:
    _key = 'OpenKatana_' + _row['name']
    NODE_CLASS_MAPPINGS[_key] = tool_class(_row)
    NODE_DISPLAY_NAME_MAPPINGS[_key] = 'OpenKatana · ' + _row['name'].replace('_', ' ').capitalize()


def register_routes():
    from aiohttp import web
    from server import PromptServer
    import asyncio
    import ipaddress
    from urllib.parse import urlsplit

    def check(request):
        try:
            if not ipaddress.ip_address(request.remote).is_loopback:
                raise ValueError()
            host = urlsplit('http://' + request.host).hostname
            if host not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError()
            origin = request.headers.get('Origin')
            if origin and urlsplit(origin).netloc != request.host:
                raise ValueError()
        except ValueError:
            raise web.HTTPForbidden(text='OpenKatana Apps is local-only')

    @PromptServer.instance.routes.get('/openkatana/catalog')
    async def get_catalog(request):
        check(request)
        return web.json_response({'tools': CATALOG})

    @PromptServer.instance.routes.get('/openkatana/jobs/{job_id}')
    async def get_job(request):
        check(request)
        try:
            import uuid
            key = uuid.UUID(request.match_info['job_id']).hex
            return web.json_response(await asyncio.to_thread(invoke, 'status', job_id=key))
        except (ValueError, RuntimeError) as exc:
            return web.json_response({'error': str(exc)}, status=400)
