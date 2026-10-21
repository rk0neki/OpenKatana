"""Real hosted HTTP/MCP -> Docker worker -> video/download integration test."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid

import httpx
from PIL import Image

from openkatana.hosted.config import Settings
from openkatana.hosted.runner import check_runtime, run_one
from openkatana.hosted.store import Store


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--runtime', default='runsc'); args = parser.parse_args()
    root = args.out.resolve(); root.mkdir(parents=True, exist_ok=False)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    config = Settings(root / 'data', f'http://127.0.0.1:{port}', runtime=args.runtime, development=True,
                      workspace_bytes=512 * 1024**2, upload_bytes=8 * 1024**2,
                      worker_memory='3g', worker_cpus=2, job_seconds=180)
    check_runtime(config)
    config_path = root / 'config.json'
    config_path.write_text(json.dumps({**config.__dict__, 'data': str(config.data)}))
    store = Store(config); account = store.add_user('Integration test'); other = store.add_user('Other account')
    token = store.issue(account['user'], 'api', 3600); other_token = store.issue(other['user'], 'api', 3600)
    stop = threading.Event()
    def worker():
        while not stop.is_set():
            job = store.claim()
            if job:
                run_one(config, store, job)
            else:
                stop.wait(.1)
    thread = threading.Thread(target=worker, daemon=True); thread.start()
    log = (root / 'server.log').open('w')
    process = subprocess.Popen([sys.executable, '-m', 'openkatana.hosted.cli', '--config', str(config_path), 'web', '--port', str(port)], stdout=log, stderr=log)
    checks = {}
    try:
        with httpx.Client(base_url=config.public_url, headers={'Authorization': 'Bearer ' + token}, timeout=15) as client:
            for _ in range(100):
                try:
                    if client.get('/healthz').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError('Hosted test server did not start')
            def call(tool, arguments):
                r = client.post('/api/call', json={'tool': tool, 'arguments': arguments, 'request_id': uuid.uuid4().hex})
                r.raise_for_status(); job = r.json()['_hosted_job']; end = time.monotonic() + 240
                while job['state'] in ('queued', 'running'):
                    if time.monotonic() > end:
                        raise TimeoutError('Hosted job did not finish: ' + tool)
                    time.sleep(.3); job = client.get('/api/tool-jobs/' + job['id']).json()
                if job['state'] != 'succeeded':
                    raise RuntimeError(tool + ': ' + str(job))
                return job['result']['result']
            cap = call('get_capabilities', {}); checks['runtime_dependencies'] = bool(cap['ffmpeg'] and cap['chrome'])
            project = call('create_project', {'name': 'Hosted render', 'project_id': 'film'})
            client.post('/api/select-project', json={'project_id': 'film'}).raise_for_status()
            import io
            data = io.BytesIO(); Image.new('RGB', (96, 64), '#578bb1').save(data, 'PNG')
            upload = client.post('/api/upload', content=data.getvalue(), headers={'X-File-Name': 'plate.png'}); upload.raise_for_status()
            source = upload.json()['source']; call('inspect_media', {'source': source})
            asset = call('import_media', {'project_id': 'film', 'source': source, 'rights': 'own'})
            plan = call('plan_edit', {'project_id': 'film', 'asset_ids': [asset['id']], 'recipe': 'Drift', 'seconds': 1, 'width': 96, 'height': 64, 'fps': 6})
            call('save_timeline', {'project_id': 'film', 'timeline': plan['timeline'], 'revision': project['state']['revision']})
            call('preview_timeline', {'project_id': 'film', 'frames': [0, 5]})
            rendered = call('start_render', {'project_id': 'film', 'request_id': 'one-render'})
            url = '/files/' + rendered['video_path'].removeprefix('workspace://')
            download = client.get(url); download.raise_for_status(); (root / 'video.mp4').write_bytes(download.content)
            checks['video_render_and_download'] = rendered['state'] == 'succeeded' and len(download.content) > 100
            denied = client.get(url, headers={'Authorization': 'Bearer ' + other_token})
            checks['other_account_cannot_download'] = denied.status_code == 404
            from openkatana.scene3d import starter
            scene = call('create_scene3d', {'project_id': 'film', 'name': 'orbital',
                                          'scene': starter(width=96, height=64, fps=3, frames=3)})
            three = call('render_scene3d', {'project_id': 'film', 'scene': scene['scene'], 'preview_frames': [0, 2], 'video': False})
            checks['webgl_in_sandbox'] = bool(three)
            authored = call('write_project_file', {'project_id': 'film', 'path': 'notes.txt', 'text': 'Hosted authored asset'})
            read = call('read_project_file', {'project_id': 'film', 'path': 'notes.txt'})
            checks['author_without_checkout'] = read['text'] == 'Hosted authored asset' and read['sha256'] == authored['sha256']
            headers = {'Accept': 'application/json, text/event-stream'}
            mcp = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}); mcp.raise_for_status()
            checks['real_http_mcp_catalog'] = len(mcp.json()['result']['tools']) == 78
            response = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'get_project', 'arguments': {'project_id': 'film'}}})
            response.raise_for_status(); mcp_job = response.json()['result']['structuredContent']
            for _ in range(150):
                if mcp_job['state'] not in ('queued', 'running'):
                    break
                time.sleep(.3)
                response = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'get_tool_job', 'arguments': {'job_id': mcp_job['id']}}})
                response.raise_for_status(); mcp_job = response.json()['result']['structuredContent']
            checks['mcp_executes_same_workspace'] = mcp_job['state'] == 'succeeded' and mcp_job['result']['project_id'] == 'film'
            report = {'passed': all(checks.values()), 'checks': checks, 'runtime': args.runtime, 'credits_used': 0, 'deployed': False}
            (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report, indent=2)); return 0 if report['passed'] else 1
    finally:
        stop.set(); thread.join(timeout=190)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
        log.close()


if __name__ == '__main__':
    raise SystemExit(main())
