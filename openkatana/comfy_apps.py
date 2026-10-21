"""Local ComfyUI adapter process. Uses the same AgentAPI as CLI and MCP.

Requests arrive on stdin, never through a shell. ComfyUI keeps its own Python
environment. Model collection runs in a background process to free its queue.
"""
import contextlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from .agent_api import AgentAPI, TOOLS
from .contracts import ContractError, local_path
from .render import write_json

BACKGROUND_TOOLS = {'process_clip', 'run_model_workflow', 'collect_workflow'}


def catalog():
    api = AgentAPI('.')
    rows = api.catalog()
    for row in rows:
        params = inspect.signature(getattr(api, row['name'])).parameters
        row['parameters'] = {n: {'type': str(p.annotation),
            'required': p.default is inspect.Parameter.empty,
            **({} if p.default is inspect.Parameter.empty else {'default': p.default})}
            for n, p in params.items()}
    return rows


def local_arguments(api, tool, arguments):
    """Keep this distribution local-only, including collection of old receipts."""
    if tool not in TOOLS:
        raise ContractError('Unknown OpenKatana tool')
    if not isinstance(arguments, dict):
        raise ContractError('Arguments must be a JSON object')
    if arguments.get('execution', 'local') != 'local' or arguments.get('allow_paid', False) is not False:
        raise ContractError('ComfyUI Apps uses local execution only; paid/cloud calls are disabled')
    from .comfy import local_endpoint
    for key in ('endpoint', 'native_endpoint'):
        if key in arguments:
            local_endpoint(arguments[key])
    if tool in ('collect_workflow', 'import_workflow_output'):
        root = api._project(arguments.get('project_id', ''))
        receipt = local_path(root, arguments.get('directory', '')) / 'job.json'
        if receipt.is_file():
            data = json.loads(receipt.read_text(encoding='utf-8'))
            if data.get('execution', 'local') != 'local':
                raise ContractError('Cloud receipts cannot be collected through local Apps')
            if data.get('endpoint'):
                local_endpoint(data['endpoint'])
    return arguments


def call(workspace, tool, arguments):
    api = AgentAPI(workspace)
    return api.call(tool, local_arguments(api, tool, arguments))


def job_folder(workspace, job_id):
    return Path(workspace).resolve() / '.comfy-apps' / 'jobs' / uuid.UUID(job_id).hex


def job_status(workspace, job_id):
    folder = job_folder(workspace, job_id)
    result = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
    if result['state'] == 'running' and (folder / 'process.json').is_file():
        from .jobs import alive
        pid = json.loads((folder / 'process.json').read_text())['pid']
        if alive(pid) is False:
            result.update(state='interrupted', error='Worker exited; inspect receipts before retrying.')
    return result


def start_background(workspace, tool, arguments):
    local_arguments(AgentAPI(workspace), tool, arguments)
    job_id = uuid.uuid4().hex
    folder = job_folder(workspace, job_id)
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / 'request.json', {'tool': tool, 'arguments': arguments})
    write_json(folder / 'status.json', {'job_id': job_id, 'tool': tool, 'state': 'running'})
    try:
        with (folder / 'log.txt').open('w', encoding='utf-8') as log:
            proc = subprocess.Popen([sys.executable, '-m', 'openkatana.comfy_apps',
                '--worker', str(Path(workspace).resolve()), job_id], stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        write_json(folder / 'process.json', {'pid': proc.pid})
        threading.Thread(target=proc.wait, daemon=True).start()
    except Exception as exc:
        write_json(folder / 'status.json', {'job_id': job_id, 'tool': tool, 'state': 'failed', 'error': str(exc)})
        raise
    return job_status(workspace, job_id)


def run_background(workspace, job_id):
    folder = job_folder(workspace, job_id)
    request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    status = {'job_id': job_id, 'tool': request['tool']}
    try:
        result = call(workspace, request['tool'], request['arguments'])
        status.update(state='succeeded', result=result)
    except Exception as exc:
        status.update(state='failed', error=f'{type(exc).__name__}: {exc}')
    write_json(folder / 'status.json', status)


def studio(workspace, project_id, name):
    """Start or reuse a loopback Studio for this exact project, without opening tabs."""
    import urllib.request
    from .onboarding import setup_project
    root = AgentAPI(workspace)._project(project_id)
    setup = setup_project(root, name)
    folder = root / '.openkatana' / 'comfy-studio'
    folder.mkdir(parents=True, exist_ok=True)
    address_file = folder / 'address.json'
    if address_file.is_file():
        try:
            address = json.loads(address_file.read_text())
            from .comfy import local_endpoint
            local_endpoint(address['studio'])
            with urllib.request.urlopen(address['studio'] + '/api/studio-info', timeout=2) as response:
                data = json.load(response)
            if Path(data['project_path']).resolve() == root:
                return {**setup, 'studio': address['studio']}
        except (OSError, ValueError, KeyError):
            pass
    log_path = folder / ('server-' + uuid.uuid4().hex + '.log')
    with log_path.open('w', encoding='utf-8') as log:
        proc = subprocess.Popen([sys.executable, '-m', 'openkatana', 'studio', str(root)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        threading.Thread(target=proc.wait, daemon=True).start()
    for _ in range(100):
        lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines()
        if lines:
            try:
                address = json.loads(lines[0])
                if 'studio' in address:
                    write_json(address_file, address)
                    return {**setup, 'studio': address['studio']}
            except ValueError:
                pass
        time.sleep(.1)
    raise RuntimeError('Studio did not start; inspect ' + str(log_path))


def scene(workspace, project_id, template, width, height, frames, fps):
    from .onboarding import setup_project
    from .contracts import number
    from .scene3d import starter as scene_template
    for key, value, low, high in [('width', width, 64, 3840), ('height', height, 64, 2160),
                                  ('frames', frames, 1, 1800), ('fps', fps, 1, 120)]:
        number(value, key, low, high, integer=True)
    api = AgentAPI(workspace)
    setup_project(api._project(project_id), 'My 3D film')
    document = scene_template(template, width=width, height=height, frames=frames, fps=fps)
    created = api.create_scene3d(project_id, name='app-' + uuid.uuid4().hex[:8], scene=document)
    return api.render_scene3d(project_id, created['scene'])


def dispatch(request):
    action = request['action']
    if action == 'catalog':
        return {'tools': catalog()}
    workspace = Path(request['workspace']).expanduser().resolve()
    if action == 'studio':
        return studio(workspace, request['project_id'], request.get('name', 'My film'))
    if action == 'status':
        return job_status(workspace, request['job_id'])
    if action == 'scene':
        return scene(workspace, **{k: request[k] for k in ('project_id', 'template', 'width', 'height', 'frames', 'fps')})
    if action == 'call':
        tool, arguments = request['tool'], request['arguments']
        if tool in BACKGROUND_TOOLS:
            return start_background(workspace, tool, arguments)
        return call(workspace, tool, arguments)
    raise ValueError('Unknown adapter action')


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        run_background(sys.argv[2], sys.argv[3])
        return
    # Model libraries may print diagnostics. Keep stdout a single JSON response.
    try:
        request = json.loads(sys.stdin.read())
        with contextlib.redirect_stdout(sys.stderr):
            result = dispatch(request)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {exc}'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
