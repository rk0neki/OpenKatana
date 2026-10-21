"""Single-host worker. It alone talks to Docker; the web server has no socket."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

from .config import Settings
from .dispatch import MODEL_TOOLS
from .files import inventory, pack, unpack
from .store import Store


def command(settings, job, source):
    args = ['docker', 'run', '--detach', '--name', 'openkatana-job-' + job['id'],
            '--label', 'openkatana.worker=1', '--read-only', '--user', '1000:1000',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '256', '--memory', settings.worker_memory, '--memory-swap', settings.worker_memory,
            '--cpus', str(settings.worker_cpus), '--init', '--log-driver', 'none',
            '--tmpfs', f'/workspace:rw,nosuid,nodev,size={settings.workspace_bytes},uid=1000,gid=1000',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=1073741824,uid=1000,gid=1000',
            '--shm-size', '256m', '--mount', f'type=bind,src={source},dst=/input,readonly']
    if settings.runtime:
        args += ['--runtime', settings.runtime]
    proxy, native, model_network = settings.models_for(job.get('user', ''))
    network = model_network if job['tool'] in MODEL_TOOLS else 'none'
    args += ['--network', network]
    if network != 'none':
        args += ['--env', 'OPENKATANA_PRIVATE_COMFY_ENDPOINTS=' + json.dumps([proxy, native])]
    return args + [settings.worker_image, 'python', '-m', 'openkatana.hosted.executor']


def docker(args, timeout=30):
    result = subprocess.run(['docker', *args], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-1500:])
    return result.stdout


def check_runtime(settings):
    info = json.loads(docker(['info', '--format', '{{json .}}']))
    if info.get('OSType') != 'linux':
        raise RuntimeError('Hosted workers require the Linux Docker engine')
    if settings.runtime and settings.runtime not in info.get('Runtimes', {}):
        raise RuntimeError(f'Install the configured sandbox runtime: {settings.runtime}')
    if settings.model_network and '{user}' not in settings.model_network:
        network = json.loads(docker(['network', 'inspect', settings.model_network]))[0]
        if not network.get('Internal'):
            raise RuntimeError('The Comfy network must be internal, with no public internet route')
    docker(['image', 'inspect', settings.worker_image])


def run_one(settings, store, job):
    root = store.workspace(job['user']); root.mkdir(parents=True, exist_ok=True)
    work = settings.data / 'worker-tmp'; work.mkdir(exist_ok=True)
    name = 'openkatana-job-' + job['id']
    expired = threading.Event()
    def timeout():
        expired.set()
        # Also unblocks a stalled docker-exec export, not just the polling loop.
        subprocess.run(['docker', 'rm', '--force', name], capture_output=True, timeout=30)
    watchdog = None
    try:
        if job['tool'] in MODEL_TOOLS:
            _, _, network_name = settings.models_for(job['user'])
            network = json.loads(docker(['network', 'inspect', network_name]))[0]
            if not network.get('Internal'):
                raise RuntimeError('This account needs a private, internal model network')
        # Reserve space for input, a new snapshot and the current workspace.
        if shutil.disk_usage(work).free < settings.workspace_bytes * 3:
            raise RuntimeError('Insufficient temporary storage for an isolated job')
        with tempfile.TemporaryDirectory(prefix='job-', dir=work) as temporary:
            temp = Path(temporary); source = temp / 'input'; source.mkdir()
            with (source / 'workspace.tar').open('wb') as out:
                pack(root, out, settings.workspace_bytes)
            request = {'tool': job['tool'], 'arguments': json.loads(job['arguments']), 'limit': settings.workspace_bytes}
            (source / 'request.json').write_text(json.dumps(request), encoding='utf-8')
            source.chmod(0o755)
            for item in source.iterdir():
                item.chmod(0o644)
            started = subprocess.run(command(settings, job, source), capture_output=True, timeout=60)
            if started.returncode:
                raise RuntimeError(started.stderr.decode(errors='replace')[-1500:])
            watchdog = threading.Timer(settings.job_seconds, timeout)
            watchdog.daemon = True; watchdog.start()
            deadline = time.monotonic() + settings.job_seconds
            while True:
                if store.job(job['user'], job['id'])['state'] == 'cancelled':
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError('Job exceeded its runtime limit; it was stopped and will not be retried')
                state = json.loads(docker(['inspect', '--format', '{{json .State}}', name]))
                if not state['Running']:
                    raise RuntimeError('Worker stopped before returning a result (possibly its memory limit)')
                probe = subprocess.run(['docker', 'exec', name, 'test', '-f', '/tmp/tool-result.json'], capture_output=True, timeout=15)
                if probe.returncode == 0:
                    break
                time.sleep(.3)
            raw = docker(['exec', name, 'head', '-c', str(8 * 1024**2 + 1), '/tmp/tool-result.json'])
            if len(raw) > 8 * 1024**2:
                raise RuntimeError('Tool result exceeds 8 MiB')
            response = json.loads(raw)
            snapshot = temp / 'output.tar'
            # No writable host directory is visible inside the worker. Copy a
            # bounded tar stream, then reject links and traversal before commit.
            with snapshot.open('wb') as out:
                proc = subprocess.Popen(['docker', 'exec', name, 'python', '-m', 'openkatana.hosted.executor', 'pack'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                try:
                    copied = 0
                    while block := proc.stdout.read(1024 * 1024):
                        copied += len(block)
                        if copied > settings.workspace_bytes + 256 * 1024**2:
                            raise RuntimeError('Snapshot transport exceeded its quota')
                        out.write(block)
                    if proc.wait(timeout=30):
                        raise RuntimeError('Worker could not export its workspace')
                finally:
                    if proc.poll() is None:
                        proc.kill(); proc.wait()
                    proc.stdout.close()
            candidate = temp / 'candidate'
            with snapshot.open('rb') as src:
                unpack(src, candidate, settings.workspace_bytes)
            if expired.is_set():
                raise TimeoutError('Job exceeded its runtime limit; it was stopped and will not be retried')
            # Serialize the final swap with uploads and cancellation. A cancelled
            # job must never overwrite an upload made after cancellation.
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                current = db.execute('SELECT state FROM jobs WHERE id=?', (job['id'],)).fetchone()
                if current['state'] != 'running':
                    return
                backup = temp / 'previous'
                root.rename(backup)
                try:
                    candidate.rename(root)
                except BaseException:
                    backup.rename(root)
                    raise
                store.finish(job['id'], result=response if response['ok'] else None,
                             error=None if response['ok'] else response.get('error', 'Tool failed'), db=db)
    except Exception as e:
        store.finish(job['id'], error=f'{type(e).__name__}: {e}')
    finally:
        if watchdog:
            watchdog.cancel()
        subprocess.run(['docker', 'rm', '--force', name], capture_output=True, timeout=30)


def serve(settings):
    check_runtime(settings)
    store = Store(settings)
    # Only one runner is supported. A file lock prevents double recovery/claim.
    import fcntl
    with (settings.data / 'runner.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        active = docker(['ps', '-aq', '--filter', 'label=openkatana.worker=1']).decode().split()
        if active:
            docker(['rm', '--force', *active])
        store.recover()
        while True:
            job = store.claim()
            if job:
                run_one(settings, store, job)
            else:
                time.sleep(.3)
