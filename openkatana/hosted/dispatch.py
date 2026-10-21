"""Shared hosted tool schemas and container-side dispatch."""
import base64
import inspect
import json
import os
from pathlib import Path
import time
from typing import Literal

from ..agent_api import AgentAPI, TOOLS
from .files import inventory, safe_path


FILE_TOOLS = ('write_project_file', 'read_project_file', 'list_project_files', 'preview_edit')
MODEL_TOOLS = {'submit_workflow', 'collect_workflow', 'run_model_workflow', 'check_workflow'}


class HostedAPI(AgentAPI):
    def get_capabilities(self) -> dict:
        """Discover this worker's installed runtimes, tools and hosted execution limits."""
        value = super().get_capabilities()
        value.update(hosted=True, tools=[*TOOLS, *FILE_TOOLS],
                     comfy_execution='Configured account-isolated model services only; paid cloud execution is disabled in this pilot',
                     transport='Remote Streamable HTTP MCP; poll get_tool_job for queued operations',
                     authoring='Upload media in Studio. Use write_project_file and read_project_file; no checkout or CLI needed.')
        value['guides'].append('hosted')
        return value

    def read_guide(self, topic: Literal['agent','timeline','effects','compatibility','tool-audit','comfy-models','scene3d','composition','release-tools','hdr','animation','webgl','hosted']='agent') -> dict:
        """Read hosted editing instructions and the exact supported contracts before choosing tool arguments."""
        if topic == 'hosted':
            import sys
            for base in (Path(__file__).resolve().parents[2] / 'docs', Path(sys.prefix) / 'share/openkatana/docs',
                         Path(__file__).resolve().parents[2] / 'share/openkatana/docs'):
                path = base / 'HOSTING.md'
                if path.is_file():
                    return {'topic': topic, 'markdown': path.read_text(encoding='utf-8')}
            raise ValueError('Hosted guide is not installed')
        result = super().read_guide(topic)
        result['markdown'] = ('# Hosted session\n\nUse the connected remote MCP tools; skip local installation, cloning and stdio setup below. '
                              'Read the hosted guide for account files and queue semantics. Upload media in Studio, author files with '
                              'write_project_file, and poll get_tool_job until completion. Never treat queued as success.\n\n' + result['markdown'])
        return result

    def preview_edit(self, project_id: str, timeline: dict, frames: list[int]) -> dict:
        """Render proposed timeline frames in the worker without saving the human's draft."""
        from ..preview import timeline_frames
        from ..gates import record_preview
        from ..projects import fingerprint
        root = self._project(project_id)
        result = timeline_frames(timeline, root, self._output(root, 'hosted-previews'), frames)
        record_preview(root, fingerprint(timeline), frames)
        return result

    def _source(self, source):
        p = super()._source(source)
        fonts = Path(__file__).resolve().parents[1] / 'fonts'
        if not p.is_relative_to(self.workspace) and not p.is_relative_to(fonts):
            raise ValueError('Upload source media to your hosted workspace first')
        return p

    def write_project_file(self, project_id: str, path: str, text: str, previous_sha256: str | None = None) -> dict:
        """Write an authored script, scene, workflow or text asset. Supply the current hash to replace a file. Use save_timeline for timelines."""
        from ..render import digest
        root = self._project(project_id)
        if not (root / 'project.json').is_file():
            raise ValueError('Create the project first')
        p = safe_path(root, path)
        if p.suffix.lower() not in {'.py', '.js', '.html', '.css', '.svg', '.json', '.txt', '.md', '.srt', '.vtt', '.obj', '.mtl', '.gltf'}:
            raise ValueError('Upload binary media through the file upload endpoint')
        relative = p.relative_to(root).as_posix()
        if relative in ('project.json', 'timeline.json') or relative.startswith('.openkatana/'):
            raise ValueError('Use the project and timeline tools for managed files')
        if len(text.encode()) > 2 * 1024**2:
            raise ValueError('Text file exceeds 2 MiB')
        if p.exists() and (not previous_sha256 or digest(p) != previous_sha256):
            raise ValueError('File changed; read its current hash before overwriting')
        if not p.exists() and previous_sha256 is not None:
            raise ValueError('Expected file does not exist')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return {'path': 'workspace://' + p.relative_to(self.workspace).as_posix(), 'sha256': digest(p)}

    def read_project_file(self, project_id: str, path: str) -> dict:
        """Read up to 2 MiB of UTF-8 authored content and its hash, scoped to your project."""
        from ..render import digest
        p = safe_path(self._project(project_id), path)
        if not p.is_file() or p.stat().st_size > 2 * 1024**2:
            raise ValueError('Expected a text file no larger than 2 MiB')
        return {'text': p.read_text(encoding='utf-8'), 'sha256': digest(p)}

    def list_project_files(self, project_id: str) -> dict:
        """List project-relative paths and sizes for authored assets and downloadable outputs."""
        return {'files': [{'path': n, 'bytes': s} for n, s in inventory(self._project(project_id), 64 * 1024**3)]}


def schemas():
    from mcp.server.fastmcp.utilities.func_metadata import func_metadata
    api = HostedAPI('.')
    rows = []
    for name in (*TOOLS, *FILE_TOOLS):
        method = getattr(api, name)
        schema = func_metadata(method).arg_model.model_json_schema()
        schema['additionalProperties'] = False
        rows.append({'name': name, 'description': inspect.getdoc(method),
                     'signature': str(inspect.signature(method)), 'inputSchema': schema})
    return rows


def validate_call(tool, arguments):
    if tool not in (*TOOLS, *FILE_TOOLS):
        raise ValueError('Unknown OpenKatana tool')
    from mcp.server.fastmcp.utilities.func_metadata import func_metadata
    from pydantic import ConfigDict
    model = func_metadata(getattr(HostedAPI('.'), tool)).arg_model
    strict = type(model.__name__, (model,), {'model_config': ConfigDict(**model.model_config, extra='forbid')})
    strict.model_validate(arguments)
    if arguments.get('reviewed_local_nodes'):
        raise ValueError('Custom Comfy nodes require an operator-audited worker image')


def map_paths(value, workspace):
    if isinstance(value, str) and value.startswith('workspace://'):
        return str(safe_path(workspace, value[len('workspace://'):]))
    if isinstance(value, list):
        return [map_paths(v, workspace) for v in value]
    if isinstance(value, dict):
        return {k: map_paths(v, workspace) for k, v in value.items()}
    return value


def portable(value, workspace):
    if isinstance(value, str):
        root = str(workspace).replace('\\', '/')
        candidate = value.replace('\\', '/')
        if candidate.startswith(root + '/'):
            return 'workspace://' + candidate[len(root) + 1:]
        if candidate == root:
            return 'workspace://'
        return value
    if isinstance(value, list):
        return [portable(v, workspace) for v in value]
    if isinstance(value, dict):
        return {k: portable(v, workspace) for k, v in value.items()}
    return value


def execute(workspace, tool, arguments):
    workspace = Path(workspace).resolve(); workspace.mkdir(parents=True, exist_ok=True)
    os.chdir(workspace)
    validate_call(tool, arguments)
    api = HostedAPI(workspace)
    result = getattr(api, tool)(**map_paths(arguments, workspace))
    if tool == 'start_render':
        # The container must live as long as its child renderer. The hosted queue
        # already makes this asynchronous to browsers and MCP clients.
        while result['state'] == 'running':
            time.sleep(.2)
            result = api.get_render(arguments['project_id'], result['id'])
        if result['state'] != 'succeeded':
            raise RuntimeError(result.get('message', 'Render did not finish'))
    media = []
    for name in result.get('preview_images', [])[:4]:
        from PIL import Image
        import io
        p = Path(name).resolve()
        if p.is_relative_to(workspace):
            with Image.open(p) as im:
                im = im.convert('RGB'); im.thumbnail((1024, 768)); out = io.BytesIO(); im.save(out, 'JPEG', quality=85)
            media.append({'type': 'image', 'data': base64.b64encode(out.getvalue()).decode(), 'mimeType': 'image/jpeg'})
    return {'result': portable(result, workspace), 'content': media}
