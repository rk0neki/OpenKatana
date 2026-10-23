"""Official SDK bridge with explicit local and paid Comfy Cloud execution."""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .render import digest, write_json


BASE_NODES = {'EmptyImage', 'LoadImage', 'ImageScale', 'ImageInvert', 'ImageCompositeMasked',
               'SolidMask', 'InvertMask', 'MaskToImage', 'ImageToMask', 'SaveImage', 'PreviewImage'}

def local_endpoint(url):
    value = urlsplit(url)
    # Hosting operators may configure exact private Comfy service URLs in a
    # dedicated model worker. Browser/agent arguments cannot expand this list.
    private = json.loads(os.environ.get('OPENKATANA_PRIVATE_COMFY_ENDPOINTS', '[]'))
    if url.rstrip('/') in private and value.scheme == 'http' and value.hostname and not (value.username or value.password or value.query or value.fragment or value.path not in ('', '/')):
        return url.rstrip('/')
    if value.scheme != 'http' or value.hostname not in ('127.0.0.1', 'localhost', '::1') or value.username or value.password or value.query or value.fragment or value.path not in ('', '/'):
        raise ValueError('This release accepts only a local HTTP Comfy API proxy endpoint')
    return url.rstrip('/')


def execution_endpoint(endpoint, execution='local'):
    if execution == 'local':
        return local_endpoint(endpoint)
    if execution != 'cloud':
        raise ValueError('Execution must be local or cloud')
    if endpoint.rstrip('/') != 'https://cloud.comfy.org':
        raise ValueError('Cloud execution requires https://cloud.comfy.org')
    return 'https://cloud.comfy.org'


def authorize_execution(endpoint, execution='local', allow_paid=False):
    execution_endpoint(endpoint, execution)
    if execution == 'cloud':
        if allow_paid is not True:
            raise ValueError('Cloud workflows may incur charges and upload media; explicit allow_paid=true is required')
        if not os.environ.get('COMFY_API_KEY', '').strip():
            raise ValueError('Configure COMFY_API_KEY in the process environment; never put credentials in tool arguments or workflows')


PROXY_SETUP = (r'start the local Comfy API proxy, e.g. ".venv\Scripts\comfy-api-proxy.exe run --comfyui http://127.0.0.1:8000 '
               '--port 8189 --state-dir work/proxy-state" (README "Local Comfy"), or pass the endpoint where it runs')


def require_reachable(url, role='Comfy API proxy'):
    """Fail before anything is written when the local endpoint does not accept connections (audit F-GEN-001)."""
    import socket
    value = urlsplit(url)
    try:
        socket.create_connection((value.hostname, value.port or 80), timeout=2).close()
    except OSError as err:
        hint = PROXY_SETUP if role == 'Comfy API proxy' else 'start ComfyUI there or pass the endpoint where it runs'
        raise ConnectionError(f'{role} not reachable at {url} ({err.__class__.__name__}: {err.strerror or err}). Nothing was submitted; {hint}') from None


@contextmanager
def client_at(endpoint, execution='local'):
    # SDK 0.5 takes its base URL from the environment. This CLI is single-process,
    # single-job; do not use this context concurrently in a web server.
    from comfy_sdk import Comfy
    old = os.environ.get('COMFY_BASE_URL')
    os.environ['COMFY_BASE_URL'] = execution_endpoint(endpoint, execution)
    try:
        with Comfy(api_key=os.environ.get('COMFY_API_KEY', '') if execution == 'cloud' else '', client_info='openkatana', timeout=15) as client:
            yield client
    finally:
        if old is None:
            os.environ.pop('COMFY_BASE_URL', None)
        else:
            os.environ['COMFY_BASE_URL'] = old


def reviewed_nodes(value=None):
    """Explicit per-call extension, never a process-wide relaxation of local policy."""
    if value is None:return set()
    if not isinstance(value,(list,tuple)) or any(not isinstance(n,str) or not n.strip() for n in value):
        raise ValueError('reviewed_local_nodes must be a list of inspected local node class names')
    if any('download' in n.lower() for n in value):
        raise ValueError('Download-capable nodes need a dedicated installed-file guard, not a generic local review')
    return set(value)


def validate_workflow(path, execution='local', reviewed_local_nodes=None):
    if execution not in ('local', 'cloud'):raise ValueError('Execution must be local or cloud')
    graph = json.loads(path.read_text(encoding='utf-8'))
    # A deliberately narrow audited list prevents a local endpoint from silently
    # executing a partner API node. Add model nodes only with explicit contracts.
    from .workflows import LOCAL_NODES
    extra=reviewed_nodes(reviewed_local_nodes)
    if execution!='local' and extra:raise ValueError('reviewed_local_nodes applies only to local execution')
    allowed=BASE_NODES|LOCAL_NODES|extra
    if not isinstance(graph, dict) or not graph:
        raise ValueError('Expected an API-format workflow object')
    for key, node in graph.items():
        if not isinstance(node, dict) or not isinstance(node.get('class_type'), str) or not node['class_type'] or (execution == 'local' and node['class_type'] not in allowed):
            raise ValueError(f'Node {key}: not in the initial local-only workflow allowlist')
        if not isinstance(node.get('inputs'), dict):
            raise ValueError(f'Node {key}: missing inputs')
        if any(k.lower() in ('api_key', 'token', 'password', 'authorization', 'comfy_api_key') for k in node['inputs']):
            raise ValueError('Credentials must not be embedded in workflows')
        for value in node['inputs'].values():
            if isinstance(value,list):
                if len(value)!=2 or str(value[0]) not in graph or not isinstance(value[1],int) or value[1]<0:raise ValueError(f'Node {key}: invalid connection')
    return graph


def submit(workflow: Path, directory: Path, endpoint: str, assets=(), native_endpoint=None, execution='local', allow_paid=False, reviewed_local_nodes=None):
    authorize_execution(endpoint, execution, allow_paid)
    # Partner (API) nodes on Comfy Cloud authenticate with this key, which the SDK sends as
    # extra_data.api_key_comfy_org. Never send it for local execution: the local proxy passes
    # extra_data on to ComfyUI. The key is never written to job.json or workflow.json.
    partner_auth = {'api_key': os.environ['COMFY_API_KEY'].strip()} if execution == 'cloud' else {}
    graph=validate_workflow(workflow, execution, reviewed_local_nodes)
    advanced=any(n['class_type'] not in BASE_NODES for n in graph.values())
    if advanced and execution == 'local':
        if not native_endpoint:raise ValueError('Advanced workflows require --native-endpoint for capability checks')
        require_reachable(native_endpoint, 'ComfyUI (native endpoint)')
        from .workflows import preflight
        check=preflight(graph,native_endpoint,reviewed_local_nodes) if reviewed_local_nodes else preflight(graph,native_endpoint)
        if not check['ready']:raise ValueError('; '.join(check['errors']))
    if execution == 'local':require_reachable(endpoint)
    directory.mkdir(parents=True, exist_ok=False)
    receipt = {'schema': 1, 'endpoint': endpoint, 'execution': execution, 'paid_authorized': execution == 'cloud' and allow_paid, 'workflow_sha256': digest(workflow),
               'idempotency_key': str(uuid.uuid4()), 'created_at': datetime.now(timezone.utc).isoformat(),
               'state': 'prepared', 'job_id': None, 'assets': []}
    if reviewed_local_nodes:receipt['reviewed_local_nodes']=sorted(reviewed_nodes(reviewed_local_nodes))
    write_json(directory / 'workflow.json', json.loads(workflow.read_text(encoding='utf-8')))
    with client_at(endpoint, execution) as client:
        wf = client.workflows.from_file(str(workflow))
        for binding in assets:
            node_input, filename = binding.split('=', 1)
            node, field = node_input.split('.', 1)
            path = Path(filename).resolve()
            receipt['assets'].append({'node': node, 'input': field, 'sha256': digest(path)})
            wf.set_input(node, field, client.assets.from_file(str(path)))
        receipt['state'] = 'submitting'
        write_json(directory / 'job.json', receipt)
        try:
            job = client.submit(wf, idempotency_key=receipt['idempotency_key'], **partner_auth)
        except Exception:
            receipt['state'] = 'submission_unknown'
            write_json(directory / 'job.json', receipt)
            raise
        receipt.update(job_id=job.id, state='submitted')
        write_json(directory / 'job.json', receipt)
    return receipt


def collect(directory: Path):
    path = directory / 'job.json'
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if not receipt.get('job_id'):
        raise ValueError('No recorded job ID. Resolve the original submission; do not resubmit it')
    if receipt['state'] == 'collected':
        for item in receipt['outputs']:
            if digest(directory / item['file']) != item['sha256']:
                raise ValueError('A previously collected output has changed')
        return receipt
    with client_at(receipt['endpoint'], receipt.get('execution', 'local')) as client:
        job = client.jobs.get(receipt['job_id'])
        receipt['state'] = job.status
        if job.status != 'succeeded':
            write_json(path, receipt)
            return receipt
        outputs = []
        for index, output in enumerate(job.outputs):
            filename = f'{index:03d}-{Path(output.name.replace(chr(92), "/")).name}'
            target = directory / filename
            output.to_file(str(target))
            outputs.append({'file': filename, 'sha256': digest(target), 'type': output.type})
        receipt.update(state='collected', outputs=outputs)
        write_json(path, receipt)
    return receipt
