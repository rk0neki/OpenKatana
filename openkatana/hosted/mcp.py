"""Official SDK Streamable HTTP transport behind the shared authentication gate."""
import inspect
import json
from .auth import current_user
from .dispatch import HostedAPI, FILE_TOOLS
from ..agent_api import TOOLS


def create(service):
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
    from mcp.types import CallToolResult, ImageContent, TextContent
    from urllib.parse import urlsplit
    origin = service.settings.public_url
    server = FastMCP('OpenKatana', stateless_http=True, json_response=True,
                     transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                         allowed_hosts=[urlsplit(origin).netloc], allowed_origins=[origin]),
                     instructions=(
        'This is hosted OpenKatana. You do not need a checkout or shell. Read get_capabilities and read_guide. '
        'Tools enqueue isolated jobs: poll get_tool_job until succeeded, failed or cancelled; queued is not success. '
        'Use workspace:// paths returned by uploads and tools. Author scripts with write_project_file, preserving hashes. '
        'Use list_project_files and download links for outputs. Inspect preview images, then review with the human. '
        'Do not infer approval or publish. Model-dependent tools need configured models. Never blindly resubmit an uncertain job.'))

    def user():
        value = current_user.get()
        if not value:
            raise ValueError('Authentication required')
        return value

    def wrap(name):
        method = getattr(HostedAPI('.'), name)
        async def invoke(**kwargs):
            job = service.submit(user(), name, kwargs)
            job = await service.wait(user(), job['id'])
            return result(job)
        signature = inspect.signature(method).replace(return_annotation=CallToolResult)
        invoke.__signature__ = signature
        invoke.__annotations__ = {n: p.annotation for n, p in signature.parameters.items()}
        invoke.__annotations__['return'] = CallToolResult
        invoke.__name__ = name; invoke.__doc__ = method.__doc__
        return invoke

    def result(job):
        payload = dict(job)
        content = []
        if payload.get('result'):
            returned = dict(payload['result'])
            for item in returned.pop('content', []):
                if item.get('type') == 'image':
                    content.append(ImageContent(**item))
            payload['result'] = returned.get('result', returned)
        content.insert(0, TextContent(type='text', text=json.dumps(payload, ensure_ascii=False)))
        return CallToolResult(content=content, structuredContent=payload, isError=job['state'] in ('failed', 'interrupted'))

    from pydantic import ConfigDict
    for name in (*TOOLS, *FILE_TOOLS):
        server.add_tool(wrap(name), name=name, structured_output=False)
        registered = server._tool_manager.get_tool(name)
        base = registered.fn_metadata.arg_model
        registered.fn_metadata.arg_model = type(base.__name__, (base,), {'model_config': ConfigDict(**base.model_config, extra='forbid')})
        registered.parameters['additionalProperties'] = False

    @server.tool(structured_output=False)
    def get_tool_job(job_id: str) -> CallToolResult:
        """Poll a hosted job. Only succeeded includes a completed tool result. Never resubmits."""
        return result(service.store.job(user(), job_id))

    @server.tool(structured_output=False)
    def cancel_tool_job(job_id: str) -> CallToolResult:
        """Cancel a queued/running hosted job. External model submissions may still finish; inspect receipts."""
        return result(service.store.cancel(user(), job_id))

    return server
