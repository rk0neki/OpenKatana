"""Local integration check: real Comfy prompts, renders, SDK jobs, CLI and MCP.

Uses new projects and synthetic media. No model weights or paid services.
"""
import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

from PIL import Image, ImageChops
from openkatana.agent_api import TOOLS
from openkatana.render import write_json


def request(endpoint, path, data=None):
    req = urllib.request.Request(endpoint + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


async def mcp_check(workspace, project_id, revision, out):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable,
        args=['-m', 'openkatana', 'mcp', '--workspace', str(workspace)], cwd=str(Path.cwd()))
    with (out / 'mcp-stderr.log').open('w', encoding='utf8') as log:
        async with stdio_client(params, errlog=log) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=90)) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                assert names == set(TOOLS)
                result = await session.call_tool('get_project', {'project_id': project_id})
                assert not result.isError and result.structuredContent['revision'] == revision
                guide = await session.call_tool('read_guide', {'topic': 'comfy-apps'})
                assert not guide.isError and 'ComfyUI Apps' in guide.structuredContent['markdown']
    return len(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default='http://127.0.0.1:8000')
    parser.add_argument('--workspace', required=True, type=Path, help='Workspace configured by install_comfy_nodes.py')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    endpoint, workspace, out = args.endpoint.rstrip('/'), args.workspace.resolve(), args.out.resolve()
    from openkatana.comfy import local_endpoint
    local_endpoint(endpoint)
    out.mkdir(parents=True, exist_ok=False)
    queue = request(endpoint, '/queue')
    assert not queue['queue_running'] and not queue['queue_pending'], 'Wait for existing Comfy jobs first'
    node_info = request(endpoint, '/object_info')
    expected = {'OpenKatana_' + tool for tool in TOOLS}
    assert expected <= set(node_info)
    assert len(request(endpoint, '/openkatana/catalog')['tools']) == len(TOOLS)
    evidence = []

    def run(node, inputs, expect_error=False):
        posted = request(endpoint, '/prompt', {'prompt': {'1': {'class_type': node, 'inputs': inputs}},
                                               'client_id': 'openkatana-local-check'})
        prompt_id = posted['prompt_id']
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            history = request(endpoint, '/history/' + prompt_id)
            if prompt_id in history:
                row = history[prompt_id]
                write_json(out / (prompt_id + '.json'), row)
                evidence.append({'node': node, 'prompt_id': prompt_id, 'status': row['status']['status_str']})
                errors = [value for kind, value in row['status']['messages'] if kind == 'execution_error']
                if expect_error:
                    assert errors, row
                    return errors[0]['exception_message']
                assert row['status']['status_str'] == 'success', errors
                print(node + ': passed', flush=True)
                return json.loads(row['outputs']['1']['text'][0])
            time.sleep(.25)
        raise TimeoutError('Inspect existing prompt, do not blindly retry: ' + prompt_id)

    project = 'apps-check-' + uuid.uuid4().hex[:8]
    def call(tool, **arguments):
        return run('OpenKatana_' + tool, {'project_id': project, 'arguments': json.dumps(arguments)})

    studio = run('OpenKatanaWorkspace', {'project_id': project, 'name': 'Comfy Apps validation'})
    assert Path(studio['workspace']).resolve() == workspace
    reused = run('OpenKatanaWorkspace', {'project_id': project, 'name': 'Preserve existing name'})
    assert reused['studio'] == studio['studio']
    assert Path(request(studio['studio'], '/api/studio-info')['project_path']).resolve() == workspace / project
    call('get_capabilities')
    call('read_guide', topic='comfy-apps')
    rendered = run('OpenKatanaScene', {'project_id': project, 'template': 'morph',
        'width': 320, 'height': 180, 'frames': 12, 'fps': 12})
    assert Path(rendered['video']).is_file()
    frames = sorted((Path(rendered['output']) / 'frames').glob('*.png'))
    assert len(frames) == 12
    assert ImageChops.difference(Image.open(frames[0]).convert('RGB'), Image.open(frames[-1]).convert('RGB')).getbbox()
    asset = call('import_media', source=rendered['video'], rights='own')
    timeline = call('plan_edit', asset_ids=[asset['id']], seconds=1, width=320, height=180, fps=12)['timeline']
    state = call('get_project')
    saved = call('save_timeline', timeline=timeline, revision=state['revision'])
    stale = run('OpenKatana_save_timeline', {'project_id': project,
        'arguments': json.dumps({'timeline': timeline, 'revision': 'stale'})}, expect_error=True)
    assert 'revision' in stale.lower() or 'changed' in stale.lower(), stale
    call('preview_timeline', frames=[0, 11])
    render = call('start_render', request_id='apps-check-render')
    deadline = time.monotonic() + 120
    while render['state'] == 'running' and time.monotonic() < deadline:
        time.sleep(1)
        render = call('get_render', job_id=render['id'])
    assert render['state'] == 'succeeded', render
    assert Path(render['video_path']).is_file()
    blocked = run('OpenKatana_submit_workflow', {'project_id': project,
        'arguments': json.dumps({'workflow': 'absent.json', 'request_id': 'never-submit',
                                'execution': 'cloud', 'allow_paid': True})}, expect_error=True)
    assert 'disabled' in blocked, blocked
    arguments = out / 'project-arguments.json'
    write_json(arguments, {'project_id': project})
    cli = subprocess.run([sys.executable, '-m', 'openkatana', 'call', 'get_project',
        '--workspace', str(workspace), '--arguments', str(arguments)], capture_output=True,
        encoding='utf8', check=True)
    assert json.loads(cli.stdout)['revision'] == saved['revision']
    assert request(studio['studio'], '/api/state')['revision'] == saved['revision']
    mcp_tools = asyncio.run(mcp_check(workspace, project, saved['revision'], out))

    # A tiny EmptyImage workflow proves queue handoff and official SDK collection.
    # Own this temporary local proxy; never stop another user's proxy.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    proxy_exe = Path(sys.executable).parent / ('comfy-api-proxy.exe' if os.name == 'nt' else 'comfy-api-proxy')
    with (out / 'proxy.log').open('w', encoding='utf8') as log:
        proxy = subprocess.Popen([str(proxy_exe), 'run', '--comfyui', endpoint, '--port', str(port),
            '--state-dir', str(out / 'proxy-state')], stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2): break
                except OSError: time.sleep(.1)
            graph = {'1': {'class_type': 'EmptyImage', 'inputs': {'width': 64, 'height': 64, 'batch_size': 1, 'color': 3368652}},
                     '2': {'class_type': 'SaveImage', 'inputs': {'images': ['1', 0], 'filename_prefix': 'OpenKatana/apps-check'}}}
            write_json(workspace / project / 'local-smoke.json', graph)
            submitted = call('submit_workflow', workflow='local-smoke.json', request_id='apps-check-local-sdk',
                             endpoint=f'http://127.0.0.1:{port}', native_endpoint=endpoint)
            deadline = time.monotonic() + 90
            collected = None
            while time.monotonic() < deadline:
                job = call('collect_workflow', directory=submitted['directory'])
                while job['state'] == 'running' and time.monotonic() < deadline:
                    time.sleep(.3)
                    job = request(endpoint, '/openkatana/jobs/' + job['job_id'])
                assert job['state'] == 'succeeded', job
                collected = job['result']
                if collected['state'] == 'collected': break
                time.sleep(.5)
            assert collected['state'] == 'collected' and collected['outputs'], collected
            status = run('OpenKatanaJob', {'job_id': job['job_id']})
            assert status['result'] == collected
        finally:
            proxy.terminate(); proxy.wait(timeout=15)
    report = {'passed': True, 'tool_count': len(TOOLS), 'node_count': sum(n.startswith('OpenKatana') for n in node_info),
        'mcp_tools': mcp_tools, 'project_id': project, 'studio': studio['studio'], 'scene_video': rendered['video'],
        'timeline_video': render['video_path'], 'scene_motion_verified': True, 'shared_revision_verified': True,
        'stale_revision_rejected': True, 'paid_calls_rejected': True, 'sdk_background_collection': True,
        'prompts': evidence, 'paid_calls': 0, 'model_weight_downloads': 0,
        'versions': request(endpoint, '/system_stats')['system']}
    write_json(out / 'validation.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
